"""Measure every curated ingestion case against real disposable PostgreSQL-backed HTTP."""

import asyncio
import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.contracts.schemas import (
    ActiveChunkPageResponse,
    DocumentDetail,
    ErrorResponse,
    IngestionJobResponse,
    IngestionResponse,
    IngestionStageTiming,
)
from apps.workbench.persistence.models import WorkspaceContext
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.db_seed import seed_development
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_DIRECTORY = Path(__file__).resolve().parents[4]
_FIXTURES = Path(__file__).parents[2] / "chunking/tests/fixtures/chunking/manifest.json"
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _timings(stages: list[IngestionStageTiming]) -> dict[str, float | None]:
    values = {stage.stage: stage.duration_ms for stage in stages}
    return {
        "parse_ms": values.get("parsing"),
        "chunk_ms": values.get("chunking"),
        "publication_ms": values.get("publication"),
    }


def _distribution(values: list[int]) -> dict[str, int | float | str | None]:
    ordered = sorted(values)
    count = len(ordered)
    return {
        "sample_count": count,
        "min": ordered[0] if count else None,
        "max": ordered[-1] if count else None,
        "mean": sum(ordered) / count if count else None,
        "p50": ordered[(count + 1) // 2 - 1] if count else None,
        "p95": ordered[(95 * count + 99) // 100 - 1] if count else None,
        "convention": "nearest-rank: sorted[ceil(p*n)-1]",
    }


async def _active_chunks(client: httpx.AsyncClient, source_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = await client.get(
            f"{_DOCUMENTS}/{source_id}/chunks", params={"limit": 100, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200
        page = ActiveChunkPageResponse.model_validate(response.json())
        for item in page.items:
            assert item.content.strip() and item.page is None
            assert sha256(item.content.encode()).hexdigest() == item.content_hash
            assert not {"embedding", "embedding_profile_id", "dimensions"}.intersection(item.model_fields_set)
            items.append(
                {
                    "chunk_id": item.chunk_id,
                    "order": item.order,
                    "content_sha256": item.content_hash,
                    "content_bytes": len(item.content.encode()),
                }
            )
        assert len(items) <= 10_000
        if page.next_cursor is None:
            return items
        assert page.next_cursor != cursor
        cursor = page.next_cursor


async def _successful_case(client: httpx.AsyncClient, response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 201
    uploaded = IngestionResponse.model_validate(response.json())
    assert uploaded.outcome == "created" and not uploaded.replayed
    job_response = await client.get(f"/api/v1/workspaces/development/jobs/{uploaded.job_id}")
    assert job_response.status_code == 200
    job = IngestionJobResponse.model_validate(job_response.json())
    assert job.status == "completed" and job.source_version_id == uploaded.source_version_id
    detail_response = await client.get(f"{_DOCUMENTS}/{uploaded.source_id}")
    assert detail_response.status_code == 200
    detail = DocumentDetail.model_validate(detail_response.json())
    assert detail.active_version_id == uploaded.source_version_id and not detail.original_content_available
    chunks = await _active_chunks(client, uploaded.source_id)
    assert len(chunks) == uploaded.chunk_count == detail.chunk_count == job.chunk_count
    return {
        "outcome": "completed",
        "source_id": uploaded.source_id,
        "source_version_id": uploaded.source_version_id,
        "job_id": uploaded.job_id,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "chunk_utf8_bytes": _distribution([chunk["content_bytes"] for chunk in chunks]),
        "warnings": detail.warnings,
        **_timings(uploaded.stages),
    }


async def _failed_case(client: httpx.AsyncClient, response: httpx.Response) -> dict[str, Any]:
    assert response.status_code == 400
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == "INVALID_DOCUMENT" and error.error.job_id is not None
    job_response = await client.get(f"/api/v1/workspaces/development/jobs/{error.error.job_id}")
    assert job_response.status_code == 200
    job = IngestionJobResponse.model_validate(job_response.json())
    assert job.status == "failed" and job.source_version_id is None and job.finished_at is not None
    return {
        "outcome": "expected_failure",
        "job_id": job.job_id,
        "error_code": error.error.code,
        "chunk_count": 0,
        "chunks": [],
        "chunk_utf8_bytes": _distribution([]),
        **_timings(job.stages),
    }


async def test_curated_upload_stability_is_measured_in_a_disposable_database(
    disposable_database: DisposableDatabase, tmp_path: Path
) -> None:
    """Keep all 25 uploads/refusals in the measured denominator without touching the development database."""
    manifest = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    assert len(manifest["cases"]) >= 20
    run_token = uuid4().hex
    report: dict[str, Any] = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "scope": "ASGI HTTP with fixture-owned real PostgreSQL",
        "fixture_sha256": sha256(_FIXTURES.read_bytes()).hexdigest(),
        "run_token": run_token,
        "language_policy": "configured_sentence_language",
        "cases": [],
        "result": "RUNNING",
        "latency_scope": "sequential upload request elapsed; server stages separate; no throughput SLA",
    }
    regressions: list[str] = []
    repository = PostgresPersistence(disposable_database.app_dsn)
    try:
        migrate(disposable_database.admin_dsn)
        await repository.start()
        await seed_development(repository)
        app = create_app(settings=ApiSettings(), persistence=repository)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1:8011",
                headers={"Origin": "http://127.0.0.1:4173"},
            ) as client,
        ):
            for fixture in manifest["cases"]:
                content = "".join(part["text"] * part["repeat"] for part in fixture["parts"]).encode()
                assert len(content) <= 1_048_576
                case: dict[str, Any] = {
                    "case_id": fixture["case_id"],
                    "fixture_language_hint_not_transmitted": fixture["language"],
                    "file_bytes": len(content),
                    "source_sha256": sha256(content).hexdigest(),
                }
                started = monotonic()
                mime = "text/markdown" if fixture["filename"].endswith(".md") else "text/plain"
                response = await client.post(
                    _DOCUMENTS,
                    headers={"Idempotency-Key": f"stability_{run_token}_{fixture['case_id']}"},
                    files={"file": (fixture["filename"], content, mime)},
                )
                case.update(
                    total_ms=(monotonic() - started) * 1000,
                    http_status=response.status_code,
                    request_id=response.headers.get("X-Request-ID"),
                )
                try:
                    observation = await (
                        _failed_case(client, response)
                        if fixture.get("expected_error")
                        else _successful_case(client, response)
                    )
                    case.update(observation)
                except (AssertionError, ValueError):
                    case.update(outcome="verification_failed", failure_code="INGESTION_CASE_MISMATCH")
                    regressions.append(fixture["case_id"])
                report["cases"].append(case)
            report.update(
                attempted=len(report["cases"]),
                completed=sum(case["outcome"] == "completed" for case in report["cases"]),
                expected_failures=sum(case["outcome"] == "expected_failure" for case in report["cases"]),
                failed_verifications=regressions,
                chunk_utf8_bytes=_distribution(
                    [chunk["content_bytes"] for case in report["cases"] for chunk in case.get("chunks", [])]
                ),
            )
            corpus = await repository.corpus_snapshot(WorkspaceContext(workspace_id="development"))
            assert corpus.chunk_count <= 10_000 and corpus.content_bytes <= 52_428_800
            report.update(active_corpus_chunks=corpus.chunk_count, active_corpus_bytes=corpus.content_bytes)
            assert len(report["cases"]) == len(manifest["cases"])
            assert not regressions, "Curated ingestion cases failed: " + ",".join(regressions)
            report["result"] = "PASS"
    finally:
        await repository.close()
        if report["result"] != "PASS":
            report["result"] = "FAIL"
        evidence_directory = Path(os.environ.get("WORKBENCH_TEST_EVIDENCE_DIRECTORY", str(tmp_path)))
        await asyncio.to_thread(evidence_directory.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            (evidence_directory / "stability.json").write_text,
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )

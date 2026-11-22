"""Python uses the same bounded HTTP jobs, real PostgreSQL and lexical ranker as prose."""

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.workbench.api.application import create_app
from apps.workbench.api.chunking_adapters import count_tokens
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase
from apps.workbench.api.tests.test_ingestion_routes import _DOCUMENTS, _counts, _error, _search, _upload
from apps.workbench.api.tests.test_ingestion_routes import ingestion_repository as ingestion_repository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="function"),
    pytest.mark.usefixtures("ingestion_repository"),
]
_FIXTURES = Path(__file__).parent / "fixtures/python"


@asynccontextmanager
async def _client(database: DisposableDatabase) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=ApiSettings(), persistence=PostgresPersistence(database.app_dsn))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        yield client


async def _chunks(client: httpx.AsyncClient, source: str) -> list[dict[str, Any]]:
    response = await client.get(f"{_DOCUMENTS}/{source}/chunks", params={"limit": 100})
    assert response.status_code == 200, response.text
    assert response.json()["next_cursor"] is None
    return response.json()["items"]


async def test_python_upload_search_restart_replay_and_atomic_refusals(disposable_database: DisposableDatabase) -> None:
    """A new application lifecycle reuses stored identities; invalid updates cannot hide the old code."""
    content = b"class Ledger:\n    @staticmethod\n    def refundledgerproof():\n        return 'persisted-code'\n"
    key = uuid4().hex
    async with _client(disposable_database) as client:
        created = await _upload(client, filename="ledger.py", mime="text/x-python", content=content, key=key)
        assert created.status_code == 201, created.text
        document = created.json()
        source, version = document["source_id"], document["source_version_id"]
        chunks = await _chunks(client, source)
        assert len(chunks) == document["chunk_count"]
        for chunk in chunks:
            assert chunk["page"] is None and chunk["metadata"]["strategy"] == "python_ast"
            assert chunk["metadata"]["source_file"] == "ledger.py"
            assert "Ledger.refundledgerproof" in {s["qualified_symbol"] for s in chunk["metadata"]["symbols"]}
            assert chunk["content"] == content.decode()
        found = await _search(client, "refundledgerproof")
        assert found["results"][0]["score_type"] == "postgres_ts_rank_cd"
        assert found["results"][0]["chunk_id"] == chunks[0]["chunk_id"]
        assert found["results"][0]["source_id"] == source
        before = _counts(disposable_database)
        fields = {"source_id": source, "expected_active_version_id": version}
        unchanged = await _upload(client, filename="ledger.py", mime="text/plain", content=content, fields=fields)
        assert unchanged.status_code == 200 and unchanged.json()["outcome"] == "unchanged"
        for body, mime, code, status in [
            (b"def privatecanary(:\n", "text/x-python", "UNPARSEABLE_SOURCE", 400),
            (b"x = '\xff'", "text/x-python", "INVALID_DOCUMENT", 400),
            (b"x = '\0'", "text/x-python", "INVALID_DOCUMENT", 400),
            (content, "application/pdf", "UNSUPPORTED_MEDIA_TYPE", 415),
            (b"x = '" + b"z" * 33_000 + b"'", "text/x-python", "PAYLOAD_TOO_LARGE", 413),
        ]:
            failure = await _upload(client, filename="ledger.py", mime=mime, content=body, fields=fields)
            error = _error(failure, status=status, code=code)
            assert "privatecanary" not in failure.text
            job = await client.get(f"/api/v1/workspaces/development/jobs/{error['error']['job_id']}")
            assert job.json()["status"] == "failed"
            assert (await _chunks(client, source)) == chunks
        assert _counts(disposable_database)[:3] == before[:3]
        updated_content = content.replace(b"persisted-code", b"new-code")
        responses = await asyncio.gather(
            *[
                _upload(client, filename="ledger.py", mime="text/x-python", content=updated_content, fields=fields)
                for _ in range(2)
            ]
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        current = (await client.get(f"{_DOCUMENTS}/{source}")).json()
        assert current["active_version_id"] != version
        foreign = await client.post(
            "/api/v1/workspaces/foreign/documents",
            files={"file": ("x.py", content, "text/x-python")},
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert foreign.status_code == 404
    async with _client(disposable_database) as client:
        replay = await _upload(client, filename="ledger.py", mime="text/x-python", content=content, key=key)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        assert replay.json()["source_version_id"] == version
        detail = (await client.get(f"{_DOCUMENTS}/{source}")).json()
        assert detail["active_version_id"] == current["active_version_id"]
        assert (await _search(client, "refundledgerproof"))["results"][0]["source_version_id"] == current[
            "active_version_id"
        ]


@pytest.mark.parametrize("policy", ["python_ast", "prose_control"])
async def test_code_family_lexical_comparison_records_real_ranked_results(
    disposable_database: DisposableDatabase, tmp_path: Path, policy: str
) -> None:
    """Both policies use identical source bytes, FTS ranker and top-k; the control is explicitly prose."""
    manifest = json.loads((_FIXTURES / "queries.json").read_text(encoding="utf-8"))
    queries = manifest["queries"]
    files = sorted({query["file"] for query in queries})
    assert len(files) >= 10 and len(queries) >= 20
    report: dict[str, Any] = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Synthetic fixtures, real ASGI HTTP and disposable PostgreSQL; lexical only",
        "ranker": "postgres_ts_rank_cd",
        "top_k": 5,
        "files": [],
        "policies": {},
        "evidence_precision_definition": (
            "Returned labelled-source chunks with identifier and return marker / returned labelled-source chunks"
        ),
        "result": "RUNNING",
    }
    try:
        async with _client(disposable_database) as client:
            for selected_policy in (policy,):
                sources: dict[str, str] = {}
                chunks_total = overlaps = tokens = 0
                started = perf_counter()
                for filename in files:
                    content = (_FIXTURES / filename).read_bytes()
                    control = selected_policy == "prose_control"
                    response = await _upload(
                        client,
                        filename=filename.removesuffix(".py") + ".txt" if control else filename,
                        mime="text/plain" if control else "text/x-python",
                        content=content,
                    )
                    assert response.status_code == 201, response.text
                    source = response.json()["source_id"]
                    sources[filename] = source
                    chunks = await _chunks(client, source)
                    if not control and filename == "ledger.py":
                        report["sample_ast_chunks"] = chunks
                    chunks_total += len(chunks)
                    overlaps += sum(chunk["metadata"]["actual_overlap_tokens"] for chunk in chunks)
                    tokens += sum(count_tokens(chunk["content"]) for chunk in chunks)
                    assert all(
                        chunk["metadata"]["strategy"] == ("prose_recursive" if control else "python_ast")
                        for chunk in chunks
                    )
                    report["files"].append(
                        {
                            "file": filename,
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "bytes": len(content),
                            "original_tokens": count_tokens(content.decode()),
                        }
                    )
                duration = (perf_counter() - started) * 1000
                cases = []
                for label in queries:
                    response = await client.post(
                        "/api/v1/workspaces/development/search",
                        json={
                            "query": label["query"],
                            "top_k": 5,
                            "profile_id": "postgres-fts-baseline",
                            "expected_profile_revision": "postgres-fts-baseline-r1",
                        },
                    )
                    assert response.status_code == 200
                    hits = [hit for hit in response.json()["results"] if hit["source_id"] in sources.values()][:5]
                    relevant = [hit for hit in hits if hit["source_id"] == sources[label["file"]]]
                    cases.append(
                        {
                            "query": label["query"],
                            "file": label["file"],
                            "qualified_symbol": label["qualified_symbol"],
                            "symbol_hit_at_5": any(label["query"] in hit["content"] for hit in relevant),
                            "returned": len(relevant),
                            "complete_evidence": sum(
                                label["query"] in hit["content"] and label["context_marker"] in hit["content"]
                                for hit in relevant
                            ),
                            "hits": [
                                {"chunk_id": hit["chunk_id"], "source_id": hit["source_id"], "score": hit["score"]}
                                for hit in hits
                            ],
                        }
                    )
                denominator = sum(case["returned"] for case in cases)
                report["policies"][policy] = {
                    "chunks": chunks_total,
                    "tokens": tokens,
                    "duplicated_overlap_tokens": overlaps,
                    "indexing_and_chunk_read_ms": duration,
                    "symbol_hit_at_5": sum(case["symbol_hit_at_5"] for case in cases) / len(cases),
                    "evidence_precision": sum(case["complete_evidence"] for case in cases) / denominator
                    if denominator
                    else 0,
                    "cases": cases,
                }
            if policy == "python_ast":
                assert report["policies"][policy]["symbol_hit_at_5"] == 1
            report["result"] = "PASS"
    finally:
        destination = Path(os.environ.get("WORKBENCH_PYTHON_EVIDENCE_DIRECTORY", str(tmp_path)))
        await asyncio.to_thread(destination.mkdir, parents=True, exist_ok=True)
        (destination / f"code-quality-{policy}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

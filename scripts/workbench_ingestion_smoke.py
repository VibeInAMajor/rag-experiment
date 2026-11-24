"""Collect synthetic ingestion over actual HTTP; follow-up phases never publish data."""

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any, TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from apps.workbench.contracts.schemas import (
    ActiveChunkItem,
    ActiveChunkPageResponse,
    CapabilitiesResponse,
    DocumentDetail,
    DocumentPage,
    IngestionJobResponse,
    IngestionResponse,
    Meta,
    ReadyResponse,
    SearchResponse,
)
from apps.workbench.retrieval.profiles import POSTGRES_FTS_PROFILE_ID

_EVIDENCE = Path("tasks/evidence/ingestion-2026-11-22/live-http.json")
_CASES = Path("apps/workbench/retrieval/fixtures/lexical-evaluation.json")
_DOCUMENTS = "/api/v1/workspaces/development/documents"
_JOBS = "/api/v1/workspaces/development/jobs"
_SEARCH = "/api/v1/workspaces/development/search"
_REVISION = "ingestion-live-http-r1"
_Model = TypeVar("_Model", bound=Meta)


class _CheckFailed(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _require(condition: object, code: str) -> None:
    if not condition:
        raise _CheckFailed(code)


def _fingerprint(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    _require(
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment,
        "LOOPBACK_HTTP_URL_REQUIRED",
    )
    return value.rstrip("/")


def _save(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    pending.replace(path)


class _Observer:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.requests: list[dict[str, Any]] = []

    def payload(
        self, response: httpx.Response, *, label: str, expected: tuple[int, ...], model: type[_Model]
    ) -> _Model:
        item = response.json()
        observed = {
            "operation": label,
            "http_status": response.status_code,
            "request_id": item.get("request_id"),
            "trace_id": item.get("trace_id"),
            "client_elapsed_ms": response.elapsed.total_seconds() * 1000,
        }
        if isinstance(item.get("error"), dict):
            observed["error_code"] = item["error"].get("code")
            observed["job_id"] = item["error"].get("job_id")
        self.requests.append(observed)
        _require(response.status_code in expected, "UNEXPECTED_HTTP_STATUS")
        result = model.model_validate_json(response.content)
        _require(result.request_id == response.headers.get("X-Request-ID") and result.trace_id, "CORRELATION_MISMATCH")
        return result

    def get(self, path: str, *, label: str, model: type[_Model], params: dict[str, Any] | None = None) -> _Model:
        return self.payload(self.client.get(path, params=params), label=label, expected=(200,), model=model)


def _discovery(observer: _Observer) -> dict[str, str]:
    observer.get("/api/v1/health/ready", label="readiness", model=ReadyResponse)
    capabilities = observer.get("/api/v1/capabilities", label="capabilities", model=CapabilitiesResponse)
    _require(
        capabilities.features.upload and capabilities.features.document_details and capabilities.features.jobs,
        "INGESTION_NOT_QUALIFIED",
    )
    profiles = [profile for profile in capabilities.profiles if profile.profile_id == POSTGRES_FTS_PROFILE_ID]
    _require(len(profiles) == 1 and "development" in profiles[0].workspace_ids, "LEXICAL_PROFILE_NOT_QUALIFIED")
    return {"profile_id": profiles[0].profile_id, "profile_revision": profiles[0].profile_revision}


def _documents(observer: _Observer) -> dict[str, Any]:
    items: dict[str, Any] = {}
    cursor: str | None = None
    revision: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        page = observer.get(_DOCUMENTS, label="documents", model=DocumentPage, params=params)
        revision = page.corpus_revision if revision is None else revision
        _require(page.corpus_revision == revision, "CORPUS_CHANGED_DURING_PAGE_READ")
        for item in page.items:
            _require(item.source_id not in items, "DUPLICATE_SOURCE")
            items[item.source_id] = _fingerprint(item.model_dump(mode="json"))
        _require(len(items) <= 10_000, "SOURCE_PAGE_LIMIT")
        if page.next_cursor is None:
            return {"corpus_revision": revision, "sources": items, "source_count": len(items)}
        _require(page.next_cursor != cursor and page.items, "INVALID_SOURCE_PAGINATION")
        cursor = page.next_cursor


def _specimen(kind: str, token: str) -> tuple[str, bytes, str, str]:
    marker = f"RagIngestion{kind.title()}{token}"
    if kind == "text":
        text = (
            f"Synthetic ingestion specimen {marker}.\n"
            "Русский текст сохраняет источник.\nУкраїнський текст зберігає джерело.\n"
        )
        return "ingestion-smoke.txt", text.encode("utf-8-sig"), "text/plain", marker
    text = (
        f"# Synthetic ingestion {marker}\n\nEnglish, русский and український text is retained.\n\n"
        "## Protected example\n\n```text\nLiteral synthetic example, never execute.\n```\n\n"
        "## Protected table\n\n| Field | Value |\n| --- | --- |\n| State | synthetic |\n\n"
        f"## Retrieval\n\n{marker}\n"
    )
    return "ingestion-smoke.md", text.encode(), "text/markdown", marker


def _upload(observer: _Observer, *, kind: str, token: str) -> IngestionResponse:
    name, content, mime, _marker = _specimen(kind, token)
    response = observer.client.post(
        _DOCUMENTS,
        headers={"Idempotency-Key": f"ingestion_smoke_{token}_{kind}"},
        files={"file": (name, content, mime)},
    )
    result = observer.payload(response, label=f"{kind}.upload", expected=(200, 201), model=IngestionResponse)
    _require(result.outcome == "created", "UNEXPECTED_CREATE_OUTCOME")
    _require(response.status_code == 201 or result.replayed, "UNEXPLAINED_CREATE_REPLAY")
    return result


def _chunks(observer: _Observer, source_id: str) -> tuple[list[ActiveChunkItem], str]:
    chunks: list[ActiveChunkItem] = []
    cursor: str | None = None
    version: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = observer.get(
            f"{_DOCUMENTS}/{source_id}/chunks", label="active_chunks", model=ActiveChunkPageResponse, params=params
        )
        version = page.source_version_id if version is None else version
        _require(page.source_id == source_id and page.source_version_id == version, "CHUNK_VERSION_CHANGED")
        chunks.extend(page.items)
        _require(len(chunks) <= 10_000, "CHUNK_PAGE_LIMIT")
        if page.next_cursor is None:
            return chunks, page.corpus_revision
        _require(page.next_cursor != cursor and page.items, "INVALID_CHUNK_PAGINATION")
        cursor = page.next_cursor


def _chunk_evidence(chunks: list[ActiveChunkItem], text: str) -> list[dict[str, Any]]:
    evidence = []
    covered = 0
    for ordinal, chunk in enumerate(chunks):
        span = chunk.metadata.get("source_span")
        if not isinstance(span, dict):
            raise TypeError("SOURCE_SPAN_MISSING")
        start, end = span["start"], span["end"]
        if type(start) is not int or type(end) is not int:
            raise RuntimeError("INVALID_SOURCE_SPAN")
        _require(
            chunk.order == ordinal
            and 0 <= start < end <= len(text)
            and end > covered
            and not text[covered:start].strip()
            and text[start:end] == chunk.content,
            "SOURCE_COVERAGE_MISMATCH",
        )
        _require(
            chunk.content_hash == sha256(chunk.content.encode()).hexdigest() and chunk.page is None, "CHUNK_CONTRACT"
        )
        evidence.append(
            {
                "chunk_id": chunk.chunk_id,
                "order": chunk.order,
                "content_sha256": chunk.content_hash,
                "content_bytes": len(chunk.content.encode()),
                "source_span": span,
                "page": None,
                "section_path_sha256": _fingerprint(chunk.section_path),
                "has_section_path": bool(chunk.section_path),
                "metadata_sha256": _fingerprint(chunk.metadata),
            }
        )
        covered = end
    _require(chunks and not text[covered:].strip(), "INCOMPLETE_SOURCE_COVERAGE")
    return evidence


def _search(observer: _Observer, *, profile: dict[str, str], query: str, label: str) -> SearchResponse:
    response = observer.client.post(
        _SEARCH,
        json={
            "query": query,
            "top_k": 5,
            "profile_id": profile["profile_id"],
            "expected_profile_revision": profile["profile_revision"],
        },
    )
    result = observer.payload(response, label=label, expected=(200,), model=SearchResponse)
    _require(
        len(result.results) <= 5
        and [hit.rank for hit in result.results] == list(range(1, len(result.results) + 1))
        and all(hit.score_type == "postgres_ts_rank_cd" for hit in result.results),
        "LEXICAL_RANK_CONTRACT",
    )
    return result


def _canonical_queries(observer: _Observer, profile: dict[str, str]) -> dict[str, Any]:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"fixture_sha256": sha256(_CASES.read_bytes()).hexdigest()}
    for name, key, expected in (("exact", "gated_exact_queries", 10), ("paraphrase", "diagnostic_paraphrases", 3)):
        _require(len(fixture[key]) == expected, "CANONICAL_FIXTURE_CHANGED")
        cases = []
        for ordinal, gold in enumerate(fixture[key], 1):
            case: dict[str, Any] = {
                "case_id": f"{name}-{ordinal:02d}",
                "query_sha256": sha256(gold["query"].encode()).hexdigest(),
                "expected_source_id": gold["expected_source_id"],
                "hit_at_5": 0,
                "reciprocal_rank": 0,
                "outcome": "failed",
                "returned_results": [],
            }
            try:
                result = _search(observer, profile=profile, query=gold["query"], label=case["case_id"])
                rank = next((hit.rank for hit in result.results if hit.source_id == gold["expected_source_id"]), None)
                case.update(
                    outcome="success",
                    hit_at_5=int(rank is not None),
                    reciprocal_rank=1 / rank if rank else 0,
                    request_id=result.request_id,
                    trace_id=result.trace_id,
                    run_id=result.run_id,
                    corpus_revision=result.corpus_revision,
                    server_duration_ms=result.duration_ms,
                    returned_results=[
                        {
                            "source_id": hit.source_id,
                            "source_version_id": hit.source_version_id,
                            "chunk_id": hit.chunk_id,
                            "rank": hit.rank,
                            "score": hit.score,
                            "score_type": hit.score_type,
                            "content_sha256": sha256(hit.content.encode()).hexdigest(),
                        }
                        for hit in result.results
                    ],
                )
            except Exception as error:
                case["failure_code"] = error.code if isinstance(error, _CheckFailed) else "CANONICAL_QUERY_FAILED"
            cases.append(case)
        hits = sum(case["hit_at_5"] for case in cases)
        report[name] = {
            "attempted": len(cases),
            "successful": sum(case["outcome"] == "success" for case in cases),
            "hits_at_5": hits,
            "expected_source_hit_rate_at_5": hits / expected,
            "mrr_at_5": sum(case["reciprocal_rank"] for case in cases) / expected,
            "cases": cases,
        }
    return report


def _inspect(
    observer: _Observer, *, created: dict[str, Any], kind: str, token: str, profile: dict[str, str]
) -> dict[str, Any]:
    source_id, version_id, job_id = (created[key] for key in ("source_id", "source_version_id", "job_id"))
    detail = observer.get(f"{_DOCUMENTS}/{source_id}", label=f"{kind}.detail", model=DocumentDetail)
    job = observer.get(f"{_JOBS}/{job_id}", label=f"{kind}.job", model=IngestionJobResponse)
    _require(
        detail.active_version_id == version_id and detail.status == "ready" and not detail.original_content_available,
        "DOCUMENT_DETAIL_MISMATCH",
    )
    _require(
        job.status == "completed"
        and job.source_id == source_id
        and job.source_version_id == version_id
        and job.chunk_count == detail.chunk_count
        and job.finished_at is not None,
        "DURABLE_JOB_MISMATCH",
    )
    _require(detail.processing_profile is not None and detail.parser is not None, "PROCESSING_PROVENANCE_MISSING")
    chunks, corpus_revision = _chunks(observer, source_id)
    name, content, _mime, marker = _specimen(kind, token)
    _require(detail.title == name and len(chunks) == detail.chunk_count, "ACTIVE_CHUNK_COUNT_MISMATCH")
    _require(
        all(chunk.metadata.get("source_sha256") == sha256(content).hexdigest() for chunk in chunks),
        "ORIGINAL_BYTE_HASH_MISMATCH",
    )
    chunk_evidence = _chunk_evidence(chunks, content.decode("utf-8-sig"))
    if kind == "markdown":
        _require(any(chunk.section_path for chunk in chunks), "MARKDOWN_CONTEXT_MISSING")
        _require({"CODE_FENCE_UNPARSED", "TABLE_UNPARSED"}.issubset(detail.warnings), "RAW_MARKDOWN_WARNING_MISSING")
    search = _search(observer, profile=profile, query=marker, label=f"{kind}.search")
    _require(search.corpus_revision == corpus_revision == detail.corpus_revision, "CORPUS_READ_MISMATCH")
    expected_ids = {chunk.chunk_id for chunk in chunks}
    _require(
        search.results
        and all(
            hit.source_id == source_id
            and hit.source_version_id == version_id
            and hit.chunk_id in expected_ids
            and hit.score_type == "postgres_ts_rank_cd"
            and hit.page is None
            for hit in search.results
        ),
        "UPLOADED_TERM_NOT_RETRIEVED",
    )
    return {
        "source_id": source_id,
        "source_version_id": version_id,
        "job_id": job_id,
        "source_sha256": sha256(content).hexdigest(),
        "query_sha256": sha256(marker.encode()).hexdigest(),
        "corpus_revision": corpus_revision,
        "chunk_count": detail.chunk_count,
        "chunks": chunk_evidence,
        "profile_sha256": _fingerprint(detail.processing_profile),
        "parser_sha256": _fingerprint(detail.parser),
        "warnings": detail.warnings,
        "job_stages": [stage.model_dump() for stage in job.stages],
        "search": {
            "run_id": search.run_id,
            "request_id": search.request_id,
            "trace_id": search.trace_id,
            "results": [
                {"chunk_id": hit.chunk_id, "rank": hit.rank, "score": hit.score, "score_type": hit.score_type}
                for hit in search.results
            ],
        },
    }


def _stable_source(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "source_id",
            "source_version_id",
            "job_id",
            "source_sha256",
            "chunk_count",
            "chunks",
            "profile_sha256",
            "parser_sha256",
        )
    }


def _run(phase: str, *, base_url: str, evidence: Path) -> None:
    report: dict[str, Any] = (
        json.loads(evidence.read_text(encoding="utf-8"))
        if evidence.exists()
        else {
            "report_revision": _REVISION,
            "run_token": uuid4().hex,
            "base_url": base_url,
            "scope": "two synthetic sources over actual local HTTP; no original bytes retained",
        }
    )
    _require(
        report.get("report_revision") == _REVISION and report.get("base_url") == base_url, "EVIDENCE_SCOPE_MISMATCH"
    )
    previous = report.get(phase)
    _require(previous is None or phase == "baseline" and previous.get("result") != "PASS", "PHASE_ALREADY_RECORDED")
    if previous is not None:
        report.setdefault("previous_failed_attempts", []).append({"phase": phase, **previous})
    _require(phase == "baseline" or report.get("baseline", {}).get("result") == "PASS", "BASELINE_REQUIRED")
    _save(evidence, report)
    started = monotonic()
    observation: dict[str, Any] = {"checked_at_utc": datetime.now(UTC).isoformat(), "result": "RUNNING"}
    with httpx.Client(base_url=base_url, timeout=40, headers={"Origin": "http://127.0.0.1:4173"}) as client:
        observer = _Observer(client)
        try:
            profile = _discovery(observer)
            before = _documents(observer)
            if phase == "baseline":
                created = report.setdefault("created", {})
                for kind in ("text", "markdown"):
                    result = _upload(observer, kind=kind, token=report["run_token"])
                    created[kind] = result.model_dump(mode="json")
                    _save(evidence, report)
                for kind in ("text", "markdown"):
                    replay = _upload(observer, kind=kind, token=report["run_token"])
                    _require(replay.replayed, "IDEMPOTENCY_REPLAY_NOT_IDENTIFIED")
                    _require(
                        all(
                            getattr(replay, key) == created[kind][key]
                            for key in ("source_id", "source_version_id", "job_id", "chunk_count")
                        ),
                        "IDEMPOTENCY_IDENTITY_CHANGED",
                    )
            sources = {
                kind: _inspect(
                    observer, created=report["created"][kind], kind=kind, token=report["run_token"], profile=profile
                )
                for kind in ("text", "markdown")
            }
            canonical = _canonical_queries(observer, profile)
            observation["canonical_evaluation"] = canonical
            _require(
                canonical["exact"]["successful"] == 10
                and canonical["exact"]["hits_at_5"] >= 9
                and canonical["paraphrase"]["successful"] == 3,
                "CANONICAL_LEXICAL_BASELINE_REGRESSION",
            )
            after = _documents(observer)
            _require(
                all(after["sources"].get(key) == value for key, value in before["sources"].items()),
                "EXISTING_SOURCE_CHANGED",
            )
            if phase != "baseline":
                baseline = report["baseline"]
                _require(after == baseline["documents_after"], "RESTART_CHANGED_CORPUS")
                _require(
                    all(_stable_source(sources[kind]) == _stable_source(baseline["sources"][kind]) for kind in sources),
                    "RESTART_CHANGED_DURABLE_IDENTITIES",
                )
            observation.update(result="PASS", profile=profile, sources=sources, documents_after=after)
        except Exception as error:
            code = error.code if isinstance(error, _CheckFailed) else "LIVE_INGESTION_CHECK_FAILED"
            observation.update(result="FAIL", failure_code=code)
            raise RuntimeError(code) from None
        finally:
            observation.update(requests=observer.requests, client_total_ms=(monotonic() - started) * 1000)
            report[phase] = observation
            _save(evidence, report)
    print(json.dumps({"phase": phase, "result": "PASS", "source_count": 2, "requests": len(observer.requests)}))


def main() -> None:
    """Explicitly create two synthetic sources, or inspect their persisted state without publishing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "after-api", "after-database"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--evidence", type=Path, default=_EVIDENCE)
    arguments = parser.parse_args()
    _run(arguments.phase, base_url=_base_url(arguments.base_url), evidence=arguments.evidence)


if __name__ == "__main__":
    main()

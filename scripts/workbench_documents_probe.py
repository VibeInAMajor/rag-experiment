"""Own an isolated UI verification database and compare durable HTTP/SQL identities."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql

from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.postgres import PostgresPersistence
from scripts.workbench_ingestion_probe import _database_snapshot

_DIRECTORY = Path("tasks/evidence/live-documents-2026-11-23")
_STATE = Path(".cache/workbench-documents-probe.json")


def _dsn(original: str, database: str) -> str:
    parsed = urlsplit(original)
    return urlunsplit(parsed._replace(path=f"/{database}"))


async def _seed(dsn: str) -> None:
    repository = PostgresPersistence(dsn)
    await repository.start()
    try:
        await seed_development(repository)
    finally:
        await repository.close()


def _database(*, create: bool) -> str:
    if create:
        name = f"rag_test_{uuid4().hex}"
        _STATE.parent.mkdir(exist_ok=True)
        _STATE.write_text(json.dumps({"database": name}), encoding="utf-8")
        with psycopg.connect(_dsn(os.environ["WORKBENCH_DB_ADMIN_DSN"], "postgres"), autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        admin = _dsn(os.environ["WORKBENCH_DB_ADMIN_DSN"], name)
        migrate(admin)
        asyncio.run(_seed(_dsn(os.environ["WORKBENCH_DB_DSN"], name)))
    else:
        name = json.loads(_STATE.read_text(encoding="utf-8"))["database"]
    if not name.startswith("rag_test_") or len(name) != 41:
        raise ValueError("Expected this probe's UUID-named disposable database.")
    return name


def _serve(*, create: bool) -> None:
    name = _database(create=create)
    environment = dict(os.environ)
    environment["WORKBENCH_DB_DSN"] = _dsn(environment["WORKBENCH_DB_DSN"], name)
    environment["WORKBENCH_API_PORT"] = "8012"
    environment["WORKBENCH_API_ALLOWED_ORIGINS"] = "http://127.0.0.1:4174"
    environment.pop("WORKBENCH_DB_ADMIN_DSN", None)
    environment.pop("WORKBENCH_DB_ADMIN_PASSWORD", None)
    environment.pop("WORKBENCH_DB_APP_PASSWORD", None)
    print("Disposable seeded Documents server: 127.0.0.1:8012", flush=True)
    subprocess.run([sys.executable, "-m", "apps.workbench.api"], env=environment, check=True)


def _capture(phase: str) -> None:
    name = _database(create=False)
    snapshot = _database_snapshot(_dsn(os.environ["WORKBENCH_DB_DSN"], name))
    cases = []
    with httpx.Client(base_url="http://127.0.0.1:8012", timeout=30) as client:
        capabilities = client.get("/api/v1/capabilities").json()
        listing = client.get("/api/v1/workspaces/development/documents").json()
        for item in listing["items"]:
            source = item["source_id"]
            detail = client.get(f"/api/v1/workspaces/development/documents/{source}").json()
            chunks = client.get(f"/api/v1/workspaces/development/documents/{source}/chunks").json()
            while chunks["next_cursor"]:
                page = client.get(
                    f"/api/v1/workspaces/development/documents/{source}/chunks",
                    params={"cursor": chunks["next_cursor"]},
                ).json()
                assert page["source_version_id"] == chunks["source_version_id"]
                assert page["corpus_revision"] == chunks["corpus_revision"]
                chunks["items"].extend(page["items"])
                chunks["next_cursor"] = page["next_cursor"]
            stored = [
                row
                for row in snapshot["chunks"]
                if row["source_id"] == source and row["version_id"] == detail["active_version_id"]
            ]
            assert len(stored) == detail["chunk_count"] == len(chunks["items"])
            assert {(row["chunk_id"], row["content_hash"]) for row in stored} == {
                (row["chunk_id"], row["content_hash"]) for row in chunks["items"]
            }
            assert chunks["source_version_id"] == detail["active_version_id"]
            jobs = [row for row in snapshot["jobs"] if row["source_id"] == source]
            confirmed_jobs = []
            for stored_job in jobs:
                job = client.get(f"/api/v1/workspaces/development/jobs/{stored_job['job_id']}").json()
                assert job["status"] == stored_job["status"]
                assert job["source_version_id"] == stored_job["effective_version_id"]
                confirmed_jobs.append(job)
            cases.append(
                {
                    "source_id": source,
                    "source_version_id": detail["active_version_id"],
                    "chunk_count": detail["chunk_count"],
                    "parser": detail.get("parser"),
                    "processing_profile_fingerprint": detail.get("processing_profile_fingerprint"),
                    "chunks": [
                        {"chunk_id": row["chunk_id"], "content_hash": row["content_hash"]} for row in chunks["items"]
                    ],
                    "jobs": confirmed_jobs,
                }
            )
    report = {
        "phase": phase,
        "database_scope": "isolated_seeded_disposable",
        "capabilities": capabilities,
        "snapshot": snapshot,
        "cases": cases,
        "http_sql_parity": True,
    }
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    (_DIRECTORY / f"{phase}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "sources": snapshot["source_count"],
                "jobs": snapshot["job_count"],
                "http_sql_parity": True,
            }
        )
    )


def _confirmed(response: httpx.Response, *, status: int = 200, code: str | None = None) -> dict[str, Any]:
    if response.status_code != status:
        raise ValueError(f"Expected HTTP {status}; received HTTP {response.status_code}.")
    payload = response.json()
    if payload["contract_revision"] != "rag-api-v1.0" or payload["request_id"] != response.headers["x-request-id"]:
        raise ValueError("Response envelope correlation mismatch.")
    if code is not None and (payload["error"]["code"] != code or payload["error"]["http_status"] != status):
        raise ValueError(f"Expected error code {code}.")
    return payload


def _safe_envelope(payload: dict[str, Any], *, status: int) -> dict[str, Any]:
    fields = (
        "request_id",
        "trace_id",
        "source_id",
        "source_version_id",
        "job_id",
        "outcome",
        "status",
        "chunk_count",
        "corpus_revision",
        "replayed",
        "stages",
    )
    safe = {field: payload[field] for field in fields if field in payload}
    safe["http_status"] = status
    if "error" in payload:
        safe["error"] = {
            field: payload["error"][field]
            for field in ("code", "http_status", "retryable", "job_id")
            if field in payload["error"]
        }
    return safe


def _source_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "sources": sorted(row["source_id"] for row in snapshot["sources"]),
        "versions": sorted((row["source_id"], row["version_id"], row["status"]) for row in snapshot["versions"]),
        "chunks": sorted(
            (row["source_id"], row["version_id"], row["chunk_id"], row["content_hash"]) for row in snapshot["chunks"]
        ),
    }


def _verified_source(client: httpx.Client, original: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    source_id = original["source_id"]
    detail = _confirmed(client.get(f"/api/v1/workspaces/development/documents/{source_id}"))
    if detail["active_version_id"] != original["source_version_id"] or detail["chunk_count"] != original["chunk_count"]:
        raise ValueError("Browser publication identity changed unexpectedly.")
    chunks: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {"limit": "25"}
        if cursor is not None:
            params["cursor"] = cursor
        page = _confirmed(client.get(f"/api/v1/workspaces/development/documents/{source_id}/chunks", params=params))
        if (
            page["source_version_id"] != detail["active_version_id"]
            or page["corpus_revision"] != detail["corpus_revision"]
        ):
            raise ValueError("Chunk envelope scope mismatch.")
        chunks.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        if len(chunks) > 10000:
            raise ValueError("Chunk verification exceeded its bound.")
    stored = [
        row
        for row in snapshot["chunks"]
        if row["source_id"] == source_id and row["version_id"] == detail["active_version_id"]
    ]
    if len(stored) != len(chunks) or len(chunks) != detail["chunk_count"]:
        raise ValueError("HTTP/SQL chunk count mismatch.")
    if {(row["chunk_id"], row["content_hash"]) for row in stored} != {
        (row["chunk_id"], row["content_hash"]) for row in chunks
    }:
        raise ValueError("HTTP/SQL chunk identity mismatch.")
    job = _confirmed(client.get(f"/api/v1/workspaces/development/jobs/{original['job_id']}"))
    stored_jobs = [row for row in snapshot["jobs"] if row["job_id"] == original["job_id"]]
    if (
        len(stored_jobs) != 1
        or job["source_version_id"] != original["source_version_id"]
        or job["status"] != "completed"
    ):
        raise ValueError("Browser job durability mismatch.")
    parser = detail.get("parser") or {}
    return {
        "source_id": source_id,
        "source_version_id": detail["active_version_id"],
        "job_id": original["job_id"],
        "chunk_count": len(chunks),
        "corpus_revision": detail["corpus_revision"],
        "parser": {key: parser[key] for key in ("id", "revision", "parser_id", "parser_revision") if key in parser},
        "processing_profile_fingerprint": detail.get("processing_profile_fingerprint"),
        "chunks": [{"chunk_id": row["chunk_id"], "content_hash": row["content_hash"]} for row in chunks],
        "http_sql_parity": True,
    }


def _verify_negative_cases(client: httpx.Client, browser: list[dict[str, Any]]) -> list[dict[str, Any]]:
    negative = []
    original = browser[0]["response"]
    original_path = Path(".cache/workbench-documents-inputs/license.txt")
    content = original_path.read_bytes()
    endpoint = "/api/v1/workspaces/development/documents"
    trials = (
        (
            "stale_version",
            409,
            "VERSION_CONFLICT",
            {"source_id": original["source_id"], "expected_active_version_id": "missing-version"},
            content,
            "text/plain",
        ),
        ("invalid_mime", 415, None, {}, b"valid plain content", "application/pdf"),
        ("oversize_text", 413, None, {}, b"x" * 1048577, "text/plain"),
        ("partial_update_fields", 400, "INVALID_REQUEST", {"source_id": original["source_id"]}, content, "text/plain"),
    )
    for label, status, code, fields, data, mime in trials:
        response = client.post(
            endpoint,
            files={"file": (original_path.name, data, mime)},
            data=fields,
            headers={"Idempotency-Key": uuid4().hex},
        )
        payload = _confirmed(response, status=status, code=code)
        negative.append({"case": label, **_safe_envelope(payload, status=status)})
    for label, route in (
        ("missing_source", endpoint + "/missing-source"),
        ("missing_job", "/api/v1/workspaces/development/jobs/missing-job"),
        ("wrong_workspace", "/api/v1/workspaces/foreign/documents"),
    ):
        response = client.get(route)
        payload = _confirmed(response, status=404)
        negative.append({"case": label, **_safe_envelope(payload, status=404)})
    listing = _confirmed(client.get(endpoint, params={"limit": 1}))
    cursor = listing["next_cursor"]
    if not cursor:
        raise ValueError("Expected a signed document cursor.")
    tampered = ("A" if cursor[0] != "A" else "B") + cursor[1:]
    payload = _confirmed(client.get(endpoint, params={"cursor": tampered}), status=400, code="INVALID_CURSOR")
    negative.append({"case": "tampered_document_cursor", **_safe_envelope(payload, status=400)})
    first_source = browser[0]["response"]["source_id"]
    second_source = browser[1]["response"]["source_id"]
    chunks = _confirmed(client.get(f"{endpoint}/{first_source}/chunks", params={"limit": 1}))
    if not chunks["next_cursor"]:
        raise ValueError("Expected a signed chunk cursor.")
    payload = _confirmed(
        client.get(f"{endpoint}/{second_source}/chunks", params={"cursor": chunks["next_cursor"]}),
        status=400,
        code="INVALID_CURSOR",
    )
    negative.append({"case": "cross_source_chunk_cursor", **_safe_envelope(payload, status=400)})
    return negative


def _verify() -> None:
    name = _database(create=False)
    dsn = _dsn(os.environ["WORKBENCH_DB_DSN"], name)
    before = _database_snapshot(dsn)
    browser = json.loads((_DIRECTORY / "browser-uploads.json").read_text(encoding="utf-8"))
    fixtures = (
        ("txt", Path(".cache/workbench-documents-inputs/license.txt"), "text/plain", "Apache"),
        ("markdown", Path(".cache/workbench-documents-inputs/api-guide.md"), "text/markdown", "ingestion"),
        ("python", Path(".cache/workbench-documents-inputs/db-seed.py"), "text/x-python", "seed_development"),
        (
            "pdf",
            Path("tasks/evidence/pdf-layout-2026-11-22/live/california-warn-report-page-1.pdf"),
            "application/pdf",
            "TaylorMade",
        ),
    )
    if len(browser) != len(fixtures) or any(entry["http_status"] != 201 for entry in browser):
        raise ValueError("Expected four browser-created source records.")
    cases = []
    with httpx.Client(base_url="http://127.0.0.1:8012", timeout=240) as client:
        capabilities = _confirmed(client.get("/api/v1/capabilities"))
        if not capabilities["features"]["upload"] or not capabilities["pdf_ingestion"]["available"]:
            raise ValueError("Expected all four qualified runtime formats.")
        profile = next(
            profile for profile in capabilities["profiles"] if profile["profile_id"] == "postgres-fts-baseline"
        )
        for entry, (format_id, path, mime, query) in zip(browser, fixtures, strict=True):
            original = entry["response"]
            case = _verified_source(client, original, before)
            case["format"] = format_id
            started = perf_counter()
            search = _confirmed(
                client.post(
                    "/api/v1/workspaces/development/search",
                    json={
                        "query": query,
                        "top_k": 50,
                        "profile_id": profile["profile_id"],
                        "expected_profile_revision": profile["profile_revision"],
                    },
                )
            )
            matched = [
                result
                for result in search["results"]
                if result["source_id"] == original["source_id"]
                and result["source_version_id"] == original["source_version_id"]
            ]
            if not matched:
                raise ValueError(f"Live lexical verification missed the {format_id} browser source.")
            case["search"] = {
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "request_id": search["request_id"],
                "trace_id": search["trace_id"],
                "run_id": search["run_id"],
                "corpus_revision": search["corpus_revision"],
                "duration_ms": search["duration_ms"],
                "http_elapsed_ms": (perf_counter() - started) * 1000,
                "matched_chunks": [
                    {
                        "chunk_id": result["chunk_id"],
                        "source_id": result["source_id"],
                        "source_version_id": result["source_version_id"],
                        "rank": result["rank"],
                    }
                    for result in matched
                ],
            }
            content = path.read_bytes()
            key = uuid4().hex
            fields = {"source_id": original["source_id"], "expected_active_version_id": original["source_version_id"]}
            unchanged = _confirmed(
                client.post(
                    "/api/v1/workspaces/development/documents",
                    files={"file": (path.name, content, mime)},
                    data=fields,
                    headers={"Idempotency-Key": key},
                )
            )
            if (
                unchanged["outcome"] != "unchanged"
                or unchanged["replayed"]
                or unchanged["source_version_id"] != original["source_version_id"]
            ):
                raise ValueError("Guarded unchanged upload changed source identity.")
            after_unchanged = _database_snapshot(dsn)
            replay = _confirmed(
                client.post(
                    "/api/v1/workspaces/development/documents",
                    files={"file": (path.name, content, mime)},
                    data=fields,
                    headers={"Idempotency-Key": key},
                )
            )
            if not replay["replayed"] or any(
                replay[field] != unchanged[field]
                for field in ("source_id", "source_version_id", "job_id", "chunk_count", "outcome")
            ):
                raise ValueError("Same-key replay changed publication identity.")
            after_replay = _database_snapshot(dsn)
            if (
                _source_identity(before) != _source_identity(after_replay)
                or after_unchanged["job_count"] != after_replay["job_count"]
            ):
                raise ValueError("Unchanged/replay created duplicate source versions or jobs.")
            case["unchanged"] = _safe_envelope(unchanged, status=200)
            case["replay"] = _safe_envelope(replay, status=200)
            case["operation_key_sha256"] = hashlib.sha256(key.encode()).hexdigest()
            case["no_duplicate_versions_or_replay_jobs"] = True
            cases.append(case)
        negative = _verify_negative_cases(client, browser)
    after = _database_snapshot(dsn)
    if _source_identity(before) != _source_identity(after):
        raise ValueError("Negative or unchanged operations mutated the published corpus.")
    report = {
        "summary": {
            "qualified_formats_verified": [case["format"] for case in cases],
            "lexical_sources_matched": len(cases),
            "guarded_unchanged_uploads": len(cases),
            "same_key_replays": len(cases),
            "negative_cases_passed": len(negative),
            "duplicate_versions_created": 0,
            "replay_jobs_created": 0,
        },
        "database_scope": "isolated_seeded_disposable",
        "transport": "real_http_8012",
        "http_sql_parity": True,
        "sources": cases,
        "negative_cases": negative,
        "published_corpus_unchanged": True,
        "before_counts": {key: before[key] for key in ("source_count", "version_count", "chunk_count", "job_count")},
        "after_counts": {key: after[key] for key in ("source_count", "version_count", "chunk_count", "job_count")},
    }
    (_DIRECTORY / "http-sql-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "sources_verified": len(cases),
                "negative_cases_verified": len(negative),
                "http_sql_parity": True,
                "published_corpus_unchanged": True,
            }
        )
    )


def main() -> None:
    """Run one isolated verification operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create-server", "restart-server", "capture", "verify"))
    parser.add_argument("--phase", default="after-upload")
    args = parser.parse_args()
    if args.action == "capture":
        _capture(args.phase)
    elif args.action == "verify":
        _verify()
    else:
        _serve(create=args.action == "create-server")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()

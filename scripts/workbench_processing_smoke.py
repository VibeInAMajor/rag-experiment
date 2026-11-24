"""Qualify configured processing through live HTTP without retaining source passages or credentials."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.workbench.chunking.chunking_adapters import count_tokens
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter
from scripts.workbench_ingestion_probe import _database_snapshot

_DIRECTORY = Path("tasks/evidence/config-2026-11-22")
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _require(condition: object, code: str) -> None:
    if not condition:
        raise RuntimeError(code)


def _write(name: str, value: object) -> None:
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    (_DIRECTORY / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _payload(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    _require(response.status_code == status, "UNEXPECTED_HTTP_STATUS")
    result = response.json()
    _require(result["request_id"] == response.headers["X-Request-ID"] and result["trace_id"], "CORRELATION_MISMATCH")
    return result


def _cases(nonce: str) -> list[tuple[str, str, str, bytes]]:
    sentence = (
        "Dr. Adams reviewed the release at 9 a.m. The team checked sentence boundaries, "
        "overlap, and Unicode: English, русский, український. Each record retains its source coordinates. "
    )
    return [
        (
            "txt",
            "processing-proof.txt",
            "text/plain",
            (f"ProcessingText{nonce}.\n\n" + (sentence * 12 + "\n") * 3).encode(),
        ),
        (
            "md",
            "processing-proof.md",
            "text/markdown",
            (f"# ProcessingMarkdown{nonce}\n\n" + sentence * 28 + "\n\n## Next section\n\n" + sentence * 8).encode(),
        ),
    ]


def _preserved(before: dict[str, Any], after: dict[str, Any]) -> None:
    for table in ("sources", "versions", "chunks", "jobs"):
        _require(all(row in after[table] for row in before[table]), "EXISTING_RECORD_CHANGED")
    _require(before["ledger"] == after["ledger"] and before["schema"] == after["schema"], "SCHEMA_CHANGED")


def _qualify(client: httpx.Client, record: dict[str, Any], counter: LocalQwenTokenCounter) -> dict[str, Any]:
    source_id = record["source_id"]
    detail = _payload(client.get(f"{_DOCUMENTS}/{source_id}"))
    _require(detail["active_version_id"] == record["source_version_id"], "VERSION_MISMATCH")
    _require(detail["default_language"] == "en", "DEFAULT_LANGUAGE_MISMATCH")
    _require(detail["language_policy"] == "configured_sentence_language", "LANGUAGE_POLICY_MISMATCH")
    chunks: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = _payload(client.get(f"{_DOCUMENTS}/{source_id}/chunks", params={"cursor": cursor} if cursor else None))
        for chunk in page["items"]:
            metadata = chunk["metadata"]
            _require(metadata["sentence_language"] == "en" and not metadata["fallback_reasons"], "SENTENCE_FALLBACK")
            _require(metadata["target_size"] == 500 and metadata["requested_overlap"] == 50, "SIZE_MISMATCH")
            native = counter.count_tokens(chunk["content"])
            encoding = count_tokens(chunk["content"])
            _require(native == metadata["length_model_token"] <= 32768, "NATIVE_COUNT_MISMATCH")
            _require(encoding == metadata["length_tiktoken"] <= 500, "ENCODING_COUNT_MISMATCH")
            _require(metadata["model_counter_revision"] == counter.counter_revision, "COUNTER_REVISION_MISMATCH")
            chunks.append({"chunk_id": chunk["chunk_id"], "content_hash": chunk["content_hash"], "metadata": metadata})
        cursor = page["next_cursor"]
        if cursor is None:
            break
    _require(len(chunks) == record["chunk_count"] and len(chunks) > 1, "CHUNK_COUNT_MISMATCH")
    _require(any(chunk["metadata"]["model_minus_tiktoken"] != 0 for chunk in chunks), "TOKEN_COUNTS_ASSUMED_EQUAL")
    job = _payload(client.get(f"/api/v1/workspaces/development/jobs/{record['job_id']}"))
    _require(job["status"] == "completed" and job["chunk_count"] == len(chunks), "JOB_MISMATCH")
    result = _payload(
        client.post(
            "/api/v1/workspaces/development/search",
            json={
                "query": record["query"],
                "top_k": 10,
                "profile_id": "postgres-fts-baseline",
                "expected_profile_revision": "postgres-fts-baseline-r1",
            },
        )
    )
    _require(any(hit["source_id"] == source_id for hit in result["results"]), "LIVE_SEARCH_MISSING")
    return {
        "detail": detail,
        "chunks": chunks,
        "job": job,
        "search": {key: value for key, value in result.items() if key != "results"},
        "matching_chunk_ids": [hit["chunk_id"] for hit in result["results"] if hit["source_id"] == source_id],
    }


def main() -> None:
    """Collect a baseline, publish two synthetic probes, or verify immutable replay after restart."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after", "verify"))
    args = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise RuntimeError("APPLICATION_DATABASE_REQUIRED")
    snapshot = _database_snapshot(dsn)
    if args.phase == "before":
        _require(not (_DIRECTORY / "before.json").exists(), "BASELINE_ALREADY_EXISTS")
        _write("before.json", snapshot)
        print(json.dumps({"phase": "before", "sources": snapshot["source_count"], "chunks": snapshot["chunk_count"]}))
        return
    before = json.loads((_DIRECTORY / "before.json").read_text(encoding="utf-8"))
    _preserved(before, snapshot)
    if args.phase == "after":
        _require(not (_DIRECTORY / "after.json").exists(), "UPLOAD_EVIDENCE_ALREADY_EXISTS")
    settings = ApiSettings.from_env()
    guard = settings.document_processing.native_model_guard
    if not guard.enabled or guard.local_asset_directory is None:
        raise RuntimeError("NATIVE_GUARD_NOT_CONFIGURED")
    counter = LocalQwenTokenCounter(Path(guard.local_asset_directory))
    if args.phase == "after":
        nonce = uuid4().hex
        records = []
    else:
        previous = json.loads((_DIRECTORY / "after.json").read_text(encoding="utf-8"))
        nonce, records = previous["nonce"], previous["records"]
        _require(snapshot == previous["database"], "PERSISTED_STATE_CHANGED_AFTER_RESTART")
    observations = []
    with httpx.Client(base_url="http://127.0.0.1:8011", timeout=30, trust_env=False) as client:
        capabilities = _payload(client.get("/api/v1/capabilities"))
        _require(capabilities["features"]["upload"], "UPLOAD_UNAVAILABLE")
        for index, (kind, filename, mime, content) in enumerate(_cases(nonce)):
            response = client.post(
                _DOCUMENTS,
                files={"file": (filename, content, mime)},
                headers={"Idempotency-Key": f"processing_{nonce}_{kind}"},
            )
            upload = _payload(response, 201 if args.phase == "after" else 200)
            if args.phase == "after":
                records.append(
                    {
                        **upload,
                        "query": f"Processing{'Text' if kind == 'txt' else 'Markdown'}{nonce}",
                        "source_sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            else:
                _require(upload["replayed"] and upload["job_id"] == records[index]["job_id"], "REPLAY_CHANGED")
            observations.append(_qualify(client, records[index], counter))
    after = _database_snapshot(dsn)
    _preserved(before, after)
    if args.phase == "verify":
        _require(after == snapshot, "REPLAY_PUBLISHED_CHANGES")
    _write(
        f"{args.phase}.json",
        {
            "recorded_at": datetime.now(UTC).isoformat(),
            "nonce": nonce,
            "records": records,
            "observations": observations,
            "database": after,
            "old_records_unchanged": True,
            "native_counts_independently_verified": True,
        },
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "sources": after["source_count"],
                "chunks": after["chunk_count"],
                "old_records_unchanged": True,
                "native_counts_independently_verified": True,
            }
        )
    )


if __name__ == "__main__":
    main()

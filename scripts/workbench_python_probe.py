"""Qualify real project source on the running loopback API; retain hashes and provenance, never source bodies."""

import argparse
import hashlib
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from apps.workbench.api.document_processing import load_document_processing
from apps.workbench.api.model_token_counter import LocalQwenTokenCounter
from scripts.workbench_ingestion_probe import _database_snapshot

_DIRECTORY = Path("tasks/evidence/python-ast-2026-11-22")
_SOURCE = Path("apps/workbench/api/ingestion.py")
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _assert_preserved(before: dict, after: dict) -> None:
    for table in ("sources", "versions", "chunks", "jobs"):
        for row in before[table]:
            if row not in after[table]:
                raise RuntimeError("An existing application row changed during qualification.")


def _assert_sql_chunks(uploaded: dict, validation: dict, database: dict) -> None:
    stored = {
        row["chunk_id"]: row
        for row in database["chunks"]
        if row["source_id"] == uploaded["source_id"] and row["version_id"] == uploaded["source_version_id"]
    }
    expected = {row["chunk_id"]: row for row in validation["chunks"]}
    if stored.keys() != expected.keys():
        raise RuntimeError("HTTP and SQL chunk identities differ.")
    for identifier, row in stored.items():
        if row["content_hash"] != expected[identifier]["content_hash"] or row["content_sha256"] != row["content_hash"]:
            raise RuntimeError("SQL content hashes differ from the original real source slices.")


def _chunks(client: httpx.Client, source: str, version: str) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        response = client.get(
            f"{_DOCUMENTS}/{source}/chunks", params={"limit": 100, **({"cursor": cursor} if cursor else {})}
        )
        response.raise_for_status()
        page = response.json()
        if page["source_version_id"] != version:
            raise RuntimeError("Active chunk version mismatch.")
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return items


def _verify(client: httpx.Client, uploaded: dict, content: bytes) -> dict:
    source = uploaded["source_id"]
    chunks = _chunks(client, source, uploaded["source_version_id"])
    text = content.decode("utf-8-sig")
    lines = io.StringIO(text, newline="").readlines()
    hashes = []
    native_lengths = []
    symbols: set[str] = set()
    guard = load_document_processing(os.environ).native_model_guard
    if not guard.enabled or guard.local_asset_directory is None:
        raise RuntimeError("Live qualification requires the configured native guard.")
    counter = LocalQwenTokenCounter(Path(guard.local_asset_directory))
    for chunk in chunks:
        metadata = chunk["metadata"]
        if metadata["strategy"] != "python_ast" or metadata["unit"] != "effective_line" or chunk["page"] is not None:
            raise RuntimeError("The running server did not select the qualified Python policy.")
        expected = "".join(lines[metadata["start_line"] - 1 : metadata["end_line"]])
        if chunk["content"] != expected or hashlib.sha256(expected.encode()).hexdigest() != chunk["content_hash"]:
            raise RuntimeError("Stored code does not match the real project's line range.")
        recounted = counter.count_tokens(guard.prefix + expected + guard.suffix)
        if recounted != metadata.get("length_model_token") or counter.counter_revision != metadata.get(
            "model_counter_revision"
        ):
            raise RuntimeError("Independent native token recount differs from the server metadata.")
        native_lengths.append(metadata.get("length_model_token"))
        symbols.update(symbol["qualified_symbol"] for symbol in metadata["symbols"])
        hashes.append(
            {
                "chunk_id": chunk["chunk_id"],
                "content_hash": chunk["content_hash"],
                "start_line": metadata["start_line"],
                "end_line": metadata["end_line"],
                "model_tokens": metadata.get("length_model_token"),
                "model_counter_revision": metadata.get("model_counter_revision"),
            }
        )
    if not chunks or not all(isinstance(value, int) and value > 0 for value in native_lengths):
        raise RuntimeError("Native Qwen token admission was not demonstrated on the running server.")
    response = client.post(
        "/api/v1/workspaces/development/search",
        json={
            "query": "IngestionService",
            "top_k": 5,
            "profile_id": "postgres-fts-baseline",
            "expected_profile_revision": "postgres-fts-baseline-r1",
        },
    )
    response.raise_for_status()
    hits = [hit for hit in response.json()["results"] if hit["source_id"] == source]
    if not hits or any(hit["score_type"] != "postgres_ts_rank_cd" for hit in hits):
        raise RuntimeError("The real source was not found by the running lexical route.")
    if not all(hit["chunk_id"] in {chunk["chunk_id"] for chunk in chunks} for hit in hits):
        raise RuntimeError("Search identities differ from persisted chunks.")
    return {
        "chunks": hashes,
        "symbol_count": len(symbols),
        "query": "IngestionService",
        "search_hits": [
            {
                "chunk_id": hit["chunk_id"],
                "source_version_id": hit["source_version_id"],
                "score": hit["score"],
                "score_type": hit["score_type"],
            }
            for hit in hits
        ],
        "all_line_ranges_exact": True,
        "all_native_counts_present": True,
    }


def main() -> None:
    """Upload once, then verify durable real-source identities after an explicit operator restart."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("upload", "after-restart", "sql-parity"))
    phase = parser.parse_args().phase
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    output = _DIRECTORY / f"live-{phase}.json"
    if output.exists():
        raise SystemExit("Existing live evidence will not be overwritten.")
    dsn = os.environ["WORKBENCH_DB_DSN"]
    content = _SOURCE.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    before = _database_snapshot(dsn)
    with httpx.Client(
        base_url="http://127.0.0.1:8011", headers={"Origin": "http://127.0.0.1:4173"}, timeout=60, trust_env=False
    ) as client:
        if phase == "upload":
            intent_path = _DIRECTORY / "live-intent.json"
            if intent_path.exists():
                intent = json.loads(intent_path.read_text(encoding="utf-8"))
                if intent["source_sha256"] != digest:
                    raise SystemExit("The real source changed since the reserved qualification intent.")
            else:
                intent = {"idempotency_key": uuid4().hex, "source_sha256": digest, "database_before": before}
                intent_path.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")
            response = client.post(
                _DOCUMENTS,
                headers={"Idempotency-Key": intent["idempotency_key"]},
                files={"file": (_SOURCE.name, content, "text/x-python")},
            )
            response.raise_for_status()
            uploaded = response.json()
            validation = _verify(client, uploaded, content)
            invalid = client.post(
                _DOCUMENTS,
                headers={"Idempotency-Key": uuid4().hex},
                files={"file": (_SOURCE.name, content + b"\ndef broken(\n", "text/x-python")},
                data={"source_id": uploaded["source_id"], "expected_active_version_id": uploaded["source_version_id"]},
            )
            if invalid.status_code != 400 or invalid.json()["error"]["code"] != "UNPARSEABLE_SOURCE":
                raise RuntimeError("The live server accepted a corrupted update of the real source.")
            if _verify(client, uploaded, content) != validation:
                raise RuntimeError("A rejected syntax update changed the active code or search results.")
            after = _database_snapshot(dsn)
            _assert_preserved(intent["database_before"], after)
        else:
            first = json.loads((_DIRECTORY / "live-upload.json").read_text(encoding="utf-8"))
            intent = json.loads((_DIRECTORY / "live-intent.json").read_text(encoding="utf-8"))
            if digest != first["source_sha256"]:
                raise SystemExit("The real source changed since upload; refusing to claim a matching replay.")
            uploaded = first["upload"]
            validation = _verify(client, uploaded, content)
            if validation != first["validation"]:
                raise RuntimeError("Source/chunk/search provenance changed after API restart.")
            replay = client.post(
                _DOCUMENTS,
                headers={"Idempotency-Key": intent["idempotency_key"]},
                files={"file": (_SOURCE.name, content, "text/x-python")},
            )
            replay.raise_for_status()
            if not replay.json()["replayed"] or replay.json()["source_version_id"] != uploaded["source_version_id"]:
                raise RuntimeError("Terminal replay changed the stored source version.")
            if before != first["database_after"]:
                raise RuntimeError("Database state changed between the live upload and restart verification.")
            after = _database_snapshot(dsn)
            if after != before:
                raise RuntimeError("Read/search/replay changed the corpus.")
        _assert_sql_chunks(uploaded, validation, after)
        report = {
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "scope": "real project file, running HTTP server and application-role SQL",
            "source_path": _SOURCE.as_posix(),
            "source_sha256": digest,
            "source_bytes": len(content),
            "upload": uploaded,
            "validation": validation,
            "database_after": after,
            "existing_rows_preserved": True,
            "http_original_file_sql_chunk_parity": True,
            "corrupted_real_source_update_refused_without_active_version_change": True,
            "result": "PASS",
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "phase": phase,
                    "result": "PASS",
                    "source_id": uploaded["source_id"],
                    "chunks": uploaded["chunk_count"],
                    "existing_rows_preserved": True,
                }
            )
        )


if __name__ == "__main__":
    main()

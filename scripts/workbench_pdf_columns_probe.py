"""Prove original PDF numbers survive the running ingestion API and PostgreSQL unchanged."""

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from pypdf import PdfReader

from scripts.workbench_ingestion_probe import _database_snapshot
from scripts.workbench_python_probe import _assert_preserved, _assert_sql_chunks, _chunks

_INPUT = Path("tasks/evidence/pdf-layout-2026-11-22/qualification/inputs/two-columns.pdf")
_OUTPUT = Path("tasks/evidence/pdf-layout-2026-11-23/two-columns-live")
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _numeric_values(text: str) -> Counter[str]:
    return Counter(re.findall(r"\d+(?:[.,]\d+)*", unicodedata.normalize("NFKC", text)))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=_OUTPUT)
    parser.add_argument("--source-id")
    parser.add_argument("--expected-version")
    options = parser.parse_args()
    if bool(options.source_id) != bool(options.expected_version):
        parser.error("--source-id and --expected-version must be supplied together")
    return options


def _stored_numeric_counts(*, source_id: str, version_id: str) -> Counter[str]:
    with psycopg.connect(os.environ["WORKBENCH_DB_DSN"], connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SELECT set_config('workbench.workspace_id','development',true)")
        connection.execute("SELECT set_config('statement_timeout','5000',true)")
        rows = connection.execute(
            "SELECT metadata->>'original_excerpt' FROM workbench.chunks "
            "WHERE workspace_id=%s AND source_id=%s AND version_id=%s ORDER BY chunk_id LIMIT 10001",
            ("development", source_id, version_id),
        ).fetchall()
    if not rows or len(rows) > 10_000 or any(not isinstance(row[0], str) for row in rows):
        raise RuntimeError("Stored source excerpts are missing or outside the qualified budget")
    return _numeric_values("\n".join(row[0] for row in rows))


def main() -> None:
    """Use the same formerly refused fixture; verify actual stored source excerpts, not repeated context."""
    options = _arguments()
    output = options.output_dir
    output.mkdir(parents=True, exist_ok=True)
    fields = (
        {"source_id": options.source_id, "expected_active_version_id": options.expected_version}
        if options.source_id
        else None
    )
    content = _INPUT.read_bytes()
    original = "\n".join(page.extract_text() or "" for page in PdfReader(_INPUT).pages)
    expected = _numeric_values(original)
    intent_path = output / "intent.json"
    if intent_path.exists():
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        if intent["sha256"] != hashlib.sha256(content).hexdigest():
            raise RuntimeError("The reserved PDF input changed")
    else:
        intent = {
            "key": uuid4().hex,
            "sha256": hashlib.sha256(content).hexdigest(),
            "input_kind": "original reproducible two-column fixture from the earlier refused run",
        }
        intent_path.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    before = _database_snapshot(os.environ["WORKBENCH_DB_DSN"])
    with httpx.Client(
        base_url="http://127.0.0.1:8011", timeout=215, trust_env=False, headers={"Origin": "http://127.0.0.1:4173"}
    ) as client:
        response = client.post(
            _DOCUMENTS,
            files={"file": ("two-column-numeric-completeness.pdf", content, "application/pdf")},
            data=fields,
            headers={"Idempotency-Key": intent["key"]},
        )
        response.raise_for_status()
        result = response.json()
        assert result["status"] == "completed"
        chunks = _chunks(client, result["source_id"], result["source_version_id"])
        detail = client.get(f"{_DOCUMENTS}/{result['source_id']}")
        detail.raise_for_status()
        assert detail.json()["parser"]["parser_revision"] == "docling-pdf-r2"
        assert detail.json()["parser"]["pdf_tables"] == 0
        assert "PDF_COLUMNS_PROJECTED_AS_TEXT" in detail.json()["warnings"]
        if options.source_id:
            assert "PDF_NATIVE_CELL_RECOVERY" in detail.json()["warnings"]
            assert result["source_version_id"] != options.expected_version
        excerpts = "\n".join(chunk["metadata"]["original_excerpt"] for chunk in chunks)
        actual = _numeric_values(excerpts)
        assert actual == expected, (expected - actual, actual - expected)
        assert all(chunk["page"] == 1 for chunk in chunks)
        assert all(
            f"{side} section observation {index}." in excerpts for side in ("Left", "Right") for index in range(12)
        )
        assert all(chunk["metadata"]["block_kind"] != "table" for chunk in chunks)
        search = client.post(
            "/api/v1/workspaces/development/search",
            json={
                "query": "Right observation 11",
                "top_k": 5,
                "profile_id": "postgres-fts-baseline",
                "expected_profile_revision": "postgres-fts-baseline-r1",
            },
        )
        search.raise_for_status()
        hits = [hit for hit in search.json()["results"] if hit["source_id"] == result["source_id"]]
        assert hits and all(hit["page"] == 1 for hit in hits)
        replay = client.post(
            _DOCUMENTS,
            files={"file": ("two-column-numeric-completeness.pdf", content, "application/pdf")},
            data=fields,
            headers={"Idempotency-Key": intent["key"]},
        )
        replay.raise_for_status()
        assert replay.json()["source_version_id"] == result["source_version_id"]
    database_counts = _stored_numeric_counts(source_id=result["source_id"], version_id=result["source_version_id"])
    assert database_counts == expected
    validation = {
        "chunks": [{"chunk_id": chunk["chunk_id"], "content_hash": chunk["content_hash"]} for chunk in chunks],
        "source_numeric_counts": dict(expected),
        "stored_excerpt_numeric_counts": dict(actual),
        "direct_sql_numeric_counts": dict(database_counts),
        "direct_sql_numeric_comparison_passed": True,
        "source_numeric_occurrences": sum(expected.values()),
        "stored_numeric_occurrences": sum(actual.values()),
        "source_digit_characters": sum(character.isdecimal() for character in original),
        "stored_digit_characters": sum(character.isdecimal() for character in excerpts),
        "missing_numbers": dict(expected - actual),
        "extra_numbers": dict(actual - expected),
        "all_24_sentences_preserved": True,
        "all_pages_verified": True,
        "retrieval_context_repetitions_excluded": True,
        "parser": detail.json()["parser"],
        "warnings": detail.json()["warnings"],
        "search_hits": [{"chunk_id": hit["chunk_id"], "page": hit["page"]} for hit in hits],
    }
    after = _database_snapshot(os.environ["WORKBENCH_DB_DSN"])
    _assert_preserved(
        {
            key: [row for row in before[key] if row.get("source_id") != options.source_id]
            for key in ("sources", "versions", "chunks", "jobs")
        },
        {
            key: [row for row in after[key] if row.get("source_id") != options.source_id]
            for key in ("sources", "versions", "chunks", "jobs")
        },
    )
    assert all(row in after["chunks"] for row in before["chunks"])
    _assert_sql_chunks(result, validation, after)
    evidence = {
        "result": result,
        "input": intent,
        "validation": validation,
        "database_before": before,
        "database_after": after,
        "existing_corpus_preserved": True,
    }
    (output / "successful-numeric-completeness.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "completed",
                "source_id": result["source_id"],
                "chunks": len(chunks),
                "numeric_occurrences": sum(actual.values()),
                "digit_characters": validation["stored_digit_characters"],
                "missing": dict(expected - actual),
                "extra": dict(actual - expected),
                "sql_parity": True,
            }
        )
    )


if __name__ == "__main__":
    main()

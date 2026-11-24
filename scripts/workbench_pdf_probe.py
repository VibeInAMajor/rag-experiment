"""Real public PDF evidence through the running API, SQL, native token admission and restarts."""

import argparse
import hashlib
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pypdf import PdfReader, PdfWriter

from apps.workbench.configuration.document_processing import load_document_processing
from apps.workbench.embedding.model_token_counter import LocalQwenTokenCounter
from scripts.workbench_ingestion_probe import _database_snapshot
from scripts.workbench_python_probe import _assert_preserved, _assert_sql_chunks, _chunks

_ROOT = Path("tasks/evidence/pdf-layout-2026-11-22/live")
_PUBLIC_SOURCE = Path("tmp/pdfs/ca-warn-report.pdf")
_INPUT = _ROOT / "california-warn-report-page-1.pdf"
_DOCUMENTS = "/api/v1/workspaces/development/documents"


def _upload(client: httpx.Client, content: bytes, *, key: str, fields: dict[str, str] | None = None) -> httpx.Response:
    return client.post(
        _DOCUMENTS,
        files={"file": (_INPUT.name, content, "application/pdf")},
        data=fields,
        headers={"Idempotency-Key": key},
    )


def _verify(client: httpx.Client, result: dict[str, Any], content: bytes) -> dict[str, Any]:
    chunks = _chunks(client, result["source_id"], result["source_version_id"])
    detail = client.get(f"{_DOCUMENTS}/{result['source_id']}")
    detail.raise_for_status()
    parser = detail.json()["parser"]
    assert parser["pdf_pages"] == 1 and parser["visual_processing_status"] == "incomplete"
    assert parser["original_evidence_status"] == "unavailable" and parser["pdf_ocr_enabled"] is False
    guard = load_document_processing(os.environ).native_model_guard
    assert guard.enabled and guard.local_asset_directory
    counter = LocalQwenTokenCounter(Path(guard.local_asset_directory))
    hashes = []
    table_rows = []
    for chunk in chunks:
        metadata = chunk["metadata"]
        assert chunk["page"] == metadata["page_number"] == 1
        assert metadata["strategy"] == "page_layout" and metadata["target_size"] == 768
        assert metadata["source_sha256"] == hashlib.sha256(content).hexdigest()
        assert metadata["original_evidence_status"] == "unavailable" and "asset_id" not in metadata
        text = chunk["content"]
        assert hashlib.sha256(text.encode()).hexdigest() == chunk["content_hash"] == metadata["retrieval_sha256"]
        assert hashlib.sha256(metadata["original_excerpt"].encode()).hexdigest() == metadata["original_excerpt_sha256"]
        prefix = (
            " > ".join(metadata["heading_path"]) + "\n\n"
            if guard.include_heading_path and metadata["heading_path"]
            else ""
        )
        length = counter.count_tokens(guard.prefix + prefix + text + guard.suffix)
        assert length == metadata["length_model_token"] <= guard.max_tokens
        assert counter.counter_revision == metadata["model_counter_revision"]
        if metadata["block_kind"] == "table":
            assert "Notice Date" in text and "Company" in text and "Layoff/Closure" in text
            table_rows.extend(range(metadata["table_row_start"], metadata["table_row_end"]))
        hashes.append(
            {
                "chunk_id": chunk["chunk_id"],
                "content_hash": chunk["content_hash"],
                "page": 1,
                "native_model_tokens": length,
                "model_counter_revision": counter.counter_revision,
            }
        )
    assert table_rows == list(range(1, 37))
    response = client.post(
        "/api/v1/workspaces/development/search",
        json={
            "query": "TaylorMade",
            "top_k": 5,
            "profile_id": "postgres-fts-baseline",
            "expected_profile_revision": "postgres-fts-baseline-r1",
        },
    )
    response.raise_for_status()
    hits = [hit for hit in response.json()["results"] if hit["source_id"] == result["source_id"]]
    assert hits and all(hit["page"] == 1 and hit["score_type"] == "postgres_ts_rank_cd" for hit in hits)
    assert any("64" in hit["content"] and "Carlsbad" in hit["content"] for hit in hits)
    return {
        "chunks": hashes,
        "table_body_rows": 36,
        "independent_native_recount": True,
        "parser": parser,
        "query": "TaylorMade",
        "hits": [
            {"chunk_id": hit["chunk_id"], "page": hit["page"], "score": hit["score"], "score_type": hit["score_type"]}
            for hit in hits
        ],
    }


def main() -> None:  # noqa: PLR0915 -- Explicit phases keep live writes and restart-only verification reviewable.
    """Keep original corpus intact while recording actual upload/replay/update/restart evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("upload", "after-restart", "update", "after-update-restart"))
    phase = parser.parse_args().phase
    _ROOT.mkdir(parents=True, exist_ok=True)
    result_path = _ROOT / f"{phase}.json"
    if result_path.exists():
        raise SystemExit("Existing live evidence will not be overwritten")
    if not _INPUT.exists():
        writer = PdfWriter()
        writer.add_page(PdfReader(_PUBLIC_SOURCE).pages[0])
        writer.write(_INPUT)
    original = _INPUT.read_bytes()
    before = _database_snapshot(os.environ["WORKBENCH_DB_DSN"])
    intent_path = _ROOT / "intent.json"
    if not intent_path.exists():
        intent_path.write_text(
            json.dumps(
                {
                    "idempotency_key": uuid4().hex,
                    "database_before": before,
                    "public_source": "https://raw.githubusercontent.com/jsvine/pdfplumber/stable/examples/pdfs/ca-warn-report.pdf",
                    "public_original_sha256": hashlib.sha256(_PUBLIC_SOURCE.read_bytes()).hexdigest(),
                    "uploaded_scope": "first actual page only; full 16-page original is not qualified by this probe",
                    "source_sha256": hashlib.sha256(original).hexdigest(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    content = original
    with httpx.Client(
        base_url="http://127.0.0.1:8011", headers={"Origin": "http://127.0.0.1:4173"}, timeout=215, trust_env=False
    ) as client:
        capabilities = client.get("/api/v1/capabilities")
        capabilities.raise_for_status()
        assert capabilities.json()["pdf_ingestion"]["available"] is True
        if phase == "upload":
            response = _upload(client, original, key=intent["idempotency_key"])
            response.raise_for_status()
            result = response.json()
            assert result["status"] == "completed"
            replay = _upload(client, original, key=intent["idempotency_key"])
            replay.raise_for_status()
            assert replay.json()["source_version_id"] == result["source_version_id"]
        else:
            result = json.loads((_ROOT / "upload.json").read_text())["result"]
            if phase == "update":
                writer = PdfWriter()
                writer.add_page(PdfReader(io.BytesIO(original)).pages[0])
                writer.add_metadata({"/Title": "Audited public WARN report page one"})
                stream = io.BytesIO()
                writer.write(stream)
                content = stream.getvalue()
                (_ROOT / "metadata-updated-page-1.pdf").write_bytes(content)
                response = _upload(
                    client,
                    content,
                    key=uuid4().hex,
                    fields={
                        "source_id": result["source_id"],
                        "expected_active_version_id": result["source_version_id"],
                    },
                )
                response.raise_for_status()
                updated = response.json()
                assert updated["source_version_id"] != result["source_version_id"]
                result = updated
            elif phase == "after-update-restart":
                result = json.loads((_ROOT / "update.json").read_text())["result"]
                content = (_ROOT / "metadata-updated-page-1.pdf").read_bytes()
        validation = _verify(client, result, content)
        failures = []
        if phase == "upload":
            fields = {"source_id": result["source_id"], "expected_active_version_id": result["source_version_id"]}
            for invalid, expected in (
                (b"%PDF-1.7\ncorrupt", "PDF_CORRUPT"),
                ((_ROOT / "ca-warn-first-two-pages.pdf").read_bytes(), "TABLE_STRUCTURE_UNCERTAIN"),
            ):
                response = _upload(client, invalid, key=uuid4().hex, fields=fields)
                assert response.status_code == 400, response.text
                assert response.json()["error"]["code"] == expected
                failures.append({"code": expected, "status": response.status_code})
            _verify(client, result, content)
    after = _database_snapshot(os.environ["WORKBENCH_DB_DSN"])
    if phase == "update":
        # Replacement intentionally changes this source's active version only.
        untouched_before = {
            key: [row for row in rows if row.get("source_id") != result["source_id"]]
            for key, rows in before.items()
            if isinstance(rows, list)
        }
        untouched_after = {
            key: [row for row in rows if row.get("source_id") != result["source_id"]]
            for key, rows in after.items()
            if isinstance(rows, list)
        }
        _assert_preserved(untouched_before, untouched_after)
    else:
        _assert_preserved(before, after)
    _assert_sql_chunks(result, validation, after)
    evidence = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": phase,
        "result": result,
        "validation": validation,
        "failures": failures,
        "database_before": before,
        "database_after": after,
        "existing_corpus_preserved": True,
        "update_scope": "PDF title metadata only" if phase == "update" else None,
    }
    result_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "source_id": result["source_id"],
                "version_id": result["source_version_id"],
                "chunks": len(validation["chunks"]),
                "actual_table_body_rows": 36,
                "failures": failures,
                "existing_corpus_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    main()

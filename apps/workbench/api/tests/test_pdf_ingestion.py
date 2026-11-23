"""Candidate PDF adapter qualification through actual ASGI jobs and disposable PostgreSQL."""

import hashlib
import io
from pathlib import Path
from uuid import uuid4

import pytest
from pypdf import PdfReader, PdfWriter

from apps.workbench.api.chunking_adapters import count_tokens
from apps.workbench.api.tests.conftest import DisposableDatabase
from apps.workbench.api.tests.test_ingestion_routes import _DOCUMENTS, _search, _upload
from apps.workbench.api.tests.test_ingestion_routes import ingestion_repository as ingestion_repository
from apps.workbench.api.tests.test_python_ingestion import _client
from scripts.workbench_pdf_fixtures import pdf_bytes

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="function"),
    pytest.mark.usefixtures("ingestion_repository"),
]


async def test_pdf_upload_rows_pages_replay_restart_and_atomic_failure(disposable_database: DisposableDatabase) -> None:
    """Only actual committed page/table evidence may appear in the existing lexical results."""
    content = pdf_bytes(table=True, pages=2)
    key = uuid4().hex
    async with _client(disposable_database) as client:
        response = await _upload(
            client, content=content, filename="water-evidence.pdf", mime="application/pdf", key=key
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["status"] == "completed"
        detail = (await client.get(f"{_DOCUMENTS}/{result['source_id']}")).json()
        assert detail["parser"]["pdf_pages"] == 2
        assert detail["parser"]["visual_processing_status"] == "incomplete"
        assert detail["parser"]["original_evidence_status"] == "unavailable"
        assert "VISUAL_EVIDENCE_UNAVAILABLE" in detail["warnings"]
        chunks = (await client.get(f"{_DOCUMENTS}/{result['source_id']}/chunks", params={"limit": 100})).json()["items"]
        assert {chunk["page"] for chunk in chunks} == {1, 2}
        assert len(chunks) == result["chunk_count"]
        for chunk in chunks:
            metadata = chunk["metadata"]
            assert metadata["source_sha256"] == hashlib.sha256(content).hexdigest()
            assert metadata["length_tiktoken"] == count_tokens(chunk["content"]) <= 768
            assert metadata["page_number"] == chunk["page"]
            assert metadata["source_span_basis"] == "extracted_pdf_projection"
            assert "asset_id" not in metadata
        hits = (await _search(client, "Station2R8"))["results"]
        assert hits and hits[0]["source_id"] == result["source_id"]
        assert hits[0]["page"] == 2 and "2056" in hits[0]["content"]
        replay = await _upload(client, content=content, filename="water-evidence.pdf", mime="application/pdf", key=key)
        assert replay.status_code == 200 and replay.json()["source_version_id"] == result["source_version_id"]
        fields = {"source_id": result["source_id"], "expected_active_version_id": result["source_version_id"]}
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(content)))
        writer.encrypt("negative-test")
        stream = io.BytesIO()
        writer.write(stream)
        for invalid, expected in (
            (stream.getvalue(), "PDF_ENCRYPTED"),
            (pdf_bytes(scanned=True), "NO_EXTRACTABLE_TEXT"),
            (b"%PDF-1.7\ncorrupt", "PDF_CORRUPT"),
        ):
            refused = await _upload(
                client, content=invalid, filename="water-evidence.pdf", mime="application/pdf", fields=fields
            )
            assert refused.status_code == 400, refused.text
            assert refused.json()["error"]["code"] == expected
            active = (await client.get(f"{_DOCUMENTS}/{result['source_id']}")).json()
            assert active["active_version_id"] == result["source_version_id"]
    async with _client(disposable_database) as client:
        hits = (await _search(client, "Station2R8"))["results"]
        assert hits[0]["source_version_id"] == result["source_version_id"] and hits[0]["page"] == 2
        assert hits[0]["score_type"] == "postgres_ts_rank_cd"


async def test_mixed_figure_publication_preserves_json_geometry_and_incomplete_status(
    disposable_database: DisposableDatabase,
) -> None:
    """Detected pictures must publish valid JSON without inventing assets or diagram semantics."""
    async with _client(disposable_database) as client:
        response = await _upload(client, content=pdf_bytes(mixed=True), filename="mixed.pdf", mime="application/pdf")
        assert response.status_code == 201, response.text
        result = response.json()
        detail = (await client.get(f"{_DOCUMENTS}/{result['source_id']}")).json()
        parser = detail["parser"]
        assert parser["visual_region_count"] == 1
        assert parser["visual_processing_status"] == "incomplete"
        region = parser["visual_regions"][0]
        assert region["page"] == 1 and isinstance(region["heading_path"], list)
        assert region["evidence_status"] == "visual_evidence_unavailable"
        assert "asset_id" not in region and "arrows" not in region
        assert (await _search(client, "UNOBSERVED START"))["results"] == []


async def test_missing_pdf_assets_hide_capability_and_preserve_text_upload(
    disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An absent optional runtime is disclosed without disabling the existing text ingestion path."""
    monkeypatch.setenv("WORKBENCH_PDF_MODEL_DIRECTORY", str(tmp_path))
    async with _client(disposable_database) as client:
        capability = (await client.get("/api/v1/capabilities")).json()["pdf_ingestion"]
        assert capability["available"] is False and capability["ocr"] is False
        assert capability["original_evidence"] is False and capability["visual_understanding"] is False
        response = await _upload(
            client, content=b"ordinarytextstillavailable", filename="ordinary.txt", mime="text/plain"
        )
        assert response.status_code == 201, response.text


async def test_pdf_and_text_have_separate_transport_caps(disposable_database: DisposableDatabase) -> None:
    """A PDF candidate reaches binary validation above 1 MiB; text and global caps remain enforced."""
    async with _client(disposable_database) as client:
        response = await _upload(
            client, content=b"%PDF-1.7\n" + b"x" * 1_100_000, filename="invalid.pdf", mime="application/pdf"
        )
        assert response.status_code == 400 and response.json()["error"]["code"] == "PDF_CORRUPT"
        response = await _upload(client, content=b"x" * 1_100_000, filename="large.txt", mime="text/plain")
        assert response.status_code == 413
        response = await _upload(
            client, content=b"%PDF-1.7\n" + b"x" * 8_388_608, filename="large.pdf", mime="application/pdf"
        )
        assert response.status_code == 413


async def test_two_column_pdf_indexes_every_sentence_and_replays_the_same_version(
    disposable_database: DisposableDatabase,
) -> None:
    """The previously refused input publishes real page-scoped prose without synthetic table headers."""
    key = uuid4().hex
    content = pdf_bytes(two_columns=True)
    async with _client(disposable_database) as client:
        response = await _upload(client, content=content, filename="columns.pdf", mime="application/pdf", key=key)
        assert response.status_code == 201, response.text
        result = response.json()
        detail = (await client.get(f"{_DOCUMENTS}/{result['source_id']}")).json()
        assert detail["parser"]["parser_revision"] == "docling-pdf-r2"
        assert detail["parser"]["pdf_tables"] == 0
        assert "PDF_COLUMNS_PROJECTED_AS_TEXT" in detail["warnings"]
        chunks = (await client.get(f"{_DOCUMENTS}/{result['source_id']}/chunks", params={"limit": 100})).json()["items"]
        text = "\n".join(chunk["metadata"]["original_excerpt"] for chunk in chunks)
        assert all(chunk["page"] == 1 for chunk in chunks)
        for side in ("Left", "Right"):
            for index in range(12):
                assert f"{side} section observation {index}." in text
        assert not any(chunk["metadata"]["block_kind"] == "table" for chunk in chunks)
        hits = (await _search(client, "Right observation 11"))["results"]
        assert hits and hits[0]["source_id"] == result["source_id"] and hits[0]["page"] == 1
        replay = await _upload(client, content=content, filename="columns.pdf", mime="application/pdf", key=key)
        assert replay.status_code == 200 and replay.json()["source_version_id"] == result["source_version_id"]

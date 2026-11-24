"""PDF row/coordinate and visual-coverage contracts, including real isolated Docling execution."""

import hashlib
import io
from pathlib import Path

import pytest
from docling_core.types.doc import BoundingBox, CoordOrigin, ProvenanceItem
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from apps.workbench.chunking.chunking_adapters import count_tokens
from apps.workbench.chunking.chunking_profiles import ChunkingError, PdfChunkingProfile
from apps.workbench.chunking.pdf.pdf_chunking_adapter import _document, split_pdf_block
from apps.workbench.ingestion.upload_policy import upload_file_byte_limit
from apps.workbench.parsing.parser_registry import ParseErrorCode, ParsingError
from apps.workbench.parsing.pdf.pdf_assets import pdf_runtime_available
from apps.workbench.parsing.pdf.pdf_models import (
    PdfBlock,
    PdfBox,
    PdfCell,
    PdfDocument,
    PdfLimits,
    PdfPage,
    PdfVisualRegion,
)
from apps.workbench.parsing.pdf.pdf_parser import _PARSER_SLOT, _decode_result, extract_pdf
from apps.workbench.parsing.pdf.pdf_worker import _preflight, _project, _verify_numbers
from apps.workbench.parsing.pdf.pdf_worker import _table as _project_table
from scripts.workbench_pdf_fixtures import pdf_bytes


def _table(*, rows: int = 160, oversized: bool = False) -> PdfBlock:
    cells = []
    for row in range(rows):
        values = ("Station", "Volume litres") if row == 0 else (f"Station{row}", str(row * 7))
        for column, text in enumerate(values):
            cells.append(
                PdfCell(
                    text="x " * 2000 if oversized and row == 1 else text,
                    row_start=row,
                    row_end=row + 1,
                    column_start=column,
                    column_end=column + 1,
                    column_header=row == 0,
                )
            )
    return PdfBlock(
        block_id="table-1",
        page=2,
        kind="table",
        text="\n".join(cell.text for cell in cells),
        bbox=PdfBox(left=10.0, top=10.0, right=500.0, bottom=700.0),
        cells=tuple(cells),
        row_count=rows,
        column_count=2,
        caption="Audited water table",
        heading_path=("Water report",),
    )


@pytest.mark.parametrize("target,overlap", [(512, 64), (768, 0), (768, 64)])
def test_hybrid_chunker_preserves_full_table_rows_and_headers(target: int, overlap: int) -> None:
    """Each policy must retain every observed row and repeat its column context."""
    table = _table()
    children = split_pdf_block(table, profile=PdfChunkingProfile(target_size=target, overlap=overlap))
    rows: list[int] = []
    assert len(children) > 1
    for child in children:
        assert count_tokens(child.content) <= target
        assert "Station" in child.content and "Volume litres" in child.content
        assert table.caption is not None and table.caption in child.content
        assert child.row_start is not None and child.row_end is not None
        rows.extend(range(child.row_start, child.row_end))
        for cell in child.original_cells:
            assert cell.text in child.original_excerpt
    assert rows == list(range(1, table.row_count))


def test_indivisible_row_is_refused_without_truncation() -> None:
    """Splitting a row into disconnected columns cannot qualify as table preservation."""
    with pytest.raises(ChunkingError) as failure:
        split_pdf_block(_table(rows=3, oversized=True), profile=PdfChunkingProfile())
    assert failure.value.reason == "TABLE_OVERFLOW"


def test_overlap_cannot_cross_a_pdf_block_or_page() -> None:
    """Overlap is derived from the same observed prose block and separately budgeted."""
    block = _table().model_copy(
        update={
            "kind": "text",
            "cells": (),
            "row_count": 0,
            "column_count": 0,
            "text": "A verified sample is recorded. " * 200,
            "caption": None,
        }
    )
    children = split_pdf_block(block, profile=PdfChunkingProfile(target_size=512, overlap=64))
    assert len(children) > 1
    assert children[0].overlap_tokens == 0
    assert all(child.overlap_tokens <= 64 and count_tokens(child.content) <= 512 for child in children)
    assert "".join(child.original_excerpt for child in children).replace(" ", "") == block.text.replace(" ", "")


def test_table_cell_gaps_and_overlaps_are_rejected() -> None:
    """A nominal table is refused unless the observed cells cover it exactly once."""
    table = _table(rows=3)
    for cells in (table.cells[:-1], (*table.cells, table.cells[0])):
        with pytest.raises(ValidationError):
            PdfBlock.model_validate({**table.model_dump(), "cells": cells})


def test_pdf_limits_do_not_widen_text_uploads() -> None:
    """The larger binary allowance applies only to the PDF transport candidate."""
    assert upload_file_byte_limit() == 1_048_576
    assert upload_file_byte_limit(filename="report.pdf", declared_mime="application/pdf") == 8_388_608
    assert upload_file_byte_limit(filename="report.pdf", declared_mime="text/plain") == 1_048_576
    with pytest.raises(ValidationError):
        PdfLimits(max_bytes=8_388_609)


@pytest.mark.parametrize(
    "kind,code",
    [
        ("scan", ParseErrorCode.NO_EXTRACTABLE_TEXT),
        ("encrypted", ParseErrorCode.PDF_ENCRYPTED),
        ("pages", ParseErrorCode.PDF_TOO_LARGE),
        ("javascript", ParseErrorCode.PDF_UNSAFE_CONTENT),
        ("rotated", ParseErrorCode.PDF_LAYOUT_UNCERTAIN),
    ],
)
def test_real_pdf_preflight_negatives(kind: str, code: ParseErrorCode) -> None:
    """Unsafe or unsupported actual PDF bytes are refused before model loading."""
    content = pdf_bytes(scanned=kind == "scan", pages=2 if kind == "pages" else 1)
    limits = PdfLimits(max_pages=1) if kind == "pages" else PdfLimits()
    if kind in {"encrypted", "javascript", "rotated"}:
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(content)))
        if kind == "encrypted":
            writer.encrypt("test-password")
        elif kind == "javascript":
            writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
                {NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("untrusted program")}
            )
        else:
            writer.pages[0].rotate(90)
        output = io.BytesIO()
        writer.write(output)
        content = output.getvalue()
    with pytest.raises(ParsingError) as failure:
        _preflight(content, limits)
    assert failure.value.code is code


def test_worker_crash_and_protocol_errors_are_sanitized() -> None:
    """Only reviewed error codes escape the isolated parser protocol."""
    with pytest.raises(ParsingError) as failure:
        _decode_result(b"ERROR:private parser traceback", 0)
    assert failure.value.code is ParseErrorCode.PDF_CORRUPT
    with pytest.raises(ParsingError) as failure:
        _decode_result(b"", 101)
    assert failure.value.code is ParseErrorCode.PDF_RESOURCE_LIMIT


def test_one_parser_slot_refuses_parallel_work_without_waiting() -> None:
    """CPU-heavy parser concurrency has an explicit bounded refusal."""
    assert pdf_runtime_available()
    assert _PARSER_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(ParsingError) as failure:
            extract_pdf(b"%PDF-1.7")
        assert failure.value.code is ParseErrorCode.PDF_BUSY
    finally:
        _PARSER_SLOT.release()


def test_missing_models_disable_the_pdf_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dependency presence without provisioned assets grants no parsing capability."""
    monkeypatch.setenv("WORKBENCH_PDF_MODEL_DIRECTORY", str(tmp_path))
    assert not pdf_runtime_available()
    with pytest.raises(ParsingError) as failure:
        extract_pdf(b"%PDF-1.7")
    assert failure.value.code is ParseErrorCode.PARSER_UNAVAILABLE


def test_actual_parser_deadline_terminates_the_owned_child() -> None:
    """A real child with an insufficient wall budget cannot retain the only parser slot."""
    with pytest.raises(ParsingError) as failure:
        extract_pdf(pdf_bytes(), limits=PdfLimits(wall_seconds=1))
    assert failure.value.code is ParseErrorCode.PDF_PARSE_TIMEOUT
    assert _PARSER_SLOT.acquire(blocking=False)
    _PARSER_SLOT.release()


def test_actual_cpu_quota_terminates_the_owned_child() -> None:
    """CPU exhaustion is a bounded resource error rather than an uncontained parser process."""
    with pytest.raises(ParsingError) as failure:
        extract_pdf(pdf_bytes(table=True), limits=PdfLimits(cpu_seconds=1))
    assert failure.value.code is ParseErrorCode.PDF_RESOURCE_LIMIT


def test_continuation_data_dates_cannot_be_published_as_column_headers() -> None:
    """The real-report continuation failure is retained as an explicit header-role guard."""
    block = _table(rows=3)
    cells = tuple(
        cell.model_copy(update={"text": "07/17/2015"}) if cell.column_header else cell for cell in block.cells
    )
    document = _document(block.model_copy(update={"cells": cells}))
    with pytest.raises(ParsingError) as failure:
        _project_table(
            document.tables[0], common={"block_id": block.block_id, "page": 2, "bbox": block.bbox}, document=document
        )
    assert failure.value.code is ParseErrorCode.TABLE_STRUCTURE_UNCERTAIN


def test_projection_honors_tightened_cell_budget() -> None:
    """The deployment ceiling can be tightened without silently reverting to model defaults."""
    block = _table(rows=3).model_copy(update={"heading_path": (), "caption": None})
    document = _document(block)
    document.tables[0].prov.append(
        ProvenanceItem(
            page_no=1,
            charspan=(0, len(block.text)),
            bbox=BoundingBox(l=10.0, t=700.0, r=500.0, b=10.0, coord_origin=CoordOrigin.BOTTOMLEFT),
        )
    )
    with pytest.raises(ParsingError) as failure:
        _project(document, [PdfPage(number=1, width=600.0, height=800.0)], PdfLimits(max_cells=4))
    assert failure.value.code is ParseErrorCode.PDF_TOO_LARGE


def test_visual_regions_cannot_claim_links_or_graph_relations() -> None:
    """Geometry-only regions reject invented evidence IDs, arrows and chart data."""
    region = PdfVisualRegion(region_id="picture-1", page=1, bbox=PdfBox(left=10.0, top=10.0, right=50.0, bottom=50.0))
    assert region.processing_status == "incomplete"
    assert region.evidence_status == "visual_evidence_unavailable"
    for field in ("asset_id", "arrows", "chart_values"):
        with pytest.raises(ValidationError):
            PdfVisualRegion.model_validate({**region.model_dump(), field: "invented"})


@pytest.mark.parametrize("mixed", [False, True])
def test_real_isolated_docling_text_and_mixed_figure(mixed: bool) -> None:
    """Actual parser/model execution; no mocked projection or HTTP success is substituted."""
    content = pdf_bytes(mixed=mixed, table=not mixed)
    document = extract_pdf(content)
    assert document.source_sha256 == hashlib.sha256(content).hexdigest()
    assert len(document.pages) == 1 and document.blocks
    assert document.visual_processing_status == "incomplete"
    assert "PDF_VISUAL_COVERAGE_UNVERIFIED" in document.warning_codes
    assert document.original_evidence_status == "unavailable"
    assert all("UNOBSERVED START" not in block.text for block in document.blocks)
    if mixed:
        assert document.visual_regions
        assert all(region.page == 1 for region in document.visual_regions)
    else:
        table = next(block for block in document.blocks if block.kind == "table")
        assert table.row_count == 9 and table.column_count == 3
        assert "1007" in table.text and "1056" in table.text
    PdfDocument.model_validate_json(document.model_dump_json())


def test_real_two_column_sentences_retain_numeric_suffixes_and_column_geometry() -> None:
    """Native cell extraction retains the final 11 and publishes no invented table headers."""
    content = pdf_bytes(two_columns=True)
    document = extract_pdf(content)
    columns = [block for block in document.blocks if "PDF_COLUMNS_PROJECTED_AS_TEXT" in block.warning_codes]
    assert len(columns) == 2
    assert all(block.kind == "text" and not block.cells for block in columns)
    assert columns[0].bbox.right < columns[1].bbox.left
    for column, side in zip(columns, ("Left", "Right"), strict=True):
        assert column.text == " ".join(f"{side} section observation {index}." for index in range(12))
        assert column.page == 1
        assert "PDF_COLUMN_ORDER_GEOMETRIC" in column.warning_codes
    assert not any(block.kind == "table" for block in document.blocks)


@pytest.mark.parametrize(
    "original,projected",
    [
        ("First 12, second 34.", "First 13, second 24."),
        ("Measured 3.14 litres.", "Measured 31.4 litres."),
        ("Left 11. Right 11.", "Left 11. Right."),
    ],
)
def test_numeric_coverage_refuses_missing_or_reassembled_numbers(original: str, projected: str) -> None:
    """Matching a bag of digits is insufficient when complete numbers or decimal positions changed."""
    block = PdfBlock(
        block_id="numbers",
        page=1,
        kind="text",
        text=projected,
        bbox=PdfBox(left=10.0, top=10.0, right=100.0, bottom=50.0),
    )
    with pytest.raises(ParsingError) as failure:
        _verify_numbers((block,), [original])
    assert failure.value.reason == "PDF_NUMERIC_COVERAGE_MISMATCH"

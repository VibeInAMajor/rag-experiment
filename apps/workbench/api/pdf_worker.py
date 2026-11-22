"""Private data-only PDF worker; never installed as a server route or command selected by an upload."""

import hashlib
import io
import logging
import math
import os
import socket
import sys
import time
import unicodedata
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

from apps.workbench.api.parser_registry import ParseErrorCode, ParsingError
from apps.workbench.api.pdf_assets import PdfAssetsUnavailable, pdf_assets_revision, verify_pdf_assets
from apps.workbench.api.pdf_models import PdfBlock, PdfBox, PdfCell, PdfDocument, PdfLimits, PdfPage

_FORBIDDEN = frozenset(
    {
        "/JS",
        "/JavaScript",
        "/OpenAction",
        "/AA",
        "/EmbeddedFiles",
        "/RichMedia",
        "/XFA",
        "/Launch",
        "/SubmitForm",
        "/ImportData",
    }
)


def _no_network(*_args: Any, **_kwargs: Any) -> Any:
    raise OSError("PDF_NETWORK_DISABLED")


def _restrict_runtime(limits: PdfLimits) -> None:
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    socket.socket.connect = _no_network
    socket.socket.connect_ex = _no_network
    socket.create_connection = _no_network
    socket.getaddrinfo = _no_network
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))


def _check_catalog(reader: Any) -> None:
    from pypdf.generic import DictionaryObject, IndirectObject, StreamObject

    pending = [reader.trailer["/Root"]]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, IndirectObject):
            item = item.get_object()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if len(seen) > 100_000:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        if isinstance(item, DictionaryObject):
            if (
                _FORBIDDEN.intersection(item)
                or item.get("/S") in {"/JavaScript", "/Launch", "/GoToR", "/SubmitForm"}
                or item.get("/Type") == "/Filespec"
                or isinstance(item, StreamObject)
                and "/F" in item
            ):
                raise ParsingError(ParseErrorCode.PDF_UNSAFE_CONTENT)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _preflight(content: bytes, limits: PdfLimits) -> tuple[list[PdfPage], list[str], tuple[str, ...]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content), strict=True)
    if reader.is_encrypted:
        raise ParsingError(ParseErrorCode.PDF_ENCRYPTED)
    if not 1 <= len(reader.pages) <= limits.max_pages:
        raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    _check_catalog(reader)
    pages: list[PdfPage] = []
    texts: list[str] = []
    notices: list[str] = []
    for number, page in enumerate(reader.pages, 1):
        pages.append(PdfPage(number=number, width=float(page.mediabox.width), height=float(page.mediabox.height)))
        stream = page.get_contents()
        if stream is not None and len(stream.get_data()) > 8_388_608:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        text = page.extract_text() or ""
        if len(text) > limits.max_characters:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        if not text.strip():
            resources = page.get("/Resources", {}).get_object()
            objects = resources.get("/XObject", {}).get_object() if "/XObject" in resources else {}
            if any(obj.get_object().get("/Subtype") == "/Image" for obj in objects.values()):
                raise ParsingError(ParseErrorCode.NO_EXTRACTABLE_TEXT)
            notices.append("PDF_PAGE_WITHOUT_TEXT")
        texts.append(text)
    if not any(text.strip() for text in texts):
        raise ParsingError(ParseErrorCode.NO_EXTRACTABLE_TEXT)
    return pages, texts, tuple(dict.fromkeys(notices))


def _box(provenance: Any, page: PdfPage) -> PdfBox:
    box = provenance.bbox.to_top_left_origin(page_height=page.height)
    return PdfBox(
        left=max(0.0, float(box.l)),
        top=max(0.0, float(box.t)),
        right=min(page.width, float(box.r)),
        bottom=min(page.height, float(box.b)),
    )


def _table(item: Any, *, common: dict[str, Any], document: Any) -> PdfBlock:
    cells = tuple(
        PdfCell(
            text=cell.text,
            row_start=cell.start_row_offset_idx,
            row_end=cell.end_row_offset_idx,
            column_start=cell.start_col_offset_idx,
            column_end=cell.end_col_offset_idx,
            column_header=cell.column_header,
            row_header=cell.row_header,
        )
        for cell in item.data.table_cells
    )
    caption = " ".join(reference.resolve(document).text for reference in item.captions) or None
    if item.data.num_rows < 2 or item.data.num_cols < 2:
        raise ParsingError(ParseErrorCode.TABLE_STRUCTURE_UNCERTAIN)
    text = "\n".join(cell.text for cell in sorted(cells, key=lambda cell: (cell.row_start, cell.column_start)))
    return PdfBlock(
        **common,
        kind="table",
        text=text,
        cells=cells,
        caption=caption,
        row_count=item.data.num_rows,
        column_count=item.data.num_cols,
        warning_codes=("TABLE_CONFIDENCE_NOT_REPORTED",),
    )


def _project(document: Any, pages: list[PdfPage], limits: PdfLimits) -> tuple[PdfBlock, ...]:
    from docling_core.types.doc import ContentLayer, TableItem, TextItem

    blocks: list[PdfBlock] = []
    headings: list[str] = []
    for item, _depth in document.iterate_items(included_content_layers=set(ContentLayer)):
        if not isinstance(item, (TableItem, TextItem)):
            continue
        if len(item.prov) != 1 or not 1 <= item.prov[0].page_no <= len(pages):
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN)
        page = pages[item.prov[0].page_no - 1]
        label = str(item.label.value)
        if isinstance(item, TextItem) and label in {"section_header", "title"}:
            level = min(6, max(1, getattr(item, "level", 1)))
            headings = headings[: level - 1] + [item.text]
        common = dict(
            block_id=item.self_ref, page=page.number, bbox=_box(item.prov[0], page), heading_path=tuple(headings)
        )
        if isinstance(item, TableItem):
            block = _table(item, common=common, document=document)
        else:
            if not item.text.strip():
                continue
            kind = "heading" if label in {"section_header", "title"} else "caption" if label == "caption" else "text"
            block = PdfBlock(**common, kind=kind, text=item.text)
        blocks.append(block)
        if len(blocks) > limits.max_blocks or sum(len(b.text) for b in blocks) > limits.max_characters:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    return tuple(blocks)


def _digits(text: str) -> Counter[str]:
    return Counter(character for character in unicodedata.normalize("NFKC", text) if character.isdecimal())


def _verify_numbers(blocks: tuple[PdfBlock, ...], originals: list[str]) -> None:
    for number, text in enumerate(originals, 1):
        projected = "\n".join(block.text for block in blocks if block.page == number)
        if _digits(projected) != _digits(text):
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_NUMERIC_COVERAGE_MISMATCH")


def _convert(content: bytes, root: Path, limits: PdfLimits) -> PdfDocument:
    started = time.perf_counter()
    pages, original_text, notices = _preflight(content, limits)
    verify_pdf_assets(root)
    import psutil
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        artifacts_path=root,
        do_ocr=False,
        do_table_structure=True,
        document_timeout=limits.wall_seconds - 10,
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=4),
        enable_remote_services=False,
        allow_external_plugins=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
    )
    options.table_structure_options.mode = TableFormerMode.FAST
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    result = converter.convert(
        DocumentStream(name="input.pdf", stream=io.BytesIO(content)),
        max_num_pages=limits.max_pages,
        max_file_size=limits.max_bytes,
        raises_on_error=False,
    )
    if result.status != ConversionStatus.SUCCESS or set(result.document.pages) != {page.number for page in pages}:
        raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN)
    for confidence in result.confidence.pages.values():
        if math.isfinite(confidence.layout_score) and confidence.layout_score < 0.5:
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN)
    blocks = _project(result.document, pages, limits)
    _verify_numbers(blocks, original_text)
    process = psutil.Process()
    memory = process.memory_info()
    cpu = process.cpu_times()
    return PdfDocument(
        source_sha256=hashlib.sha256(content).hexdigest(),
        pages=tuple(pages),
        blocks=blocks,
        warning_codes=notices,
        parser_seconds=time.perf_counter() - started,
        peak_memory_bytes=getattr(memory, "peak_wset", memory.rss),
        cpu_seconds=cpu.user + cpu.system,
        assets_revision=pdf_assets_revision(),
    )


def main() -> None:
    """Consume only a bounded PDF stream after the parent has installed OS quotas."""
    limits = PdfLimits()
    _restrict_runtime(limits)
    try:
        content = sys.stdin.buffer.read(limits.max_bytes + 1)
        if len(content) > limits.max_bytes or not content.startswith(b"%PDF-"):
            raise ParsingError(ParseErrorCode.PDF_CORRUPT)
        document = _convert(content, Path(sys.argv[1]), limits)
        payload = document.model_dump_json().encode("utf-8")
        if len(payload) > 8_388_608:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        sys.stdout.buffer.write(payload)
    except ParsingError as error:
        sys.stdout.buffer.write(b"ERROR:" + error.code.value.encode("ascii"))
    except PdfAssetsUnavailable:
        sys.stdout.buffer.write(b"ERROR:PARSER_UNAVAILABLE")
    except MemoryError:
        sys.stdout.buffer.write(b"ERROR:PDF_RESOURCE_LIMIT")
    except Exception:
        sys.stdout.buffer.write(b"ERROR:PDF_CORRUPT")


if __name__ == "__main__":
    main()

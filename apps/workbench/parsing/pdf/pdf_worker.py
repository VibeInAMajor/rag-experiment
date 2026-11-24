"""Private data-only PDF worker; never installed as a server route or command selected by an upload."""

import hashlib
import io
import logging
import math
import re
import socket
import sys
import time
import unicodedata
import warnings
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from apps.workbench.parsing.parser_registry import ParseErrorCode, ParsingError
from apps.workbench.parsing.pdf.pdf_assets import PdfAssetsUnavailable, pdf_assets_revision, verify_pdf_assets
from apps.workbench.parsing.pdf.pdf_models import (
    PdfBlock,
    PdfBox,
    PdfCell,
    PdfDocument,
    PdfLimits,
    PdfPage,
    PdfVisualRegion,
)

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
    for method in ("connect", "connect_ex"):
        setattr(socket.socket, method, _no_network)
    socket.create_connection = _no_network
    socket.getaddrinfo = _no_network
    if sys.platform != "win32":
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
        if page.rotation != 0 or page.cropbox != page.mediabox or tuple(page.mediabox.lower_left) != (0, 0):
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_PAGE_COORDINATES_UNSUPPORTED")
        pages.append(PdfPage(number=number, width=float(page.mediabox.width), height=float(page.mediabox.height)))
        stream = page.get_contents()
        if stream is not None and len(stream.get_data()) > 8_388_608:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        text = page.extract_text() or ""
        if len(text) > limits.max_characters:
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
        if not text.strip():
            resource_reference = page.get("/Resources")
            resources = resource_reference.get_object() if resource_reference is not None else {}
            object_reference = resources.get("/XObject")
            objects = object_reference.get_object() if object_reference is not None else {}
            if any(obj.get_object().get("/Subtype") == "/Image" for obj in objects.values()):
                raise ParsingError(ParseErrorCode.NO_EXTRACTABLE_TEXT)
            notices.append("PDF_PAGE_WITHOUT_TEXT")
        texts.append(text)
    if not any(text.strip() for text in texts):
        raise ParsingError(ParseErrorCode.NO_EXTRACTABLE_TEXT)
    return pages, texts, tuple(dict.fromkeys(notices))


def _box(bounding_box: Any, page: PdfPage) -> PdfBox:
    box = bounding_box.to_top_left_origin(page_height=page.height)
    return PdfBox(
        left=max(0.0, float(box.l)),
        top=max(0.0, float(box.t)),
        right=min(page.width, float(box.r)),
        bottom=min(page.height, float(box.b)),
    )


def _text_columns(item: Any, *, common: dict[str, Any], page: PdfPage) -> tuple[PdfBlock, ...]:
    # A headerless comparison and prose columns can look identical to the layout model.
    # Preserve their observed sentences without publishing inferred row/header relationships.
    if item.data.num_cols != 2 or item.data.num_rows < 3 or item.captions:
        return ()
    cells = item.data.table_cells
    if len(cells) != item.data.num_rows * 2 or {
        (cell.start_row_offset_idx, cell.start_col_offset_idx) for cell in cells
    } != {(row, column) for row in range(item.data.num_rows) for column in range(2)}:
        return ()
    columns: list[list[tuple[PdfBox, str]]] = [[], []]
    for cell in cells:
        if (
            cell.end_row_offset_idx != cell.start_row_offset_idx + 1
            or cell.end_col_offset_idx != cell.start_col_offset_idx + 1
            or cell.bbox is None
            or len(cell.text.split()) < 4
            or len(cell.text) > 32_768
            or not cell.text.rstrip().endswith((".", "!", "?"))
        ):
            return ()
        columns[cell.start_col_offset_idx].append((_box(cell.bbox, page), cell.text))
    if min(box.left for box, _text in columns[1]) - max(box.right for box, _text in columns[0]) < 12:
        return ()
    projected = []
    for index, column in enumerate(columns):
        ordered = sorted(column, key=lambda pair: pair[0].top)
        if any(first[0].bottom > second[0].top + 1 for first, second in pairwise(ordered)):
            return ()
        projected.append(
            PdfBlock(
                **{
                    **common,
                    "block_id": f"{item.self_ref}:column-{index + 1}",
                    "bbox": PdfBox(
                        left=min(box.left for box, _text in ordered),
                        top=min(box.top for box, _text in ordered),
                        right=max(box.right for box, _text in ordered),
                        bottom=max(box.bottom for box, _text in ordered),
                    ),
                },
                kind="text",
                text=" ".join(text for _bounds, text in ordered),
                warning_codes=("PDF_COLUMNS_PROJECTED_AS_TEXT", "PDF_COLUMN_ORDER_GEOMETRIC"),
            )
        )
    return tuple(projected)


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
    date_headers = [
        cell
        for cell in cells
        if cell.column_header and re.fullmatch(r"\d{1,4}[./-]\d{1,2}[./-]\d{1,4}", cell.text.strip())
    ]
    if len(date_headers) >= 2:
        # Continuation pages can mislabel a complete data row as column headers.
        # Without qualified cross-page header evidence, do not manufacture that relationship.
        raise ParsingError(ParseErrorCode.TABLE_STRUCTURE_UNCERTAIN, reason="PDF_TABLE_HEADER_ROLES_UNCERTAIN")
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
    observed_cells = 0
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
        common = {
            "block_id": item.self_ref,
            "page": page.number,
            "bbox": _box(item.prov[0].bbox, page),
            "heading_path": tuple(headings),
        }
        if isinstance(item, TableItem):
            observed_cells += len(item.data.table_cells)
            if observed_cells > limits.max_cells:
                raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
            column_blocks = _text_columns(item, common=common, page=page)
            projected = column_blocks or (_table(item, common=common, document=document),)
        else:
            if not item.text.strip():
                continue
            kind: Literal["heading", "caption", "text"] = (
                "heading" if label in {"section_header", "title"} else "caption" if label == "caption" else "text"
            )
            projected = (PdfBlock(**common, kind=kind, text=item.text),)
        blocks.extend(projected)
        if (
            len(blocks) > limits.max_blocks
            or sum(len(b.text) for b in blocks) > limits.max_characters
            or sum(len(b.cells) for b in blocks) > limits.max_cells
        ):
            raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    return tuple(blocks)


def _visual_regions(document: Any, pages: list[PdfPage], limits: PdfLimits) -> tuple[PdfVisualRegion, ...]:
    from docling_core.types.doc import ContentLayer, PictureItem

    regions: list[PdfVisualRegion] = []
    for item, _depth in document.iterate_items(included_content_layers=set(ContentLayer)):
        if not isinstance(item, PictureItem):
            continue
        for index, provenance in enumerate(item.prov):
            if not 1 <= provenance.page_no <= len(pages):
                raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN)
            regions.append(
                PdfVisualRegion(
                    region_id=f"{item.self_ref}:{index}",
                    page=provenance.page_no,
                    bbox=_box(provenance.bbox, pages[provenance.page_no - 1]),
                    caption=" ".join(ref.resolve(document).text for ref in item.captions) or None,
                )
            )
            if len(regions) > limits.max_blocks:
                raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    return tuple(regions)


def _digits(text: str) -> Counter[str]:
    return Counter(character for character in unicodedata.normalize("NFKC", text) if character.isdecimal())


def _numbers(text: str) -> Counter[str]:
    return Counter(re.findall(r"\d+(?:[.,]\d+)*", unicodedata.normalize("NFKC", text)))


def _verify_numbers(blocks: tuple[PdfBlock, ...], originals: list[str]) -> None:
    for number, text in enumerate(originals, 1):
        projected = "\n".join(block.text for block in blocks if block.page == number)
        if _digits(projected) != _digits(text) or _numbers(projected) != _numbers(text):
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_NUMERIC_COVERAGE_MISMATCH")


def _layout_document(content: bytes, *, options: Any, pages: list[PdfPage], limits: PdfLimits) -> Any:
    from docling.datamodel.base_models import ConversionStatus, DocumentStream, InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

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
    return result.document


def _recover_column_blocks(
    blocks: tuple[PdfBlock, ...], *, document: Any, candidates: set[str], pages: list[PdfPage], limits: PdfLimits
) -> tuple[PdfBlock, ...]:
    if sum(len(item.data.table_cells) for item in document.tables) > limits.max_cells:
        raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    tables = {item.self_ref: item for item in document.tables}
    recovered: list[PdfBlock] = []
    for block in blocks:
        if block.block_id not in candidates:
            recovered.append(block)
            continue
        item = tables.get(block.block_id)
        if item is None or len(item.prov) != 1 or item.prov[0].page_no != block.page:
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_COLUMN_RECOVERY_PROVENANCE")
        page = pages[block.page - 1]
        if _box(item.prov[0].bbox, page) != block.bbox:
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_COLUMN_RECOVERY_GEOMETRY")
        columns = _text_columns(
            item,
            common={
                "block_id": block.block_id,
                "page": block.page,
                "bbox": block.bbox,
                "heading_path": block.heading_path,
            },
            page=page,
        )
        if not columns:
            raise ParsingError(ParseErrorCode.PDF_LAYOUT_UNCERTAIN, reason="PDF_COLUMN_RECOVERY_UNQUALIFIED")
        recovered.extend(columns)
    if len(recovered) > limits.max_blocks or sum(len(block.text) for block in recovered) > limits.max_characters:
        raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    return tuple(recovered)


def _convert(content: bytes, root: Path, limits: PdfLimits) -> PdfDocument:
    started = time.perf_counter()
    pages, original_text, notices = _preflight(content, limits)
    verify_pdf_assets(root)
    import psutil
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, TableStructureOptions

    options = PdfPipelineOptions(
        artifacts_path=root,
        do_ocr=False,
        do_table_structure=True,
        document_timeout=max(0.1, limits.wall_seconds - 10),
        accelerator_options=AcceleratorOptions(device="cpu", num_threads=4),
        enable_remote_services=False,
        allow_external_plugins=False,
        do_picture_classification=False,
        do_picture_description=False,
        do_code_enrichment=False,
        do_formula_enrichment=False,
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=True),
    )
    document = _layout_document(content, options=options, pages=pages, limits=limits)
    blocks = _project(document, pages, limits)
    try:
        _verify_numbers(blocks, original_text)
    except ParsingError as error:
        candidates = {
            item.self_ref
            for item in document.tables
            if item.data.num_cols == 2 and item.data.num_rows >= 3 and not item.captions
        }
        candidates.intersection_update(block.block_id for block in blocks if block.kind == "table")
        if error.reason != "PDF_NUMERIC_COVERAGE_MISMATCH" or not candidates:
            raise
        recovery_options = options.model_copy(
            update={
                "table_structure_options": TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=False),
                "document_timeout": max(0.1, limits.wall_seconds - (time.perf_counter() - started) - 10),
            }
        )
        recovered_document = _layout_document(content, options=recovery_options, pages=pages, limits=limits)
        blocks = _recover_column_blocks(
            blocks, document=recovered_document, candidates=candidates, pages=pages, limits=limits
        )
        _verify_numbers(blocks, original_text)
        notices = (*notices, "PDF_NATIVE_CELL_RECOVERY")
    process = psutil.Process()
    memory = process.memory_info()
    cpu = process.cpu_times()
    return PdfDocument(
        source_sha256=hashlib.sha256(content).hexdigest(),
        pages=tuple(pages),
        blocks=blocks,
        warning_codes=tuple(
            dict.fromkeys(
                (
                    *notices,
                    "PDF_VISUAL_COVERAGE_UNVERIFIED",
                    "VISUAL_UNDERSTANDING_UNAVAILABLE",
                    "VISUAL_EVIDENCE_UNAVAILABLE",
                )
            )
        ),
        parser_seconds=time.perf_counter() - started,
        peak_memory_bytes=getattr(memory, "peak_wset", memory.rss),
        cpu_seconds=cpu.user + cpu.system,
        assets_revision=pdf_assets_revision(),
        visual_regions=_visual_regions(document, pages, limits),
    )


def _payload(content: bytes, root: Path, limits: PdfLimits) -> bytes:
    if len(content) > limits.max_bytes or not content.startswith(b"%PDF-"):
        raise ParsingError(ParseErrorCode.PDF_CORRUPT)
    document = _convert(content, root, limits)
    payload = document.model_dump_json().encode("utf-8")
    if len(payload) > 8_388_608:
        raise ParsingError(ParseErrorCode.PDF_TOO_LARGE)
    return payload


def main() -> None:
    """Consume only a bounded PDF stream after the parent has installed OS quotas."""
    limits = PdfLimits.model_validate_json(sys.argv[2])
    _restrict_runtime(limits)
    try:
        content = sys.stdin.buffer.read(limits.max_bytes + 1)
        sys.stdout.buffer.write(_payload(content, Path(sys.argv[1]), limits))
    except ParsingError as error:
        sys.stdout.buffer.write(b"ERROR:" + error.code.value.encode("ascii"))
    except PdfAssetsUnavailable:
        sys.stdout.buffer.write(b"ERROR:PARSER_UNAVAILABLE")
    except MemoryError:
        sys.stdout.buffer.write(b"ERROR:PDF_RESOURCE_LIMIT")
    except ValidationError:
        sys.stdout.buffer.write(b"ERROR:PDF_LAYOUT_UNCERTAIN")
    except Exception:
        sys.stdout.buffer.write(b"ERROR:PDF_CORRUPT")


if __name__ == "__main__":
    main()

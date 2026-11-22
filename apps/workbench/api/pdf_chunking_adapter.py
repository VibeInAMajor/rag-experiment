"""Explicit Docling HybridChunker serialization and row-preserving child verification."""

from dataclasses import dataclass
from typing import Any

from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.serializer.base import BaseDocSerializer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling_core.types.doc import DocItemLabel, DoclingDocument, TableCell, TableData, TableItem

from apps.workbench.api.chunking_adapters import count_tokens
from apps.workbench.api.chunking_profiles import ChunkingError, ChunkingErrorCode, PdfChunkingProfile
from apps.workbench.api.pdf_models import PdfBlock, PdfCell


class _OrdinaryTokenizer(BaseTokenizer):
    max_tokens: int

    def count_tokens(self, text: str) -> int:
        """Use the app's pinned ordinary-text o200k counter, including special-token spellings."""
        return count_tokens(text)

    def get_max_tokens(self) -> int:
        """Return the declared working-token ceiling, separate from native model admission."""
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        """semchunk accepts the same exact token-count callable used for final verification."""
        return count_tokens


class _MarkdownProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc: DoclingDocument) -> BaseDocSerializer:
        """Avoid the default triplet table serializer, which loses physical row segmentation."""
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


@dataclass(frozen=True)
class PdfChild:
    """Retrieval representation and original excerpt are deliberately distinct."""

    content: str
    original_excerpt: str
    source_start: int
    source_end: int
    overlap_tokens: int = 0
    row_start: int | None = None
    row_end: int | None = None
    table_headers: tuple[str, ...] = ()
    original_cells: tuple[PdfCell, ...] = ()


def _chunker(max_tokens: int) -> HybridChunker:
    return HybridChunker(tokenizer=_OrdinaryTokenizer(max_tokens=max_tokens), serializer_provider=_MarkdownProvider(),
                         merge_peers=False, repeat_table_header=True, omit_header_on_overflow=False)


def _document(block: PdfBlock) -> DoclingDocument:
    document = DoclingDocument(name="verified-page-block")
    for index, heading in enumerate(block.heading_path, 1):
        document.add_heading(text=heading, level=index)
    if block.kind != "table":
        document.add_text(label=DocItemLabel.TEXT, text=block.text)
        return document
    cells = [TableCell(
        text=cell.text, start_row_offset_idx=cell.row_start, end_row_offset_idx=cell.row_end,
        start_col_offset_idx=cell.column_start, end_col_offset_idx=cell.column_end,
        row_span=cell.row_end-cell.row_start, col_span=cell.column_end-cell.column_start,
        column_header=cell.column_header, row_header=cell.row_header,
    ) for cell in block.cells]
    caption = document.add_text(label=DocItemLabel.CAPTION, text=block.caption) if block.caption else None
    document.add_table(data=TableData(table_cells=cells, num_rows=block.row_count, num_cols=block.column_count),
                       caption=caption)
    return document


def _table_chunks(block: PdfBlock, profile: PdfChunkingProfile) -> tuple[PdfChild, ...]:
    document = _document(block)
    serializer = _MarkdownProvider().get_serializer(document)
    whole_chunker = _chunker(1_000_000)
    whole = next((chunk for chunk in whole_chunker.chunk(document)
                  if any(isinstance(item, TableItem) for item in chunk.meta.doc_items)), None)
    if whole is None:
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_NOT_SERIALIZED")
    headers, rows = serializer.table_serializer.get_header_and_body_lines(table_text=whole.text)
    if not headers or not rows:
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_HEADER_UNAVAILABLE")
    header = "".join(headers)
    heading_prefix = "\n".join(block.heading_path) + "\n" if block.heading_path else ""
    caption_prefix = block.caption + "\n" if block.caption else ""
    if any(count_tokens(heading_prefix+caption_prefix+header+row) > profile.target_size for row in rows):
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="TABLE_OVERFLOW")
    header_rows = {row for cell in block.cells if cell.column_header for row in range(cell.row_start,cell.row_end)}
    if not header_rows or header_rows != set(range(max(header_rows)+1)):
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_HEADER_UNCERTAIN")
    first_body_row = len(header_rows)
    if len(rows) != block.row_count-first_body_row:
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_ROW_SERIALIZATION")
    result: list[PdfChild] = []
    cursor = 0
    chunker = _chunker(profile.target_size)
    for chunk in chunker.chunk(document):
        if not any(isinstance(item, TableItem) for item in chunk.meta.doc_items):
            continue
        piece_headers, piece_rows = serializer.table_serializer.get_header_and_body_lines(table_text=chunk.text)
        if piece_headers != headers or rows[cursor:cursor+len(piece_rows)] != piece_rows or not piece_rows:
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_ROW_LOSS")
        start, end = first_body_row+cursor, first_body_row+cursor+len(piece_rows)
        content = chunker.contextualize(chunk)
        if block.caption and block.caption not in content:
            content = block.caption + "\n" + content
        if count_tokens(content) > profile.target_size:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="TABLE_OVERFLOW")
        cells = tuple(cell for cell in block.cells if cell.row_start < end and cell.row_end > start)
        original = "\n".join(cell.text for cell in sorted(cells,key=lambda cell:(cell.row_start,cell.column_start)))
        result.append(PdfChild(content=content, original_excerpt=original, source_start=0, source_end=len(block.text),
                               row_start=start, row_end=end, table_headers=tuple(headers), original_cells=cells))
        cursor += len(piece_rows)
    if cursor != len(rows):
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TABLE_ROW_LOSS")
    return tuple(result)


def _prose_chunks(block: PdfBlock, profile: PdfChunkingProfile) -> tuple[PdfChild, ...]:
    document = _document(block)
    chunker = _chunker(profile.target_size-profile.overlap)
    result: list[PdfChild] = []
    cursor = 0
    previous = ""
    for chunk in chunker.chunk(document):
        body = chunk.text
        if not body.strip():
            continue
        start = block.text.find(body, cursor)
        if start < 0 or block.text[cursor:start].strip():
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TEXT_SOURCE_CONFLICT")
        end = start+len(body)
        tail = previous
        while tail and count_tokens(tail) > profile.overlap:
            tail = tail[1:]
        content = chunker.contextualize(chunk)
        if tail:
            prefix_length = len(content)-len(body)
            content = content[:prefix_length]+tail+"\n\n"+body
        if count_tokens(content) > profile.target_size:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PDF_CONTEXT_OVERFLOW")
        result.append(PdfChild(content=content, original_excerpt=body, source_start=start, source_end=end,
                               overlap_tokens=count_tokens(tail) if tail else 0))
        cursor, previous = end, body
    if not result or block.text[cursor:].strip():
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PDF_TEXT_COVERAGE")
    return tuple(result)


def split_pdf_block(block: PdfBlock, *, profile: PdfChunkingProfile) -> tuple[PdfChild, ...]:
    """Apply qualified HybridChunker settings and verify exact text or complete native table rows."""
    return _table_chunks(block, profile) if block.kind == "table" else _prose_chunks(block, profile)

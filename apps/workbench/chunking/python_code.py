"""Lossless Python chunks through the pinned Haystack splitters."""

import io
from dataclasses import dataclass
from math import ceil

from apps.workbench.chunking.chunking_profiles import ChunkingError, ChunkingErrorCode, PythonChunkingProfile
from apps.workbench.parsing.python_code import PythonSymbol
from haystack import Document
from haystack.components.preprocessors import DocumentSplitter, PythonCodeSplitter


@dataclass(frozen=True)
class PythonSpan:
    """An exact source slice with truthful per-piece provenance."""

    start: int
    end: int
    start_line: int
    end_line: int
    unit_kinds: tuple[str, ...]
    symbols: tuple[PythonSymbol, ...]
    parent_start: int
    parent_end: int
    secondary_split: bool
    secondary_split_index: int
    secondary_split_total: int
    overlap_lines: int


def split_python(
    text: str, *, symbols: tuple[PythonSymbol, ...], profile: PythonChunkingProfile
) -> tuple[PythonSpan, ...]:
    """Use public splitter output, then verify exact slices and bound oversized units by physical lines."""
    # The upstream secondary path logs source identifiers and copies whole-unit line ranges.
    # Disable that path within the 1 MiB admission bound; reuse DocumentSplitter below instead.
    splitter = PythonCodeSplitter(
        min_effective_lines=1,
        max_effective_lines=profile.target_size,
        expected_chars_per_line=profile.expected_chars_per_line,
        oversized_factor=1_000_000,
        strip_docstrings=False,
        preserve_class_definition=False,
    )
    try:
        documents = splitter.run(documents=[Document(content=text)])["documents"]
    except (SyntaxError, RecursionError, ValueError):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PYTHON_SPLIT_FAILED") from None
    if len(documents) > profile.max_chunks:
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PYTHON_CHUNKS")
    lines = io.StringIO(text, newline="").readlines()
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    line_positions = {offset: index + 1 for index, offset in enumerate(offsets)}
    spans: list[PythonSpan] = []
    cursor = 0
    for document in documents:
        content = document.content or ""
        start, end = cursor, cursor + len(content)
        if not content or not text.startswith(content, start):
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PYTHON_SOURCE_CONFLICT")
        secondary = (
            len(content) > profile.hard_character_limit
            or ceil(len(content) / profile.expected_chars_per_line) > profile.target_size * profile.oversized_factor
        )
        pieces = (
            DocumentSplitter(
                split_by="line",
                split_length=profile.secondary_split_length,
                split_overlap=profile.secondary_split_overlap,
            ).run(documents=[Document(content=content)])["documents"]
            if secondary
            else [document]
        )
        previous_end = start
        for index, piece in enumerate(pieces):
            body = piece.content or ""
            relative = piece.meta.get("split_idx_start", 0) if secondary else 0
            piece_start, piece_end = start + relative, start + relative + len(body)
            if (
                not body
                or text[piece_start:piece_end] != body
                or piece_end > end
                or piece_start not in line_positions
                or (piece_start > previous_end and text[previous_end:piece_start].strip())
            ):
                raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PYTHON_SECONDARY_CONFLICT")
            start_line = line_positions[piece_start]
            end_line = start_line + len(io.StringIO(body, newline="").readlines()) - 1
            related = tuple(
                symbol for symbol in symbols if symbol.start_line <= end_line and symbol.end_line >= start_line
            )
            spans.append(
                PythonSpan(
                    piece_start,
                    piece_end,
                    start_line,
                    end_line,
                    tuple(document.meta["unit_kinds"]),
                    related,
                    start,
                    end,
                    secondary,
                    index,
                    len(pieces),
                    len(io.StringIO(text[piece_start:previous_end], newline="").readlines())
                    if piece_start < previous_end
                    else 0,
                )
            )
            previous_end = piece_end
        if previous_end != end:
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PYTHON_SECONDARY_COVERAGE")
        cursor = end
    if cursor != len(text) or not spans:
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="PYTHON_COVERAGE")
    return tuple(spans)

"""Python declaration annotations and a lossless adapter to the pinned Haystack splitter."""

import ast
import io
from dataclasses import dataclass
from math import ceil

from apps.workbench.api.chunking_profiles import ChunkingError, ChunkingErrorCode, PythonChunkingProfile
from apps.workbench.api.parser_registry import ParseErrorCode, ParsingError, UploadLimits
from haystack import Document
from haystack.components.preprocessors import DocumentSplitter, PythonCodeSplitter


@dataclass(frozen=True)
class PythonSymbol:
    """Observed declaration; nested declarations are annotations, not additional split points."""

    qualified_symbol: str
    kind: str
    start_line: int
    end_line: int
    class_name: str | None = None
    decorators: tuple[str, ...] = ()


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


def _decorator_source(node: ast.expr, lines: list[str]) -> str:
    end = node.end_lineno or node.lineno
    selected = lines[node.lineno - 1 : end]
    if sum(map(len, selected)) > 4096:
        raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PYTHON_DECORATOR_SIZE")
    if len(selected) == 1:
        return selected[0].encode("utf-8")[node.col_offset : node.end_col_offset].decode("utf-8")
    return (
        selected[0].encode("utf-8")[node.col_offset :].decode("utf-8")
        + "".join(selected[1:-1])
        + selected[-1].encode("utf-8")[: node.end_col_offset].decode("utf-8")
    )


def inspect_python(text: str, *, limits: UploadLimits) -> tuple[PythonSymbol, ...]:
    """Validate syntax without evaluation and annotate declarations using standard AST locations."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        raise ParsingError(ParseErrorCode.UNPARSEABLE_SOURCE) from None
    except (RecursionError, MemoryError):
        raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PYTHON_AST_BUDGET") from None
    symbols: list[PythonSymbol] = []
    lines = io.StringIO(text, newline="").readlines()
    pending: list[tuple[ast.AST, tuple[str, ...], str | None]] = [(tree, (), None)]
    nodes = 0
    while pending:
        node, parents, class_name = pending.pop()
        nodes += 1
        if nodes > limits.max_elements * 16:
            raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PYTHON_AST_NODES")
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = ".".join((*parents, node.name))
            start = min((item.lineno for item in node.decorator_list), default=node.lineno)
            if node.decorator_list:
                while start > 1 and not lines[start - 1].lstrip().startswith("@"):
                    start -= 1
            decorators = tuple(_decorator_source(item, lines) for item in node.decorator_list)
            if len(name) > 512 or sum(map(len, decorators)) > 2048 or len(symbols) >= limits.max_elements:
                raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PYTHON_SYMBOLS")
            symbols.append(
                PythonSymbol(name, type(node).__name__, start, node.end_lineno or node.lineno, class_name, decorators)
            )
            parents = (*parents, node.name)
            if isinstance(node, ast.ClassDef):
                class_name = name
        pending.extend((child, parents, class_name) for child in reversed(list(ast.iter_child_nodes(node))))
    return tuple(symbols)


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

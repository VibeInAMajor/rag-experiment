"""Bounded Python declaration inspection without evaluation."""

import ast
import io
from dataclasses import dataclass

from apps.workbench.parsing.parser_registry import ParseErrorCode, ParsingError, UploadLimits


@dataclass(frozen=True)
class PythonSymbol:
    """Observed declaration; nested declarations are annotations, not additional split points."""

    qualified_symbol: str
    kind: str
    start_line: int
    end_line: int
    class_name: str | None = None
    decorators: tuple[str, ...] = ()


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

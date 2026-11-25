"""Non-executing Markdown cleanup with an explicit map to original source characters."""

import re
from bisect import bisect_right
from dataclasses import dataclass

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SERVICE = re.compile(r'<!--.*?(?:-->|\Z)|{{[<%](?:"[^"]*"|\'[^\']*\'|[^"\'])*?(?:>}}|%}})', re.DOTALL)
_ATTRIBUTE = re.compile(r'\b(text|term_id)\s*=\s*(["\'])(.*?)\2', re.DOTALL)
_INLINE_CODE = re.compile(r"(`+)(?!`)(.*?)(?<!`)\1(?!`)", re.DOTALL)


@dataclass(frozen=True)
class MarkdownProjection:
    """Source-only text and ordered (projection start, projection end, original start) copy runs."""

    text: str
    copy_runs: tuple[tuple[int, int, int], ...]

    def source_bounds(self, start: int, end: int) -> tuple[int, int]:
        """Map a nonempty half-open projection range to its original source envelope."""
        first = self.copy_runs[bisect_right(self.copy_runs, start, key=lambda run: run[0]) - 1]
        last = self.copy_runs[bisect_right(self.copy_runs, end - 1, key=lambda run: run[0]) - 1]
        return first[2] + start - first[0], last[2] + end - last[0]


def _literal_ranges(text: str) -> tuple[list[tuple[int, int]], int]:
    protected = [(match.start(), match.end()) for match in _INLINE_CODE.finditer(text)]
    fence: str | None = None
    offset = 0
    frontmatter_end = 0
    lines = text.splitlines(keepends=True)
    frontmatter = lines[0].strip() if lines and lines[0].strip() in {"---", "+++"} else None
    terminators = {"---", "..."} if frontmatter == "---" else {"+++"}
    if frontmatter and not any(line.strip() in terminators for line in lines[1:]):
        frontmatter = None
    for index, line in enumerate(lines):
        if frontmatter is not None:
            frontmatter_end = offset + len(line)
            if index and line.strip() in ({"---", "..."} if frontmatter == "---" else {"+++"}):
                frontmatter = None
        else:
            marker = _FENCE.fullmatch(line.rstrip("\r\n"))
            if fence is not None or marker is not None or line.startswith(("    ", "\t")):
                protected.append((offset, offset + len(line)))
                if fence is not None:
                    if re.fullmatch(
                        r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line.rstrip("\r\n")
                    ):
                        fence = None
                elif marker is not None and not (marker[1][0] == "`" and "`" in marker[2]):
                    fence = marker[1]
        offset += len(line)
    return protected, frontmatter_end


def _removed_ranges(text: str) -> list[tuple[int, int]]:
    protected, frontmatter_end = _literal_ranges(text)
    removed = [(0, frontmatter_end)] if frontmatter_end else []
    for match in _SERVICE.finditer(text):
        if match.start() < frontmatter_end or any(start <= match.start() < end for start, end in protected):
            continue
        raw = match[0]
        label = None
        # Only literal tooltip labels are available locally; external Hugo definitions are not expanded.
        if re.match(r"{{[<%]\s*glossary_tooltip\b", raw):
            attributes = {attribute[1]: attribute for attribute in _ATTRIBUTE.finditer(raw)}
            label = attributes.get("text") or attributes.get("term_id")
        if label is None:
            removed.append((match.start(), match.end()))
        else:
            removed.extend(
                [(match.start(), match.start() + label.start(3)), (match.start() + label.end(3), match.end())]
            )
    return removed


def project_markdown(text: str) -> MarkdownProjection:
    """
    Remove service comments, frontmatter and Hugo delimiters without executing templates.

    :param text: Decoded original Markdown.
    :returns: Compact source text with original line separators and a character map. Code examples,
        tooltip labels and bodies of paired shortcodes remain literal source content.
    """
    copied: list[tuple[int, int]] = []
    cursor = 0
    for start, end in _removed_ranges(text):
        if cursor < start:
            copied.append((cursor, start))
        # Preserve every line separator so line numbers still refer to the uploaded original.
        copied.extend(
            (start + index, start + index + 1)
            for index, char in enumerate(text[start:end])
            if char in "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"
        )
        cursor = end
    if cursor < len(text):
        copied.append((cursor, len(text)))
    output: list[str] = []
    runs: list[tuple[int, int, int]] = []
    offset = 0
    for start, end in copied:
        output.append(text[start:end])
        runs.append((offset, offset + end - start, start))
        offset += end - start
    return MarkdownProjection(text="".join(output), copy_runs=tuple(runs))

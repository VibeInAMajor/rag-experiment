"""Bounded inspection and loss-aware, immutable text, Markdown and Python projection."""

import hashlib
import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from time import perf_counter

from apps.workbench.parsing.parser_registry import (
    ElementKind,
    FormatId,
    ParseErrorCode,
    ParsingError,
    UploadLimits,
    format_rules,
    select_parser,
)
from apps.workbench.parsing.parsing_adapters import extract_text as _extract_text
from apps.workbench.parsing.pdf.pdf_models import PdfDocument, PdfLimits
from apps.workbench.parsing.pdf.pdf_parser import extract_pdf
from apps.workbench.parsing.python_code import PythonSymbol, inspect_python

_logger = logging.getLogger(__name__)
_DETECTOR_REVISION = "text-inspection-r1"
_ISO_MEDIA_HEADER = b"ftyp"
_DISGUISED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".dll",
        ".com",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".msi",
        ".scr",
        ".html",
        ".htm",
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
    }
)
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_MIME = re.compile(r'([a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+)(?:\s*;\s*charset=(?:"(utf-8|utf8)"|(utf-8|utf8)))?')
_BINARY_HEADERS = (
    b"%PDF-",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"PK\x07\x08",
    b"MZ",
    b"\x7fELF",
    b"\x1f\x8b",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"RIFF",
    b"Rar!",
    b"7z\xbc\xaf\x27\x1c",
    b"\xd0\xcf\x11\xe0",
    b"OggS",
    b"fLaC",
    b"ID3",
    b"\x00asm",
)


@dataclass(frozen=True)
class InspectedSource:
    """Verified text identity; names remain untrusted display data, never paths."""

    original_name: str
    safe_basename: str
    declared_mime: str | None
    verified_mime: str
    format_id: FormatId
    content_sha256: str
    bytes_count: int
    detector_revision: str
    evidence_codes: tuple[str, ...]
    ambiguous: bool = False


@dataclass(frozen=True)
class SourceSpan:
    """Half-open character bounds; the owning record declares original or extracted-projection coordinates."""

    start: int
    end: int


@dataclass(frozen=True)
class ParsedElement:
    """Observed text span, relative to extracted_text when present; raw blocks make no AST/table-cell claim."""

    element_id: str
    order: int
    kind: ElementKind
    text: str
    source_span: SourceSpan
    line_start: int
    line_end: int
    heading_path: tuple[str, ...] = ()
    parent_anchor: str | None = None
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessingClassification:
    """Content-free policy input; chunking must not repeat MIME classification."""

    format_id: FormatId
    element_kinds: tuple[ElementKind, ...]
    has_protected_spans: bool
    selection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ParsedDocument:
    """Revisioned internal handoff; Markdown/PDF elements use extracted_text, while source hashes bind originals."""

    inspected_source: InspectedSource
    format_id: FormatId
    parser_id: str
    parser_revision: str
    source_sha256: str
    detector_revision: str
    elements: tuple[ParsedElement, ...]
    warning_codes: tuple[str, ...]
    classification: ProcessingClassification
    contract_revision: str = "parsed-elements-v1"
    code_symbols: tuple[PythonSymbol, ...] = ()
    pdf_document: PdfDocument | None = None
    extracted_text: str | None = None
    projection_sha256: str | None = None


def _check_deadline(started: float, limits: UploadLimits) -> None:
    if (perf_counter() - started) * 1000 > limits.deadline_ms:
        raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="DEADLINE_EXCEEDED")


def _basename(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_BASENAME")
    normalized = unicodedata.normalize("NFC", value)
    if (
        normalized.startswith(".")
        or normalized != normalized.strip()
        or normalized.endswith(".")
        or ".." in normalized
        or any(c in normalized for c in '/\\:<>"|?*')
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in normalized)
        or len(normalized.encode("utf-8")) > 255
    ):
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_BASENAME")
    stem = normalized.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_BASENAME")
    return normalized


def _declared_mime(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_MIME")
    match = _MIME.fullmatch(value.strip().lower())
    if not match:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_MIME")
    return match[1]


def _decode_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_UTF8") from None
    if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="BINARY_CONTENT")
    if not text.strip():
        raise ParsingError(ParseErrorCode.EMPTY_EXTRACTION, reason="EMPTY_SOURCE")
    return text


def inspect_format(
    content: bytes,
    *,
    safe_basename: str,
    declared_type: str | None = None,
    upload_limits: UploadLimits = UploadLimits(),
) -> InspectedSource:
    """
    Verify the initial allowlist without filesystem access or parser invocation.

    :param content: Already bounded upload bytes; UTF-8 text or a PDF signature candidate.
    :param safe_basename: Untrusted single filename, at most 255 UTF-8 bytes; paths are refused.
    :param declared_type: Optional reviewed MIME alias with an optional UTF-8 charset parameter.
    :param upload_limits: Positive limits capped at application ceilings; defaults to 1 MiB.
    :returns: Immutable text/PDF-candidate identity and original byte digest; PDF safety follows in its worker.
    :raises ParsingError: Sanitized refusal for mismatches, unavailable formats or resource limits.
    """
    started = perf_counter()
    if not isinstance(content, bytes):
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="INVALID_BYTES")
    pdf_hint = isinstance(safe_basename, str) and safe_basename.lower().endswith(".pdf")
    if len(content) > (PdfLimits().max_bytes if pdf_hint else upload_limits.max_bytes):
        raise ParsingError(
            ParseErrorCode.PDF_TOO_LARGE if pdf_hint else ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_BYTES"
        )
    basename = _basename(safe_basename)
    declared_mime = _declared_mime(declared_type)
    parts = basename.lower().split(".")
    if len(parts) < 2:
        raise ParsingError(ParseErrorCode.UNSUPPORTED_FORMAT, reason="EXTENSION_NOT_ALLOWED")
    rules = format_rules()
    rule = next((rule for rule in rules if f".{parts[-1]}" in rule.extensions), None)
    if not rule:
        raise ParsingError(ParseErrorCode.UNSUPPORTED_FORMAT, reason="EXTENSION_NOT_ALLOWED")
    known_extensions = {extension for item in rules for extension in item.extensions} | _DISGUISED_EXTENSIONS
    if any(f".{part.strip()}" in known_extensions for part in parts[1:-1]):
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="MULTIPLE_FORMAT_EXTENSIONS")
    if declared_mime is not None and declared_mime not in rule.mime_aliases:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="MIME_EXTENSION_CONFLICT")
    if rule.format_id not in {FormatId.PLAIN_TEXT, FormatId.MARKDOWN, FormatId.PYTHON, FormatId.PDF}:
        raise ParsingError(ParseErrorCode.PARSER_UNAVAILABLE, reason="FORMAT_NOT_QUALIFIED")
    if rule.format_id is FormatId.PDF:
        if not content.startswith(b"%PDF-"):
            raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="PDF_SIGNATURE_MISMATCH")
        return InspectedSource(
            original_name=safe_basename,
            safe_basename=basename,
            declared_mime=declared_mime,
            verified_mime=rule.verified_mime,
            format_id=FormatId.PDF,
            content_sha256=hashlib.sha256(content).hexdigest(),
            bytes_count=len(content),
            detector_revision="pdf-inspection-r1",
            evidence_codes=("REVIEWED_EXTENSION", "MIME_AGREES" if declared_mime else "MIME_ABSENT", "PDF_SIGNATURE"),
        )
    header = content.removeprefix(b"\xef\xbb\xbf").lstrip()[:512]
    if header.startswith(_BINARY_HEADERS) or header[4:8] == _ISO_MEDIA_HEADER:
        raise ParsingError(ParseErrorCode.FORMAT_MISMATCH, reason="BINARY_SIGNATURE")
    _decode_text(content)
    _check_deadline(started, upload_limits)
    return InspectedSource(
        original_name=safe_basename,
        safe_basename=basename,
        declared_mime=declared_mime,
        verified_mime=rule.verified_mime,
        format_id=rule.format_id,
        content_sha256=hashlib.sha256(content).hexdigest(),
        bytes_count=len(content),
        detector_revision=_DETECTOR_REVISION,
        evidence_codes=(
            "REVIEWED_EXTENSION",
            "MIME_AGREES" if declared_mime else "MIME_ABSENT",
            "VALID_UTF8",
            "NO_BINARY_SIGNATURE",
        ),
    )


def _fence_end(lines: list[str], start: int, match: re.Match[str]) -> tuple[int, tuple[str, ...]]:
    marker = match[1]
    close = re.compile(r"^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
    for index in range(start + 1, len(lines)):
        if close.fullmatch(lines[index].rstrip("\r\n")):
            return index + 1, ("CODE_FENCE_UNPARSED",)
    return len(lines), ("CODE_FENCE_UNPARSED", "UNCLOSED_CODE_FENCE")


def _heading(lines: list[str], index: int) -> tuple[int, str, int] | None:
    line = lines[index].rstrip("\r\n")
    # Container/indented Markdown is deliberately outside the qualified heading subset.
    if _raw_warning(line):
        return None
    if match := _ATX.fullmatch(line):
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match[2] or "").strip()
        return len(match[1]), title, index + 1
    if index + 1 < len(lines) and line.strip() and not line.startswith(("    ", "\t")):
        underline = _SETEXT.fullmatch(lines[index + 1].rstrip("\r\n"))
        if underline:
            return 1 if underline[1][0] == "=" else 2, line.strip(), index + 2
    return None


def _raw_warning(line: str) -> str | None:
    if "|" in line:
        return "TABLE_UNPARSED"
    if (
        line.startswith((" ", "\t"))
        or re.match(r"^(?:[>\[<`~]|[-+*](?:\s|$)|\d+[.)]\s)", line)
        or re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})[ \t]*", line)
    ):
        return "MARKDOWN_STRUCTURE_UNPARSED"
    return None


def _literal_block_end(lines: list[str], index: int) -> int | None:
    line = lines[index].strip()
    terminators: tuple[str, ...] = ()
    if index == 0 and line in {"---", "+++"}:
        terminators = ("---", "...") if line == "---" else ("+++",)
        for end in range(index + 1, len(lines)):
            if lines[end].strip() in terminators:
                return end + 1
        return len(lines)
    if line.startswith("<!--"):
        terminators = ("-->",)
    elif line.startswith("<![CDATA["):
        terminators = ("]]>",)
    elif line.startswith("<?"):
        terminators = ("?>",)
    elif match := re.match(r"<(script|pre|style|textarea)(?:\s|>|$)", line, flags=re.IGNORECASE):
        terminators = (f"</{match[1].lower()}>",)
    if terminators:
        for end in range(index, len(lines)):
            if any(marker in lines[end].lower() for marker in terminators):
                return end + 1
        return len(lines)
    return None


def _paragraph_end(lines: list[str], index: int) -> tuple[int, bool]:
    end = index + 1
    while end < len(lines) and lines[end].strip():
        line = lines[end].rstrip("\r\n")
        # A multiline Setext title is preserved as one raw block, never a partial heading.
        if _SETEXT.fullmatch(line):
            return end + 1, True
        if _ATX.fullmatch(line) or _FENCE.fullmatch(line) or _raw_warning(line):
            break
        end += 1
    return end, False


def _block(
    lines: list[str], index: int, *, markdown: bool
) -> tuple[int, ElementKind, tuple[str, ...], tuple[int, str] | None]:
    if not markdown:
        end = index + 1
        while end < len(lines) and lines[end].strip():
            end += 1
        return end, ElementKind.PARAGRAPH, (), None
    line = lines[index].rstrip("\r\n")
    if literal_end := _literal_block_end(lines, index):
        return literal_end, ElementKind.PROTECTED_RAW, ("MARKDOWN_STRUCTURE_UNPARSED",), None
    fence = _FENCE.fullmatch(line)
    if fence and not (fence[1][0] == "`" and "`" in fence[2]):
        end, warnings = _fence_end(lines, index, fence)
        return end, ElementKind.PROTECTED_RAW, warnings, None
    if heading := _heading(lines, index):
        level, title, end = heading
        return end, ElementKind.HEADING, (), (level, title)
    warning = _raw_warning(line)
    if warning is None:
        end, ambiguous = _paragraph_end(lines, index)
        if ambiguous:
            return end, ElementKind.PROTECTED_RAW, ("MARKDOWN_STRUCTURE_UNPARSED",), None
        return end, ElementKind.PARAGRAPH, (), None
    end = index + 1
    while end < len(lines) and lines[end].strip():
        next_line = lines[end].rstrip("\r\n")
        if warning == "TABLE_UNPARSED" and _raw_warning(next_line) != warning:
            break
        end += 1
    return end, ElementKind.PROTECTED_RAW, (warning,), None


def _project_elements(
    text: str, *, source: InspectedSource, limits: UploadLimits, started: float
) -> tuple[ParsedElement, ...]:
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    elements: list[ParsedElement] = []
    headings: list[tuple[int, str, str]] = []
    index = 0
    while index < len(lines):
        _check_deadline(started, limits)
        if not lines[index].strip():
            index += 1
            continue
        if len(elements) >= limits.max_elements:
            raise ParsingError(ParseErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_ELEMENTS")
        end, kind, warnings, heading = _block(lines, index, markdown=source.format_id == FormatId.MARKDOWN)
        span = SourceSpan(start=offsets[index], end=offsets[end])
        anchor = f"{source.content_sha256}:{span.start}:{span.end}:{kind.value}"
        parent = headings[-1][2] if headings else None
        if heading:
            level, title = heading
            while headings and headings[-1][0] >= level:
                headings.pop()
            parent = headings[-1][2] if headings else None
            headings.append((level, title, anchor))
        elements.append(
            ParsedElement(
                element_id=anchor,
                order=len(elements),
                kind=kind,
                text=text[span.start : span.end],
                source_span=span,
                line_start=index + 1,
                line_end=end,
                heading_path=tuple(item[1] for item in headings),
                parent_anchor=parent,
                warning_codes=warnings,
            )
        )
        index = end
    if not elements:
        raise ParsingError(ParseErrorCode.EMPTY_EXTRACTION, reason="NO_ELEMENTS")
    return tuple(elements)


def _pdf_text(document: PdfDocument, source: InspectedSource) -> str:
    if document.source_sha256 != source.content_sha256:
        raise ParsingError(ParseErrorCode.STRUCTURE_LOSS)
    return "\n\n".join(block.text for block in document.blocks)


def parse_source(
    content: bytes,
    *,
    safe_basename: str,
    declared_type: str | None = None,
    upload_limits: UploadLimits = UploadLimits(),
) -> ParsedDocument:
    """
    Inspect once, dispatch one approved in-memory adapter and preserve observed spans.

    :param content: Bounded bytes, never interpreted as code, a path or a remote target.
    :param safe_basename: Untrusted single filename; used only by the inspection gate.
    :param declared_type: Optional MIME alias; contradictions are refused before dispatch.
    :param upload_limits: Byte/element ceilings and a cooperative wall-time budget (not process isolation).
    :returns: Immutable ordered elements and metadata-only processing classification.
    :raises ParsingError: Stable, sanitized inspection, extraction or resource refusal.
    """
    started = perf_counter()
    source: InspectedSource | None = None
    parser_id = "none"
    parser_revision = "none"
    try:
        source = inspect_format(
            content, safe_basename=safe_basename, declared_type=declared_type, upload_limits=upload_limits
        )
        descriptor = select_parser(source.format_id)
        parser_id, parser_revision = descriptor.parser_id, descriptor.parser_revision
        _check_deadline(started, upload_limits)
        pdf_document = extract_pdf(content) if source.format_id is FormatId.PDF else None
        if pdf_document is not None:
            text = _pdf_text(pdf_document, source)
        else:
            try:
                text = _extract_text(content)
            except ImportError:
                raise ParsingError(ParseErrorCode.PARSER_UNAVAILABLE, reason="DEPENDENCY_MISSING") from None
            except ParsingError:
                raise
            except Exception:
                raise ParsingError(ParseErrorCode.PARSE_FAILED, reason="EXTRACTION_FAILED") from None
        if source.format_id is FormatId.MARKDOWN:
            from apps.workbench.parsing.markdown_projection import project_markdown

            text = project_markdown(text).text
        code_symbols: tuple[PythonSymbol, ...] = ()
        elements: tuple[ParsedElement, ...]
        if pdf_document is not None:
            elements = (
                ParsedElement(
                    element_id=f"{source.content_sha256}:pdf-layout",
                    order=0,
                    kind=ElementKind.PDF_LAYOUT,
                    text=text,
                    source_span=SourceSpan(start=0, end=len(text)),
                    line_start=1,
                    line_end=len(text.splitlines()),
                    warning_codes=pdf_document.warning_codes,
                ),
            )
        elif source.format_id is FormatId.PYTHON:
            code_symbols = inspect_python(text, limits=upload_limits)
            elements = (
                ParsedElement(
                    element_id=f"{source.content_sha256}:0:{len(text)}:python_source",
                    order=0,
                    kind=ElementKind.PYTHON_SOURCE,
                    text=text,
                    source_span=SourceSpan(start=0, end=len(text)),
                    line_start=1,
                    line_end=len(io.StringIO(text, newline="").readlines()),
                ),
            )
        else:
            elements = _project_elements(text, source=source, limits=upload_limits, started=started)
        if pdf_document is None:
            _check_deadline(started, upload_limits)
        warnings = tuple(dict.fromkeys(code for element in elements for code in element.warning_codes))
        classification = ProcessingClassification(
            format_id=source.format_id,
            element_kinds=tuple(dict.fromkeys(element.kind for element in elements)),
            has_protected_spans=any(element.kind == ElementKind.PROTECTED_RAW for element in elements),
            selection_reasons=source.evidence_codes + ("QUALIFIED_PARSER",),
        )
        document = ParsedDocument(
            inspected_source=source,
            format_id=source.format_id,
            parser_id=parser_id,
            parser_revision=parser_revision,
            source_sha256=source.content_sha256,
            detector_revision=source.detector_revision,
            elements=elements,
            warning_codes=warnings,
            classification=classification,
            code_symbols=code_symbols,
            pdf_document=pdf_document,
            extracted_text=text if pdf_document is not None or source.format_id is FormatId.MARKDOWN else None,
            projection_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
            if pdf_document is not None or source.format_id is FormatId.MARKDOWN
            else None,
        )
    except ParsingError as error:
        _logger.info(
            "Source parsing refused",
            extra={
                "code": error.code.value,
                "reason": error.reason,
                "format_id": source.format_id.value if source else "unsupported",
                "parser_id": parser_id,
                "parser_revision": parser_revision,
                "detector_revision": _DETECTOR_REVISION,
                "bytes_count": len(content) if isinstance(content, bytes) else 0,
                "element_count": 0,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        raise
    _logger.info(
        "Source parsing completed",
        extra={
            "format_id": source.format_id.value,
            "parser_id": parser_id,
            "parser_revision": parser_revision,
            "detector_revision": _DETECTOR_REVISION,
            "bytes_count": source.bytes_count,
            "element_count": len(elements),
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        },
    )
    return document

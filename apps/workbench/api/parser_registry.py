"""Reviewed application parser catalog; upstream converters do not qualify uploads."""

from dataclasses import dataclass, replace
from enum import StrEnum
from importlib import metadata

_MAX_SOURCE_BYTES = 1_048_576
_MAX_ELEMENTS = 4096
_DEADLINE_MS = 2000


class FormatId(StrEnum):
    """Canonical source-format vocabulary, independent of filename or parser."""

    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    WORD_DOCUMENT = "word_document"
    PRESENTATION = "presentation"
    WORKBOOK = "workbook"
    DELIMITED_TABLE = "delimited_table"
    JSON = "json"
    JSON_LINES = "json_lines"
    YAML = "yaml"
    TOML = "toml"
    XML = "xml"
    PYTHON = "python"
    SOURCE_CODE = "source_code"
    EMAIL = "email"
    TIMED_TRANSCRIPT = "timed_transcript"
    AUDIO = "audio"
    VIDEO = "video"
    RASTER_IMAGE = "raster_image"
    UNSUPPORTED = "unsupported"


class ElementKind(StrEnum):
    """Structures actually emitted by the initial qualified adapters."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    PROTECTED_RAW = "protected_raw"
    PYTHON_SOURCE = "python_source"
    PDF_LAYOUT = "pdf_layout"


class ParseErrorCode(StrEnum):
    """Low-cardinality refusal codes for a future HTTP error projection."""

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
    PARSE_FAILED = "PARSE_FAILED"
    EMPTY_EXTRACTION = "EMPTY_EXTRACTION"
    CONTENT_LIMIT_EXCEEDED = "CONTENT_LIMIT_EXCEEDED"
    STRUCTURE_LOSS = "STRUCTURE_LOSS"
    UNPARSEABLE_SOURCE = "UNPARSEABLE_SOURCE"
    PDF_ENCRYPTED = "PDF_ENCRYPTED"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    PDF_TOO_LARGE = "PDF_TOO_LARGE"
    PDF_PARSE_TIMEOUT = "PDF_PARSE_TIMEOUT"
    PDF_LAYOUT_UNCERTAIN = "PDF_LAYOUT_UNCERTAIN"
    PDF_CORRUPT = "PDF_CORRUPT"
    PDF_UNSAFE_CONTENT = "PDF_UNSAFE_CONTENT"
    PDF_RESOURCE_LIMIT = "PDF_RESOURCE_LIMIT"
    TABLE_STRUCTURE_UNCERTAIN = "TABLE_STRUCTURE_UNCERTAIN"
    TABLE_OVERFLOW = "TABLE_OVERFLOW"
    PDF_BUSY = "PDF_BUSY"


class ParsingError(ValueError):
    """A sanitized failure; optional reason labels must be static application codes."""

    def __init__(self, code: ParseErrorCode, *, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason or code.value
        super().__init__(code.value)


@dataclass(frozen=True)
class UploadLimits:
    """Per-call limits may tighten, but cannot raise, the qualified resource budget."""

    max_bytes: int = _MAX_SOURCE_BYTES
    max_elements: int = _MAX_ELEMENTS
    deadline_ms: int = _DEADLINE_MS

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.max_bytes, _MAX_SOURCE_BYTES),
            (self.max_elements, _MAX_ELEMENTS),
            (self.deadline_ms, _DEADLINE_MS),
        ):
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("Parser limits must be positive integers within the qualified budget.")


@dataclass(frozen=True)
class FormatRule:
    """Reviewed filename/MIME evidence; presence here is not permission to parse."""

    format_id: FormatId
    extensions: tuple[str, ...]
    mime_aliases: tuple[str, ...]
    verified_mime: str


@dataclass(frozen=True)
class ParserDescriptor:
    """Immutable parser identity, qualification, provenance and allocation contract."""

    parser_id: str
    parser_revision: str
    accepted_format_ids: tuple[FormatId, ...]
    available: bool
    qualified: bool
    dependency_revisions: tuple[str, ...]
    max_bytes: int
    max_elements: int
    deadline_ms: int
    emitted_element_kinds: tuple[ElementKind, ...]
    required_provenance: tuple[str, ...]
    constraints: tuple[str, ...]


_FORMAT_RULES = (
    FormatRule(FormatId.PLAIN_TEXT, (".txt",), ("text/plain",), "text/plain"),
    FormatRule(
        FormatId.MARKDOWN, (".md", ".markdown"), ("text/markdown", "text/x-markdown", "text/plain"), "text/markdown"
    ),
    FormatRule(FormatId.PDF, (".pdf",), ("application/pdf",), "application/pdf"),
    FormatRule(
        FormatId.WORD_DOCUMENT,
        (".docx", ".doc"),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    FormatRule(
        FormatId.PRESENTATION,
        (".pptx", ".ppt"),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.ms-powerpoint"),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    FormatRule(
        FormatId.WORKBOOK,
        (".xlsx", ".xls"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel"),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    FormatRule(FormatId.DELIMITED_TABLE, (".csv", ".tsv"), ("text/csv", "text/tab-separated-values"), "text/csv"),
    FormatRule(FormatId.JSON, (".json",), ("application/json", "text/json"), "application/json"),
    FormatRule(
        FormatId.JSON_LINES,
        (".jsonl", ".ndjson"),
        ("application/x-ndjson", "application/jsonl"),
        "application/x-ndjson",
    ),
    FormatRule(
        FormatId.YAML, (".yaml", ".yml"), ("application/yaml", "text/yaml", "application/x-yaml"), "application/yaml"
    ),
    FormatRule(FormatId.TOML, (".toml",), ("application/toml", "text/toml"), "application/toml"),
    FormatRule(FormatId.XML, (".xml",), ("application/xml", "text/xml"), "application/xml"),
    FormatRule(
        FormatId.PYTHON, (".py",), ("text/x-python", "application/x-python-code", "text/plain"), "text/x-python"
    ),
    FormatRule(
        FormatId.SOURCE_CODE,
        (".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".rs", ".go", ".sh"),
        ("text/javascript", "application/javascript", "text/x-c", "text/x-java-source", "text/x-shellscript"),
        "text/plain",
    ),
    FormatRule(FormatId.EMAIL, (".eml", ".msg"), ("message/rfc822", "application/vnd.ms-outlook"), "message/rfc822"),
    FormatRule(FormatId.TIMED_TRANSCRIPT, (".srt", ".vtt"), ("application/x-subrip", "text/vtt"), "text/vtt"),
    FormatRule(
        FormatId.AUDIO,
        (".mp3", ".wav", ".flac", ".m4a", ".ogg"),
        ("audio/mpeg", "audio/wav", "audio/flac", "audio/mp4", "audio/ogg"),
        "audio/mpeg",
    ),
    FormatRule(
        FormatId.VIDEO,
        (".mp4", ".webm", ".mov", ".avi"),
        ("video/mp4", "video/webm", "video/quicktime", "video/x-msvideo"),
        "video/mp4",
    ),
    FormatRule(
        FormatId.RASTER_IMAGE,
        (".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".webp", ".bmp"),
        ("image/png", "image/jpeg", "image/gif", "image/tiff", "image/webp", "image/bmp"),
        "image/png",
    ),
    FormatRule(FormatId.UNSUPPORTED, (), (), "application/octet-stream"),
)


def _descriptor(format_id: FormatId) -> ParserDescriptor:
    if format_id is FormatId.PDF:
        return ParserDescriptor(
            parser_id="docling-pdf",
            parser_revision="docling-pdf-r2",
            accepted_format_ids=(FormatId.PDF,),
            available=True,
            qualified=True,
            dependency_revisions=(
                "docling==2.151.1",
                "docling-core==2.108.0",
                "docling-ibm-models==4.0.4",
                "docling-parse==7.27.0",
            ),
            max_bytes=8_388_608,
            max_elements=4096,
            deadline_ms=180_000,
            emitted_element_kinds=(ElementKind.PDF_LAYOUT,),
            required_provenance=("source_sha256", "page_number", "bbox", "source_span_basis"),
            constraints=(
                "TEXT_LAYER_ONLY",
                "NO_OCR",
                "NO_NETWORK",
                "PROCESS_QUOTAS",
                "PINNED_MODEL_ASSETS",
                "VISUAL_COVERAGE_INCOMPLETE",
                "ORIGINAL_EVIDENCE_UNAVAILABLE",
            ),
        )
    qualified = format_id in (FormatId.PLAIN_TEXT, FormatId.MARKDOWN, FormatId.PYTHON)
    parser_id = {
        FormatId.PLAIN_TEXT: "haystack-text",
        FormatId.MARKDOWN: "raw-markdown",
        FormatId.PYTHON: "python-source",
    }.get(format_id, f"planned-{format_id.value}")
    kinds: tuple[ElementKind, ...] = (ElementKind.PARAGRAPH,)
    if format_id is FormatId.MARKDOWN:
        kinds += (ElementKind.HEADING, ElementKind.PROTECTED_RAW)
    elif format_id is FormatId.PYTHON:
        kinds = (ElementKind.PYTHON_SOURCE,)
    return ParserDescriptor(
        parser_id=parser_id,
        parser_revision=f"{parser_id}-r1" if qualified else "not-qualified",
        accepted_format_ids=(format_id,),
        available=qualified,
        qualified=qualified,
        dependency_revisions=("haystack-ai==3.5.0",) if qualified else (),
        max_bytes=_MAX_SOURCE_BYTES if qualified else 0,
        max_elements=_MAX_ELEMENTS if qualified else 0,
        deadline_ms=_DEADLINE_MS if qualified else 0,
        emitted_element_kinds=kinds if qualified else (),
        required_provenance=("source_sha256", "source_span", "line_range") if qualified else (),
        constraints=("UTF8_ONLY", "IN_MEMORY_ONLY", "NO_NETWORK", "COOPERATIVE_DEADLINE")
        + (("RAW_MARKDOWN_STRUCTURES",) if format_id is FormatId.MARKDOWN else ())
        if qualified
        else ("PLANNED_APP_ADAPTER", "NO_PUBLIC_UPLOAD_CAPABILITY"),
    )


_PARSER_REGISTRY = tuple(_descriptor(format_id) for format_id in FormatId)


def format_rules() -> tuple[FormatRule, ...]:
    """Return immutable classification rules, including unqualified format families."""
    return _FORMAT_RULES


def _dependency_available() -> bool:
    try:
        return metadata.version("haystack-ai") == "3.5.0"
    except metadata.PackageNotFoundError:
        return False


def parser_descriptors() -> tuple[ParserDescriptor, ...]:
    """Return reviewed descriptors with current installed-dependency availability."""
    available = _dependency_available()
    from apps.workbench.api.pdf_assets import pdf_runtime_available

    return tuple(
        replace(
            descriptor,
            available=descriptor.available
            and available
            and (descriptor.accepted_format_ids != (FormatId.PDF,) or pdf_runtime_available()),
        )
        for descriptor in _PARSER_REGISTRY
    )


def select_parser(format_id: FormatId) -> ParserDescriptor:
    """
    Resolve one qualified installed adapter or raise a sanitized refusal.

    :param format_id: Canonical format obtained from source inspection, not a parser import path.
    :returns: The sole reviewed descriptor for that format.
    :raises ParsingError: If the format is unsupported or its adapter is unavailable/unqualified.
    """
    if not isinstance(format_id, FormatId) or format_id is FormatId.UNSUPPORTED:
        raise ParsingError(ParseErrorCode.UNSUPPORTED_FORMAT)
    descriptor = next(item for item in parser_descriptors() if format_id in item.accepted_format_ids)
    if not descriptor.qualified or not descriptor.available:
        raise ParsingError(ParseErrorCode.PARSER_UNAVAILABLE)
    return descriptor

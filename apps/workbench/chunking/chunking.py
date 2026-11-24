"""Verified parser-to-chunk preparation, without persistence or upload authority."""

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Protocol

from apps.workbench.chunking.chunking_profiles import (
    ChunkingDecision,
    ChunkingError,
    ChunkingErrorCode,
    ChunkingProfile,
    ChunkingResources,
    DocumentFeatures,
    PdfChunkingProfile,
    PythonChunkingProfile,
    resolve_profile,
)
from apps.workbench.chunking.python_code import PythonSpan, split_python
from apps.workbench.parsing.parser_registry import ElementKind, FormatId, ParsingError, UploadLimits, select_parser
from apps.workbench.parsing.parsing import (
    InspectedSource,
    ParsedDocument,
    ParsedElement,
    ProcessingClassification,
    SourceSpan,
)
from apps.workbench.persistence.models import Chunk

_logger = logging.getLogger(__name__)
_ALGORITHM_REVISION = "structural-token-chunks-r1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_METADATA_BYTES = 16_384
_MAX_PREPARED_BYTES = 52_428_800
_DEADLINE_SECONDS = 10


@dataclass(frozen=True)
class ChunkingInput:
    """Server-owned identities and exact decoded text accompanying a successful parser result."""

    parsed_document: ParsedDocument
    normalized_content: str
    workspace_id: str
    source_id: str
    source_version_id: str
    language: str = "en"


class ExactModelCounter(Protocol):
    """An application-configured, pinned counter; never deserialize one from document text."""

    @property
    def counter_revision(self) -> str:
        """Identity of tokenizer assets, model revision and special-token configuration."""
        ...

    def count_tokens(self, text: str) -> int:
        """Count the complete final embedding input, including configured special tokens."""
        ...


@dataclass(frozen=True)
class ModelTokenAdmission:
    """Optional exact-model admission, independent of the working lexical token splitter."""

    counter_revision: str
    max_tokens: int
    prefix: str = ""
    suffix: str = ""
    include_heading_path: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.counter_revision, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+@=,/-]{0,255}", self.counter_revision) is None
            or type(self.max_tokens) is not int
            or not 0 < self.max_tokens <= 1_000_000
            or not isinstance(self.prefix, str)
            or not isinstance(self.suffix, str)
            or len(self.prefix) + len(self.suffix) > 8192
            or type(self.include_heading_path) is not bool
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)

    def embedding_input(self, content: str, *, heading_path: tuple[str, ...] = ()) -> str:
        """
        Format the exact input shared by admission and the future embedding adapter.

        :param content: Unmodified prepared chunk text.
        :param heading_path: Observed headings, used only when include_heading_path is enabled.
        :returns: Prefix, optional heading context, text and suffix; the counter owns special tokens.
        """
        context = " > ".join(heading_path) + "\n\n" if self.include_heading_path and heading_path else ""
        return self.prefix + context + content + self.suffix


@dataclass(frozen=True)
class PreparedChunk:
    """Immutable, per-occurrence chunk; to_chunk validates the existing storage record without writing."""

    workspace_id: str
    source_id: str
    source_version_id: str
    chunk_id: str
    ordinal: int
    content: str
    content_hash: str
    source_span: SourceSpan
    heading_path: tuple[str, ...]
    parent_structural_id: str
    effective_size: int
    overlap_tokens: int
    processing_fingerprint: str
    decision: ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile]
    source_sha256: str
    parser_id: str
    parser_revision: str
    detector_revision: str
    warning_codes: tuple[str, ...] = ()
    length_model_token: int | None = None
    length_tiktoken_model_input: int | None = None
    model_counter_revision: str | None = None
    python_span: PythonSpan | None = None
    pdf_metadata_json: bytes | None = None
    page: int | None = None

    def metadata(self) -> dict[str, Any]:
        """Return a fresh, bounded JSON projection; native page defaults are deliberately absent."""
        profile = self.decision.profile
        metadata = {
            "ordinal": self.ordinal,
            "source_span": asdict(self.source_span),
            "heading_path": list(self.heading_path),
            "parent_structural_id": self.parent_structural_id,
            "processing_fingerprint": self.processing_fingerprint,
            "source_sha256": self.source_sha256,
            "parser_id": self.parser_id,
            "parser_revision": self.parser_revision,
            "detector_revision": self.detector_revision,
            "parser_contract_revision": "parsed-elements-v1",
            "strategy": self.decision.strategy,
            "profile_id": profile.profile_id,
            "profile_revision": profile.profile_revision,
            "unit": profile.unit,
            "target_size": profile.target_size,
            "requested_overlap": profile.overlap,
            "actual_overlap_tokens": self.overlap_tokens,
            "length_tiktoken": self.effective_size,
            "tokenizer_ref": "tiktoken:o200k_base",
            "token_counter_revision": self.decision.token_counter_revision,
            "selection_reason": self.decision.selection_reason,
            "fallback_reasons": list(self.decision.fallback_reasons),
            "warnings": list(self.warning_codes),
            "source_id": self.source_id,
            "parent_id": self.parent_structural_id,
            "split_id": self.ordinal,
            "split_idx_start": self.source_span.start,
        }
        if isinstance(profile, ChunkingProfile):
            metadata.update(
                {
                    "separator_profile_id": profile.separator_profile_id,
                    "separators": list(profile.separators),
                    "sentence_language": profile.sentence_language,
                    "sentence_keep_white_spaces": profile.sentence_keep_white_spaces,
                    "sentence_resource_revision": profile.sentence_resource_revision,
                }
            )
        if self.python_span is not None:
            span = self.python_span
            metadata.update(
                {
                    "verified_document_type": "python_source",
                    "start_line": span.start_line,
                    "end_line": span.end_line,
                    "unit_kinds": list(span.unit_kinds),
                    "symbols": [{**asdict(symbol), "decorators": list(symbol.decorators)} for symbol in span.symbols],
                    "secondary_split": span.secondary_split,
                    "secondary_split_index": span.secondary_split_index,
                    "secondary_split_total": span.secondary_split_total,
                    "actual_overlap_lines": span.overlap_lines,
                    "length_effective_line": (len(self.content) + 44) // 45,
                }
            )
            innermost = [
                symbol
                for symbol in span.symbols
                if not any(other.qualified_symbol.startswith(symbol.qualified_symbol + ".") for other in span.symbols)
            ]
            if len(innermost) == 1:
                metadata["qualified_symbol"] = innermost[0].qualified_symbol
                if innermost[0].class_name:
                    metadata["class_name"] = innermost[0].class_name
                if innermost[0].decorators:
                    metadata["decorators"] = list(innermost[0].decorators)
        if self.pdf_metadata_json is not None:
            metadata.update(json.loads(self.pdf_metadata_json))
        if self.length_model_token is not None:
            metadata.update(
                {
                    "length_model_token": self.length_model_token,
                    "model_counter_revision": self.model_counter_revision,
                    "model_minus_tiktoken": self.length_model_token - self.effective_size,
                    "length_tiktoken_model_input": self.length_tiktoken_model_input,
                    "model_minus_tiktoken_model_input": (
                        self.length_model_token - self.length_tiktoken_model_input
                        if self.length_tiktoken_model_input is not None
                        else None
                    ),
                }
            )
        if len(_canonical_bytes(metadata)) > _MAX_METADATA_BYTES:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="METADATA_BYTES")
        return metadata

    def to_chunk(self, *, title: str) -> Chunk:
        """Validate a persistence-compatible record; this method performs no database operation."""
        return Chunk(
            workspace_id=self.workspace_id,
            source_id=self.source_id,
            version_id=self.source_version_id,
            chunk_id=self.chunk_id,
            title=title,
            content=self.content,
            content_hash=self.content_hash,
            page=self.page,
            metadata=self.metadata(),
        )


@dataclass(frozen=True)
class _Section:
    start: int
    end: int
    heading_path: tuple[str, ...]
    anchor: str


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _validate_source(source: ChunkingInput) -> DocumentFeatures:
    if not isinstance(source, ChunkingInput) or not isinstance(source.parsed_document, ParsedDocument):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
    if any(
        not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None
        for value in (source.workspace_id, source.source_id, source.source_version_id)
    ):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="INVALID_OWNER_ID")
    text, parsed = source.normalized_content, source.parsed_document
    if not isinstance(text, str) or not text.strip() or not parsed.elements:
        raise ChunkingError(ChunkingErrorCode.EMPTY_INPUT)
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="INVALID_TEXT") from None
    is_pdf = parsed.format_id is FormatId.PDF
    from apps.workbench.parsing.pdf.pdf_models import PdfLimits

    byte_limit = PdfLimits().max_bytes if is_pdf else UploadLimits().max_bytes
    if len(encoded) > byte_limit:
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="INPUT_BYTES")
    inspected = parsed.inspected_source
    if not isinstance(inspected, InspectedSource) or not isinstance(parsed.classification, ProcessingClassification):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
    if (
        parsed.contract_revision != "parsed-elements-v1"
        or type(inspected.bytes_count) is not int
        or not 0 < inspected.bytes_count <= byte_limit
        or inspected.ambiguous
        or parsed.format_id != inspected.format_id
        or parsed.format_id != parsed.classification.format_id
        or not isinstance(parsed.source_sha256, str)
        or parsed.source_sha256 != inspected.content_sha256
        or _SHA256.fullmatch(parsed.source_sha256) is None
        or parsed.detector_revision != inspected.detector_revision
        or (
            not is_pdf
            and not any(
                len(candidate) == inspected.bytes_count
                and hashlib.sha256(candidate).hexdigest() == parsed.source_sha256
                for candidate in (encoded, b"\xef\xbb\xbf" + encoded)
            )
        )
    ):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PARSER_SOURCE_CONFLICT")
    if is_pdf:
        pdf = parsed.pdf_document
        if (
            pdf is None
            or pdf.source_sha256 != parsed.source_sha256
            or parsed.extracted_text != text
            or parsed.projection_sha256 != hashlib.sha256(encoded).hexdigest()
            or text != "\n\n".join(block.text for block in pdf.blocks)
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PDF_PROJECTION_CONFLICT")
    _validate_elements(text, parsed.elements)
    kinds = tuple(dict.fromkeys(element.kind for element in parsed.elements))
    if kinds != parsed.classification.element_kinds or parsed.classification.has_protected_spans != (
        ElementKind.PROTECTED_RAW in kinds
    ):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="CLASSIFICATION_CONFLICT")
    return DocumentFeatures(
        format_id=parsed.format_id,
        has_headings=ElementKind.HEADING in kinds,
        element_kinds=kinds,
        language=source.language,
    )


def _validate_elements(text: str, elements: tuple[ParsedElement, ...]) -> None:
    if type(elements) is not tuple or len(elements) > UploadLimits().max_elements:
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
    previous = 0
    anchors: set[str] = set()
    headings: dict[str, tuple[str, ...]] = {}
    current_path: tuple[str, ...] = ()
    current_heading: str | None = None
    for order, element in enumerate(elements):
        if not isinstance(element, ParsedElement) or not isinstance(element.kind, ElementKind):
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
        if (
            not isinstance(element.element_id, str)
            or not 0 < len(element.element_id) <= 256
            or (element.parent_anchor is not None and not isinstance(element.parent_anchor, str))
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="INVALID_ELEMENT_ANCHOR")
        span = element.source_span
        if (
            not isinstance(span, SourceSpan)
            or type(span.start) is not int
            or type(span.end) is not int
            or not previous <= span.start < span.end <= len(text)
            or text[previous : span.start].strip()
            or text[span.start : span.end] != element.text
            or element.order != order
            or element.element_id in anchors
            or type(element.heading_path) is not tuple
            or len(element.heading_path) > 6
            or any(not isinstance(item, str) for item in element.heading_path)
            or len(_canonical_bytes(element.heading_path)) > 8192
            or type(element.warning_codes) is not tuple
            or any(
                not isinstance(code, str) or re.fullmatch(r"[A-Z_]{1,64}", code) is None
                for code in element.warning_codes
            )
            or (element.parent_anchor is not None and element.parent_anchor not in headings)
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="ELEMENT_SPAN_CONFLICT")
        if element.kind is ElementKind.HEADING:
            ancestor = headings[element.parent_anchor] if element.parent_anchor else ()
            if not element.heading_path or element.heading_path[:-1] != ancestor:
                raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="HEADING_ANCESTRY_CONFLICT")
            headings[element.element_id] = element.heading_path
            current_path, current_heading = element.heading_path, element.element_id
        elif element.heading_path != current_path or element.parent_anchor != current_heading:
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="HEADING_ANCESTRY_CONFLICT")
        anchors.add(element.element_id)
        previous = span.end
    if text[previous:].strip():
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="UNCOVERED_SOURCE")


def resolve_chunking(
    source: ChunkingInput,
    *,
    resources: ChunkingResources,
    profile: ChunkingProfile = ChunkingProfile(),
    pdf_profile: PdfChunkingProfile = PdfChunkingProfile(),
) -> ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile]:
    """
    Resolve a format-aware policy from a validated parser result and explicit resource identities.

    :param source: Server-owned scope, exact decoded text and immutable parser output.
    :param resources: Already inspected resource identities; this function performs no I/O.
    :param profile: Reviewed prose settings, defaulting to 500/50 tiktoken tokens; Python uses its fixed AST profile.
    :param pdf_profile: Reviewed PDF child target; page/table provenance is retained independently of this target.
    :returns: One immutable strategy with explicit language/structure fallback reasons.
    :raises ChunkingError: If input provenance, the profile or required resources are invalid.
    """
    features = _validate_source(source)
    if features.format_id is FormatId.PDF:
        if not isinstance(pdf_profile, PdfChunkingProfile):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        return ChunkingDecision(
            profile=pdf_profile,
            strategy="page_layout",
            selection_reason="verified_pdf_pages_and_tables",
            fallback_reasons=(),
            token_counter_revision=resources.token_counter_revision,
        )
    if features.format_id is FormatId.PYTHON:
        return ChunkingDecision(
            profile=PythonChunkingProfile(),
            strategy="python_ast",
            selection_reason="verified_python_source",
            fallback_reasons=(),
            token_counter_revision=resources.token_counter_revision,
        )
    return resolve_profile(features, profile=profile, resources=resources)


def _sections(source: ChunkingInput) -> tuple[_Section, ...]:
    headings = [element for element in source.parsed_document.elements if element.kind is ElementKind.HEADING]
    if not headings:
        return (_Section(0, len(source.normalized_content), (), "root"),)
    sections = []
    if headings[0].source_span.start > 0:
        sections.append(_Section(0, headings[0].source_span.start, (), "root"))
    for index, heading in enumerate(headings):
        end = headings[index + 1].source_span.start if index + 1 < len(headings) else len(source.normalized_content)
        sections.append(_Section(heading.source_span.start, end, heading.heading_path, heading.element_id))
    return tuple(sections)


def _runs(source: ChunkingInput, section: _Section) -> tuple[tuple[int, int, tuple[str, ...], bool], ...]:
    runs: list[tuple[int, int, tuple[str, ...], bool]] = []
    cursor = section.start
    for element in source.parsed_document.elements:
        if (
            element.kind is not ElementKind.PROTECTED_RAW
            or not section.start <= element.source_span.start < section.end
        ):
            continue
        if element.source_span.start > cursor:
            runs.append((cursor, element.source_span.start, (), False))
        runs.append((element.source_span.start, element.source_span.end, element.warning_codes, True))
        cursor = element.source_span.end
    if cursor < section.end:
        runs.append((cursor, section.end, (), False))
    return tuple(runs)


def _model_size(
    text: str,
    *,
    heading_path: tuple[str, ...],
    admission: ModelTokenAdmission | None,
    counter: ExactModelCounter | None,
) -> int | None:
    if admission is None:
        return None
    if counter is None:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE)
    try:
        length = (
            counter.count_tokens(admission.embedding_input(text, heading_path=heading_path))
            if counter.counter_revision == admission.counter_revision
            else None
        )
    except Exception:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE) from None
    if type(length) is not int or length <= 0:
        raise ChunkingError(ChunkingErrorCode.MODEL_COUNTER_UNAVAILABLE)
    if length > admission.max_tokens:
        raise ChunkingError(ChunkingErrorCode.MODEL_TOKEN_LIMIT_EXCEEDED)
    return length


def _prepared(
    source: ChunkingInput,
    *,
    section: _Section,
    start: int,
    end: int,
    size: int,
    overlap: int,
    ordinal: int,
    decision: ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile],
    fingerprint: str,
    warnings: tuple[str, ...],
    admission: ModelTokenAdmission | None,
    counter: ExactModelCounter | None,
    python_span: PythonSpan | None = None,
) -> PreparedChunk:
    from apps.workbench.chunking.chunking_adapters import count_tokens

    text = source.normalized_content[start:end]
    if (
        not text.strip()
        or len(text) > decision.profile.hard_character_limit
        or (isinstance(decision.profile, ChunkingProfile) and size > decision.profile.target_size)
    ):
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="CHUNK_BUDGET")
    identity = (source.workspace_id, source.source_id, source.source_version_id)
    parent = _fingerprint((*identity, source.parsed_document.source_sha256, section.anchor))
    chunk = PreparedChunk(
        workspace_id=source.workspace_id,
        source_id=source.source_id,
        source_version_id=source.source_version_id,
        chunk_id=_fingerprint((*identity, fingerprint, ordinal, start, end)),
        ordinal=ordinal,
        content=text,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_span=SourceSpan(start=start, end=end),
        heading_path=section.heading_path,
        parent_structural_id=parent,
        effective_size=size,
        overlap_tokens=overlap,
        processing_fingerprint=fingerprint,
        decision=decision,
        source_sha256=source.parsed_document.source_sha256,
        parser_id=source.parsed_document.parser_id,
        parser_revision=source.parsed_document.parser_revision,
        detector_revision=source.parsed_document.detector_revision,
        warning_codes=tuple(dict.fromkeys(warnings)),
        length_model_token=_model_size(text, heading_path=section.heading_path, admission=admission, counter=counter),
        length_tiktoken_model_input=(
            count_tokens(admission.embedding_input(text, heading_path=section.heading_path)) if admission else None
        ),
        model_counter_revision=admission.counter_revision if admission else None,
        python_span=python_span,
    )
    chunk.metadata()
    return chunk


def _processing_fingerprint(
    source: ChunkingInput,
    *,
    profile: ChunkingProfile,
    decision: ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile],
    resources: ChunkingResources,
    admission: ModelTokenAdmission | None,
) -> str:
    return _fingerprint(
        {
            "algorithm": _ALGORITHM_REVISION,
            "source_sha256": source.parsed_document.source_sha256,
            "parser": (source.parsed_document.parser_id, source.parsed_document.parser_revision),
            "detector": source.parsed_document.detector_revision,
            "elements": source.parsed_document.contract_revision,
            "requested_profile": asdict(
                decision.profile if isinstance(decision.profile, PythonChunkingProfile) else profile
            ),
            "decision": asdict(decision),
            "resources": {"token_counter_revision": resources.token_counter_revision}
            if isinstance(decision.profile, PythonChunkingProfile)
            else asdict(resources),
            "structure": [
                (
                    element.kind.value,
                    asdict(element.source_span),
                    element.heading_path,
                    element.parent_anchor,
                    element.warning_codes,
                )
                for element in source.parsed_document.elements
            ],
            "model_admission": asdict(admission) if admission else None,
        }
    )


def _verify_output(source: ChunkingInput, chunks: list[PreparedChunk]) -> None:
    from apps.workbench.chunking import chunking_adapters as adapters

    covered = 0
    previous: PreparedChunk | None = None
    for chunk in chunks:
        start, end = chunk.source_span.start, chunk.source_span.end
        if (
            not 0 <= start < end <= len(source.normalized_content)
            or end <= covered
            or source.normalized_content[covered:start].strip()
            or source.normalized_content[start:end] != chunk.content
            or chunk.effective_size != adapters.count_tokens(chunk.content)
            or (previous is not None and start < previous.source_span.start)
        ):
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="CHUNK_SOURCE_CONFLICT")
        actual_overlap = adapters.count_tokens(source.normalized_content[start:covered]) if start < covered else 0
        if (
            actual_overlap != chunk.overlap_tokens
            or actual_overlap > chunk.decision.profile.overlap
            or (
                previous is not None and previous.parent_structural_id != chunk.parent_structural_id and start < covered
            )
        ):
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="OVERLAP_CONFLICT")
        covered, previous = end, chunk
    if not chunks or source.normalized_content[covered:].strip():
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="UNCOVERED_SOURCE")


def _prepare_python(
    source: ChunkingInput,
    *,
    decision: ChunkingDecision[ChunkingProfile | PythonChunkingProfile | PdfChunkingProfile],
    fingerprint: str,
    admission: ModelTokenAdmission | None,
    counter: ExactModelCounter | None,
    started: float,
) -> tuple[PreparedChunk, ...]:
    from apps.workbench.chunking import chunking_adapters as adapters

    if not isinstance(decision.profile, PythonChunkingProfile):
        raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
    python_spans = split_python(
        source.normalized_content, symbols=source.parsed_document.code_symbols, profile=decision.profile
    )
    code_chunks: list[PreparedChunk] = []
    total_bytes = 0
    covered = 0
    for code_span in python_spans:
        span = code_span
        if len(code_chunks) >= decision.profile.max_chunks or perf_counter() - started > _DEADLINE_SECONDS:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PREPARATION_BUDGET")
        text = source.normalized_content[span.start : span.end]
        if not text.strip():
            covered = span.end
            continue
        chunk = _prepared(
            source,
            section=_Section(span.parent_start, span.parent_end, (), f"python:{span.parent_start}:{span.parent_end}"),
            start=span.start,
            end=span.end,
            size=adapters.count_tokens(text),
            overlap=adapters.count_tokens(source.normalized_content[span.start : covered])
            if span.start < covered
            else 0,
            ordinal=len(code_chunks),
            decision=decision,
            fingerprint=fingerprint,
            warnings=("PYTHON_SECONDARY_LINE_SPLIT",) if span.secondary_split else (),
            admission=admission,
            counter=counter,
            python_span=span,
        )
        total_bytes += len(chunk.content.encode("utf-8"))
        if total_bytes > _MAX_PREPARED_BYTES:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PREPARED_BYTES")
        code_chunks.append(chunk)
        covered = span.end
    return tuple(code_chunks)


def _prepare(
    source: ChunkingInput,
    *,
    profile: ChunkingProfile,
    resources: ChunkingResources | None,
    admission: ModelTokenAdmission | None,
    counter: ExactModelCounter | None,
    started: float,
    pdf_profile: PdfChunkingProfile,
) -> tuple[PreparedChunk, ...]:
    from apps.workbench.chunking import chunking_adapters as adapters

    _validate_source(source)
    try:
        descriptor = select_parser(source.parsed_document.format_id)
    except ParsingError:
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PARSER_NOT_QUALIFIED") from None
    if (source.parsed_document.parser_id, source.parsed_document.parser_revision) != (
        descriptor.parser_id,
        descriptor.parser_revision,
    ):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE, reason="PARSER_REVISION_MISMATCH")
    actual = adapters.inspect_chunking_resources()
    declared = resources or actual
    if declared.token_counter_revision != actual.token_counter_revision:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_REVISION_MISMATCH")
    decision = resolve_chunking(source, profile=profile, resources=declared, pdf_profile=pdf_profile)
    if isinstance(decision.profile, PdfChunkingProfile):
        from apps.workbench.chunking.pdf.pdf_chunk_preparation import prepare_pdf_chunks

        return prepare_pdf_chunks(
            source,
            decision=ChunkingDecision(
                profile=decision.profile,
                strategy=decision.strategy,
                selection_reason=decision.selection_reason,
                fallback_reasons=decision.fallback_reasons,
                token_counter_revision=decision.token_counter_revision,
            ),
            admission=admission,
            counter=counter,
            started=started,
        )
    if isinstance(decision.profile, PythonChunkingProfile):
        fingerprint = _processing_fingerprint(
            source, profile=profile, decision=decision, resources=declared, admission=admission
        )
        return _prepare_python(
            source, decision=decision, fingerprint=fingerprint, admission=admission, counter=counter, started=started
        )
    text_decision = ChunkingDecision(
        profile=decision.profile,
        strategy=decision.strategy,
        selection_reason=decision.selection_reason,
        fallback_reasons=decision.fallback_reasons,
        token_counter_revision=decision.token_counter_revision,
    )
    if decision.profile.sentence_language and (
        decision.profile.sentence_resource_revision
        != dict(actual.sentence_resource_revisions).get(decision.profile.sentence_language)
    ):
        raise ChunkingError(ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE, reason="SENTENCE_REVISION_MISMATCH")
    fingerprint = _processing_fingerprint(
        source, profile=profile, decision=decision, resources=declared, admission=admission
    )
    native_warnings: tuple[str, ...] = ()
    if source.parsed_document.format_id is FormatId.MARKDOWN:
        native = adapters.partition_markdown(source.normalized_content)
        trusted_starts = {section.start for section in _sections(source)}
        if {section.start for section in native} != trusted_starts:
            native_warnings = ("HEADER_BOUNDARIES_RECONCILED",)
    chunks: list[PreparedChunk] = []
    total_bytes = 0
    for section in _sections(source):
        for start, end, warnings, protected in _runs(source, section):
            text = source.normalized_content[start:end]
            if not text.strip():
                continue
            spans: tuple[adapters.SplitSpan, ...]
            if protected:
                size = adapters.count_tokens(text)
                if size > profile.target_size or len(text) > profile.hard_character_limit:
                    raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PROTECTED_SPAN_OVERFLOW")
                spans = (adapters.SplitSpan(start=0, end=len(text), token_count=size, overlap_tokens=0),)
            else:
                spans = adapters.split_prose(text, decision=text_decision)
            for span in spans:
                if len(chunks) >= profile.max_chunks or perf_counter() - started > _DEADLINE_SECONDS:
                    raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PREPARATION_BUDGET")
                chunk = _prepared(
                    source,
                    section=section,
                    start=start + span.start,
                    end=start + span.end,
                    size=span.token_count,
                    overlap=span.overlap_tokens,
                    ordinal=len(chunks),
                    decision=decision,
                    fingerprint=fingerprint,
                    warnings=warnings + span.warning_codes + native_warnings,
                    admission=admission,
                    counter=counter,
                )
                total_bytes += len(chunk.content.encode("utf-8"))
                if total_bytes > _MAX_PREPARED_BYTES:
                    raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="PREPARED_BYTES")
                chunks.append(chunk)
    _verify_output(source, chunks)
    return tuple(chunks)


def prepare_chunks(
    source: ChunkingInput,
    *,
    profile: ChunkingProfile = ChunkingProfile(),
    resources: ChunkingResources | None = None,
    model_admission: ModelTokenAdmission | None = None,
    model_counter: ExactModelCounter | None = None,
    pdf_profile: PdfChunkingProfile = PdfChunkingProfile(),
) -> tuple[PreparedChunk, ...]:
    """
    Prepare all chunks atomically in memory, preserving prose sections or verified Python source slices.

    :param source: Exact parser text, verified elements and server-owned workspace/source/version IDs.
    :param profile: Prose profile, defaulting to 500/50 tokens; Python selects its fixed effective-line profile.
    :param resources: Optional pre-inspected resource identities; execution revalidates actual assets.
    :param model_admission: Optional exact-model budget for the final prefixed/suffixed embedding input.
    :param model_counter: Pinned application counter required only for exact-model admission.
    :param pdf_profile: Allowlisted PDF child target, default 768 tokens and zero overlap.
    :returns: Deterministic immutable chunks; no partial result or database write is produced on refusal.
    :raises ChunkingError: If source structure, resources, protected spans or processing budgets fail.
    """
    started = perf_counter()
    try:
        chunks = _prepare(
            source,
            profile=profile,
            resources=resources,
            admission=model_admission,
            counter=model_counter,
            started=started,
            pdf_profile=pdf_profile,
        )
    except ChunkingError as error:
        _logger.info("Chunk preparation refused", extra={"code": error.code.value, "reason": error.reason})
        raise
    decision = chunks[0].decision
    _logger.info(
        "Chunk preparation completed",
        extra={
            "strategy": decision.strategy,
            "profile_revision": decision.profile.profile_revision,
            "fallback_reasons": decision.fallback_reasons,
            "chunk_count": len(chunks),
            "token_histogram": dict(Counter((chunk.effective_size // 100) * 100 for chunk in chunks)),
            "word_count": sum(len(chunk.content.split()) for chunk in chunks),
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        },
    )
    return chunks

"""Pure, revisioned prose-token and Python structural processing profiles."""

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Generic, Literal

from typing_extensions import TypeVar

from apps.workbench.api.parser_registry import ElementKind, FormatId

_SENTENCE_SEPARATORS = ("\n\n", "sentence", "\n", " ")
_STRUCTURAL_SEPARATORS = ("\n\n", "\n", ".", "!", "?", "。", "！", "？", "；", "،", "؛", "؟", "\u200b", " ")
_SEPARATOR_PROFILES = (
    ("prose_token_sentence_aware", _SENTENCE_SEPARATORS),
    ("prose_token_structural_fallback", _STRUCTURAL_SEPARATORS),
)
_CONFIGURED_SEPARATORS = frozenset((*_STRUCTURAL_SEPARATORS, "sentence"))
_REVISION = re.compile(r"text-token-r[1-9][0-9]{0,2}")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}")
_RESOURCE_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:+@=,/-]{0,255}")


class ChunkingErrorCode(StrEnum):
    """Stable refusals without source text, dependency traces or arbitrary identifiers."""

    INVALID_PROFILE = "INVALID_PROFILE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    INVALID_STRUCTURE = "INVALID_STRUCTURE"
    TOKEN_COUNTER_UNAVAILABLE = "TOKEN_COUNTER_UNAVAILABLE"
    SENTENCE_RESOURCE_UNAVAILABLE = "SENTENCE_RESOURCE_UNAVAILABLE"
    EMPTY_INPUT = "EMPTY_INPUT"
    CONTENT_LIMIT_EXCEEDED = "CONTENT_LIMIT_EXCEEDED"
    CHUNKING_FAILED = "CHUNKING_FAILED"
    MODEL_COUNTER_UNAVAILABLE = "MODEL_COUNTER_UNAVAILABLE"
    MODEL_TOKEN_LIMIT_EXCEEDED = "MODEL_TOKEN_LIMIT_EXCEEDED"
    STRUCTURE_LOSS = "STRUCTURE_LOSS"


class ChunkingError(ValueError):
    """Printable errors expose only a stable code; reasons are static application labels."""

    def __init__(self, code: ChunkingErrorCode, *, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason or code.value
        super().__init__(code.value)


def _valid_integer(value: int, *, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_configured_separators(separators: tuple[str, ...]) -> tuple[str, ...]:
    """Validate ordered literal boundaries; only the sentence sentinel has special semantics."""
    if (
        type(separators) is not tuple
        or not 1 <= len(separators) <= len(_CONFIGURED_SEPARATORS)
        or any(not isinstance(item, str) or item not in _CONFIGURED_SEPARATORS for item in separators)
        or len(set(separators)) != len(separators)
    ):
        raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
    return separators


@dataclass(frozen=True)
class ChunkingProfile:
    """Trusted token-sized processing settings; raw separators and counters are not executable input."""

    profile_id: str = "text-token"
    profile_revision: str = "text-token-r1"
    unit: Literal["token"] = "token"
    target_size: int = 500
    overlap: int = 50
    token_counter: str = "tiktoken"
    tokenizer_encoding: str = "o200k_base"
    separator_profile_id: str = "prose_token_sentence_aware"
    separators: tuple[str, ...] = _SENTENCE_SEPARATORS
    sentence_language: str | None = None
    sentence_resource_revision: str | None = None
    require_sentences: bool = False
    hard_character_limit: int = 32_768
    max_chunks: int = 10_000
    sentence_keep_white_spaces: bool = True

    def __post_init__(self) -> None:
        identity_valid = (
            self.profile_id == "text-token"
            and isinstance(self.profile_revision, str)
            and _REVISION.fullmatch(self.profile_revision) is not None
            and self.unit == "token"
            and self.token_counter == "tiktoken"
            and self.tokenizer_encoding == "o200k_base"
        )
        limits_valid = (
            _valid_integer(self.target_size, minimum=1, maximum=8192)
            and _valid_integer(self.overlap, minimum=0, maximum=self.target_size - 1)
            and _valid_integer(self.hard_character_limit, minimum=1, maximum=32_768)
            and _valid_integer(self.max_chunks, minimum=1, maximum=10_000)
        )
        if (
            not identity_valid
            or not limits_valid
            or type(self.require_sentences) is not bool
            or type(self.sentence_keep_white_spaces) is not bool
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        if self.separator_profile_id == "prose_token_configured":
            validate_configured_separators(self.separators)
        elif (
            type(self.separators) is not tuple
            or (self.separator_profile_id, self.separators) not in _SEPARATOR_PROFILES
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        if self.sentence_language is not None and self.sentence_language not in ("en", "ru"):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        if self.sentence_resource_revision is not None and (
            not isinstance(self.sentence_resource_revision, str)
            or _RESOURCE_REVISION.fullmatch(self.sentence_resource_revision) is None
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        if "sentence" not in self.separators and (
            self.require_sentences or self.sentence_language is not None or self.sentence_resource_revision is not None
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)


def structural_token_profile() -> ChunkingProfile:
    """Select reviewed token boundaries without asserting a source's sentence language."""
    return ChunkingProfile(separator_profile_id="prose_token_structural_fallback", separators=_STRUCTURAL_SEPARATORS)


@dataclass(frozen=True, init=False)
class PythonChunkingProfile:
    """Immutable application policy; effective lines are ceil(characters / 45), never tokens."""

    profile_id: str = "python-ast"
    profile_revision: str = "python-ast-r1"
    unit: str = "effective_line"
    target_size: int = 60
    overlap: int = 0
    expected_chars_per_line: int = 45
    oversized_factor: int = 3
    secondary_split_length: int = 60
    secondary_split_overlap: int = 5
    hard_character_limit: int = 32_768
    max_chunks: int = 10_000


@dataclass(frozen=True)
class DocumentFeatures:
    """Metadata projected from a verified parser result, with an explicit declared locale."""

    format_id: FormatId
    has_headings: bool
    element_kinds: tuple[ElementKind, ...]
    language: str = "en"

    def __post_init__(self) -> None:
        if not isinstance(self.format_id, FormatId) or self.format_id not in (
            FormatId.PLAIN_TEXT,
            FormatId.MARKDOWN,
            FormatId.PYTHON,
        ):
            raise ChunkingError(ChunkingErrorCode.UNSUPPORTED_FORMAT)
        if (
            type(self.has_headings) is not bool
            or type(self.element_kinds) is not tuple
            or not self.element_kinds
            or any(not isinstance(kind, ElementKind) for kind in self.element_kinds)
            or self.has_headings != (ElementKind.HEADING in self.element_kinds)
            or (
                self.format_id is FormatId.PLAIN_TEXT
                and any(kind is not ElementKind.PARAGRAPH for kind in self.element_kinds)
            )
            or (self.format_id is FormatId.PYTHON and self.element_kinds != (ElementKind.PYTHON_SOURCE,))
        ):
            raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
        if not isinstance(self.language, str) or _LANGUAGE.fullmatch(self.language) is None:
            raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
        if self.language not in {"en", "ru", "uk"}:
            raise ChunkingError(ChunkingErrorCode.UNSUPPORTED_LANGUAGE)


@dataclass(frozen=True)
class ChunkingResources:
    """Content-free identities of already installed resources; construction performs no lookup."""

    token_counter_revision: str
    sentence_resource_revisions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.token_counter_revision, str)
            or _RESOURCE_REVISION.fullmatch(self.token_counter_revision) is None
        ):
            raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE)
        if type(self.sentence_resource_revisions) is not tuple:
            raise ChunkingError(ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE)
        languages: set[str] = set()
        for item in self.sentence_resource_revisions:
            if (
                type(item) is not tuple
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or _LANGUAGE.fullmatch(item[0]) is None
                or _RESOURCE_REVISION.fullmatch(item[1]) is None
                or item[0] in languages
            ):
                raise ChunkingError(ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE)
            languages.add(item[0])


_Profile_co = TypeVar(
    "_Profile_co", bound=ChunkingProfile | PythonChunkingProfile, default=ChunkingProfile, covariant=True
)


@dataclass(frozen=True)
class ChunkingDecision(Generic[_Profile_co]):
    """One explainable strategy with effective, resource-bound token processing settings."""

    profile: _Profile_co
    strategy: str
    selection_reason: str
    fallback_reasons: tuple[str, ...]
    token_counter_revision: str


def _sentence_fallback_reason(
    features: DocumentFeatures, *, profile: ChunkingProfile, resources: ChunkingResources
) -> str | None:
    if features.language not in ("en", "ru"):
        return "unsupported_sentence_language"
    available = dict(resources.sentence_resource_revisions).get(features.language)
    if available is None:
        return "missing_sentence_resource"
    if profile.sentence_resource_revision is not None and profile.sentence_resource_revision != available:
        return "sentence_resource_revision_mismatch"
    return None


def _resolve_sentence_profile(
    features: DocumentFeatures, *, profile: ChunkingProfile, resources: ChunkingResources
) -> tuple[ChunkingProfile, tuple[str, ...]]:
    if profile.sentence_language is not None and profile.sentence_language != features.language:
        raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
    if "sentence" not in profile.separators:
        return profile, ("structural_profile_requested",)
    reason = _sentence_fallback_reason(features, profile=profile, resources=resources)
    if reason is None:
        revision = dict(resources.sentence_resource_revisions)[features.language]
        return replace(profile, sentence_language=features.language, sentence_resource_revision=revision), ()
    if profile.require_sentences:
        raise ChunkingError(ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE, reason=reason)
    fallback = replace(
        profile,
        separator_profile_id="prose_token_structural_fallback",
        separators=_STRUCTURAL_SEPARATORS,
        sentence_language=None,
        sentence_resource_revision=None,
    )
    return fallback, (reason,)


def resolve_profile(
    features: DocumentFeatures, *, profile: ChunkingProfile, resources: ChunkingResources
) -> ChunkingDecision:
    """
    Resolve one deterministic text policy using verified metadata and installed-resource identities.

    :param features: Verified format, observed element kinds and explicit source language.
    :param profile: Allowlisted token processing parameters; defaults are 500 tokens with 50-token overlap.
    :param resources: Already inspected tokenizer and sentence-resource revisions; no I/O is performed here.
    :returns: One strategy, effective immutable profile and visible fallback reasons.
    :raises ChunkingError: If the profile, structure or required sentence resources are invalid/unavailable.
    """
    if not isinstance(features, DocumentFeatures):
        raise ChunkingError(ChunkingErrorCode.INVALID_STRUCTURE)
    if not isinstance(profile, ChunkingProfile):
        raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE)
    if not isinstance(resources, ChunkingResources):
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE)
    if features.format_id is FormatId.PYTHON:
        raise ChunkingError(ChunkingErrorCode.INVALID_PROFILE, reason="PYTHON_REQUIRES_AST_POLICY")
    effective, fallback_reasons = _resolve_sentence_profile(features, profile=profile, resources=resources)
    if features.format_id is FormatId.MARKDOWN and features.has_headings:
        strategy, reason = "markdown_sections", "markdown_with_usable_headings"
    else:
        strategy = "prose_recursive"
        reason = "plain_text_without_structural_blocks"
        if features.format_id is FormatId.MARKDOWN:
            reason = "markdown_without_usable_headings"
            fallback_reasons = ("missing_usable_headings", *fallback_reasons)
    return ChunkingDecision(
        profile=effective,
        strategy=strategy,
        selection_reason=reason,
        fallback_reasons=fallback_reasons,
        token_counter_revision=resources.token_counter_revision,
    )

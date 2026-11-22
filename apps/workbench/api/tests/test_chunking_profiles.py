"""Pure policy resolution distinguishes token accounting, sentence boundaries and source structure."""

import builtins
from dataclasses import FrozenInstanceError, asdict, replace
from typing import Any

import pytest

from apps.workbench.api.chunking_profiles import (
    ChunkingDecision,
    ChunkingError,
    ChunkingErrorCode,
    ChunkingProfile,
    ChunkingResources,
    DocumentFeatures,
    resolve_profile,
)
from apps.workbench.api.parser_registry import ElementKind, FormatId

_RESOURCES = ChunkingResources(
    token_counter_revision="tiktoken-0.12.0:o200k_base:encoding-sha256",
    sentence_resource_revisions=(("en", "nltk-3.9.2:punkt_tab:en:sha256"), ("ru", "nltk-3.9.2:punkt_tab:ru:sha256")),
)


def _features(*, format_id: FormatId = FormatId.PLAIN_TEXT, language: str = "en") -> DocumentFeatures:
    return DocumentFeatures(
        format_id=format_id, has_headings=False, element_kinds=(ElementKind.PARAGRAPH,), language=language
    )


def _decision(*, language: str = "en", resources: ChunkingResources = _RESOURCES) -> ChunkingDecision:
    return resolve_profile(_features(language=language), profile=ChunkingProfile(), resources=resources)


def test_default_policy_combines_sentence_boundaries_with_500_50_encoding_tokens() -> None:
    """The usable default counts declared tiktoken tokens without requiring an exact model counter."""
    decision = _decision()
    assert decision.strategy == "prose_recursive"
    assert decision.selection_reason == "plain_text_without_structural_blocks"
    assert decision.fallback_reasons == ()
    assert decision.profile.unit == "token"
    assert decision.profile.target_size == 500
    assert decision.profile.overlap == 50
    assert decision.profile.token_counter == "tiktoken"
    assert decision.profile.tokenizer_encoding == "o200k_base"
    assert decision.profile.separators == ("\n\n", "sentence", "\n", " ")
    assert decision.profile.sentence_language == "en"
    assert decision.profile.sentence_resource_revision == dict(_RESOURCES.sentence_resource_revisions)["en"]
    assert decision.token_counter_revision == _RESOURCES.token_counter_revision


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("overlap", [0, 50, 100])
def test_supported_locales_and_overlap_choices_keep_token_accounting(language: str, overlap: int) -> None:
    """Sentence segmentation and token sizing are independent settings in one effective profile."""
    profile = ChunkingProfile(overlap=overlap)
    decision = resolve_profile(_features(language=language), profile=profile, resources=_RESOURCES)
    assert decision.profile.sentence_language == language
    assert decision.profile.overlap == overlap
    assert "sentence" in decision.profile.separators
    assert decision.fallback_reasons == ()
    assert decision.profile.unit == "token"


def test_ukrainian_uses_explicit_token_fallback_without_borrowing_english_punkt() -> None:
    """Supported Ukrainian input retains token accounting with an explicit non-Punkt boundary policy."""
    decision = _decision(language="uk")
    assert decision.fallback_reasons == ("unsupported_sentence_language",)
    assert decision.profile.separator_profile_id == "prose_token_structural_fallback"
    assert "sentence" not in decision.profile.separators
    assert all(delimiter in decision.profile.separators for delimiter in ("\n\n", "\n", ".", "!", "?", " "))
    assert decision.profile.sentence_language is None
    assert decision.profile.sentence_resource_revision is None
    assert decision.profile.unit == "token"
    assert (decision.profile.target_size, decision.profile.overlap) == (500, 50)


@pytest.mark.parametrize("language", ["zh", "ja", "th", "ar", "en-us"])
def test_other_canonical_locales_are_outside_the_enabled_language_scope(language: str) -> None:
    """Well-formed locales outside EN/RU/UK receive a stable refusal rather than implicit support."""
    with pytest.raises(ChunkingError) as error:
        _decision(language=language)
    assert error.value.code is ChunkingErrorCode.UNSUPPORTED_LANGUAGE


def test_missing_sentence_resources_are_an_explicit_token_fallback() -> None:
    """An installed token counter stays usable when optional sentence assets are absent."""
    decision = _decision(resources=ChunkingResources(token_counter_revision="tiktoken:o200k_base:r1"))
    assert decision.fallback_reasons == ("missing_sentence_resource",)
    assert decision.profile.unit == "token"
    assert decision.profile.tokenizer_encoding == "o200k_base"
    assert "sentence" not in decision.profile.separators


@pytest.mark.parametrize("language", ["en", "uk"])
def test_required_sentence_fidelity_refuses_missing_or_unsupported_resources(language: str) -> None:
    """Strict sentence profiles cannot silently take the structural fallback."""
    with pytest.raises(ChunkingError, match="^SENTENCE_RESOURCE_UNAVAILABLE$"):
        resolve_profile(
            _features(language=language),
            profile=ChunkingProfile(require_sentences=True),
            resources=ChunkingResources(token_counter_revision="tiktoken:o200k_base:r1"),
        )


def test_sentence_resource_revision_mismatch_is_visible_and_can_be_strict() -> None:
    """A requested sentence resource is never silently replaced with another revision."""
    profile = ChunkingProfile(sentence_resource_revision="nltk:requested-r2")
    decision = resolve_profile(_features(), profile=profile, resources=_RESOURCES)
    assert decision.fallback_reasons == ("sentence_resource_revision_mismatch",)
    with pytest.raises(ChunkingError) as error:
        resolve_profile(_features(), profile=replace(profile, require_sentences=True), resources=_RESOURCES)
    assert error.value.code is ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE


def test_explicit_sentence_language_must_match_verified_features() -> None:
    """Conflicting locale configuration fails rather than ignoring a fingerprinted parameter."""
    with pytest.raises(ChunkingError, match="^INVALID_PROFILE$"):
        resolve_profile(_features(language="ru"), profile=ChunkingProfile(sentence_language="en"), resources=_RESOURCES)
    decision = resolve_profile(
        _features(language="ru"), profile=ChunkingProfile(sentence_language="ru"), resources=_RESOURCES
    )
    assert decision.profile.sentence_language == "ru"


def test_markdown_headings_select_sections_even_when_code_is_present() -> None:
    """A protected Python fence remains Markdown data and never selects an AST parser."""
    features = DocumentFeatures(
        format_id=FormatId.MARKDOWN,
        has_headings=True,
        element_kinds=(ElementKind.HEADING, ElementKind.PROTECTED_RAW, ElementKind.PARAGRAPH),
    )
    decision = resolve_profile(features, profile=ChunkingProfile(), resources=_RESOURCES)
    assert decision.strategy == "markdown_sections"
    assert decision.selection_reason == "markdown_with_usable_headings"
    assert decision.fallback_reasons == ()


def test_markdown_without_headings_records_both_structural_and_resource_fallbacks() -> None:
    """Unheaded Markdown uses prose refinement with separate reasons for independent fallbacks."""
    features = DocumentFeatures(
        format_id=FormatId.MARKDOWN, has_headings=False, element_kinds=(ElementKind.PROTECTED_RAW,), language="uk"
    )
    decision = resolve_profile(features, profile=ChunkingProfile(), resources=_RESOURCES)
    assert decision.strategy == "prose_recursive"
    assert decision.selection_reason == "markdown_without_usable_headings"
    assert decision.fallback_reasons == ("missing_usable_headings", "unsupported_sentence_language")


def test_heading_only_markdown_has_a_real_section_policy() -> None:
    """A document containing only verified headings is still a supported structural input."""
    features = DocumentFeatures(format_id=FormatId.MARKDOWN, has_headings=True, element_kinds=(ElementKind.HEADING,))
    assert resolve_profile(features, profile=ChunkingProfile(), resources=_RESOURCES).strategy == "markdown_sections"


@pytest.mark.parametrize(
    "format_id", [item for item in FormatId if item not in (FormatId.PLAIN_TEXT, FormatId.MARKDOWN)]
)
def test_nontext_formats_are_not_promoted_into_prose(format_id: FormatId) -> None:
    """Planned PDF, code, tables and media adapters remain unavailable to this resolver."""
    with pytest.raises(ChunkingError, match="^UNSUPPORTED_FORMAT$"):
        _features(format_id=format_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"format_id": "plain_text"},
        {"has_headings": "false"},
        {"has_headings": True},
        {"element_kinds": ()},
        {"element_kinds": [ElementKind.PARAGRAPH]},
        {"element_kinds": ("paragraph",)},
        {"element_kinds": ("python_ast",)},
        {"element_kinds": (ElementKind.PROTECTED_RAW,)},
        {"element_kinds": (ElementKind.HEADING,), "has_headings": True},
    ],
)
def test_unverified_or_inconsistent_structure_is_rejected(changes: dict[str, Any]) -> None:
    """Typed feature contracts cannot claim unsupported structures or fabricated headings."""
    with pytest.raises(ChunkingError):
        replace(_features(), **changes)


@pytest.mark.parametrize("language", ["", "EN", "english", "../../en", "en\nprivate", "https://example.com", "uk_UA"])
def test_invalid_language_identifiers_are_not_executable_or_unbounded(language: str) -> None:
    """Only bounded locale identifiers can reach sentence-resource selection."""
    with pytest.raises(ChunkingError, match="^INVALID_PROFILE$"):
        _features(language=language)


@pytest.mark.parametrize(
    "changes",
    [
        {"profile_id": "unknown"},
        {"profile_id": "evil.module.Parser"},
        {"profile_revision": ""},
        {"profile_revision": "text-token-r0"},
        {"unit": "word"},
        {"unit": "char"},
        {"unit": "model_token"},
        {"token_counter": "exact_qwen"},
        {"tokenizer_encoding": ""},
        {"tokenizer_encoding": "cl100k_base"},
        {"target_size": 0},
        {"target_size": True},
        {"target_size": 8193},
        {"target_size": "500"},
        {"overlap": -1},
        {"overlap": 500},
        {"overlap": 1.5},
        {"hard_character_limit": 0},
        {"hard_character_limit": 32_769},
        {"max_chunks": 0},
        {"max_chunks": 10_001},
        {"require_sentences": "yes"},
        {"separator_profile_id": "regex"},
        {"separators": (".*",)},
        {"separators": ("sentence", "\n\n", "\n", " ")},
        {"separators": ["\n\n", "sentence", "\n", " "]},
        {"sentence_language": "uk"},
        {"sentence_resource_revision": ""},
    ],
)
def test_invalid_or_unreviewed_profiles_fail_closed(changes: dict[str, Any]) -> None:
    """Caller-supplied units, counters and delimiters cannot bypass the reviewed processing policy."""
    with pytest.raises(ChunkingError, match="^INVALID_PROFILE$"):
        ChunkingProfile(**changes)


@pytest.mark.parametrize("revision", ["", " ", "private\nresource", None])
def test_counter_identity_is_required_even_without_exact_model_admission(revision: Any) -> None:
    """Token-based processing cannot proceed with an absent or unsafe counter revision."""
    with pytest.raises(ChunkingError, match="^TOKEN_COUNTER_UNAVAILABLE$"):
        ChunkingResources(token_counter_revision=revision)


@pytest.mark.parametrize(
    "revisions",
    [
        [("en", "r1")],
        (["en", "r1"],),
        (("en", ""),),
        (("en", "r1"), ("en", "r2")),
        (("en", "r1", "extra"),),
        (("../../en", "r1"),),
    ],
)
def test_sentence_resource_metadata_is_immutable_unique_and_bounded(revisions: Any) -> None:
    """Malformed resource metadata cannot create ambiguous language-to-revision decisions."""
    with pytest.raises(ChunkingError, match="^SENTENCE_RESOURCE_UNAVAILABLE$"):
        ChunkingResources(token_counter_revision="tiktoken:o200k_base:r1", sentence_resource_revisions=revisions)


def test_resolver_is_deterministic_without_file_or_dependency_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pure resolution uses only supplied contracts, never installed-package or filesystem lookups."""

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("Policy attempted I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    first = _decision()
    second = _decision()
    assert asdict(first) == asdict(second)
    assert first == second


def test_profile_and_resource_revisions_are_preserved_for_fingerprinting() -> None:
    """Every effective parameter and dependency revision remains visible to the processing manifest."""
    base = _decision()
    profiles = [
        ChunkingProfile(profile_revision="text-token-r2"),
        ChunkingProfile(target_size=400),
        ChunkingProfile(overlap=100),
        ChunkingProfile(hard_character_limit=1000),
        ChunkingProfile(max_chunks=5),
        ChunkingProfile(require_sentences=True),
    ]
    for profile in profiles:
        assert resolve_profile(_features(), profile=profile, resources=_RESOURCES) != base
    counter_changed = replace(_RESOURCES, token_counter_revision="tiktoken:o200k_base:encoding-r2")
    sentence_changed = replace(_RESOURCES, sentence_resource_revisions=(("en", "nltk:en:r2"),))
    assert _decision(resources=counter_changed) != base
    assert _decision(resources=sentence_changed) != base
    assert _decision(language="ru") != base


def test_explicit_structural_profile_is_visible_even_when_sentence_assets_exist() -> None:
    """A deliberately selected structural policy never re-enables sentence splitting implicitly."""
    fallback = _decision(language="uk").profile
    decision = resolve_profile(_features(), profile=fallback, resources=_RESOURCES)
    assert decision.profile == fallback
    assert decision.fallback_reasons == ("structural_profile_requested",)


def test_contracts_cannot_be_mutated_after_resolution() -> None:
    """Profiles, decisions and resource tuples remain immutable downstream data."""
    for instance, field, value in (
        (_decision(), "strategy", "python_ast"),
        (ChunkingProfile(), "unit", "word"),
        (_RESOURCES, "token_counter_revision", "changed"),
        (_features(), "format_id", FormatId.PDF),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, field, value)


def test_printable_errors_never_echo_optional_reason_values() -> None:
    """Exception surfaces remain low-cardinality even if an adapter attaches an internal reason."""
    error = ChunkingError(ChunkingErrorCode.CHUNKING_FAILED, reason="private-text")
    assert str(error) == "CHUNKING_FAILED"
    assert "private-text" not in repr(error)

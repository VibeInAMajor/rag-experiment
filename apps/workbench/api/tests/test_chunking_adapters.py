"""Real offline Haystack splitter qualification, token accounting and exact source coordinates."""

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import nltk
import pytest
import tiktoken

from apps.workbench.api import chunking_adapters as adapters
from apps.workbench.api.chunking_adapters import (
    count_tokens,
    inspect_chunking_resources,
    partition_markdown,
    split_prose,
)
from apps.workbench.api.chunking_profiles import (
    ChunkingDecision,
    ChunkingError,
    ChunkingErrorCode,
    ChunkingProfile,
    DocumentFeatures,
    resolve_profile,
)
from apps.workbench.api.parser_registry import ElementKind, FormatId
from haystack import Document
from haystack.components.preprocessors import RecursiveDocumentSplitter


@pytest.fixture(autouse=True)
def forbid_resource_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test requires provisioned resources and refuses URL-backed warm-up paths."""

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Runtime resource downloads are forbidden")

    monkeypatch.setattr(nltk, "download", forbidden)
    monkeypatch.setattr(tiktoken, "get_encoding", forbidden)


def _decision(*, language: str = "en", overlap: int = 50, target_size: int = 500) -> ChunkingDecision:
    return resolve_profile(
        DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,), language=language),
        profile=ChunkingProfile(target_size=target_size, overlap=overlap),
        resources=inspect_chunking_resources(),
    )


def _assert_source_spans(text: str, decision: ChunkingDecision) -> None:
    spans = split_prose(text, decision=decision)
    previous_end = 0
    previous_start = -1
    for span in spans:
        assert previous_start < span.start < span.end <= len(text)
        assert not text[previous_end : span.start].strip()
        content = text[span.start : span.end]
        assert content.strip()
        assert count_tokens(content) == span.token_count <= decision.profile.target_size
        assert len(content) <= decision.profile.hard_character_limit
        assert span.overlap_tokens == (
            count_tokens(text[span.start : previous_end]) if span.start < previous_end else 0
        )
        assert 0 <= span.overlap_tokens <= decision.profile.overlap
        assert span.end > previous_end
        assert "page_number" not in dict(span.native_metadata)
        assert dict(span.native_metadata)["split_idx_start"] == span.start
        previous_start, previous_end = span.start, span.end
    assert spans and not text[previous_end:].strip()
    assert spans == split_prose(text, decision=decision)


def test_pinned_assets_qualify_both_sentence_locales() -> None:
    """Only the pinned local encoding and EN/RU tables qualify sentence segmentation."""
    resources = inspect_chunking_resources()
    assert resources.token_counter_revision.startswith("tiktoken:0.14.0:o200k_base:")
    assert set(dict(resources.sentence_resource_revisions)) == {"en", "ru"}
    assert all("nltk:3.10.4:punkt_tab:" in revision for _, revision in resources.sentence_resource_revisions)
    assert _decision(language="en").profile.sentence_language == "en"
    assert _decision(language="ru").profile.sentence_language == "ru"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_sentence_and_token_modes_are_enabled_together(language: str) -> None:
    """The native component uses both sentence boundaries and the same token counter."""
    decision = _decision(language=language)
    splitter = adapters._splitter(decision)
    assert isinstance(splitter, RecursiveDocumentSplitter)
    assert splitter.split_units == "token"
    assert splitter.split_length == 500
    assert splitter.split_overlap == 50
    assert splitter.separators == ["\n\n", "sentence", "\n", " "]
    sentence_tokenizer: Any = splitter.nltk_tokenizer
    assert sentence_tokenizer.language == language
    assert splitter.tiktoken_tokenizer is not None
    assert splitter.tiktoken_tokenizer.name == "o200k_base"
    assert splitter._is_warmed_up


def test_counter_uses_ordinary_text_for_special_token_spellings() -> None:
    """Document content never requests tiktoken's privileged special-token mode."""
    text = "hello <|endoftext|> world <|endofprompt|>"
    assert count_tokens(text) == len(adapters._encoding().encode_ordinary(text))
    _assert_source_spans(text * 100, _decision())


def test_offline_encoding_configuration_matches_pinned_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-download constructor retains the upstream o200k regex, ranks and special-token IDs."""
    import tiktoken_ext.openai_public as upstream
    from tiktoken.load import load_tiktoken_bpe

    def local_ranks(_path: str, expected_hash: str) -> dict[bytes, int]:
        return load_tiktoken_bpe(str(adapters._ASSET_ROOT / "o200k_base.tiktoken"), expected_hash=expected_hash)

    monkeypatch.setattr(upstream, "load_tiktoken_bpe", local_ranks)
    expected = tiktoken.Encoding(**upstream.o200k_base())
    for text in ("hello world", "Привіт, світе!", "Русский текст без потерь.", "🧑🏽‍🚀", "<|endoftext|>"):
        assert adapters._encoding().encode_ordinary(text) == expected.encode_ordinary(text)


@pytest.mark.parametrize("overlap", [0, 50, 100])
@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("en", "A simple sentence. " * 300),
        ("en", ("First paragraph with English prose. " * 40 + "\n\n") * 5),
        ("en", "English prose with CRLF.\r\n\r\n" * 150),
        ("en", "This sentence has no ending until the last word " * 250 + "."),
        ("en", "unbrokentext" * 1000),
        ("ru", "Первое предложение. Второе предложение! Третье предложение? " * 140),
        ("ru", "Первая строка.\r\n\r\nВторая строка!\r\n" * 120),
        ("uk", "Українська мова. Наступне речення! Ще одне питання? " * 140),
        ("uk", "Нерозривнийукраїнськийтекст" * 300),
        ("en", "𠮷" * 600),
        ("en", "🧑🏽‍🚀🙂👨‍👩‍👧‍👦" * 160),
    ],
)
def test_source_coverage_and_real_token_budgets(language: str, text: str, overlap: int) -> None:
    """Paragraph, sentence, literal delimiter and terminal paths preserve every source character."""
    _assert_source_spans(text, _decision(language=language, overlap=overlap))


def test_english_sentence_golden_uses_native_boundaries() -> None:
    """Pinned sentence grouping is reproducible without LangChain output-parity claims."""
    text = "A simple sentence. " * 300
    spans = split_prose(text, decision=_decision())
    assert [(span.start, span.end, span.token_count, span.overlap_tokens) for span in spans] == [
        (0, 1900, 401, 0),
        (1670, 3800, 450, 50),
        (3570, 5700, 450, 50),
    ]
    assert all(not span.warning_codes for span in spans)
    assert all(text[: span.end].endswith(". ") for span in spans)


def test_native_unicode_loss_is_detected_and_repaired() -> None:
    """The SDK's arbitrary token slicing cannot replace an original scalar with U+FFFD."""
    text = "𠮷" * 600
    decision = _decision()
    native = adapters._splitter(decision).run(documents=[Document(content=text)])["documents"]
    assert any(
        document.content
        != text[document.meta["split_idx_start"] : document.meta["split_idx_start"] + len(document.content)]
        for document in native
    )
    spans = split_prose(text, decision=decision)
    assert all("NATIVE_OUTPUT_REPAIRED" in span.warning_codes for span in spans)
    assert all("\ufffd" not in text[span.start : span.end] for span in spans)
    _assert_source_spans(text, decision)


def test_ukrainian_uses_explicit_token_policy() -> None:
    """Ukrainian does not silently use an English Punkt model or another size unit."""
    decision = _decision(language="uk")
    assert decision.profile.sentence_language is None
    assert "sentence" not in decision.profile.separators
    assert decision.fallback_reasons
    assert decision.profile.unit == "token"
    assert decision.profile.target_size == 500
    assert decision.profile.overlap == 50


@pytest.mark.parametrize("language", ["fr", "de", "zh", "th", "en-gb"])
def test_other_languages_are_refused_before_adapter_selection(language: str) -> None:
    """Only the explicitly supported English, Russian and Ukrainian locales enter splitting."""
    with pytest.raises(ChunkingError) as failure:
        _decision(language=language)
    assert failure.value.code == ChunkingErrorCode.UNSUPPORTED_LANGUAGE


def test_missing_counter_assets_are_an_explicit_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The adapter never substitutes an ambient tokenizer or fetches a missing counter."""
    monkeypatch.setattr(adapters, "_ASSET_ROOT", tmp_path)
    with pytest.raises(ChunkingError) as failure:
        inspect_chunking_resources()
    assert failure.value.code == ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE


def test_changed_counter_asset_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Changed local BPE bytes cannot retain the reviewed counter identity."""
    (tmp_path / "o200k_base.tiktoken").write_bytes(b"untrusted BPE data")
    monkeypatch.setattr(adapters, "_ASSET_ROOT", tmp_path)
    with pytest.raises(ChunkingError) as failure:
        inspect_chunking_resources()
    assert failure.value.reason == "COUNTER_ASSET_MISMATCH"


def test_missing_sentence_tables_only_disable_sentence_qualification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Counter availability remains distinct from language-resource availability."""
    source = adapters._ASSET_ROOT / "o200k_base.tiktoken"
    (tmp_path / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(adapters, "_ASSET_ROOT", tmp_path)
    resources = inspect_chunking_resources()
    assert resources.sentence_resource_revisions == ()
    decision = resolve_profile(
        DocumentFeatures(FormatId.PLAIN_TEXT, False, (ElementKind.PARAGRAPH,)),
        profile=ChunkingProfile(),
        resources=resources,
    )
    assert decision.fallback_reasons
    assert decision.profile.unit == "token"


def test_resources_cannot_change_after_policy_resolution() -> None:
    """A stale decision cannot silently adopt a different counter identity."""
    decision = replace(_decision(), token_counter_revision="different-counter-r1")
    with pytest.raises(ChunkingError) as failure:
        split_prose("Source text", decision=decision)
    assert failure.value.reason == "COUNTER_REVISION_MISMATCH"


def test_tiny_token_budget_never_splits_a_unicode_scalar() -> None:
    """An indivisible scalar larger than the configured budget fails rather than losing bytes."""
    with pytest.raises(ChunkingError) as failure:
        split_prose("𠮷" * 10, decision=_decision(target_size=1, overlap=0))
    assert failure.value.code == ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED
    assert failure.value.reason == "UNICODE_SCALAR_TOKEN_BUDGET"


def test_chunk_count_budget_is_enforced() -> None:
    """The final native output cannot exceed the qualified chunk allocation limit."""
    decision = _decision()
    decision = replace(decision, profile=replace(decision.profile, max_chunks=1))
    with pytest.raises(ChunkingError) as failure:
        split_prose("A simple sentence. " * 300, decision=decision)
    assert failure.value.reason == "MAX_CHUNKS"


def test_impossible_chunk_budget_is_refused_before_sdk_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tiny target cannot allocate arbitrarily many native Documents before the count check."""
    decision = _decision(target_size=1, overlap=0)
    decision = replace(decision, profile=replace(decision.profile, max_chunks=2))

    def forbidden_splitter(_decision: ChunkingDecision) -> Any:
        raise AssertionError("Impossible output capacity reached the SDK")

    monkeypatch.setattr(adapters, "_splitter", forbidden_splitter)
    with pytest.raises(ChunkingError) as failure:
        split_prose("many separate text tokens cannot fit", decision=decision)
    assert failure.value.reason == "MAX_CHUNKS"


@pytest.mark.parametrize(
    "text",
    [
        "preamble\n\n# Heading\nbody\n\n## Child\nchild body",
        "\r\n# Heading\r\n\r\nbody\r\n",
        "# First\n# Second\n",
        "# First\n\nbody\n\n## Last heading\n",
        "# Parent\n\n```\n# Inside fence\n```\n\n## Child\nbody",
        "Title\n=====\n\nbody",
        "---\n# YAML comment\n---\n\n# Real\nbody",
    ],
)
def test_native_markdown_partition_preserves_original_text(text: str) -> None:
    """The native header adapter returns exact partitions while parser authority stays separate."""
    sections = partition_markdown(text)
    assert "".join(text[section.start : section.end] for section in sections) == text
    assert all(section.start < section.end for section in sections)
    assert sections == partition_markdown(text)


def test_native_header_debug_cannot_leak_heading_content(caplog: pytest.LogCaptureFixture) -> None:
    """SDK header interpolation is suppressed even when the host enables debug logging."""
    caplog.set_level(logging.DEBUG)
    partition_markdown("# heading-content-canary\n\nbody-content-canary")
    diagnostics = caplog.text + repr([record.__dict__ for record in caplog.records])
    assert "heading-content-canary" not in diagnostics
    assert "body-content-canary" not in diagnostics

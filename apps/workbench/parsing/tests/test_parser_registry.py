"""The reviewed catalog cannot promote an upstream converter into app support."""

from dataclasses import FrozenInstanceError
from importlib import metadata
from typing import Any

import pytest

from apps.workbench.parsing import parser_registry
from apps.workbench.parsing.parser_registry import (
    ElementKind,
    FormatId,
    ParseErrorCode,
    ParsingError,
    UploadLimits,
    format_rules,
    parser_descriptors,
    select_parser,
)


def test_catalog_covers_each_format_once_with_no_extension_collisions() -> None:
    """The complete vocabulary has one descriptor and one classification rule per family."""
    rules = format_rules()
    descriptors = parser_descriptors()
    assert {rule.format_id for rule in rules} == set(FormatId)
    assert len(rules) == len(FormatId)
    assert {item for descriptor in descriptors for item in descriptor.accepted_format_ids} == set(FormatId)
    assert len(descriptors) == len(FormatId)
    extensions = [extension for rule in rules for extension in rule.extensions]
    assert len(extensions) == len(set(extensions))


@pytest.mark.parametrize("format_id", list(FormatId))
def test_only_qualified_text_formats_can_select_a_parser(format_id: FormatId) -> None:
    """Each family resolves explicitly; planned adapters never execute."""
    if format_id is FormatId.PDF:
        descriptor = select_parser(format_id)
        assert descriptor.qualified and descriptor.available
        assert descriptor.parser_id == "docling-pdf" and descriptor.max_bytes == 8_388_608
        assert descriptor.deadline_ms == 180_000 and "NO_OCR" in descriptor.constraints
        return
    if format_id in (FormatId.PLAIN_TEXT, FormatId.MARKDOWN, FormatId.PYTHON):
        descriptor = select_parser(format_id)
        assert descriptor.accepted_format_ids == (format_id,)
        assert descriptor.available and descriptor.qualified
        assert descriptor.parser_revision.endswith("-r1")
        assert descriptor.dependency_revisions == ("haystack-ai==3.5.0",)
        assert descriptor.max_bytes == 1_048_576
        assert descriptor.max_elements == 4096
        assert descriptor.deadline_ms == 2000
        return
    with pytest.raises(ParsingError) as error:
        select_parser(format_id)
    assert error.value.code is (
        ParseErrorCode.UNSUPPORTED_FORMAT if format_id is FormatId.UNSUPPORTED else ParseErrorCode.PARSER_UNAVAILABLE
    )


@pytest.mark.parametrize(
    ("format_id", "extension", "mime"),
    [
        (FormatId.PLAIN_TEXT, ".txt", "text/plain"),
        (FormatId.MARKDOWN, ".md", "text/markdown"),
        (FormatId.MARKDOWN, ".markdown", "text/x-markdown"),
        (FormatId.MARKDOWN, ".md", "text/plain"),
        (FormatId.PDF, ".pdf", "application/pdf"),
        (FormatId.WORD_DOCUMENT, ".doc", "application/msword"),
        (FormatId.PRESENTATION, ".ppt", "application/vnd.ms-powerpoint"),
        (FormatId.WORKBOOK, ".xls", "application/vnd.ms-excel"),
        (FormatId.DELIMITED_TABLE, ".csv", "text/csv"),
        (FormatId.DELIMITED_TABLE, ".tsv", "text/tab-separated-values"),
        (FormatId.JSON, ".json", "text/json"),
        (FormatId.JSON_LINES, ".ndjson", "application/x-ndjson"),
        (FormatId.YAML, ".yml", "application/x-yaml"),
        (FormatId.TOML, ".toml", "application/toml"),
        (FormatId.XML, ".xml", "text/xml"),
        (FormatId.PYTHON, ".py", "text/x-python"),
        (FormatId.SOURCE_CODE, ".js", "application/javascript"),
        (FormatId.EMAIL, ".eml", "message/rfc822"),
        (FormatId.TIMED_TRANSCRIPT, ".srt", "application/x-subrip"),
        (FormatId.AUDIO, ".wav", "audio/wav"),
        (FormatId.VIDEO, ".mov", "video/quicktime"),
        (FormatId.RASTER_IMAGE, ".jpeg", "image/jpeg"),
    ],
)
def test_format_alias_matrix(format_id: FormatId, extension: str, mime: str) -> None:
    """Reviewed aliases remain distinct from application qualification."""
    rule = next(item for item in format_rules() if item.format_id is format_id)
    assert extension in rule.extensions
    assert mime in rule.mime_aliases


def test_planned_formats_have_no_executable_elements_or_resource_budget() -> None:
    """Planned metadata cannot be mistaken for a working extraction adapter."""
    planned = [descriptor for descriptor in parser_descriptors() if not descriptor.qualified]
    assert planned
    for descriptor in planned:
        assert not descriptor.available
        assert descriptor.emitted_element_kinds == ()
        assert descriptor.required_provenance == ()
        assert descriptor.parser_revision == "not-qualified"
        assert descriptor.max_bytes == descriptor.max_elements == descriptor.deadline_ms == 0
        assert "PLANNED_APP_ADAPTER" in descriptor.constraints


def test_catalog_and_qualification_are_immutable() -> None:
    """Catalog callers cannot mutate qualification, aliases or nested collections."""
    descriptor = select_parser(FormatId.MARKDOWN)
    attribute = "qualified"
    with pytest.raises(FrozenInstanceError):
        setattr(descriptor, attribute, False)
    attribute = "extensions"
    with pytest.raises(FrozenInstanceError):
        setattr(format_rules()[0], attribute, (".exe",))
    assert isinstance(parser_descriptors(), tuple)
    assert descriptor.emitted_element_kinds == (ElementKind.PARAGRAPH, ElementKind.HEADING, ElementKind.PROTECTED_RAW)
    assert parser_descriptors() == parser_descriptors()


@pytest.mark.parametrize("installed", [None, "3.4.0", "99.0.0"])
def test_missing_or_unreviewed_dependency_disables_only_execution(
    monkeypatch: pytest.MonkeyPatch, installed: str | None
) -> None:
    """Reviewed code is still qualified but cannot execute against missing or changed dependencies."""

    def package_version(name: str) -> str:
        assert name == "haystack-ai"
        if installed is None:
            raise metadata.PackageNotFoundError("sensitive path")
        return installed

    monkeypatch.setattr(parser_registry.metadata, "version", package_version)
    assert not any(descriptor.available for descriptor in parser_descriptors())
    assert sum(descriptor.qualified for descriptor in parser_descriptors()) == 4
    with pytest.raises(ParsingError, match="^PARSER_UNAVAILABLE$") as error:
        select_parser(FormatId.PLAIN_TEXT)
    assert error.value.code is ParseErrorCode.PARSER_UNAVAILABLE


@pytest.mark.parametrize("name", ["plain_text", "application/pdf", "evil.module.Parser", "https://example.com/parser"])
def test_external_names_are_not_parser_selectors(name: Any) -> None:
    """Parser selection accepts typed canonical IDs, never imports or external locations."""
    with pytest.raises(ParsingError, match="^UNSUPPORTED_FORMAT$"):
        select_parser(name)


@pytest.mark.parametrize("field", ["max_bytes", "max_elements", "deadline_ms"])
@pytest.mark.parametrize("value", [0, -1, 1_048_577, True, 1.5, "100"])
def test_limits_cannot_be_disabled_or_raised(field: str, value: Any) -> None:
    """Per-call overrides cannot weaken the qualified allocation limits."""
    with pytest.raises(ValueError, match="qualified budget"):
        UploadLimits(**{field: value})


def test_limits_allow_tighter_bounded_calls() -> None:
    """Callers can lower independent limits without mutating a shared default."""
    limits = UploadLimits(max_bytes=64, max_elements=2, deadline_ms=1)
    assert (limits.max_bytes, limits.max_elements, limits.deadline_ms) == (64, 2, 1)
    attribute = "max_bytes"
    with pytest.raises(FrozenInstanceError):
        setattr(limits, attribute, 100)


def test_failure_message_never_interpolates_optional_reason() -> None:
    """An exception's printable surface contains only its reviewed refusal code."""
    error = ParsingError(ParseErrorCode.PARSE_FAILED, reason="private-content")
    assert str(error) == "PARSE_FAILED"
    assert "private-content" not in repr(error)

"""Bounded source inspection and structure projection never guess unsupported formats."""

import hashlib
import logging
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from apps.workbench.api import parsing
from apps.workbench.api.parser_registry import ElementKind, FormatId, ParseErrorCode, ParsingError, UploadLimits
from apps.workbench.api.parsing import inspect_format, parse_source
from haystack import Document
from haystack.components.converters.txt import TextFileToDocument


@pytest.mark.parametrize(
    ("name", "mime", "content", "expected"),
    [
        ("notes.txt", None, b"notes", FormatId.PLAIN_TEXT),
        ("notes.TXT", "text/plain", b"notes", FormatId.PLAIN_TEXT),
        ("notes.txt", "TEXT/PLAIN", b"notes", FormatId.PLAIN_TEXT),
        ("notes.txt", "text/plain; charset=utf-8", b"notes", FormatId.PLAIN_TEXT),
        ("notes.txt", "text/plain", b"\xef\xbb\xbfnotes", FormatId.PLAIN_TEXT),
        ("notes.txt", None, "Привіт, світе!".encode(), FormatId.PLAIN_TEXT),
        ("notes.txt", None, b"first\r\nsecond\r\n", FormatId.PLAIN_TEXT),
        ("notes.md", None, b"# notes", FormatId.MARKDOWN),
        ("notes.MD", "text/markdown", b"# notes", FormatId.MARKDOWN),
        ("notes.markdown", "text/x-markdown", b"# notes", FormatId.MARKDOWN),
        ("notes.md", "text/plain", b"# notes", FormatId.MARKDOWN),
        ("notes.md", "text/markdown; charset=UTF-8", b"# notes", FormatId.MARKDOWN),
        ("notes.md", None, b"\xef\xbb\xbf# notes", FormatId.MARKDOWN),
        ("Огляд.md", None, "# Огляд\n\nТекст".encode(), FormatId.MARKDOWN),
    ],
)
def test_reviewed_text_aliases(name: str, mime: str | None, content: bytes, expected: FormatId) -> None:
    """Only reviewed names, MIME aliases and valid UTF-8 qualify as text."""
    result = inspect_format(content, safe_basename=name, declared_type=mime)
    assert result.format_id == expected
    assert result.content_sha256 == hashlib.sha256(content).hexdigest()
    assert result.bytes_count == len(content)
    assert result.safe_basename == name
    assert result.detector_revision
    assert result.evidence_codes
    assert result.ambiguous is False


@pytest.mark.parametrize(
    ("name", "mime", "content"),
    [
        ("notes.txt", "application/pdf", b"notes"),
        ("notes.txt", "text/markdown", b"notes"),
        ("notes.md", "application/octet-stream", b"notes"),
        ("notes.txt", "text/plain\r\nX-Secret: value", b"notes"),
        ("notes.txt", "text/plain; charset=latin-1", b"notes"),
        ("notes.txt", "text/plain; invalid", b"notes"),
        ("notes.txt", None, b"%PDF-1.7\nThis is a PDF"),
        ("notes.txt", None, b" " * 600 + b"%PDF-1.7\nHidden PDF"),
        ("notes.md", None, b"\xef\xbb\xbf%PDF-1.7\nHidden PDF"),
        ("notes.txt", None, b"PK\x03\x04fake office container"),
        ("notes.txt", None, b"PK\x05\x06empty archive"),
        ("notes.txt", None, b"MZexecutable"),
        ("notes.txt", None, b"\x7fELFexecutable"),
        ("notes.txt", None, b"\x89PNG\r\n\x1a\n"),
        ("notes.txt", None, b"\xff\xd8\xff\xe0image"),
        ("notes.txt", None, b"\x1f\x8bcompressed"),
        ("notes.txt", None, b"hello\0world"),
        ("notes.md", None, b"\xff\xfe\x00\x00"),
        ("notes.txt", None, b"\xffbroken utf-8"),
        ("notes.md", None, b"\xed\xa0\x80surrogate"),
        ("notes.txt", None, b"\xc0\xafoverlong utf-8"),
        ("notes.txt", None, b""),
        ("notes.md", None, b" \r\n\t"),
        ("notes.txt", None, b"\xef\xbb\xbf"),
        ("notes.exe", None, b"readable executable label"),
        ("notes.exe.txt", None, b"misleading executable suffix"),
        ("notes.ps1.md", None, b"misleading executable suffix"),
        ("notes.pdf.txt", None, b"misleading document suffix"),
        ("notes.pdf", "application/pdf", b"not a PDF"),
        ("notes.docx", None, b"PK\x03\x04unqualified Office"),
        ("notes.zip", None, b"PK\x03\x04unqualified archive"),
        ("notes.yaml", None, b"!!python/object/apply:os.system [echo no]"),
        ("notes", None, b"notes"),
        ("../notes.txt", None, b"notes"),
        ("..\\notes.md", None, b"notes"),
        ("/notes.txt", None, b"notes"),
        ("C:\\notes.txt", None, b"notes"),
        ("notes.txt:payload", None, b"notes"),
        ("notes.txt\0.exe", None, b"notes"),
        ("notes\n.txt", None, b"notes"),
        ("notes.txt ", None, b"notes"),
        ("notes.txt.", None, b"notes"),
        ("notes\ud800.txt", None, b"notes"),
        ("notes\u202e.txt", None, b"notes"),
        ("https://example.test/notes.txt", None, b"notes"),
    ],
)
def test_untrusted_input_never_promotes_to_text(name: str, mime: str | None, content: bytes) -> None:
    """Spoofing, unsupported containers and malformed text all produce stable refusals."""
    with pytest.raises(ParsingError) as failure:
        inspect_format(content, safe_basename=name, declared_type=mime)
    assert failure.value.code in {
        ParseErrorCode.UNSUPPORTED_FORMAT,
        ParseErrorCode.FORMAT_MISMATCH,
        ParseErrorCode.PARSER_UNAVAILABLE,
        ParseErrorCode.EMPTY_EXTRACTION,
        ParseErrorCode.CONTENT_LIMIT_EXCEEDED,
    }
    assert str(failure.value) == failure.value.code.value


def test_inspection_rejects_oversize_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The allocation limit is checked before the converter is invoked."""

    def forbidden_run(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Oversized content reached converter")

    monkeypatch.setattr(TextFileToDocument, "run", forbidden_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"x" * 33, safe_basename="notes.txt", upload_limits=UploadLimits(max_bytes=32))
    assert failure.value.code == ParseErrorCode.CONTENT_LIMIT_EXCEEDED


def test_default_byte_budget_accepts_one_mib_and_refuses_the_next_byte() -> None:
    """The actual upload boundary is one MiB, independently of tightened test limits."""
    content = b"a" * 1_048_576
    result = parse_source(content, safe_basename="limit.txt")
    assert len(result.elements) == 1
    assert result.inspected_source.bytes_count == len(content)
    with pytest.raises(ParsingError) as failure:
        inspect_format(content + b"a", safe_basename="limit.txt")
    assert failure.value.code == ParseErrorCode.CONTENT_LIMIT_EXCEEDED
    assert failure.value.reason == "MAX_BYTES"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("notes.txt", "Hello world"),
        ("notes.txt", "Привіт, світе!"),
        ("notes.txt", "🙂 Unicode and e\u0301 combining marks"),
        ("notes.txt", "First paragraph.\n\nSecond paragraph."),
        ("notes.txt", "First\r\n\r\nSecond\r\n"),
        ("notes.txt", "single line\n"),
        ("notes.txt", "  leading spaces and trailing spaces  "),
        ("notes.txt", "# literal plain text heading\n\n```plain literal fences```"),
        ("notes.txt", "A long paragraph " * 1000),
        ("notes.md", "# Overview\n\nA paragraph."),
        ("notes.md", "# Батько\n\n## Дитина\n\nТекст"),
        ("notes.md", "preamble\n\n# Heading\n\nbody"),
        ("notes.md", "# Parent\n\n### Skip level\n\nbody"),
        ("notes.md", "# First\n\n# Second\n\nbody"),
        ("notes.md", "# Closing hashes ##\n\nbody"),
        ("notes.md", "# Same\n\nbody\n\n# Same\n\nother"),
        ("notes.md", "# Heading\r\n\r\nbody\r\n"),
        ("notes.md", "```python\n# not a heading\nprint('hello')\n```\n"),
        ("notes.md", "~~~python\n# not a heading\n~~~\n\n# Real heading\nbody"),
        ("notes.md", "````python\n```\n# still code\n````\n"),
        ("notes.md", "# Heading\n\n```\n# Unclosed fence\n"),
        ("notes.md", "| Name | Value |\n| --- | --- |\n| alpha | beta |\n"),
        ("notes.md", "# Table\n\nName | Value\n--- | ---\nalpha | beta\n"),
        ("notes.md", "---\nunsafe: !!python/object:os.system\n---\n\n# Heading\nbody"),
        ("notes.md", "[remote](https://example.test/secret) and ![image](file:///private)"),
    ],
)
def test_representative_text_and_markdown_projection(name: str, text: str) -> None:
    """Golden inputs retain ordered original spans without fabricated source coordinates."""
    result = parse_source(text.encode(), safe_basename=name)
    assert result.elements
    assert result.source_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert result.parser_id
    assert result.parser_revision
    assert [element.order for element in result.elements] == list(range(len(result.elements)))
    assert len({element.element_id for element in result.elements}) == len(result.elements)
    previous_end = 0
    for element in result.elements:
        start, end = element.source_span.start, element.source_span.end
        assert 0 <= previous_end <= start < end <= len(text)
        assert element.text == text[start:end]
        assert element.line_start >= 1
        assert element.line_end >= element.line_start
        previous_end = end
    assert result == parse_source(text.encode(), safe_basename=name)


def test_projection_is_immutable() -> None:
    """Downstream consumers cannot mutate verified structural data."""
    result = parse_source(b"# Heading\n\nbody", safe_basename="notes.md")
    for target, field in [(result, "parser_revision"), (result.elements[0], "text")]:
        with pytest.raises(FrozenInstanceError):
            setattr(target, field, "changed")


def test_bom_is_removed_without_shifting_decoded_spans() -> None:
    """Spans refer to UTF-8-sig decoded characters and the hash includes original BOM bytes."""
    text = "# Заголовок\r\n\r\nТекст\r\n"
    content = b"\xef\xbb\xbf" + text.encode()
    result = parse_source(content, safe_basename="notes.md")
    assert result.source_sha256 == hashlib.sha256(content).hexdigest()
    assert result.elements[0].source_span.start == 0
    for element in result.elements:
        start, end = element.source_span.start, element.source_span.end
        assert element.text == text[start:end]


def test_plain_text_never_invents_markdown_structure() -> None:
    """A qualified TXT source keeps Markdown-looking text as ordinary paragraphs."""
    result = parse_source(b"# Literal heading\n\n```python\nprint(1)\n```", safe_basename="notes.txt")
    assert {element.kind for element in result.elements} == {ElementKind.PARAGRAPH}


def test_fences_and_tables_are_preserved_as_protected_raw_spans() -> None:
    """Raw code and table syntax is preserved without claims about AST nodes or cells."""
    text = "# Heading\n\n```python\n# Not a heading\n```\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    result = parse_source(text.encode(), safe_basename="notes.md")
    protected = [element for element in result.elements if element.kind == ElementKind.PROTECTED_RAW]
    assert len(protected) == 2
    assert all(element.warning_codes for element in protected)
    assert "# Not a heading" in protected[0].text
    assert "| 1 | 2 |" in protected[1].text
    assert len([element for element in result.elements if element.kind == ElementKind.HEADING]) == 1


def test_dispatch_invokes_one_qualified_converter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dispatcher invokes one extraction adapter for an accepted source."""
    calls: list[int] = []
    original_run = TextFileToDocument.run

    def counted_run(self: TextFileToDocument, *args: Any, **kwargs: Any) -> dict[str, list[Document]]:
        calls.append(1)
        return original_run(self, *args, **kwargs)

    monkeypatch.setattr(TextFileToDocument, "run", counted_run)
    parse_source(b"# Accepted\n\nbody", safe_basename="notes.md")
    assert calls == [1]


@pytest.mark.parametrize("documents", [[], [Document(content="")], [Document(content="   ")]])
def test_empty_converter_output_is_a_refusal(monkeypatch: pytest.MonkeyPatch, documents: list[Document]) -> None:
    """A converter's silent skip or empty document does not become a successful parse."""

    def empty_run(*_args: Any, **_kwargs: Any) -> dict[str, list[Document]]:
        return {"documents": documents}

    monkeypatch.setattr(TextFileToDocument, "run", empty_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"accepted input", safe_basename="notes.txt")
    assert failure.value.code == ParseErrorCode.EMPTY_EXTRACTION


def test_converter_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter failures disclose neither parser internals nor document excerpts."""

    def failed_run(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("private document secret")

    monkeypatch.setattr(TextFileToDocument, "run", failed_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"accepted input", safe_basename="notes.txt")
    assert failure.value.code == ParseErrorCode.PARSE_FAILED
    assert "secret" not in str(failure.value)


def test_element_budget_is_enforced() -> None:
    """Small structural elements cannot bypass the independent element allocation limit."""
    with pytest.raises(ParsingError) as failure:
        parse_source(b"one\n\ntwo\n\nthree", safe_basename="notes.txt", upload_limits=UploadLimits(max_elements=2))
    assert failure.value.code == ParseErrorCode.CONTENT_LIMIT_EXCEEDED


def test_inspection_deadline_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """A spent deadline refuses the source rather than returning partially checked metadata."""
    ticks = 0

    def advancing_clock() -> float:
        nonlocal ticks
        ticks += 1
        return float(ticks * 10)

    monkeypatch.setattr(parsing, "perf_counter", advancing_clock)
    with pytest.raises(ParsingError) as failure:
        inspect_format(b"bounded text", safe_basename="notes.txt", upload_limits=UploadLimits(deadline_ms=1))
    assert failure.value.code == ParseErrorCode.CONTENT_LIMIT_EXCEEDED
    assert failure.value.reason == "DEADLINE_EXCEEDED"


def test_heading_hierarchy_and_parent_anchors_are_observed() -> None:
    """Skipped levels and sibling headings keep ancestry derived from source headings."""
    text = "# Root\n\n### Child\n\nbody\n\n## Sibling\n\nother\n\n# Next\n\nlast"
    result = parse_source(text.encode(), safe_basename="notes.md")
    headings = [element for element in result.elements if element.kind == ElementKind.HEADING]
    assert [element.heading_path for element in headings] == [
        ("Root",),
        ("Root", "Child"),
        ("Root", "Sibling"),
        ("Next",),
    ]
    assert headings[0].parent_anchor is None
    assert headings[1].parent_anchor == headings[0].element_id
    assert headings[2].parent_anchor == headings[0].element_id
    assert headings[3].parent_anchor is None


def test_setext_heading_is_projected_without_losing_underline() -> None:
    """A Setext heading is observed structure while its raw source span stays intact."""
    text = "Title\n=====\n\nbody\n\nSubtitle\n--------\n\nmore"
    result = parse_source(text.encode(), safe_basename="notes.md")
    headings = [element for element in result.elements if element.kind == ElementKind.HEADING]
    assert [element.heading_path for element in headings] == [("Title",), ("Title", "Subtitle")]
    assert headings[0].text == "Title\n=====\n"


def test_document_classification_contains_only_verified_metadata() -> None:
    """Chunking can use verified format and structure without its own MIME classifier."""
    result = parse_source(b"# Heading\n\n```\ncode\n```", safe_basename="notes.md")
    assert result.classification.format_id == result.format_id
    assert set(result.classification.element_kinds) == {element.kind for element in result.elements}
    assert result.classification.has_protected_spans
    assert result.classification.selection_reasons
    assert result.contract_revision == "parsed-elements-v1"


def test_multiple_extracted_documents_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The initial adapter contract requires exactly one extracted document."""

    def multiple_run(*_args: Any, **_kwargs: Any) -> dict[str, list[Document]]:
        return {"documents": [Document(content="one"), Document(content="two")]}

    monkeypatch.setattr(TextFileToDocument, "run", multiple_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"accepted input", safe_basename="notes.txt")
    assert failure.value.code == ParseErrorCode.PARSE_FAILED


def test_anchors_depend_on_content_and_revisions_not_filename_aliases() -> None:
    """Renaming an accepted upload does not create synthetic source identity."""
    content = b"# Heading\n\nbody\n\n# Heading\n\nother"
    first = parse_source(content, safe_basename="first.md", declared_type="text/markdown")
    second = parse_source(content, safe_basename="second.markdown", declared_type="text/x-markdown")
    assert first.source_sha256 == second.source_sha256
    assert first.elements == second.elements
    assert first.classification == second.classification


def test_operational_logs_omit_content_and_untrusted_filename(caplog: pytest.LogCaptureFixture) -> None:
    """Diagnostics retain safe counts and decisions without source or filename excerpts."""
    caplog.set_level(logging.DEBUG)
    parse_source(b"private-document-canary", safe_basename="private-filename-canary.txt")
    diagnostic = caplog.text + repr([record.__dict__ for record in caplog.records])
    assert "private-document-canary" not in diagnostic
    assert "private-filename-canary" not in diagnostic


@pytest.mark.parametrize(
    "text",
    [
        "<!--\n# Hidden\n-->\n\n# Real\nbody",
        "---\n# Hidden YAML comment\n---\n\n# Real\nbody",
        "> quote\n---\n\n# Real\nbody",
        "- list item\n---\n\n# Real\nbody",
        "first title line\nsecond title line\n---\n\n# Real\nbody",
        "<script>\n\n# Hidden script text\n\n</script>\n\n# Real\nbody",
        "<![CDATA[\n\n# Hidden CDATA text\n\n]]>\n\n# Real\nbody",
    ],
)
def test_unsupported_markdown_constructs_do_not_fabricate_headings(text: str) -> None:
    """Protected multiline constructs cannot supply heading ancestry for ordinary text."""
    result = parse_source(text.encode(), safe_basename="notes.md")
    headings = [element for element in result.elements if element.kind == ElementKind.HEADING]
    assert len(headings) == 1
    assert headings[0].heading_path == ("Real",)
    assert any(element.kind == ElementKind.PROTECTED_RAW for element in result.elements)


def test_extraction_deadline_is_checked_before_returning_elements(monkeypatch: pytest.MonkeyPatch) -> None:
    """A late cooperative adapter result is refused instead of escaping the time budget."""
    clock = 0.0
    original_run = TextFileToDocument.run

    def current_clock() -> float:
        return clock

    def late_run(self: TextFileToDocument, *args: Any, **kwargs: Any) -> dict[str, list[Document]]:
        nonlocal clock
        result = original_run(self, *args, **kwargs)
        clock = 10.0
        return result

    monkeypatch.setattr(parsing, "perf_counter", current_clock)
    monkeypatch.setattr(TextFileToDocument, "run", late_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"accepted input", safe_basename="notes.txt", upload_limits=UploadLimits(deadline_ms=1))
    assert failure.value.code == ParseErrorCode.CONTENT_LIMIT_EXCEEDED
    assert failure.value.reason == "DEADLINE_EXCEEDED"


def test_extraction_that_changes_source_text_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flattened or rewritten extraction cannot retain misleading original source spans."""

    def altered_run(*_args: Any, **_kwargs: Any) -> dict[str, list[Document]]:
        return {"documents": [Document(content="rewritten text")]}

    monkeypatch.setattr(TextFileToDocument, "run", altered_run)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"original source text", safe_basename="notes.txt")
    assert failure.value.code == ParseErrorCode.STRUCTURE_LOSS


def test_missing_adapter_dependency_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """An import failure never triggers a generic-text fallback or silent empty result."""

    def unavailable_extraction(_content: bytes) -> str:
        raise ModuleNotFoundError("private dependency path")

    monkeypatch.setattr(parsing, "_extract_text", unavailable_extraction)
    with pytest.raises(ParsingError) as failure:
        parse_source(b"accepted input", safe_basename="notes.txt")
    assert failure.value.code == ParseErrorCode.PARSER_UNAVAILABLE
    assert "private" not in str(failure.value)


@pytest.mark.parametrize(
    ("name", "mime", "content", "expected"),
    [
        ("notes.txt", "application/pdf", b"text", ParseErrorCode.FORMAT_MISMATCH),
        ("notes.txt", None, b"\xff", ParseErrorCode.FORMAT_MISMATCH),
        ("notes.txt", None, b"%PDF-1.7", ParseErrorCode.FORMAT_MISMATCH),
        ("notes.txt", None, b" \t\r\n", ParseErrorCode.EMPTY_EXTRACTION),
        ("../notes.txt", None, b"text", ParseErrorCode.FORMAT_MISMATCH),
        ("notes.pdf", "application/pdf", b"not a PDF", ParseErrorCode.FORMAT_MISMATCH),
        ("notes.docx", None, b"PK\x03\x04", ParseErrorCode.PARSER_UNAVAILABLE),
        ("notes.zip", None, b"PK\x03\x04", ParseErrorCode.UNSUPPORTED_FORMAT),
    ],
)
def test_failure_categories_are_stable(name: str, mime: str | None, content: bytes, expected: ParseErrorCode) -> None:
    """Mismatched evidence, absent qualification and unsupported formats remain distinct."""
    for _ in range(2):
        with pytest.raises(ParsingError) as failure:
            inspect_format(content, safe_basename=name, declared_type=mime)
        assert failure.value.code == expected


def test_line_ranges_refer_to_observed_crlf_source_lines() -> None:
    """Windows line endings do not shift source line provenance or create synthetic pages."""
    text = "# Heading\r\n\r\nline one\r\nline two\r\n\r\n## Child\r\nbody"
    result = parse_source(text.encode(), safe_basename="notes.md")
    assert [(element.line_start, element.line_end) for element in result.elements] == [(1, 1), (3, 4), (6, 6), (7, 7)]

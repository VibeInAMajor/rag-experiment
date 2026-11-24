"""Real Haystack AST boundaries, exact provenance and explicit resource refusals."""

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from apps.workbench.chunking.chunking import ChunkingInput, ModelTokenAdmission, prepare_chunks
from apps.workbench.chunking.chunking_profiles import ChunkingError, ChunkingProfile, PythonChunkingProfile
from apps.workbench.parsing.parser_registry import FormatId, ParsingError, UploadLimits
from apps.workbench.parsing.parsing import parse_source
from haystack import Document
from haystack.components.preprocessors import PythonCodeSplitter

_SOURCE = '''# source header
"""Module documentation."""
from decimal import Decimal

class Ledger:
    """Ledger documentation."""
    @staticmethod
    async def refundledgerproof(amount):
        """Retain the method docstring."""
        return Decimal(amount)

    class Nested:
        def однакова(self):
            return "українська русский English"

class Other:
    def однакова(self):
        return "same body"

# trailing comment
'''


def _input(text: str, *, name: str = "ledger.py") -> ChunkingInput:
    return ChunkingInput(
        parsed_document=parse_source(text.encode(), safe_basename=name),
        normalized_content=text,
        workspace_id="development",
        source_id="code-source",
        source_version_id="code-version",
    )


def test_existing_splitter_characterization_and_exact_source_reconciliation() -> None:
    """Primary output is lossless only with automatic class prefixes disabled."""
    splitter = PythonCodeSplitter(
        min_effective_lines=1, max_effective_lines=3, preserve_class_definition=False, oversized_factor=1_000_000
    )
    first = splitter.run(documents=[Document(content=_SOURCE)])["documents"]
    second = splitter.run(documents=[Document(content=_SOURCE)])["documents"]
    golden = json.loads((Path(__file__).parent / "fixtures/python/characterization.json").read_text(encoding="utf-8"))
    assert [{"content": document.content, "metadata": document.meta} for document in first] == golden
    assert [(d.content, d.meta) for d in first] == [(d.content, d.meta) for d in second]
    assert "".join(d.content or "" for d in first) == _SOURCE
    # Native start_line refers to AST declarations; the leading comment is in content too.
    assert first[0].meta["start_line"] == 2 and (first[0].content or "").startswith("# source header")
    assert any("nested_class" in d.meta["unit_kinds"] for d in first)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_python_policy_keeps_symbols_comments_docstrings_and_true_line_ranges(newline: str) -> None:
    """Every emitted line range describes the stored source, including CRLF and CR."""
    source = _input(_SOURCE.replace("\n", newline))
    chunks = prepare_chunks(source)
    assert prepare_chunks(source) == chunks
    assert all(c.decision.strategy == "python_ast" for c in chunks)
    assert all(isinstance(c.decision.profile, PythonChunkingProfile) for c in chunks)
    assert "".join(c.content for c in chunks) == source.normalized_content
    assert all(c.python_span is not None for c in chunks)
    symbols = {s.qualified_symbol for c in chunks if c.python_span is not None for s in c.python_span.symbols}
    assert {"Ledger.refundledgerproof", "Ledger.Nested.однакова", "Other.однакова"} <= symbols
    lines = io.StringIO(source.normalized_content, newline="").readlines()
    for chunk in chunks:
        metadata = chunk.metadata()
        assert "page_number" not in metadata and "page" not in metadata
        assert metadata["unit"] == "effective_line" and metadata["requested_overlap"] == 0
        assert "".join(lines[metadata["start_line"] - 1 : metadata["end_line"]]) == chunk.content
        assert chunk.content_hash == hashlib.sha256(chunk.content.encode()).hexdigest()
        chunk.to_chunk(title="ledger.py")


def test_oversized_method_secondary_pieces_have_exact_ranges_and_parent_symbol(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Secondary pieces preserve the originating symbol without leaking it to logs."""
    text = (
        "class Huge:\n    def privatefunctioncanary(self):\n"
        + "        value = 'payload'\n" * 500
        + "        return value\n"
    )
    chunks = prepare_chunks(_input(text))
    secondary = [c for c in chunks if c.metadata()["secondary_split"]]
    assert len(secondary) > 2
    assert all(c.metadata()["qualified_symbol"] == "Huge.privatefunctioncanary" for c in secondary)
    assert {c.metadata()["secondary_split_total"] for c in secondary} == {len(secondary)}
    assert [c.metadata()["secondary_split_index"] for c in secondary] == list(range(len(secondary)))
    assert all(c.metadata()["actual_overlap_lines"] <= 5 for c in secondary)
    assert len({c.metadata()["start_line"] for c in secondary}) == len(secondary)
    assert "privatefunctioncanary" not in caplog.text and "payload" not in caplog.text
    previous_end = 0
    for chunk in chunks:
        assert not text[previous_end : chunk.source_span.start].strip()
        assert text[chunk.source_span.start : chunk.source_span.end] == chunk.content
        previous_end = chunk.source_span.end
    assert previous_end == len(text)


@pytest.mark.parametrize(
    "text", ["def broken(:\n", "class X:\n", "x = 'unterminated", "def f():\n\treturn 1\n return 2"]
)
def test_invalid_python_is_rejected_without_prose_fallback(text: str) -> None:
    """Broken syntax is a typed user error with no interpreter text."""
    with pytest.raises(ParsingError, match="^UNPARSEABLE_SOURCE$"):
        _input(text)


@pytest.mark.parametrize("content", [b"x='\xff'", b"x='\0'", "x='ї'".encode()[:-2]])
def test_invalid_unicode_nul_and_truncation_are_not_source(content: bytes) -> None:
    """UTF-8 and binary checks precede syntax analysis."""
    with pytest.raises(ParsingError):
        parse_source(content, safe_basename="bad.py")


def test_single_long_line_refuses_without_truncation() -> None:
    """An indivisible long line cannot be silently trimmed to fit storage."""
    with pytest.raises(ChunkingError, match="^CONTENT_LIMIT_EXCEEDED$"):
        prepare_chunks(_input("def large():\n    return '" + "x" * 33_000 + "'\n"))


def test_too_many_symbols_and_deep_syntax_are_bounded() -> None:
    """Declaration and parser-depth ceilings reject pathological sources."""
    with pytest.raises(ParsingError, match="^CONTENT_LIMIT_EXCEEDED$"):
        parse_source(
            b"def a(): pass\ndef b(): pass\n", safe_basename="many.py", upload_limits=UploadLimits(max_elements=1)
        )
    with pytest.raises(ParsingError, match="^UNPARSEABLE_SOURCE$"):
        _input("x = " + "(" * 1000 + "1" + ")" * 1000)


def test_prose_containing_python_is_still_prose_and_mime_mismatch_refuses() -> None:
    """Source content cannot promote a text file or override contradictory MIME."""
    chunks = prepare_chunks(_input(_SOURCE, name="ledger.txt"))
    assert all(chunk.decision.strategy == "prose_recursive" for chunk in chunks)
    with pytest.raises(ParsingError):
        parse_source(_SOURCE.encode(), safe_basename="ledger.py", declared_type="application/pdf")
    assert (
        parse_source(_SOURCE.encode(), safe_basename="ledger.py", declared_type="text/plain").format_id
        is FormatId.PYTHON
    )


def test_source_is_never_executed_and_other_content_hashes_remain_stable(tmp_path: Path) -> None:
    """A stored side-effect expression stays inert while an unrelated chunk stays reusable."""
    marker = tmp_path / "must-not-exist"
    text = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n\n"
    text += "def unchanged():\n" + "    value = 'stable payload'\n" * 150 + "    return value\n"
    text += "def changed():\n    return 'old'\n"
    before = prepare_chunks(_input(text))
    after = prepare_chunks(_input(text.replace("'old'", "'new'")))
    assert not marker.exists()
    assert {c.content_hash for c in before if "def unchanged" in c.content} <= {c.content_hash for c in after}


def test_model_admission_counts_actual_final_code_input() -> None:
    """Native admission includes the same configured prefix as future model input."""

    class Counter:
        counter_revision = "test-code-counter-r1"

        def count_tokens(self, text: str) -> int:
            return len(text)

    source = _input("def proof():\n    return 1\n")
    admission = ModelTokenAdmission(counter_revision=Counter.counter_revision, max_tokens=100, prefix="prefix:")
    chunks = prepare_chunks(source, model_counter=Counter(), model_admission=admission)
    assert chunks[0].length_model_token == len("prefix:" + source.normalized_content)
    with pytest.raises(ChunkingError, match="^MODEL_TOKEN_LIMIT_EXCEEDED$"):
        prepare_chunks(source, model_counter=Counter(), model_admission=replace(admission, max_tokens=10))
    assert isinstance(chunks[0].decision.profile, PythonChunkingProfile)
    assert isinstance(prepare_chunks(_input("some prose", name="plain.txt"))[0].decision.profile, ChunkingProfile)

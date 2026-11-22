"""Pinned offline tokenizer assets and source-preserving Haystack splitter adapters."""

import hashlib
import json
import logging
from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

from apps.workbench.api.chunking_profiles import ChunkingDecision, ChunkingError, ChunkingErrorCode, ChunkingResources

_ASSET_ROOT = Path(__file__).resolve().parents[3] / ".cache/workbench-chunking"
_NLTK_VERSION = "3.10.4"
_TIKTOKEN_VERSION = "0.14.0"
_PUNKT_URL = (
    "https://raw.githubusercontent.com/nltk/nltk_data/"
    "4f15a3d89eefe9748ec1c05be495d91289197155/packages/tokenizers/punkt_tab.zip"
)
_PUNKT_SHA256 = "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106"
_TOKEN_URL = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
_TOKEN_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
_PUNKT_FILES = ("abbrev_types.txt", "collocations.tab", "ortho_context.tab", "sent_starters.txt")
_PUNKT_LANGUAGES = (("en", "english"), ("ru", "russian"))
_PUNKT_HASHES = {
    "en": "f14317bd8ce7813da0d903f3e90d3d997f102ba6f5ccaa13858558773a53c2ac",
    "ru": "ad0208e0ce225c2dc8e04a99e301b299a0acba15f3e50aaac54f9c43e8409ba1",
}
_ENCODING_PATTERN = "|".join(
    (
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}",
        r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
        r"\s*[\r\n]+",
        r"\s+(?!\S)",
        r"\s+",
    )
)


def _punkt_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in _PUNKT_FILES:
        content = (directory / name).read_bytes()
        if len(content) > 2_000_000:
            raise ValueError("Sentence resource exceeds the qualified size.")
        digest.update(name.encode("ascii") + b"\0" + hashlib.sha256(content).digest())
    return digest.hexdigest()


@dataclass(frozen=True)
class SplitSpan:
    """Exact local source coordinates; overlap is measured on the repeated source substring."""

    start: int
    end: int
    token_count: int
    overlap_tokens: int
    warning_codes: tuple[str, ...] = ()
    native_metadata: tuple[tuple[str, str | int], ...] = ()


@dataclass(frozen=True)
class SectionSpan:
    """Native Markdown partitions, which callers reconcile with verified parser headings."""

    start: int
    end: int
    header: str
    parent_headers: tuple[str, ...]


class _NoContentDebug(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Drop SDK debug records that interpolate raw heading text."""
        return record.levelno > logging.DEBUG


_SDK_LOG_FILTER = _NoContentDebug()


def _package_matches(name: str, expected: str) -> bool:
    try:
        return metadata.version(name) == expected
    except metadata.PackageNotFoundError:
        return False


def inspect_chunking_resources() -> ChunkingResources:
    """
    Verify already provisioned package and asset identities without any network lookup.

    :returns: Counter revision and qualified EN/RU sentence resource revisions.
    :raises ChunkingError: If the required counter is absent, changed or incompatible.
    """
    if not _package_matches("tiktoken", _TIKTOKEN_VERSION) or not _package_matches("haystack-ai", "3.5.0"):
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_PACKAGE_MISMATCH")
    try:
        encoding = (_ASSET_ROOT / "o200k_base.tiktoken").read_bytes()
    except OSError:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_ASSET_MISSING") from None
    if len(encoding) > 5_000_000 or hashlib.sha256(encoding).hexdigest() != _TOKEN_SHA256:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_ASSET_MISMATCH")
    pattern_hash = hashlib.sha256(
        json.dumps([_ENCODING_PATTERN, {"<|endoftext|>": 199999, "<|endofprompt|>": 200018}], sort_keys=True).encode()
    ).hexdigest()
    counter_revision = f"tiktoken:{_TIKTOKEN_VERSION}:o200k_base:{_TOKEN_SHA256}:config:{pattern_hash}"
    sentences = []
    if _package_matches("nltk", _NLTK_VERSION):
        for code, language in _PUNKT_LANGUAGES:
            try:
                digest = _punkt_digest(_ASSET_ROOT / "nltk/tokenizers/punkt_tab" / language)
            except (OSError, ValueError):
                continue
            if digest == _PUNKT_HASHES[code]:
                sentences.append((code, f"nltk:{_NLTK_VERSION}:punkt_tab:{_PUNKT_SHA256}:{code}:{digest}"))
    return ChunkingResources(token_counter_revision=counter_revision, sentence_resource_revisions=tuple(sentences))


@lru_cache(maxsize=1)
def _encoding() -> Any:
    from tiktoken import Encoding
    from tiktoken.load import load_tiktoken_bpe

    # Calling get_encoding() could fetch a remote cache miss. This constructor reads only a verified local file.
    inspect_chunking_resources()
    return Encoding(
        name="o200k_base",
        pat_str=_ENCODING_PATTERN,
        mergeable_ranks=load_tiktoken_bpe(str(_ASSET_ROOT / "o200k_base.tiktoken"), expected_hash=_TOKEN_SHA256),
        special_tokens={"<|endoftext|>": 199999, "<|endofprompt|>": 200018},
    )


def count_tokens(text: str) -> int:
    """
    Count ordinary source text using the pinned offline o200k_base encoding.

    :param text: Source text; special-token spellings are ordinary document content.
    :returns: Exact tiktoken:o200k_base count, with no claim about an embedding model's tokenizer.
    :raises ChunkingError: If the counter has not been provisioned or cannot encode the source.
    """
    try:
        return len(_encoding().encode_ordinary(text))
    except ChunkingError:
        raise
    except Exception:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_FAILED") from None


@lru_cache(maxsize=1)
def _configure_sentence_path() -> None:
    import nltk

    # Configure this app process once, before constructing any Punkt tokenizer; never use an ambient user model.
    nltk.data.path[:] = [str(_ASSET_ROOT / "nltk")]


def _splitter(decision: ChunkingDecision) -> Any:
    from haystack.components.preprocessors import RecursiveDocumentSplitter
    from haystack.components.preprocessors.sentence_tokenizer import SentenceSplitter

    resources = inspect_chunking_resources()
    if resources.token_counter_revision != decision.token_counter_revision:
        raise ChunkingError(ChunkingErrorCode.TOKEN_COUNTER_UNAVAILABLE, reason="COUNTER_REVISION_MISMATCH")
    profile = decision.profile
    splitter: Any = RecursiveDocumentSplitter(
        split_length=profile.target_size,
        split_overlap=profile.overlap,
        split_unit="token",
        separators=list(profile.separators),
        sentence_splitter_params={"language": profile.sentence_language, "keep_white_spaces": True},
        tokenizer_encoding=profile.tokenizer_encoding,
    )
    splitter.tiktoken_tokenizer = _encoding()
    if "sentence" in profile.separators:
        revision = dict(resources.sentence_resource_revisions).get(profile.sentence_language or "")
        if revision is None or revision != profile.sentence_resource_revision:
            raise ChunkingError(ChunkingErrorCode.SENTENCE_RESOURCE_UNAVAILABLE, reason="SENTENCE_REVISION_MISMATCH")
        _configure_sentence_path()
        if profile.sentence_language == "en":
            splitter.nltk_tokenizer = SentenceSplitter(language="en", keep_white_spaces=True)
        else:
            splitter.nltk_tokenizer = SentenceSplitter(language="ru", keep_white_spaces=True)
    # Haystack 3.5.0 warm_up() calls URL-backed get_encoding(). Only replace setup state, never splitting logic.
    splitter._is_warmed_up = True
    return splitter


def _native_metadata(document: Any) -> tuple[tuple[str, str | int], ...]:
    return tuple(
        (name, document.meta[name])
        for name in ("source_id", "parent_id", "split_id", "split_idx_start")
        if type(document.meta.get(name)) in (str, int)
    )


def _native_spans(text: str, documents: list[Any], decision: ChunkingDecision) -> tuple[SplitSpan, ...] | None:
    spans: list[SplitSpan] = []
    previous_end = 0
    for document in documents:
        content = document.content
        start = document.meta.get("split_idx_start")
        if not isinstance(content, str) or type(start) is not int:
            return None
        end = start + len(content)
        if start < 0 or end > len(text) or content != text[start:end] or text[previous_end:start].strip():
            return None
        if not content.strip():
            continue
        token_count = count_tokens(content)
        overlap = count_tokens(text[start:previous_end]) if start < previous_end else 0
        if (
            token_count > decision.profile.target_size
            or len(content) > decision.profile.hard_character_limit
            or overlap > decision.profile.overlap
            or (spans and (start <= spans[-1].start or end <= previous_end))
        ):
            return None
        spans.append(
            SplitSpan(
                start=start,
                end=end,
                token_count=token_count,
                overlap_tokens=overlap,
                native_metadata=_native_metadata(document),
            )
        )
        previous_end = end
    if not spans or text[previous_end:].strip():
        return None
    return tuple(spans)


def _safe_boundaries(text: str) -> tuple[list[int], list[int]]:
    encoding = _encoding()
    tokens = encoding.encode_ordinary(text)
    byte_to_char = {0: 0}
    position = 0
    for index, char in enumerate(text, 1):
        position += len(char.encode("utf-8"))
        byte_to_char[position] = index
    token_positions, char_positions = [0], [0]
    position = 0
    for index, value in enumerate(encoding.decode_tokens_bytes(tokens), 1):
        position += len(value)
        if position in byte_to_char:
            token_positions.append(index)
            char_positions.append(byte_to_char[position])
    return token_positions, char_positions


def _terminal_repair(text: str, decision: ChunkingDecision, source_id: str) -> tuple[SplitSpan, ...]:
    token_positions, char_positions = _safe_boundaries(text)
    spans: list[SplitSpan] = []
    first = 0
    while first < len(token_positions) - 1:
        if len(spans) >= decision.profile.max_chunks:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_CHUNKS")
        last = min(
            bisect_right(token_positions, token_positions[first] + decision.profile.target_size) - 1,
            bisect_right(char_positions, char_positions[first] + decision.profile.hard_character_limit) - 1,
        )
        while (
            last > first
            and count_tokens(text[char_positions[first] : char_positions[last]]) > decision.profile.target_size
        ):
            last -= 1
        if last <= first:
            raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="UNICODE_SCALAR_TOKEN_BUDGET")
        start, end = char_positions[first], char_positions[last]
        if text[start:end].strip():
            previous_end = spans[-1].end if spans else 0
            spans.append(
                SplitSpan(
                    start=start,
                    end=end,
                    token_count=count_tokens(text[start:end]),
                    overlap_tokens=count_tokens(text[start:previous_end]) if start < previous_end else 0,
                    warning_codes=("NATIVE_OUTPUT_REPAIRED",),
                    native_metadata=(
                        ("source_id", source_id),
                        ("parent_id", source_id),
                        ("split_id", len(spans)),
                        ("split_idx_start", start),
                    ),
                )
            )
        if last == len(token_positions) - 1:
            break
        next_first = max(first + 1, bisect_right(token_positions, token_positions[last] - decision.profile.overlap - 1))
        while next_first < last and count_tokens(text[char_positions[next_first] : end]) > decision.profile.overlap:
            next_first += 1
        first = min(next_first, last)
    return tuple(spans)


def split_prose(text: str, *, decision: ChunkingDecision) -> tuple[SplitSpan, ...]:
    """
    Run the existing sentence-aware token splitter and validate every returned source span.

    :param text: At most 1 MiB of UTF-8 prose, with protected structures already isolated by the caller.
    :param decision: Resolved profile with qualified counter and sentence resource identities.
    :returns: Exact local source spans with measured token counts and actual repeated-token overlap.
    :raises ChunkingError: On empty input, incompatible resources, failed splitting or resource overflow.
    """
    from haystack import Document

    if not text.strip():
        raise ChunkingError(ChunkingErrorCode.EMPTY_INPUT)
    if len(text.encode("utf-8")) > 1_048_576:
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_SOURCE_BYTES")
    capacity = decision.profile.target_size + (decision.profile.max_chunks - 1) * (
        decision.profile.target_size - decision.profile.overlap
    )
    if count_tokens(text) > capacity:
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_CHUNKS")
    try:
        document = Document(content=text)
        documents = _splitter(decision).run(documents=[document])["documents"]
    except ChunkingError:
        raise
    except Exception:
        raise ChunkingError(ChunkingErrorCode.CHUNKING_FAILED, reason="NATIVE_SPLITTER_FAILED") from None
    spans = _native_spans(text, documents, decision)
    if spans is None:
        spans = _terminal_repair(text, decision, document.id)
    if not spans:
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="NO_PROSE_CHUNKS")
    if len(spans) > decision.profile.max_chunks:
        raise ChunkingError(ChunkingErrorCode.CONTENT_LIMIT_EXCEEDED, reason="MAX_CHUNKS")
    return spans


def partition_markdown(text: str) -> tuple[SectionSpan, ...]:
    """
    Project source-exact native Markdown partitions without granting them parser authority.

    :param text: Original Markdown; verified parser headings remain authoritative for citation boundaries.
    :returns: Native section spans with header metadata, never invented page coordinates.
    :raises ChunkingError: If native header splitting changes source content or fails.
    """
    from haystack import Document
    from haystack.components.preprocessors import MarkdownHeaderSplitter

    sdk_logger = logging.getLogger("haystack.components.preprocessors.markdown_header_splitter")
    if _SDK_LOG_FILTER not in sdk_logger.filters:
        sdk_logger.addFilter(_SDK_LOG_FILTER)
    try:
        documents = MarkdownHeaderSplitter(keep_headers=True, secondary_split=None).run(
            documents=[Document(content=text)]
        )["documents"]
    except ChunkingError:
        raise
    except Exception:
        raise ChunkingError(ChunkingErrorCode.CHUNKING_FAILED, reason="MARKDOWN_SPLITTER_FAILED") from None
    offset = 0
    sections = []
    for document in documents:
        content = document.content or ""
        end = offset + len(content)
        if text[offset:end] != content:
            raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="MARKDOWN_PARTITION_CHANGED")
        sections.append(
            SectionSpan(
                start=offset,
                end=end,
                header=document.meta.get("header", ""),
                parent_headers=tuple(document.meta.get("parent_headers", [])),
            )
        )
        offset = end
    if offset != len(text):
        raise ChunkingError(ChunkingErrorCode.STRUCTURE_LOSS, reason="MARKDOWN_PARTITION_CHANGED")
    return tuple(sections)

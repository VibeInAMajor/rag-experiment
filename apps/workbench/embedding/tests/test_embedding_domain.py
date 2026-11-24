"""Exact embedding inputs preserve source identity while bounding actual model work."""

import hashlib
from time import monotonic
from typing import Literal

import pytest
from pydantic import ValidationError

from apps.workbench.embedding.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)


class _Counter:
    counter_revision = "test-counter-r1"

    def count_tokens(self, text: str) -> int:
        return len(text)


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="local-model",
        profile_revision="local-model-r1",
        provider_adapter_id="test-adapter",
        model_id="test-model",
        model_revision="a" * 40,
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision=_Counter.counter_revision,
        dimensions=32,
        max_tokens=128,
        max_batch_tokens=128,
        query_instruction="Find relevant passages",
    )


def _request(text: str, *, purpose: Literal["query", "document"] = "document") -> EmbeddingRequest:
    return EmbeddingRequest(
        profile_id="local-model",
        profile_revision="local-model-r1",
        task_kind=purpose,
        items=(EmbeddingItem(item_id="source", text=text, input_hash=hashlib.sha256(text.encode()).hexdigest()),),
        deadline=monotonic() + 30,
        trace_id="test-trace",
    )


@pytest.mark.parametrize("purpose", ["query", "document"])
def test_count_and_hash_exact_nfc_model_input_with_distinct_source_identity(
    purpose: Literal["query", "document"],
) -> None:
    """Canonicalization changes only the model input identity, and counting follows that input."""
    request = _request("Cafe\u0301 українською", purpose=purpose)
    prepared = prepare_embedding_request(_profile(), request, _Counter())[0]
    expected = "Café українською"
    if purpose == "query":
        expected = f"Instruct: Find relevant passages\nQuery: {expected}"
    assert prepared.text == expected
    assert prepared.token_count == len(expected)
    assert prepared.input_hash == hashlib.sha256(expected.encode()).hexdigest()
    assert prepared.source_hash == request.items[0].input_hash
    assert prepared.input_hash != prepared.source_hash
    assert expected not in repr(prepared)


@pytest.mark.parametrize("text", ["", "  \n", "abc\0def", "\ud800"])
def test_invalid_source_never_enters_embedding_contract(text: str) -> None:
    """Empty, malformed or hash-inconsistent source text is rejected before any provider work."""
    with pytest.raises(ValidationError):
        EmbeddingItem(item_id="source", text=text, input_hash="a" * 64)


def test_instruction_tokens_count_against_cap_without_truncation() -> None:
    """Query formatting consumes the same exact token allowance as the supplied source."""
    profile = _profile()
    document = _request("a" * 128)
    assert prepare_embedding_request(profile, document, _Counter())[0].token_count == 128
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.REQUEST_TOO_LARGE):
        prepare_embedding_request(profile, _request("a" * 128, purpose="query"), _Counter())
    assert len(document.items[0].text) == 128


def test_counter_revision_mismatch_and_expired_deadline_refuse_preparation() -> None:
    """A stale tokenizer or deadline cannot produce dispatchable inputs."""
    request = _request("sample")
    counter = _Counter()
    counter.counter_revision = "changed-counter"
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.TOKENIZER_MISMATCH):
        prepare_embedding_request(_profile(), request, counter)
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.TIMEOUT):
        prepare_embedding_request(_profile(), request.model_copy(update={"deadline": monotonic() - 1}), _Counter())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**400, True])
def test_untrusted_numeric_values_fail_with_safe_error(value: float) -> None:
    """Malformed numeric responses expose bounded error codes even for overflowing integers."""
    profile, request = _profile(), _request("sample")
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_RESPONSE):
        validate_embedding_batch(
            profile,
            request,
            prepare_embedding_request(profile, request, _Counter()),
            vectors=((value,) + (0.0,) * 31,),
            usage_tokens=6,
            usage_provenance="provider_reported",
            duration_ms=1.0,
        )


def test_validated_batch_preserves_source_and_sent_input_hashes_without_vector_repr() -> None:
    """The public result retains provenance and suppresses private input/vector representations."""
    profile, request = _profile(), _request("private query", purpose="query")
    prepared = prepare_embedding_request(profile, request, _Counter())
    batch = validate_embedding_batch(
        profile,
        request,
        prepared,
        vectors=((1.0,) + (0.0,) * 31,),
        usage_tokens=None,
        usage_provenance="unknown",
        duration_ms=1.0,
    )
    assert batch.item_ids == ("source",)
    assert batch.source_hashes == (request.items[0].input_hash,)
    assert batch.input_hashes == (prepared[0].input_hash,)
    assert "vectors=" not in repr(batch)
    assert "private query" not in repr(batch)


def test_profile_fingerprint_binds_instruction_and_output_policy() -> None:
    """A profile revision cannot silently reuse evidence for a changed input or output policy."""
    profile = _profile()
    assert profile.fingerprint == _profile().fingerprint
    for changes in ({"query_instruction": "Find code"}, {"dimensions": 64}, {"model_digest": "d" * 64}):
        assert profile.model_copy(update=changes).fingerprint != profile.fingerprint

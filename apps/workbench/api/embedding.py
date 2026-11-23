"""Provider-neutral embedding contracts, exact input preparation and output validation."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Sequence
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.workbench.api.contracts import Identifier

if TYPE_CHECKING:
    from apps.workbench.api.chunking import ExactModelCounter


class EmbeddingErrorCode(StrEnum):
    """Safe refusals independent of transport diagnostics and model responses."""

    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NOT_QUALIFIED = "NOT_QUALIFIED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    TOKENIZER_MISMATCH = "TOKENIZER_MISMATCH"
    INVALID_DIMENSION = "INVALID_DIMENSION"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    INVALID_REQUEST = "INVALID_REQUEST"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    CAPACITY_BUSY = "CAPACITY_BUSY"


class EmbeddingError(Exception):
    """Expose a bounded code without input text, vectors, paths or transport exceptions."""

    def __init__(self, code: EmbeddingErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class EmbeddingProfile(_ImmutableModel):
    """Expected model/input contract; actual qualification is separate runtime evidence."""

    profile_id: Identifier
    profile_revision: Identifier
    provider_adapter_id: Identifier
    model_id: str = Field(min_length=1, max_length=256)
    model_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    model_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    tokenizer_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    tokenizer_revision: str = Field(min_length=1, max_length=512)
    input_format_revision: Literal["qwen-instruct-r1"] = "qwen-instruct-r1"
    dimensions: int = Field(ge=32, le=2560)
    normalized: Literal[True] = True
    pooling: Literal["last_token"] = "last_token"
    inference_dtype: Literal["float16", "float32", "bfloat16"] = "float16"
    output_encoding: Literal["float"] = "float"
    max_tokens: int = Field(default=8192, ge=1, le=32768)
    max_batch_tokens: int = Field(default=8192, ge=1, le=32768)
    max_batch_items: int = Field(default=8, ge=1, le=16)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60, allow_inf_nan=False)
    retry_attempts: Literal[0] = 0
    query_instruction: str = Field(
        default="Given a web search query, retrieve relevant passages that answer the query",
        min_length=1,
        max_length=2048,
        repr=False,
    )

    @field_validator("model_id", "tokenizer_revision", "query_instruction")
    @classmethod
    def _utf8_strings(cls, value: str) -> str:
        if "\0" in value or any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("Profile strings require valid Unicode")
        return value

    @model_validator(mode="after")
    def _batch_bounds(self) -> EmbeddingProfile:
        if self.max_tokens > self.max_batch_tokens:
            raise ValueError("Per-item token admission must fit the batch ceiling")
        return self

    @property
    def fingerprint(self) -> str:
        """Bind the full model, tokenizer, input-format and admission policy without source text."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EmbeddingRuntimeIdentity(_ImmutableModel):
    """Trusted deployment/asset attestation, rather than a model name supplied by a response."""

    deployment_id: Identifier
    adapter_id: Identifier
    model_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    tokenizer_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    tokenizer_revision: str = Field(min_length=1, max_length=512)
    served_model_id: str = Field(min_length=1, max_length=1024, repr=False)
    info_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_revision: str = Field(min_length=1, max_length=128)
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class RuntimeVerifier(Protocol):
    async def verify(self) -> EmbeddingRuntimeIdentity:
        """Recheck trusted deployment and local assets; never infer identity from a URL."""
        ...


class EmbeddingItem(_ImmutableModel):
    item_id: Identifier
    text: str = Field(min_length=1, max_length=131072, repr=False)
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _source_identity(self) -> EmbeddingItem:
        if not self.text.strip() or "\0" in self.text:
            raise ValueError("Embedding text must be nonempty Unicode")
        try:
            raw = self.text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Embedding text must contain valid Unicode") from None
        if hashlib.sha256(raw).hexdigest() != self.input_hash:
            raise ValueError("The source hash does not match the supplied text")
        return self


class EmbeddingRequest(_ImmutableModel):
    profile_id: Identifier
    profile_revision: Identifier
    task_kind: Literal["query", "document"]
    items: tuple[EmbeddingItem, ...] = Field(min_length=1, max_length=16)
    deadline: float = Field(gt=0, allow_inf_nan=False)
    workspace_id: Identifier = "development"
    trace_id: Identifier

    @model_validator(mode="after")
    def _unique_items(self) -> EmbeddingRequest:
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("Embedding item identities must be unique within a request")
        return self


class PreparedEmbeddingItem(_ImmutableModel):
    item_id: Identifier
    text: str = Field(repr=False)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    token_count: int = Field(ge=1)


UsageProvenance = Literal["provider_reported", "tokenizer_counted_proxy", "unknown"]


class EmbeddingBatch(_ImmutableModel):
    profile_id: Identifier
    profile_revision: Identifier
    model_revision: str
    model_digest: str
    tokenizer_digest: str
    task_kind: Literal["query", "document"]
    item_ids: tuple[Identifier, ...]
    source_hashes: tuple[str, ...]
    input_hashes: tuple[str, ...]
    vectors: tuple[tuple[float, ...], ...] = Field(repr=False)
    token_counts: tuple[int, ...]
    usage_tokens: int | None = Field(default=None, ge=0)
    usage_provenance: UsageProvenance
    duration_ms: float = Field(ge=0, allow_inf_nan=False)


class EmbeddingReservation(_ImmutableModel):
    reservation_id: Identifier


class EmbeddingDispatchPort(Protocol):
    async def reserve(
        self,
        *,
        profile_id: str,
        profile_revision: str,
        deployment_id: str,
        task_kind: Literal["query", "document"],
        token_count: int,
        deadline: float,
        workspace_id: str = "development",
    ) -> EmbeddingReservation:
        """Reserve through the one owner before sending any query/document inference."""
        ...

    async def mark_sent(self, reservation: EmbeddingReservation) -> None:
        """Retain attempted charges even if a sent request is cancelled or ambiguous."""
        ...

    async def finish(
        self,
        reservation: EmbeddingReservation,
        *,
        outcome: Literal["success", "failed", "ambiguous", "cancelled"],
        usage_tokens: int | None,
        usage_provenance: UsageProvenance,
        error_code: EmbeddingErrorCode | None = None,
    ) -> None:
        """Reconcile once without confusing tokenizer proxies with actual provider usage."""
        ...


class EmbeddingPort(Protocol):
    async def warm_up_async(self) -> None:
        """Perform actual asynchronous setup and positive runtime attestation."""
        ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Embed ordered items under their pinned input/profile/deadline and shared admission owner."""
        ...

    async def close_async(self) -> None:
        """Release transport resources without changing source data or provider configuration."""
        ...


def prepare_embedding_request(
    profile: EmbeddingProfile, request: EmbeddingRequest, counter: ExactModelCounter
) -> tuple[PreparedEmbeddingItem, ...]:
    """Count the exact NFC/instruction-formatted text that will be sent, without truncation."""
    if (request.profile_id, request.profile_revision) != (profile.profile_id, profile.profile_revision):
        raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
    if request.deadline <= monotonic():
        raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
    if counter.counter_revision != profile.tokenizer_revision:
        raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH)
    if len(request.items) > profile.max_batch_items:
        raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
    result = []
    total_bytes = 0
    for item in request.items:
        text = unicodedata.normalize("NFC", item.text)
        if request.task_kind == "query":
            text = f"Instruct: {profile.query_instruction}\nQuery: {text}"
        raw = text.encode("utf-8")
        total_bytes += len(raw)
        if total_bytes > 4_194_304:
            raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
        try:
            count = counter.count_tokens(text)
        except Exception:
            raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH) from None
        if type(count) is not int or count <= 0:
            raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH)
        if count > profile.max_tokens:
            raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
        result.append(
            PreparedEmbeddingItem(
                item_id=item.item_id,
                text=text,
                source_hash=item.input_hash,
                input_hash=hashlib.sha256(raw).hexdigest(),
                token_count=count,
            )
        )
    if sum(item.token_count for item in result) > profile.max_batch_tokens:
        raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
    return tuple(result)


def validate_embedding_batch(
    profile: EmbeddingProfile,
    request: EmbeddingRequest,
    prepared: tuple[PreparedEmbeddingItem, ...],
    *,
    vectors: Sequence[Sequence[float]],
    usage_tokens: int | None,
    usage_provenance: UsageProvenance,
    duration_ms: float,
) -> EmbeddingBatch:
    """Validate exact cardinality, finite full dimensions and explicit normalized-score semantics."""
    if len(vectors) != len(prepared) or len(prepared) != len(request.items):
        raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
    checked = []
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != profile.dimensions:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_DIMENSION)
        try:
            finite = all(type(value) in {float, int} and math.isfinite(value) for value in vector)
        except OverflowError:
            finite = False
        if not finite:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        norm = math.hypot(*vector)
        if not math.isfinite(norm) or abs(norm - 1.0) > 0.001:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        checked.append(tuple(float(value) for value in vector))
    total = sum(item.token_count for item in prepared)
    if usage_provenance == "unknown":
        if usage_tokens is not None:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
    elif type(usage_tokens) is not int or usage_tokens != total:
        raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH)
    if not math.isfinite(duration_ms) or duration_ms < 0:
        raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
    return EmbeddingBatch(
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        model_revision=profile.model_revision,
        model_digest=profile.model_digest,
        tokenizer_digest=profile.tokenizer_digest,
        task_kind=request.task_kind,
        item_ids=tuple(item.item_id for item in prepared),
        source_hashes=tuple(item.source_hash for item in prepared),
        input_hashes=tuple(item.input_hash for item in prepared),
        vectors=tuple(checked),
        token_counts=tuple(item.token_count for item in prepared),
        usage_tokens=usage_tokens,
        usage_provenance=usage_provenance,
        duration_ms=duration_ms,
    )

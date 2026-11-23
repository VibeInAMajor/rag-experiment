"""Offline transport qualification never sends input outside a mock loopback service."""

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx
import pytest

from apps.workbench.api import embedding_adapters
from apps.workbench.api.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingProfile,
    EmbeddingRequest,
    EmbeddingReservation,
    EmbeddingRuntimeIdentity,
    UsageProvenance,
)
from apps.workbench.api.embedding_adapters import TeiEmbeddingAdapter


class _Counter:
    counter_revision = "offline-counter-r1"

    def count_tokens(self, text: str) -> int:
        return len(text.split()) + 1


class _Governor:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.reject = False

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
        if not workspace_id:
            raise AssertionError("Workspace scope is required")
        self.events.append(("reserve", (profile_id, profile_revision, deployment_id, task_kind, token_count, deadline)))
        if self.reject:
            raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
        return EmbeddingReservation(reservation_id="test-reservation")

    async def mark_sent(self, reservation: EmbeddingReservation) -> None:
        self.events.append(("sent", reservation.reservation_id))

    async def finish(
        self,
        reservation: EmbeddingReservation,
        *,
        outcome: Literal["success", "failed", "ambiguous", "cancelled"],
        usage_tokens: int | None,
        usage_provenance: UsageProvenance,
        error_code: EmbeddingErrorCode | None = None,
    ) -> None:
        if error_code is not None and not isinstance(error_code, EmbeddingErrorCode):
            raise AssertionError("Provider errors require a safe bounded code")
        self.events.append(("finish", (reservation.reservation_id, outcome, usage_tokens, usage_provenance)))


class _Verifier:
    def __init__(self, identity: EmbeddingRuntimeIdentity) -> None:
        self.identity = identity
        self.calls = 0
        self.restart_after: int | None = None

    async def verify(self) -> EmbeddingRuntimeIdentity:
        self.calls += 1
        if self.restart_after is not None and self.calls >= self.restart_after:
            return self.identity.model_copy(update={"deployment_id": "restarted-deployment"})
        return self.identity


def _profile(**changes: Any) -> EmbeddingProfile:
    return EmbeddingProfile(
        **{
            "profile_id": "local-embedding",
            "profile_revision": "local-embedding-r1",
            "provider_adapter_id": "tei-openai",
            "model_id": "Qwen/Qwen3-Embedding-4B",
            "model_revision": "a" * 40,
            "model_digest": "b" * 64,
            "tokenizer_digest": "c" * 64,
            "tokenizer_revision": _Counter.counter_revision,
            "dimensions": 32,
            **changes,
        }
    )


def _request(*texts: str, purpose: Literal["query", "document"] = "document") -> EmbeddingRequest:
    return EmbeddingRequest(
        profile_id="local-embedding",
        profile_revision="local-embedding-r1",
        task_kind=purpose,
        items=tuple(
            EmbeddingItem(item_id=f"item-{index}", text=text, input_hash=hashlib.sha256(text.encode()).hexdigest())
            for index, text in enumerate(texts or ("private document",))
        ),
        deadline=time.monotonic() + 10.0,
        trace_id="offline-trace",
    )


def _info() -> dict[str, Any]:
    return {
        "served_model_name": "local-qwen",
        "auto_truncate": False,
        "model_dtype": "float16",
        "max_input_length": 8192,
        "max_batch_tokens": 16384,
        "max_client_batch_size": 32,
        "model_type": {"embedding": {"pooling": "last_token"}},
    }


def _identity(info: dict[str, Any]) -> EmbeddingRuntimeIdentity:
    return EmbeddingRuntimeIdentity(
        deployment_id="local-deployment",
        adapter_id="tei-openai",
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision=_Counter.counter_revision,
        served_model_id="local-qwen",
        info_digest=hashlib.sha256(
            json.dumps(info, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        runtime_revision="tei-1.9.4",
        evidence_digest="d" * 64,
    )


def _response(payload: dict[str, Any]) -> dict[str, Any]:
    total = sum(_Counter().count_tokens(text) for text in payload["input"])
    return {
        "object": "list",
        "model": "local-qwen",
        "data": [
            {"object": "embedding", "index": index, "embedding": [1.0] + [0.0] * 31}
            for index in range(len(payload["input"]))
        ],
        "usage": {"prompt_tokens": total, "total_tokens": total},
    }


def _adapter(
    *,
    governor: _Governor | None,
    transform: Callable[[dict[str, Any]], Any] = _response,
    status: int = 200,
    info: dict[str, Any] | None = None,
    profile: EmbeddingProfile | None = None,
    raw_response: bytes | None = None,
) -> tuple[TeiEmbeddingAdapter, list[dict[str, Any]], _Verifier]:
    metadata = _info() if info is None else info
    verifier = _Verifier(_identity(metadata))
    calls: list[dict[str, Any]] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=metadata)
        assert request.url.path in {"/v1/embeddings", "/embed"}
        assert governor is not None and governor.events[-1][0] == "sent"
        payload = json.loads(request.content)
        calls.append(payload)
        if raw_response is not None:
            return httpx.Response(status, content=raw_response)
        if request.url.path == "/embed":
            return httpx.Response(status, json=[[1.0] + [0.0] * 31])
        return httpx.Response(status, json=transform(payload))

    adapter = TeiEmbeddingAdapter(
        _profile() if profile is None else profile,
        endpoint="http://127.0.0.1:8081",
        token_counter=_Counter(),
        governor=governor,
        identity_verifier=verifier,
        transport=httpx.MockTransport(handle),
    )
    return adapter, calls, verifier


@pytest.mark.asyncio
async def test_query_and_document_share_admission_with_exact_sent_text() -> None:
    """Formatting, hashes, counted usage and ordering survive the real adapter boundary."""
    governor = _Governor()
    adapter, calls, verifier = _adapter(governor=governor)
    assert calls == [] and verifier.calls == 0
    await adapter.warm_up_async()
    await adapter.warm_up_async()
    assert verifier.calls == 1
    document = await adapter.embed(_request("Cafe\u0301 private text", "second input"))
    query = await adapter.embed(_request("private question", purpose="query"))
    assert calls[0]["input"] == ["Café private text", "second input"]
    assert calls[1]["input"] == [f"Instruct: {_profile().query_instruction}\nQuery: private question"]
    assert calls[0]["encoding_format"] == "float" and calls[0]["dimensions"] == 32
    assert document.item_ids == ("item-0", "item-1")
    assert document.source_hashes[0] != document.input_hashes[0]
    assert document.usage_provenance == query.usage_provenance == "provider_reported"
    assert query.usage_tokens == sum(query.token_counts)
    assert [event[0] for event in governor.events] == ["reserve", "sent", "finish"] * 2
    assert verifier.calls == 5
    await adapter.close_async()
    await adapter.close_async()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:8081",
        "http://localhost:8081",
        "http://example.com:8081",
        "http://u:p@127.0.0.1:8081",
        "http://127.0.0.1:8081/remote",
        "http://127.0.0.1:8081?key=secret",
    ],
)
def test_only_explicit_loopback_transport_is_accepted(endpoint: str) -> None:
    """The local model profile cannot redirect input to an external host or credentialed URL."""
    with pytest.raises(EmbeddingError) as error:
        TeiEmbeddingAdapter(
            _profile(),
            endpoint=endpoint,
            token_counter=_Counter(),
            governor=_Governor(),
            identity_verifier=_Verifier(_identity(_info())),
        )
    assert error.value.code == EmbeddingErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_missing_or_busy_governor_never_dispatches_inference() -> None:
    """A missing shared owner is an explicit refusal, and admission failure never reaches POST."""
    missing, calls, _ = _adapter(governor=None)
    with pytest.raises(EmbeddingError) as error:
        await missing.embed(_request())
    assert error.value.code == EmbeddingErrorCode.NOT_QUALIFIED and calls == []
    governor = _Governor()
    governor.reject = True
    busy, calls, _ = _adapter(governor=governor)
    with pytest.raises(EmbeddingError) as error:
        await busy.embed(_request())
    assert error.value.code == EmbeddingErrorCode.CAPACITY_BUSY and calls == []
    await busy.close_async()


def _malformed(payload: dict[str, Any], defect: str) -> dict[str, Any]:
    response = _response(payload)
    if defect == "model":
        response["model"] = "wrong-model"
    elif defect == "cardinality":
        response["data"].pop()
    elif defect == "reorder":
        response["data"].reverse()
    elif defect == "duplicate-index":
        response["data"][1]["index"] = 0
    elif defect == "dimension":
        response["data"][0]["embedding"].pop()
    elif defect == "zero-norm":
        response["data"][0]["embedding"] = [0.0] * 32
    elif defect == "bool":
        response["data"][0]["embedding"][0] = True
    elif defect == "tokens":
        response["usage"]["prompt_tokens"] += 1
    elif defect == "missing-usage":
        del response["usage"]
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["model", "cardinality", "reorder", "duplicate-index", "dimension", "zero-norm", "bool", "tokens"]
)
async def test_untrusted_response_never_becomes_a_batch(defect: str) -> None:
    """Wrong identity/order/dimensions/norm/usage are fail-closed and reconciled conservatively."""
    governor = _Governor()
    adapter, _, _ = _adapter(governor=governor, transform=lambda payload: _malformed(payload, defect))
    with pytest.raises(EmbeddingError):
        await adapter.embed(_request("first text", "second text"))
    assert governor.events[-1] == ("finish", ("test-reservation", "ambiguous", None, "unknown"))
    await adapter.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [
        (429, EmbeddingErrorCode.RATE_LIMITED),
        (503, EmbeddingErrorCode.MODEL_UNAVAILABLE),
        (307, EmbeddingErrorCode.MODEL_UNAVAILABLE),
        (413, EmbeddingErrorCode.REQUEST_TOO_LARGE),
    ],
)
async def test_provider_errors_are_safe_and_never_retry(status: int, code: EmbeddingErrorCode) -> None:
    """No provider details enter errors, and retryable statuses retain one attempted charge."""
    governor = _Governor()
    adapter, calls, _ = _adapter(governor=governor, status=status, transform=lambda _payload: {"error": "secret-input"})
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == code and str(error.value) == code.value
    assert len(calls) == 1
    assert governor.events[-1][1][1] == ("failed" if status == 429 else "ambiguous")
    await adapter.close_async()


@pytest.mark.asyncio
async def test_runtime_reload_discards_inflight_output() -> None:
    """The trusted verifier is checked after provider work, before any batch is returned."""
    governor = _Governor()
    adapter, _, verifier = _adapter(governor=governor)
    await adapter.warm_up_async()
    verifier.restart_after = 3
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH
    assert governor.events[-1][1][1] == "ambiguous"
    with pytest.raises(EmbeddingError) as invalidated:
        await adapter.embed(_request())
    assert invalidated.value.code == EmbeddingErrorCode.NOT_QUALIFIED
    await adapter.close_async()


@pytest.mark.asyncio
async def test_cancellation_reconciles_sent_reservation() -> None:
    """Cancellation retains accounting without inventing a zero provider usage value."""
    governor = _Governor()
    reached = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=_info())
        reached.set()
        await asyncio.Event().wait()
        raise AssertionError("Cancelled inference must not resume")

    adapter = TeiEmbeddingAdapter(
        _profile(),
        endpoint="http://127.0.0.1:8081",
        token_counter=_Counter(),
        governor=governor,
        identity_verifier=_Verifier(_identity(_info())),
        transport=httpx.MockTransport(handle),
    )
    pending = asyncio.create_task(adapter.embed(_request()))
    await asyncio.wait_for(reached.wait(), timeout=1.0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert governor.events[-1] == ("finish", ("test-reservation", "cancelled", None, "unknown"))
    await adapter.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"auto_truncate": True},
        {"max_input_length": "8192"},
        {"max_batch_tokens": 100},
        {"max_client_batch_size": 1},
        {"model_dtype": "float32"},
        {"model_type": {"embedding": {"pooling": "mean"}}},
    ],
)
async def test_attested_metadata_must_support_untruncated_profile(changes: dict[str, Any]) -> None:
    """An otherwise attested deployment cannot silently change truncation or batch limits."""
    adapter, calls, _ = _adapter(governor=_Governor(), info={**_info(), **changes})
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.IDENTITY_MISMATCH and calls == []


@pytest.mark.asyncio
async def test_missing_provider_usage_is_explicitly_unknown() -> None:
    """Missing usage never becomes a fabricated provider-reported counter."""
    governor = _Governor()
    adapter, _, _ = _adapter(governor=governor, transform=lambda payload: _malformed(payload, "missing-usage"))
    batch = await adapter.embed(_request())
    assert batch.usage_tokens is None and batch.usage_provenance == "unknown"
    assert governor.events[-1] == ("finish", ("test-reservation", "success", None, "unknown"))
    await adapter.close_async()


@pytest.mark.asyncio
async def test_native_diagnostic_has_single_item_and_proxy_usage() -> None:
    """The native comparison path cannot bypass dispatch or pretend to have indexed rows/actual usage."""
    governor = _Governor()
    adapter, calls, _ = _adapter(governor=governor)
    with pytest.raises(EmbeddingError) as error:
        await adapter.probe_native(_request("first", "second"))
    assert error.value.code == EmbeddingErrorCode.INVALID_REQUEST and calls == []
    batch = await adapter.probe_native(_request("native comparison"))
    assert calls == [{"inputs": ["native comparison"], "normalize": True, "truncate": False, "dimensions": 32}]
    assert batch.usage_provenance == "tokenizer_counted_proxy"
    assert governor.events[-1] == ("finish", ("test-reservation", "success", 3, "tokenizer_counted_proxy"))
    await adapter.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [b"{invalid", b'{"data":[],"data":[]}', b'{"value":NaN}', b'{"value":Infinity}', b"\xff"]
)
async def test_malformed_json_never_exposes_provider_body(body: bytes) -> None:
    """Invalid JSON, duplicate keys and nonfinite constants have the same safe refusal."""
    governor = _Governor()
    adapter, _, _ = _adapter(governor=governor, raw_response=body)
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.INVALID_RESPONSE
    assert str(error.value) == "INVALID_RESPONSE"
    await adapter.close_async()


@pytest.mark.asyncio
async def test_response_body_is_bounded_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider cannot force an unbounded decoded response allocation."""
    monkeypatch.setattr(embedding_adapters, "_MAX_RESPONSE_BYTES", 64)
    adapter, _, _ = _adapter(governor=_Governor(), raw_response=b" " * 65)
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.INVALID_RESPONSE
    await adapter.close_async()


@pytest.mark.asyncio
async def test_expired_deadline_never_attests_or_dispatches() -> None:
    """Admission refuses expired requests before even querying metadata."""
    adapter, calls, verifier = _adapter(governor=_Governor())
    request = _request().model_copy(update={"deadline": time.monotonic() - 1.0})
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(request)
    assert error.value.code == EmbeddingErrorCode.TIMEOUT and calls == [] and verifier.calls == 0


@pytest.mark.asyncio
async def test_preparation_time_consumes_the_total_deadline() -> None:
    """Synchronous token counting cannot extend the absolute inference window."""

    class SlowCounter(_Counter):
        def count_tokens(self, text: str) -> int:
            time.sleep(0.02)
            return super().count_tokens(text)

    verifier = _Verifier(_identity(_info()))
    adapter = TeiEmbeddingAdapter(
        _profile(timeout_seconds=0.01),
        endpoint="http://127.0.0.1:8081",
        token_counter=SlowCounter(),
        governor=_Governor(),
        identity_verifier=verifier,
    )
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.TIMEOUT and verifier.calls == 0


@pytest.mark.asyncio
async def test_deadline_covers_sent_provider_wait() -> None:
    """A hanging provider consumes one bounded attempt and releases the reservation on timeout."""
    governor = _Governor()

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(200, json=_info())
        await asyncio.Event().wait()
        raise AssertionError("Timed-out inference must not resume")

    adapter = TeiEmbeddingAdapter(
        _profile(timeout_seconds=0.02),
        endpoint="http://127.0.0.1:8081",
        token_counter=_Counter(),
        governor=governor,
        identity_verifier=_Verifier(_identity(_info())),
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(EmbeddingError) as error:
        await adapter.embed(_request())
    assert error.value.code == EmbeddingErrorCode.TIMEOUT
    assert governor.events[-1] == ("finish", ("test-reservation", "cancelled", None, "unknown"))
    await adapter.close_async()

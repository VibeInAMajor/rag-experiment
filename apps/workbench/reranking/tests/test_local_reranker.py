"""Test the diagnostic adapter with bounded mock loopback responses."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from apps.workbench.reranking import local_reranker
from apps.workbench.reranking.local_reranker import MAX_CANDIDATES, LocalReranker, RerankErrorCode, RerankFailure

_MODEL = "Qwen/Qwen3-Reranker-0.6B"
pytestmark = pytest.mark.asyncio


def _models(*, model: str = _MODEL, pair_limit: int = 4096) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": model, "max_model_len": pair_limit}]})


def _scores(*rows: tuple[int, float], model: str = _MODEL) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(
            {"model": model, "results": [{"index": index, "relevance_score": score} for index, score in rows]}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )


def _transport(handle: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    def dispatch(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.url.port == 8083
        if request.url.path == "/v1/models":
            assert request.method == "GET"
            return _models()
        assert request.url.path == "/rerank"
        assert request.method == "POST"
        return handle(request)

    return httpx.MockTransport(dispatch)


async def test_preserves_whole_multilingual_code_candidates_and_stable_score_order() -> None:
    """Unsorted batch responses must rejoin by index before the stable global sort."""
    query = "Що означає  kubectl get pods?"
    documents = ["  kubectl get pods\n", " kubectl logs --previous", "Gravedad y energía"]
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == _MODEL
        assert body["query"] == query
        assert body["top_n"] == body["max_tokens_per_query"] == body["max_tokens_per_doc"] == 0
        assert body["truncate_prompt_tokens"] is None
        assert body["use_activation"] is True
        assert request.headers["Accept-Encoding"] == "identity"
        calls.extend(body["documents"])
        return _scores((1, 0.4), (0, 0.7)) if len(calls) == 2 else _scores((0, 0.7))

    async with LocalReranker(batch_size=2, transport=_transport(handle)) as reranker:
        ranked = await reranker.rank(query, documents)

    assert calls == documents
    assert ranked.indices == (0, 2, 1)
    assert ranked.scores == (0.7, 0.4, 0.7)
    assert len(ranked.batch_latencies_ms) == 2
    assert ranked.elapsed_ms >= sum(ranked.batch_latencies_ms)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_scores((0, 0.5), (0, 0.2)), RerankErrorCode.INVALID_RESPONSE),
        (_scores((0, 0.5), (2, 0.2)), RerankErrorCode.INVALID_RESPONSE),
        (_scores((0, 0.5)), RerankErrorCode.INVALID_RESPONSE),
        (_scores((0, float("nan")), (1, 0.2)), RerankErrorCode.INVALID_RESPONSE),
        (_scores((0, float("inf")), (1, 0.2)), RerankErrorCode.INVALID_RESPONSE),
        (_scores((0, 0.5), (1, 0.2), model="other-model"), RerankErrorCode.IDENTITY_MISMATCH),
        (httpx.Response(200, content=b'{"model":"x","model":"y"}'), RerankErrorCode.INVALID_RESPONSE),
        (httpx.Response(400, content=b"oversized pair: test query"), RerankErrorCode.INPUT_REJECTED),
        (httpx.Response(500, content=b"CUDA out of memory: test query"), RerankErrorCode.RUNTIME_UNAVAILABLE),
        (httpx.Response(307, headers={"Location": "https://example.invalid"}), RerankErrorCode.RUNTIME_UNAVAILABLE),
    ],
)
async def test_refuses_bad_results_or_failed_batches_without_retries(
    response: httpx.Response, expected: RerankErrorCode
) -> None:
    """Code-only failures leave the original corpus and rankings with their caller."""
    calls = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    async with LocalReranker(transport=_transport(handle)) as reranker:
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("test query", ["first evidence", "second evidence"])
    assert failure.value.code == expected
    assert "test query" not in str(failure.value)
    assert calls == 1


async def test_a_late_batch_failure_does_not_return_partial_ranks() -> None:
    """A failed call cannot turn the previous batch into a successful ranking."""
    calls = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _scores((0, 0.3)) if calls == 1 else httpx.Response(400)

    async with LocalReranker(batch_size=1, transport=_transport(handle)) as reranker:
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("query", ["valid", "too long for runtime", "must stay unsent"])
    assert failure.value.code == RerankErrorCode.INPUT_REJECTED
    assert calls == 2


@pytest.mark.parametrize(("other_model", "pair_limit"), [("other-model", 4096), (_MODEL, 8192)])
async def test_attestation_rejects_unexpected_model_or_token_limit(other_model: str, pair_limit: int) -> None:
    """The diagnostic endpoint must serve the pinned configuration."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return _models(model=other_model, pair_limit=pair_limit)

    reranker = LocalReranker(transport=httpx.MockTransport(handle))
    with pytest.raises(RerankFailure) as failure:
        await reranker.warm_up_async()
    assert failure.value.code == RerankErrorCode.IDENTITY_MISMATCH
    with pytest.raises(RerankFailure) as closed:
        await reranker.rank("query", ["evidence"])
    assert closed.value.code == RerankErrorCode.NOT_READY


@pytest.mark.parametrize("documents", [[], ["x"] * (MAX_CANDIDATES + 1), ["good", "\udcff"], ["x" * 131_073]])
async def test_invalid_candidates_are_rejected_without_any_rank_post(documents: list[str]) -> None:
    """Preflight catches invalid documents even when a previous batch could have run."""

    def handle(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid inputs must not reach the scoring endpoint")

    async with LocalReranker(transport=_transport(handle)) as reranker:
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("query", documents)
    assert failure.value.code == RerankErrorCode.INVALID_INPUT


async def test_oversized_response_is_rejected() -> None:
    """An echoed body is subject to the same bounded response reader."""
    transport = _transport(lambda _request: httpx.Response(200, content=b"x" * 4_194_305))
    async with LocalReranker(transport=transport) as reranker:
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("query", ["evidence"])
    assert failure.value.code == RerankErrorCode.INVALID_RESPONSE


async def test_cancellation_releases_the_single_in_flight_slot() -> None:
    """A cancelled invocation leaves the client ready for the following trial."""
    entered = asyncio.Event()
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/v1/models":
            return _models()
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()
        return _scores((0, 0.2))

    async with LocalReranker(transport=httpx.MockTransport(handle)) as reranker:
        active_rank = asyncio.create_task(reranker.rank("query", ["evidence"]))
        await entered.wait()
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("other query", ["other evidence"])
        assert failure.value.code == RerankErrorCode.BUSY
        active_rank.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active_rank
        assert (await reranker.rank("query", ["evidence"])).indices == (0,)
    assert calls == 2


@pytest.mark.parametrize("deadline_setting", ["BATCH_TIMEOUT_SECONDS", "RANK_TIMEOUT_SECONDS"])
async def test_unresponsive_batch_stops_at_deadline(monkeypatch: pytest.MonkeyPatch, deadline_setting: str) -> None:
    """Check both the per-batch and whole-ranking clocks."""
    monkeypatch.setattr(local_reranker, deadline_setting, 0.02)

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _models()
        await asyncio.Event().wait()
        pytest.fail("The timeout did not stop the batch")

    async with LocalReranker(transport=httpx.MockTransport(handle)) as reranker:
        with pytest.raises(RerankFailure) as failure:
            await reranker.rank("query", ["evidence"])
    assert failure.value.code == RerankErrorCode.TIMEOUT

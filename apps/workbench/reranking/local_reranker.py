"""Bounded qualification-only transport for the standalone local reranker."""

import asyncio
import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

import httpx

DEFAULT_BATCH_SIZE = 8
MAX_BATCH_SIZE = 16
MAX_CANDIDATES = 50
BATCH_TIMEOUT_SECONDS = 15
RANK_TIMEOUT_SECONDS = 90

_ENDPOINT = "http://127.0.0.1:8083"
_MODEL = "Qwen/Qwen3-Reranker-0.6B"
_MAX_PAIR_TOKENS = 4096
_MAX_TEXT_BYTES = 131_072
_MAX_REQUEST_BYTES = 1_048_576
_MAX_RESPONSE_BYTES = 4_194_304


class RerankErrorCode(StrEnum):
    """Safe failure labels for the qualification runner."""

    INVALID_INPUT = "invalid_input"
    NOT_READY = "not_ready"
    BUSY = "busy"
    TIMEOUT = "timeout"
    INPUT_REJECTED = "input_rejected"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    INVALID_RESPONSE = "invalid_response"
    IDENTITY_MISMATCH = "identity_mismatch"


class RerankFailure(Exception):
    """A failed rank operation with no candidate content or provider exception text."""

    def __init__(self, code: RerankErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class RerankResult:
    """A complete ordering, scores indexed in input order, and measured client timings."""

    indices: tuple[int, ...]
    scores: tuple[float, ...]
    elapsed_ms: float
    batch_latencies_ms: tuple[float, ...]


class LocalReranker:
    """Rank exactly the supplied candidates against the pinned loopback model."""

    def __init__(
        self, *, batch_size: int = DEFAULT_BATCH_SIZE, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise RerankFailure(RerankErrorCode.INVALID_INPUT)
        self._batch_size = batch_size
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._rank_lock = asyncio.Lock()

    async def warm_up_async(self) -> None:
        """Open a local client and verify the served model and configured pair limit."""
        async with self._lifecycle_lock:
            if self._client is not None:
                return
            client = httpx.AsyncClient(
                base_url=_ENDPOINT,
                transport=self._transport,
                timeout=BATCH_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            )
            try:
                _check_model(await _request(client, path="/v1/models"))
            except BaseException:
                await client.aclose()
                raise
            self._client = client

    async def close_async(self) -> None:
        """Release resources after the active rank ends."""
        async with self._lifecycle_lock, self._rank_lock:
            client, self._client = self._client, None
            if client is not None:
                await client.aclose()

    async def __aenter__(self) -> Self:
        await self.warm_up_async()
        return self

    async def __aexit__(self, *_error: object) -> None:
        await self.close_async()

    async def rank(self, query: str, documents: Sequence[str]) -> RerankResult:
        """Submit bounded batches in order and return only a complete, verified ranking."""
        if self._rank_lock.locked():
            raise RerankFailure(RerankErrorCode.BUSY)
        started = time.monotonic()
        async with self._rank_lock:
            client = self._client
            if client is None:
                raise RerankFailure(RerankErrorCode.NOT_READY)
            batches = _prepare_batches(query, documents, batch_size=self._batch_size)
            scores: list[float] = []
            latencies: list[float] = []
            try:
                async with asyncio.timeout(RANK_TIMEOUT_SECONDS):
                    for body, count in batches:
                        batch_started = time.monotonic()
                        response = await _request(client, path="/rerank", body=body)
                        scores.extend(_batch_scores(response, expected_count=count))
                        latencies.append((time.monotonic() - batch_started) * 1000)
            except TimeoutError:
                raise RerankFailure(RerankErrorCode.TIMEOUT) from None
        indices = tuple(sorted(range(len(scores)), key=lambda index: -scores[index]))
        return RerankResult(
            indices=indices,
            scores=tuple(scores),
            elapsed_ms=(time.monotonic() - started) * 1000,
            batch_latencies_ms=tuple(latencies),
        )


def _check_model(response: object) -> None:
    rows = response.get("data") if isinstance(response, dict) else None
    if not isinstance(rows, list) or len(rows) != 1:
        raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
    model = rows[0]
    if (
        not isinstance(model, dict)
        or model.get("id") != _MODEL
        or type(model.get("max_model_len")) is not int
        or model["max_model_len"] != _MAX_PAIR_TOKENS
    ):
        raise RerankFailure(RerankErrorCode.IDENTITY_MISMATCH)


def _validate_text(text: object) -> None:
    if not isinstance(text, str) or not text.strip() or "\x00" in text or len(text) > _MAX_TEXT_BYTES:
        raise RerankFailure(RerankErrorCode.INVALID_INPUT)
    try:
        if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise RerankFailure(RerankErrorCode.INVALID_INPUT)
    except UnicodeEncodeError:
        raise RerankFailure(RerankErrorCode.INVALID_INPUT) from None


def _prepare_batches(query: str, documents: Sequence[str], *, batch_size: int) -> list[tuple[bytes, int]]:
    if not isinstance(documents, Sequence) or isinstance(documents, str) or not 1 <= len(documents) <= MAX_CANDIDATES:
        raise RerankFailure(RerankErrorCode.INVALID_INPUT)
    _validate_text(query)
    candidates = tuple(documents[index] for index in range(len(documents)))
    for document in candidates:
        _validate_text(document)
    batches = []
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        body = json.dumps(
            {
                "model": _MODEL,
                "query": query,
                "documents": batch,
                "top_n": 0,
                "use_activation": True,
                "truncate_prompt_tokens": None,
                "max_tokens_per_query": 0,
                "max_tokens_per_doc": 0,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise RerankFailure(RerankErrorCode.INVALID_INPUT)
        batches.append((body, len(batch)))
    return batches


async def _request(client: httpx.AsyncClient, *, path: str, body: bytes | None = None) -> object:
    try:
        async with (
            asyncio.timeout(BATCH_TIMEOUT_SECONDS),
            client.stream(
                "GET" if body is None else "POST",
                path,
                content=body,
                headers=None if body is None else {"Content-Type": "application/json"},
            ) as response,
        ):
            if response.status_code in {400, 413, 422}:
                raise RerankFailure(RerankErrorCode.INPUT_REJECTED)
            if response.status_code != 200:
                raise RerankFailure(RerankErrorCode.RUNTIME_UNAVAILABLE)
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                if len(payload) + len(chunk) > _MAX_RESPONSE_BYTES:
                    raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
                payload.extend(chunk)
    except (TimeoutError, httpx.TimeoutException):
        raise RerankFailure(RerankErrorCode.TIMEOUT) from None
    except httpx.HTTPError:
        raise RerankFailure(RerankErrorCode.RUNTIME_UNAVAILABLE) from None
    try:
        return json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise RerankFailure(RerankErrorCode.INVALID_RESPONSE) from None


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def _unique_object(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _batch_scores(response: object, *, expected_count: int) -> tuple[float, ...]:
    if not isinstance(response, dict):
        raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
    if response.get("model") != _MODEL:
        raise RerankFailure(RerankErrorCode.IDENTITY_MISMATCH)
    rows = response.get("results")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
    scores: dict[int, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
        index, score = row.get("index"), row.get("relevance_score")
        if type(index) is not int or not 0 <= index < expected_count or index in scores:
            raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
        try:
            numerical_score = float(score)
        except OverflowError:
            raise RerankFailure(RerankErrorCode.INVALID_RESPONSE) from None
        if not math.isfinite(numerical_score):
            raise RerankFailure(RerankErrorCode.INVALID_RESPONSE)
        scores[index] = numerical_score
    return tuple(scores[index] for index in range(expected_count))

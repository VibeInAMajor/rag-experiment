"""Bounded local TEI transport behind the shared embedding dispatch owner."""

import asyncio
import hashlib
import json
import math
import time
from typing import Any

import httpx

from apps.workbench.chunking.chunking import ExactModelCounter
from apps.workbench.embedding.embedding import (
    EmbeddingBatch,
    EmbeddingDispatchPort,
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingProfile,
    EmbeddingRequest,
    EmbeddingRuntimeIdentity,
    PreparedEmbeddingItem,
    RuntimeVerifier,
    UsageProvenance,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.embedding.embedding_config import validate_embedding_endpoint

_MAX_REQUEST_BYTES = 4_194_304
_MAX_INFO_BYTES = 65_536
_MAX_RESPONSE_BYTES = 8_388_608


def _local_endpoint(endpoint: str) -> str:
    try:
        return validate_embedding_endpoint(endpoint)
    except ValueError:
        raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST) from None


def _decode_json(body: bytes) -> Any:
    try:
        return json.loads(body, parse_constant=_invalid_constant, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE) from None


def _invalid_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON value")


def _unique_object(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _within_capacity(info: dict[str, Any], *, name: str, required: int) -> bool:
    actual = info.get(name)
    return type(actual) is int and actual >= required


class TeiEmbeddingAdapter:
    """Use the attested TEI OpenAI route without retries, redirects or environment proxies."""

    def __init__(
        self,
        profile: EmbeddingProfile,
        *,
        endpoint: str,
        token_counter: ExactModelCounter,
        governor: EmbeddingDispatchPort | None,
        identity_verifier: RuntimeVerifier,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if profile.provider_adapter_id != "tei-openai":
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        self._profile = profile
        self._endpoint = _local_endpoint(endpoint)
        self._token_counter = token_counter
        self._governor = governor
        self._identity_verifier = identity_verifier
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._identity: EmbeddingRuntimeIdentity | None = None
        self._invalidated = False
        self._lifecycle_lock = asyncio.Lock()

    async def warm_up_async(self) -> None:
        """Construct the async client and attest metadata without executing model inference."""
        async with self._lifecycle_lock:
            if self._invalidated:
                raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
            if self._client is not None:
                return
            if self._governor is None:
                raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
            self._client = httpx.AsyncClient(
                base_url=self._endpoint,
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(self._profile.timeout_seconds),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            )
            try:
                async with asyncio.timeout(self._profile.timeout_seconds):
                    self._identity = await self._attest()
            except BaseException as error:
                await self._client.aclose()
                self._client = None
                self._identity = None
                if isinstance(error, (EmbeddingError, asyncio.CancelledError)):
                    raise
                if isinstance(error, (TimeoutError, httpx.TimeoutException)):
                    raise EmbeddingError(EmbeddingErrorCode.TIMEOUT) from None
                raise EmbeddingError(EmbeddingErrorCode.MODEL_UNAVAILABLE) from None

    async def close_async(self) -> None:
        """Release transport resources; repeated closes are harmless."""
        async with self._lifecycle_lock:
            client, self._client = self._client, None
            self._identity = None
            self._invalidated = False
            if client is not None:
                await client.aclose()

    async def check_ready_async(self) -> None:
        """Reattest current model availability without generating a query or reserving tokens."""
        await self.warm_up_async()
        await self._attest()

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Prepare, admit and validate one ordered batch under the request deadline."""
        return await self._embed(request, native_probe=False)

    async def probe_native(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Compare one native TEI row during qualification using the same admission owner."""
        if len(request.items) != 1:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        return await self._embed(request, native_probe=True)

    async def _embed(self, request: EmbeddingRequest, *, native_probe: bool) -> EmbeddingBatch:
        started = time.monotonic()
        if not math.isfinite(request.deadline) or request.deadline <= started:
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
        prepared = prepare_embedding_request(self._profile, request, self._token_counter)
        payload = self._payload(prepared, native_probe=native_probe)
        remaining = min(request.deadline, started + self._profile.timeout_seconds) - time.monotonic()
        if remaining <= 0:
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
        try:
            async with asyncio.timeout(remaining):
                await self.warm_up_async()
                return await self._dispatch(
                    request=request, prepared=prepared, payload=payload, started=started, native_probe=native_probe
                )
        except (TimeoutError, httpx.TimeoutException):
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT) from None
        except httpx.HTTPError:
            raise EmbeddingError(EmbeddingErrorCode.MODEL_UNAVAILABLE) from None

    def _payload(self, prepared: tuple[PreparedEmbeddingItem, ...], *, native_probe: bool) -> bytes:
        if native_probe:
            value = {
                "inputs": [item.text for item in prepared],
                "normalize": True,
                "truncate": False,
                "dimensions": self._profile.dimensions,
            }
        else:
            value = {
                "input": [item.text for item in prepared],
                "model": self._profile.model_id,
                "encoding_format": self._profile.output_encoding,
                "dimensions": self._profile.dimensions,
            }
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_REQUEST_BYTES:
            raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
        return payload

    async def _dispatch(
        self,
        *,
        request: EmbeddingRequest,
        prepared: tuple[PreparedEmbeddingItem, ...],
        payload: bytes,
        started: float,
        native_probe: bool,
    ) -> EmbeddingBatch:
        identity = await self._attest()
        governor = self._governor
        if governor is None:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        reservation = await governor.reserve(
            profile_id=self._profile.profile_id,
            profile_revision=self._profile.profile_revision,
            deployment_id=identity.deployment_id,
            task_kind=request.task_kind,
            token_count=sum(item.token_count for item in prepared),
            deadline=request.deadline,
            workspace_id=request.workspace_id,
        )
        sent = False
        provenance: UsageProvenance
        usage: int | None
        try:
            await governor.mark_sent(reservation)
            sent = True
            path = "/embed" if native_probe else "/v1/embeddings"
            response = await self._request("POST", path, payload=payload, limit=_MAX_RESPONSE_BYTES)
            if native_probe:
                vectors, usage = self._native_response(response, prepared=prepared)
                provenance = "tokenizer_counted_proxy"
            else:
                vectors, usage, provenance = self._response(response, prepared=prepared, identity=identity)
            await self._attest()
            batch = validate_embedding_batch(
                self._profile,
                request,
                prepared,
                vectors=vectors,
                usage_tokens=usage,
                usage_provenance=provenance,
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except asyncio.CancelledError:
            await governor.finish(reservation, outcome="cancelled", usage_tokens=None, usage_provenance="unknown")
            raise
        except BaseException as error:
            code = error.code if isinstance(error, EmbeddingError) else None
            await governor.finish(
                reservation,
                outcome="failed" if not sent or code == EmbeddingErrorCode.RATE_LIMITED else "ambiguous",
                usage_tokens=None,
                usage_provenance="unknown",
                error_code=code,
            )
            raise
        await governor.finish(reservation, outcome="success", usage_tokens=usage, usage_provenance=provenance)
        return batch

    def _native_response(
        self, response: Any, *, prepared: tuple[PreparedEmbeddingItem, ...]
    ) -> tuple[tuple[tuple[float, ...], ...], int]:
        if (
            not isinstance(response, list)
            or len(response) != 1
            or not isinstance(response[0], list)
            or any(type(value) not in {int, float} for value in response[0])
        ):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        return (tuple(response[0]),), sum(item.token_count for item in prepared)

    async def _request(self, method: str, path: str, *, limit: int, payload: bytes | None = None) -> Any:
        client = self._client
        if client is None:
            raise EmbeddingError(EmbeddingErrorCode.MODEL_UNAVAILABLE)
        async with client.stream(
            method, path, content=payload, headers={"Content-Type": "application/json", "Accept-Encoding": "identity"}
        ) as response:
            if response.status_code != 200:
                if response.status_code == 429:
                    raise EmbeddingError(EmbeddingErrorCode.RATE_LIMITED)
                if response.status_code in {400, 413, 422}:
                    raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
                raise EmbeddingError(EmbeddingErrorCode.MODEL_UNAVAILABLE)
            if response.headers.get("content-encoding", "identity") != "identity":
                raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=16_384):
                if len(body) + len(chunk) > limit:
                    raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
                body.extend(chunk)
        return _decode_json(bytes(body))

    async def _attest(self) -> EmbeddingRuntimeIdentity:
        if self._invalidated:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        try:
            return await self._attest_identity()
        except EmbeddingError:
            self._invalidated = self._identity is not None
            raise
        except (TimeoutError, httpx.TimeoutException):
            self._invalidated = self._identity is not None
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT) from None
        except Exception:
            self._invalidated = self._identity is not None
            raise EmbeddingError(EmbeddingErrorCode.MODEL_UNAVAILABLE) from None

    async def _attest_identity(self) -> EmbeddingRuntimeIdentity:
        identity = await self._identity_verifier.verify()
        profile = self._profile
        if (
            identity.adapter_id != profile.provider_adapter_id
            or identity.model_digest != profile.model_digest
            or identity.tokenizer_digest != profile.tokenizer_digest
            or identity.tokenizer_revision != profile.tokenizer_revision
            or self._token_counter.counter_revision != profile.tokenizer_revision
            or (self._identity is not None and identity != self._identity)
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        info = await self._request("GET", "/info", limit=_MAX_INFO_BYTES)
        if not isinstance(info, dict):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        digest = hashlib.sha256(
            json.dumps(info, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest()
        if (
            digest != identity.info_digest
            or info.get("served_model_name") != identity.served_model_id
            or info.get("auto_truncate") is not False
            or info.get("model_dtype") != profile.inference_dtype
            or info.get("model_type") != {"embedding": {"pooling": profile.pooling}}
            or not _within_capacity(info, name="max_input_length", required=profile.max_tokens)
            or not _within_capacity(info, name="max_batch_tokens", required=profile.max_batch_tokens)
            or not _within_capacity(info, name="max_client_batch_size", required=profile.max_batch_items)
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        return identity

    def _response(
        self, response: Any, *, prepared: tuple[PreparedEmbeddingItem, ...], identity: EmbeddingRuntimeIdentity
    ) -> tuple[tuple[tuple[float, ...], ...], int | None, UsageProvenance]:
        if (
            not isinstance(response, dict)
            or response.get("object") != "list"
            or response.get("model") != identity.served_model_id
            or not isinstance(response.get("data"), list)
            or len(response["data"]) != len(prepared)
        ):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        vectors = []
        for index, item in enumerate(response["data"]):
            if (
                not isinstance(item, dict)
                or item.get("object") != "embedding"
                or type(item.get("index")) is not int
                or item["index"] != index
                or not isinstance(item.get("embedding"), list)
                or any(type(value) not in {int, float} for value in item["embedding"])
            ):
                raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
            vectors.append(tuple(item["embedding"]))
        usage = response.get("usage")
        if usage is None:
            return tuple(vectors), None, "unknown"
        expected_tokens = sum(item.token_count for item in prepared)
        if (
            not isinstance(usage, dict)
            or type(usage.get("prompt_tokens")) is not int
            or type(usage.get("total_tokens")) is not int
            or usage["prompt_tokens"] != expected_tokens
            or usage["total_tokens"] != expected_tokens
        ):
            raise EmbeddingError(EmbeddingErrorCode.TOKENIZER_MISMATCH)
        return tuple(vectors), expected_tokens, "provider_reported"

"""Microsoft Agent Framework adapter for direct OpenAI Responses requests."""

import json
import re
from collections.abc import Callable
from typing import Final

import httpx2
from agent_framework import Agent
from agent_framework.exceptions import ChatClientContentFilterException
from agent_framework.observability import disable_instrumentation
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from openai import APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

from agent_runtime.configuration import ModelProfile
from agent_runtime.contracts import ErrorCode, Usage, decode_json
from agent_runtime.runtime import ProviderObservation, RuntimeFailure

_BASE_URL = "https://api.openai.com/v1"
_RESPONSES_URL = f"{_BASE_URL}/responses"
_REQUEST_ID = re.compile(r"req_[a-zA-Z0-9_-]{1,120}")
_MODEL_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}")
_CACHE_MODE: Final = "explicit"
_CACHE_TTL: Final = "30m"


class MafOpenAIRuntime:
    """Run a fresh MAF agent against the fixed Responses endpoint."""

    def __init__(self, *, transport_factory: Callable[[], httpx2.AsyncBaseTransport] | None = None) -> None:
        self._transport_factory = transport_factory

    async def invoke(
        self,
        *,
        profile: ModelProfile,
        instructions: str,
        input_json: str,
        output_schema: type[BaseModel],
        api_key: str,
        observation: ProviderObservation,
    ) -> str:
        """Return the MAF agent's output text for independent application validation."""
        response_format = {
            "type": "json_schema",
            "name": output_schema.__name__,
            "schema": output_schema.model_json_schema(),
            "strict": True,
        }
        options: OpenAIChatOptions[None] = {
            "response_format": response_format,
            "store": False,
            "background": False,
            "truncation": "disabled",
            "reasoning": {"effort": profile.reasoning_effort},
            "max_tokens": profile.max_output_tokens,
            "service_tier": "default",
            "prompt_cache_options": {"mode": _CACHE_MODE, "ttl": _CACHE_TTL},
        }
        try:
            disable_instrumentation()
            transport = (
                self._transport_factory() if self._transport_factory else httpx2.AsyncHTTPTransport(trust_env=False)
            )
            guard = _ResponsesTransport(
                transport=transport,
                profile=profile,
                response_format=response_format,
                instructions=instructions,
                input_json=input_json,
                observation=observation,
                api_key=api_key,
            )
            async with (
                httpx2.AsyncClient(transport=guard, follow_redirects=False, trust_env=False) as http,
                AsyncOpenAI(
                    api_key=api_key,
                    base_url=_BASE_URL,
                    admin_api_key="",
                    organization="",
                    project="",
                    webhook_secret="",
                    default_headers={"Authorization": f"Bearer {api_key}"},
                    max_retries=0,
                    timeout=profile.timeout_seconds,
                    http_client=http,
                ) as sdk,
            ):
                client: OpenAIChatClient[OpenAIChatOptions[None]] = OpenAIChatClient(
                    model=profile.model,
                    async_client=sdk,
                    function_invocation_configuration={"enabled": False},
                )
                agent = Agent(client=client, instructions=instructions)
                response = await agent.run(input_json, options=options)
                output = response.text
                if api_key in output:
                    raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)
                return output
        except Exception as exc:
            raise RuntimeFailure(_error_code(exc)) from None


class _ResponsesTransport(httpx2.AsyncBaseTransport):
    def __init__(
        self,
        *,
        transport: httpx2.AsyncBaseTransport,
        profile: ModelProfile,
        response_format: dict[str, object],
        instructions: str,
        input_json: str,
        observation: ProviderObservation,
        api_key: str,
    ) -> None:
        self._transport = transport
        self._profile = profile
        self._response_format = response_format
        self._instructions = instructions
        self._input_json = input_json
        self._observation = observation
        self._api_key = api_key

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            request = self._guarded_request(request)
            self._observation.requests += 1
            response = await self._transport.handle_async_request(request)
            return await self._read_response(response)
        except Exception as exc:
            # MAF can log the SDK exception at debug level. Sanitize before it crosses into the SDK.
            raise RuntimeFailure(_error_code(exc)) from None

    async def _read_response(self, response: httpx2.Response) -> httpx2.Response:
        try:
            correlation_id = _safe_metadata(response.headers.get("x-request-id"), _REQUEST_ID, self._api_key)
            self._observation.correlation_id = correlation_id
            if response.status_code == 429:
                raise RuntimeFailure(ErrorCode.RATE_LIMITED)
            body = await _read_bounded(response, limit=self._profile.max_response_bytes)
            if not response.is_success:
                _reject_http_error(response.status_code, body)
            self._check_response(body)
            headers = {"content-type": "application/json"}
            if correlation_id is not None:
                headers["x-request-id"] = correlation_id
            return httpx2.Response(response.status_code, headers=headers, content=body)
        finally:
            await response.aclose()

    def _guarded_request(self, request: httpx2.Request) -> httpx2.Request:
        if self._observation.requests or request.method != "POST" or request.url != _RESPONSES_URL:
            raise RuntimeFailure(ErrorCode.PRIVACY_POLICY)
        payload = _decode_object(request.content, error=ErrorCode.PRIVACY_POLICY)
        # MAF requests encrypted reasoning for stateless replay, which this one-shot agent never uses.
        include = payload.pop("include", None)
        required = {
            "background": False,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": self._input_json}]}
            ],
            "instructions": self._instructions,
            "max_output_tokens": self._profile.max_output_tokens,
            "model": self._profile.model,
            "prompt_cache_options": {"mode": _CACHE_MODE, "ttl": _CACHE_TTL},
            "reasoning": {"effort": self._profile.reasoning_effort},
            "service_tier": "default",
            "store": False,
            "stream": False,
            "text": {"format": self._response_format},
            "truncation": "disabled",
        }
        if (
            payload != required
            or any(payload.get(key) is not False for key in ("background", "store", "stream"))
            or include not in (None, ["reasoning.encrypted_content"])
        ):
            raise RuntimeFailure(ErrorCode.PRIVACY_POLICY)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > self._profile.max_input_tokens:
            raise RuntimeFailure(ErrorCode.INVALID_INPUT)
        # The SDK also reads OPENAI_CUSTOM_HEADERS. Construct the wire headers explicitly.
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        return httpx2.Request(
            request.method, request.url, content=encoded, headers=headers, extensions=request.extensions
        )

    def _check_response(self, body: bytes) -> None:
        payload = _decode_object(body, error=ErrorCode.INVALID_OUTPUT)
        self._observation.model = _safe_metadata(payload.get("model"), _MODEL_ID, self._api_key)
        self._observation.usage = _reported_usage(payload.get("usage"))
        if payload.get("store", False) is not False:
            raise RuntimeFailure(ErrorCode.PRIVACY_POLICY)
        status = payload.get("status")
        if status == "failed" or payload.get("error") is not None:
            raise RuntimeFailure(ErrorCode.PROVIDER_FAILURE)
        if status == "cancelled":
            raise RuntimeFailure(ErrorCode.CANCELLED)
        incomplete_reason = _mapping(payload.get("incomplete_details")).get("reason")
        if incomplete_reason == "content_filter":
            raise RuntimeFailure(ErrorCode.REFUSAL)
        if status != "completed" or payload.get("incomplete_details") is not None:
            raise RuntimeFailure(ErrorCode.INCOMPLETE_OUTPUT)
        _validate_output_items(payload.get("output"))


async def _read_bounded(response: httpx2.Response, *, limit: int) -> bytes:
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise RuntimeFailure(ErrorCode.PROVIDER_FAILURE)
    data = bytearray()
    async for chunk in response.aiter_bytes():
        if len(chunk) > limit - len(data):
            raise RuntimeFailure(ErrorCode.RESPONSE_TOO_LARGE)
        data.extend(chunk)
    return bytes(data)


def _reject_http_error(status: int, body: bytes) -> None:
    if status == 400:
        error = _mapping(_decode_object(body, error=ErrorCode.PROVIDER_FAILURE).get("error"))
        if error.get("code") == "content_filter":
            raise RuntimeFailure(ErrorCode.REFUSAL)
    raise RuntimeFailure(ErrorCode.PROVIDER_FAILURE)


def _validate_output_items(value: object) -> None:
    if not isinstance(value, list):
        raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)
    text_parts = 0
    for item in map(_mapping, value):
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)
        if item.get("status") != "completed":
            raise RuntimeFailure(ErrorCode.INCOMPLETE_OUTPUT)
        content = item.get("content")
        if not isinstance(content, list):
            raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)
        for part in map(_mapping, content):
            if part.get("type") == "refusal":
                raise RuntimeFailure(ErrorCode.REFUSAL)
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)
            text_parts += 1
    if text_parts != 1:
        raise RuntimeFailure(ErrorCode.INVALID_OUTPUT)


def _decode_object(data: bytes, *, error: ErrorCode) -> dict[str, object]:
    try:
        value = decode_json(data.decode("utf-8"))
    except (ValueError, RecursionError):
        raise RuntimeFailure(error) from None
    if not isinstance(value, dict):
        raise RuntimeFailure(error)
    return value


def _safe_metadata(value: object, pattern: re.Pattern[str], secret: str) -> str | None:
    if isinstance(value, str) and pattern.fullmatch(value) and secret not in value:
        return value
    return None


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _reported_usage(value: object) -> Usage | None:
    if not isinstance(value, dict):
        return None
    return Usage(
        input_tokens=_token_count(value.get("input_tokens")),
        output_tokens=_token_count(value.get("output_tokens")),
        reasoning_tokens=_token_count(_mapping(value.get("output_tokens_details")).get("reasoning_tokens")),
        cached_input_tokens=_token_count(_mapping(value.get("input_tokens_details")).get("cached_tokens")),
    )


def _token_count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**53 - 1 else None


def _error_code(error: BaseException) -> ErrorCode:
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, RuntimeFailure):
            return cause.code
        if isinstance(cause, (APITimeoutError, httpx2.TimeoutException)):
            return ErrorCode.TIMEOUT
        if isinstance(cause, ChatClientContentFilterException):
            return ErrorCode.REFUSAL
        cause = cause.__cause__
    return ErrorCode.PROVIDER_FAILURE

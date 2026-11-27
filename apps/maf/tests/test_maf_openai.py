"""Exercise the installed MAF and OpenAI SDK over an offline HTTP transport."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from hashlib import sha256
from typing import Any

import httpx2
import pytest
from agent_framework import Agent
from pydantic import BaseModel, ConfigDict, Field

from agent_runtime.adapters.maf_openai import MafOpenAIRuntime
from agent_runtime.agents.semantic_judge.contracts import JudgeContextResult
from agent_runtime.agents.structured_smoke import SMOKE_REQUEST
from agent_runtime.configuration import SEMANTIC_REVIEW_PROFILE, ModelProfile, RunPolicy, load_profiles
from agent_runtime.contracts import ErrorCode, InvocationRequest, Usage
from agent_runtime.runtime import AgentApplication, ProviderObservation, RuntimeFailure

_PROFILE = ModelProfile(profile_id="semantic-review", model="gpt-6.1-sol")
_KEY = "fixture-key-never-logged"
_INPUT = '{"label":"blue"}'
_INSTRUCTIONS = "Extract the requested test label."
_OUTPUT = '{"label":"blue"}'
_CHECKED_MODEL = "gpt-6.1-sol-2026-07-02"
_REQUEST_ID = "req_mock_wire"


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str = Field(min_length=1, max_length=8)


def _record(label: str = _OUTPUT) -> dict[str, Any]:
    return {
        "id": "resp_mock_wire",
        "object": "response",
        "created_at": 1_790_000_000,
        "model": _CHECKED_MODEL,
        "status": "completed",
        "completed_at": 1_790_000_001,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "output": [
            {"type": "reasoning", "id": "rs_mock", "summary": []},
            {
                "type": "message",
                "id": "msg_mock_wire",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": label, "annotations": []}],
            },
        ],
        "parallel_tool_calls": False,
        "service_tier": "default",
        "store": False,
        "temperature": 1.0,
        "tool_choice": "none",
        "tools": [],
        "top_p": 1.0,
        "usage": {
            "input_tokens": 76,
            "output_tokens": 29,
            "total_tokens": 105,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 17},
        },
    }


def _call(
    handler: Callable[[httpx2.Request], httpx2.Response],
    observation: ProviderObservation,
    *,
    profile: ModelProfile = _PROFILE,
) -> str:
    runtime = MafOpenAIRuntime(transport_factory=lambda: httpx2.MockTransport(handler))
    return asyncio.run(
        runtime.invoke(
            profile=profile,
            instructions=_INSTRUCTIONS,
            input_json=_INPUT,
            output_schema=_Output,
            api_key=_KEY,
            observation=observation,
        )
    )


def test_real_sdk_wire_applies_stateless_responses_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://other.invalid")
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-key")
    monkeypatch.setenv("OPENAI_ORG_ID", "ignored-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "ignored-project")
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", "Host: other.invalid\nAuthorization: other-key\nX-Extra: ignored")
    monkeypatch.setenv("OPENAI_MODEL", "ignored-model")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://other.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "https://other.invalid")
    requests = []

    def capture(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=_record(), headers={"x-request-id": _REQUEST_ID})

    observation = ProviderObservation()
    assert _call(capture, observation) == _OUTPUT
    assert len(requests) == observation.requests == 1
    request = requests[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.openai.com/v1/responses")
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    assert request.headers["Host"] == "api.openai.com"
    assert request.headers["Accept-Encoding"] == "identity"
    assert "OpenAI-Organization" not in request.headers
    assert "OpenAI-Project" not in request.headers
    assert "X-Extra" not in request.headers
    body = json.loads(request.content)
    assert body["store"] is False
    assert body["background"] is False
    assert body["stream"] is False
    assert body["model"] == _PROFILE.model
    assert body["reasoning"] == {"effort": _PROFILE.reasoning_effort}
    assert body["truncation"] == "disabled"
    assert body["service_tier"] == "default"
    assert body["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert body["max_output_tokens"] == _PROFILE.max_output_tokens
    assert {"tools", "conversation", "previous_response_id", "include", "temperature", "seed"}.isdisjoint(body)
    assert body["instructions"] == _INSTRUCTIONS
    (user,) = body["input"]
    assert user["role"] == "user"
    assert user["content"] == [{"type": "input_text", "text": _INPUT}]
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "_Output",
        "strict": True,
        "schema": _Output.model_json_schema(),
    }
    assert observation.model == _CHECKED_MODEL
    assert observation.correlation_id == _REQUEST_ID
    assert observation.usage == Usage(input_tokens=76, output_tokens=29, reasoning_tokens=17, cached_input_tokens=0)


def test_missing_usage_and_unsafe_provider_metadata(caplog: pytest.LogCaptureFixture) -> None:
    observation = ProviderObservation()
    with caplog.at_level("DEBUG"):
        _call(
            lambda _: httpx2.Response(
                200, json=_record() | {"usage": None, "model": _KEY}, headers={"x-request-id": f"req_{_KEY}"}
            ),
            observation,
        )
    assert observation.usage is None
    assert observation.model is None
    assert observation.correlation_id is None
    assert _KEY not in caplog.text


def test_large_ordered_context_reaches_provider_without_truncation() -> None:
    tail = "The final excerpt says nothing about the requested dock."
    fragments = []
    for index in range(12):
        text = f"Log {index}: " + "Щ" * 330 + (f" {tail}" if index == 11 else "")
        fragments.append(
            {
                "id": f"log-{index}",
                "start": 0,
                "end": len(text),
                "sha256": sha256(text.encode()).hexdigest(),
                "text": text,
            }
        )
    request = InvocationRequest(
        schema_version=1,
        request_id="full-context",
        agent_id="semantic-judge",
        profile_id=SEMANTIC_REVIEW_PROFILE,
        input={
            "mode": "judge_context",
            "question": "Which dock does the ship berth at?",
            "language": "en",
            "reference": {"revision": "fixture", "answerability": "unknown", "facts": [], "constraints": []},
            "context": fragments,
        },
    )
    output = {
        "mode": "judge_context",
        "rationale": "No docking information found.",
        "sufficiency": "insufficient",
        "constraint_assessments": [],
        "fact_assessments": [],
        "spans": [{"kind": "irrelevant", "quote": {"source_id": "log-11", "start": None, "end": None, "text": tail}}],
    }
    sent = []

    def capture(http_request: httpx2.Request) -> httpx2.Response:
        sent.append(http_request.content)
        record = _record(json.dumps(output))
        record["usage"].update(output_tokens=5_000, total_tokens=5_076)
        return httpx2.Response(200, json=record, headers={"x-request-id": _REQUEST_ID})

    runtime = MafOpenAIRuntime(transport_factory=lambda: httpx2.MockTransport(capture))
    app = AgentApplication(lambda: runtime, load_profiles({}))
    result = asyncio.run(
        app.invoke(
            request,
            policy=RunPolicy(allow_external=True, data_classification="synthetic"),
            environ={"OPENAI_API_KEY": _KEY},
        )
    )

    assert result.error is None, result
    assert result.metadata.requests == 1
    assert result.metadata.usage is not None
    assert result.metadata.usage.output_tokens == 5_000
    (raw,) = sent
    assert len(request.model_dump_json().encode()) > 8_192
    assert len(raw) > 8_192
    body = json.loads(raw)
    assert body["truncation"] == "disabled"
    assert body["max_output_tokens"] == 32_000
    assert json.loads(body["input"][0]["content"][0]["text"]) == request.input
    (span,) = JudgeContextResult.model_validate(result.output).spans
    assert span.quote.start == len(fragments[-1]["text"]) - len(tail)


@pytest.mark.parametrize(
    ("status", "incomplete", "items", "code"),
    [
        ("incomplete", {"reason": "max_output_tokens"}, [], ErrorCode.INCOMPLETE_OUTPUT),
        ("incomplete", {"reason": "content_filter"}, [], ErrorCode.REFUSAL),
        ("queued", None, [], ErrorCode.INCOMPLETE_OUTPUT),
        ("cancelled", None, [], ErrorCode.CANCELLED),
        ("failed", None, [], ErrorCode.PROVIDER_FAILURE),
        ("completed", None, [{"type": "function_call", "arguments": _KEY}], ErrorCode.INVALID_OUTPUT),
        (
            "completed",
            None,
            [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal"}]}],
            ErrorCode.REFUSAL,
        ),
    ],
)
def test_terminal_response_errors_preserve_available_usage(
    status: str, incomplete: dict[str, str] | None, items: list[dict[str, object]], code: ErrorCode
) -> None:
    record = _record() | {"status": status, "incomplete_details": incomplete, "output": items}
    observation = ProviderObservation()
    with pytest.raises(RuntimeFailure) as failure:
        _call(lambda _: httpx2.Response(200, json=record), observation)
    assert failure.value.code == code
    assert observation.requests == 1
    assert observation.model == _CHECKED_MODEL
    assert observation.usage is not None
    assert observation.usage.reasoning_tokens == 17


@pytest.mark.parametrize(
    ("status", "code"),
    [(429, ErrorCode.RATE_LIMITED), (307, ErrorCode.PROVIDER_FAILURE), (401, ErrorCode.PROVIDER_FAILURE)],
)
def test_http_errors_are_redacted_without_redirects_or_retries(
    status: int, code: ErrorCode, caplog: pytest.LogCaptureFixture
) -> None:
    observation = ProviderObservation()
    with caplog.at_level("DEBUG"), pytest.raises(RuntimeFailure) as failure:
        _call(
            lambda _: httpx2.Response(
                status,
                json={"error": {"message": _KEY}},
                headers={"Retry-After": "0", "Location": "https://other.invalid", "x-request-id": _REQUEST_ID},
            ),
            observation,
        )
    assert failure.value.code == code
    assert failure.value.__suppress_context__
    assert _KEY not in str(failure.value) + caplog.text
    assert observation.requests == 1
    assert observation.correlation_id == _REQUEST_ID
    assert observation.usage is None


def test_transport_timeout(caplog: pytest.LogCaptureFixture) -> None:
    def timed_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout(_KEY, request=request)

    observation = ProviderObservation()
    with caplog.at_level("DEBUG"), pytest.raises(RuntimeFailure) as failure:
        _call(timed_out, observation)
    assert failure.value.code == ErrorCode.TIMEOUT
    assert observation.requests == 1
    assert _KEY not in caplog.text


def test_rejects_unparseable_provider_response() -> None:
    with pytest.raises(RuntimeFailure) as failure:
        _call(lambda _: httpx2.Response(200, content=b"{broken"), ProviderObservation())
    assert failure.value.code == ErrorCode.INVALID_OUTPUT


class _ChunkedResponse(httpx2.AsyncByteStream):
    chunks = 0
    closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(4):
            self.chunks += 1
            yield b"x" * 16

    async def aclose(self) -> None:
        self.closed = True


def test_response_limit_closes_the_stream_before_reading_remaining_bytes() -> None:
    stream = _ChunkedResponse()
    observation = ProviderObservation()
    with pytest.raises(RuntimeFailure) as failure:
        _call(
            lambda _: httpx2.Response(200, stream=stream), observation, profile=replace(_PROFILE, max_response_bytes=20)
        )
    assert failure.value.code == ErrorCode.RESPONSE_TOO_LARGE
    assert observation.requests == 1
    assert stream.chunks == 2
    assert stream.closed


def test_wire_input_limit_fails_before_network_transport() -> None:
    def must_not_send(_: httpx2.Request) -> httpx2.Response:
        pytest.fail("Oversized request reached the HTTP transport")

    observation = ProviderObservation()
    with pytest.raises(RuntimeFailure) as failure:
        _call(must_not_send, observation, profile=replace(_PROFILE, max_input_tokens=20))
    assert failure.value.code == ErrorCode.INVALID_INPUT
    assert observation.requests == 0


def test_store_policy_fails_closed_if_maf_does_not_forward_the_option(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = Agent.run

    def run_without_store(self: Agent[Any], messages: str, *, options: dict[str, Any]) -> Any:
        return real_run(self, messages, options={key: value for key, value in options.items() if key != "store"})

    def must_not_send(_: httpx2.Request) -> httpx2.Response:
        pytest.fail("Request missing store=false reached the HTTP transport")

    monkeypatch.setattr(Agent, "run", run_without_store)
    observation = ProviderObservation()
    with pytest.raises(RuntimeFailure) as failure:
        _call(must_not_send, observation)
    assert failure.value.code == ErrorCode.PRIVACY_POLICY
    assert observation.requests == 0


@pytest.mark.parametrize("text", ['{"marker":"cobalt"}', '{"marker":"Cobalt","extra":1}'])
def test_real_agent_response_is_independently_validated_by_the_application(text: str) -> None:
    http = httpx2.MockTransport(lambda _: httpx2.Response(200, json=_record(text)))
    app = AgentApplication(lambda: MafOpenAIRuntime(transport_factory=lambda: http), {_PROFILE.profile_id: _PROFILE})
    result = asyncio.run(
        app.invoke(
            SMOKE_REQUEST,
            policy=RunPolicy(allow_external=True, data_classification="synthetic"),
            environ={"OPENAI_API_KEY": _KEY},
        )
    )
    assert result.metadata.requests == 1
    if text == '{"marker":"cobalt"}':
        assert result.outcome == "ok"
        assert result.output == {"marker": "cobalt"}
    else:
        assert result.outcome == "error"
        assert result.error is not None
        assert result.error.code == ErrorCode.INVALID_OUTPUT

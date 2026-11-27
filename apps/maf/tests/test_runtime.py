import asyncio
from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from agent_runtime.configuration import RunPolicy, load_profiles
from agent_runtime.contracts import ErrorCode, InvocationRequest, Usage
from agent_runtime.runtime import AgentApplication, AgentRuntime, ProviderObservation

_KEY = "offline-provider-key-sentinel"
_APPROVED = RunPolicy(allow_external=True, data_classification="synthetic")


def _request(
    *, agent_id: str = "structured-smoke", profile_id: str = "semantic-review", text: str = "The marker is cobalt."
) -> InvocationRequest:
    return InvocationRequest(
        schema_version=1, request_id="synthetic-request", agent_id=agent_id, profile_id=profile_id, input={"text": text}
    )


@pytest.mark.parametrize(
    ("invocation", "policy", "environ", "expected"),
    [
        (_request(agent_id="unknown"), _APPROVED, {"OPENAI_API_KEY": _KEY}, ErrorCode.UNKNOWN_AGENT),
        (_request(profile_id="unknown"), _APPROVED, {"OPENAI_API_KEY": _KEY}, ErrorCode.UNKNOWN_PROFILE),
        (_request(), RunPolicy(), {"OPENAI_API_KEY": _KEY}, ErrorCode.EGRESS_DISABLED),
        (_request(), RunPolicy(allow_external=True), {"OPENAI_API_KEY": _KEY}, ErrorCode.EGRESS_DISABLED),
        (_request(), _APPROVED, {}, ErrorCode.MISSING_CREDENTIALS),
        (_request(text=f"Sensitive input {_KEY}"), _APPROVED, {"OPENAI_API_KEY": _KEY}, ErrorCode.PRIVACY_POLICY),
        (
            _request(),
            RunPolicy(allow_external=True, data_classification="synthetic", max_cost_usd=Decimal("0.000001")),
            {"OPENAI_API_KEY": _KEY},
            ErrorCode.BUDGET_EXCEEDED,
        ),
        (
            _request(),
            replace(_APPROVED, max_cost_usd=Decimal("0.10")),
            {"OPENAI_API_KEY": _KEY},
            ErrorCode.BUDGET_EXCEEDED,
        ),
        (_request(text="a" * 8192), _APPROVED, {"OPENAI_API_KEY": _KEY}, ErrorCode.INVALID_INPUT),
    ],
)
def test_rejected_invocation_never_calls_port(
    invocation: InvocationRequest, policy: RunPolicy, environ: dict[str, str], expected: ErrorCode
) -> None:
    port = AsyncMock(spec=AgentRuntime)
    factory = Mock(return_value=port)
    app = AgentApplication(factory, load_profiles({}))

    result = asyncio.run(app.invoke(invocation, policy=policy, environ=environ))

    assert result.outcome == "error"
    assert result.error is not None and result.error.code == expected
    assert result.output is None
    assert _KEY not in result.model_dump_json()
    assert result.metadata.requests == 0
    factory.assert_not_called()
    port.invoke.assert_not_called()


def test_incompatible_profile_fails_before_provider_execution() -> None:
    port = AsyncMock(spec=AgentRuntime)
    profiles = dict(load_profiles({}))
    profiles["semantic-review"] = replace(profiles["semantic-review"], capabilities=frozenset({"structured_output"}))
    app = AgentApplication(lambda: port, profiles)

    result = asyncio.run(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))

    assert result.error is not None and result.error.code == ErrorCode.UNSUPPORTED_CAPABILITY
    port.invoke.assert_not_called()


def test_success_reports_provider_observation_and_configured_profile() -> None:
    usage = Usage(input_tokens=90, output_tokens=20, reasoning_tokens=13, cached_input_tokens=15)

    async def respond(*, observation: ProviderObservation, **_kwargs: object) -> str:
        observation.model = "gpt-6.2-sol"
        observation.usage = usage
        observation.correlation_id = "synthetic-correlation"
        observation.requests = 1
        return '{"marker":"cobalt"}'

    port = AsyncMock(spec=AgentRuntime)
    port.invoke.side_effect = respond
    app = AgentApplication(lambda: port, load_profiles({"MAF_OPENAI_REASONING_EFFORT": "low"}))

    result = asyncio.run(
        app.invoke(_request(profile_id="semantic-review-6.2"), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY})
    )

    assert result.outcome == "ok"
    assert result.error is None
    assert result.output == {"marker": "cobalt"}
    assert result.metadata.configured_model == "gpt-6.2-sol"
    assert result.metadata.model == "gpt-6.2-sol"
    assert result.metadata.correlation_id == "synthetic-correlation"
    assert result.metadata.usage == usage
    assert result.metadata.requests == 1
    assert result.metadata.retries == 0
    assert result.metadata.pricing_version
    estimate = result.metadata.estimated_cost_usd
    maximum = result.metadata.estimated_max_cost_usd
    assert estimate == Decimal("0.0004279")
    assert maximum is not None and estimate <= maximum <= _APPROVED.max_cost_usd
    assert result.metadata.prompt_revision
    assert result.metadata.output_schema_revision
    assert _KEY not in result.model_dump_json()
    port.invoke.assert_awaited_once()
    assert port.invoke.call_args.kwargs["profile"].reasoning_effort == "low"
    assert _KEY not in port.invoke.call_args.kwargs["input_json"]


@pytest.mark.parametrize(("output_tokens", "accepted"), [(4_097, True), (32_000, True), (32_001, False)])
def test_review_output_usage_is_bounded_by_profile(output_tokens: int, accepted: bool) -> None:
    async def respond(*, observation: ProviderObservation, **_kwargs: object) -> str:
        observation.model = "gpt-6.1-sol"
        observation.usage = Usage(input_tokens=76, output_tokens=output_tokens, reasoning_tokens=17)
        observation.requests = 1
        return '{"marker":"cobalt"}'

    port = AsyncMock(spec=AgentRuntime)
    port.invoke.side_effect = respond
    app = AgentApplication(lambda: port, load_profiles({}))

    result = asyncio.run(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))

    if accepted:
        assert result.outcome == "ok"
        assert result.error is None
        assert result.output == {"marker": "cobalt"}
    else:
        assert result.error is not None and result.error.code == ErrorCode.BUDGET_EXCEEDED
        assert result.output is None
    assert result.metadata.requests == 1
    assert result.metadata.usage is not None
    assert result.metadata.usage.output_tokens == output_tokens
    port.invoke.assert_awaited_once()


def test_success_keeps_missing_usage_and_actual_model_unknown() -> None:
    port = AsyncMock(spec=AgentRuntime)
    port.invoke.return_value = '{"marker":"cobalt"}'
    app = AgentApplication(lambda: port, load_profiles({}))

    result = asyncio.run(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))

    assert result.outcome == "ok"
    assert result.metadata.usage is None
    assert result.metadata.estimated_cost_usd is None
    assert result.metadata.configured_model == "gpt-6.1-sol"
    assert result.metadata.model is None


@pytest.mark.parametrize("raw_output", ["malformed", "{}", '{"marker":5}', '{"marker":"cobalt","extra":true}'])
def test_invalid_structured_output_is_an_operational_error(raw_output: str) -> None:
    port = AsyncMock(spec=AgentRuntime)
    port.invoke.return_value = raw_output
    app = AgentApplication(lambda: port, load_profiles({}))

    result = asyncio.run(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))

    assert result.outcome == "error"
    assert result.error is not None and result.error.code == ErrorCode.INVALID_OUTPUT
    assert result.output is None


def test_runtime_timeout_cancels_port_and_does_not_retry() -> None:
    async def wait_for_timeout(**_kwargs: object) -> str:
        await asyncio.Event().wait()
        raise AssertionError("event was never set")

    port = AsyncMock(spec=AgentRuntime)
    port.invoke.side_effect = wait_for_timeout
    profiles = dict(load_profiles({}))
    profiles["semantic-review"] = replace(profiles["semantic-review"], timeout_seconds=0.01)
    app = AgentApplication(lambda: port, profiles)

    result = asyncio.run(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))

    assert result.error is not None and result.error.code == ErrorCode.TIMEOUT
    assert result.output is None
    port.invoke.assert_awaited_once()


def test_cancellation_while_executing_returns_cancelled() -> None:
    async def invoke_and_cancel() -> None:
        started = asyncio.Event()

        async def wait_for_cancellation(**_kwargs: object) -> str:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("event was never set")

        port = AsyncMock(spec=AgentRuntime)
        port.invoke.side_effect = wait_for_cancellation
        app = AgentApplication(lambda: port, load_profiles({}))
        invocation = asyncio.create_task(app.invoke(_request(), policy=_APPROVED, environ={"OPENAI_API_KEY": _KEY}))
        await asyncio.wait_for(started.wait(), timeout=1)
        invocation.cancel()
        result = await invocation

        assert result.error is not None and result.error.code == ErrorCode.CANCELLED
        assert result.output is None
        port.invoke.assert_awaited_once()

    asyncio.run(invoke_and_cancel())

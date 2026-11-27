"""Provider-neutral invocation port, agent registration and admission policy."""

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import version
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, JsonValue

from agent_runtime.agents.structured_smoke import SMOKE_INSTRUCTIONS, SmokeInput, SmokeOutput
from agent_runtime.configuration import (
    INPUT_FRAMING_TOKENS,
    MAX_RUN_COST_USD,
    PRICING_VERSION,
    ModelProfile,
    RunPolicy,
    estimate_usage_cost,
)
from agent_runtime.contracts import (
    ErrorCode,
    InvocationError,
    InvocationMetadata,
    InvocationRequest,
    InvocationResult,
    Usage,
    decode_json,
)

_RUNTIME_REVISION = version("rag-maf-agent-runtime")


@dataclass(slots=True)
class ProviderObservation:
    """Safe provider details collected even when invocation fails or is cancelled."""

    model: str | None = None
    usage: Usage | None = None
    correlation_id: str | None = None
    requests: int = 0


class RuntimeFailure(Exception):
    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class AgentRuntime(Protocol):
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
        """Run one stateless agent invocation and return its structured JSON text."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class _AgentDefinition:
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    instructions: str
    prompt_revision: str
    output_schema_revision: str
    required_capabilities: frozenset[str]


_AGENTS = {
    "structured-smoke": _AgentDefinition(
        input_schema=SmokeInput,
        output_schema=SmokeOutput,
        instructions=SMOKE_INSTRUCTIONS,
        prompt_revision="1",
        output_schema_revision="1",
        required_capabilities=frozenset({"structured_output", "reasoning"}),
    ),
}


class AgentApplication:
    """Resolve and admit one request before creating a provider runtime."""

    def __init__(self, runtime_factory: Callable[[], AgentRuntime], profiles: Mapping[str, ModelProfile]) -> None:
        self._runtime_factory = runtime_factory
        self._profiles = dict(profiles)

    async def invoke(
        self, request: InvocationRequest, *, policy: RunPolicy, environ: Mapping[str, str]
    ) -> InvocationResult:
        start = perf_counter()
        agent = _AGENTS.get(request.agent_id)
        profile = self._profiles.get(request.profile_id)
        observation = ProviderObservation()
        output: dict[str, JsonValue] | None = None
        error = None
        try:
            if agent is None:
                raise RuntimeFailure(ErrorCode.UNKNOWN_AGENT)
            if profile is None:
                raise RuntimeFailure(ErrorCode.UNKNOWN_PROFILE)
            input_json = _admit_input(request, agent=agent, profile=profile, policy=policy)
            api_key = _resolve_key(environ, profile=profile, input_json=input_json)
            async with asyncio.timeout(profile.timeout_seconds):
                raw_output = await self._runtime_factory().invoke(
                    profile=profile,
                    instructions=agent.instructions,
                    input_json=input_json,
                    output_schema=agent.output_schema,
                    api_key=api_key,
                    observation=observation,
                )
            output = _validate_output(raw_output, schema=agent.output_schema, profile=profile, usage=observation.usage)
        except RuntimeFailure as exc:
            error = exc.code
        except TimeoutError:
            error = ErrorCode.TIMEOUT
        except asyncio.CancelledError:
            error = ErrorCode.CANCELLED
        except Exception:
            error = ErrorCode.PROVIDER_FAILURE

        metadata = InvocationMetadata(
            runtime_revision=_RUNTIME_REVISION,
            elapsed_ms=round((perf_counter() - start) * 1_000),
            provider=profile.provider if profile else None,
            configured_model=profile.model if profile else None,
            model=observation.model,
            prompt_revision=agent.prompt_revision if agent else None,
            output_schema_revision=agent.output_schema_revision if agent else None,
            correlation_id=observation.correlation_id,
            usage=observation.usage,
            requests=observation.requests,
            pricing_version=PRICING_VERSION if profile else None,
            estimated_max_cost_usd=profile.estimated_max_cost_usd if profile else None,
            estimated_cost_usd=estimate_usage_cost(profile, observation.model, observation.usage) if profile else None,
        )
        return InvocationResult(
            request_id=request.request_id,
            agent_id=request.agent_id,
            profile_id=request.profile_id,
            outcome="error" if error else "ok",
            output=output,
            error=InvocationError(code=error) if error else None,
            metadata=metadata,
        )


def local_error(code: ErrorCode, request: InvocationRequest | None = None) -> InvocationResult:
    """Return a sanitized failure before execution could start."""
    return InvocationResult(
        request_id=request.request_id if request else None,
        agent_id=request.agent_id if request else None,
        profile_id=request.profile_id if request else None,
        outcome="error",
        output=None,
        error=InvocationError(code=code),
        metadata=InvocationMetadata(runtime_revision=_RUNTIME_REVISION, elapsed_ms=0),
    )


def _admit_input(
    request: InvocationRequest, *, agent: _AgentDefinition, profile: ModelProfile, policy: RunPolicy
) -> str:
    if not agent.required_capabilities <= profile.capabilities:
        raise RuntimeFailure(ErrorCode.UNSUPPORTED_CAPABILITY)
    try:
        input_json = agent.input_schema.model_validate(request.input).model_dump_json()
        input_bytes = len(input_json.encode("utf-8"))
    except ValueError:
        raise RuntimeFailure(ErrorCode.INVALID_INPUT) from None
    schema_bytes = len(json.dumps(agent.output_schema.model_json_schema()).encode("utf-8"))
    estimated_input = input_bytes + len(agent.instructions.encode("utf-8")) + schema_bytes + INPUT_FRAMING_TOKENS
    if estimated_input > profile.max_input_tokens:
        raise RuntimeFailure(ErrorCode.INVALID_INPUT)
    if not policy.allow_external or policy.data_classification not in {"synthetic", "public"}:
        raise RuntimeFailure(ErrorCode.EGRESS_DISABLED)
    if not policy.max_cost_usd.is_finite() or not 0 < policy.max_cost_usd <= MAX_RUN_COST_USD:
        raise RuntimeFailure(ErrorCode.CONFIGURATION_ERROR)
    if profile.estimated_max_cost_usd > policy.max_cost_usd:
        raise RuntimeFailure(ErrorCode.BUDGET_EXCEEDED)
    return input_json


def _resolve_key(environ: Mapping[str, str], *, profile: ModelProfile, input_json: str) -> str:
    api_key = environ.get(profile.credential_env_var, "").strip()
    if not api_key or not api_key.isascii() or any(character.isspace() for character in api_key):
        raise RuntimeFailure(ErrorCode.MISSING_CREDENTIALS)
    if api_key in input_json:
        raise RuntimeFailure(ErrorCode.PRIVACY_POLICY)
    return api_key


def _validate_output(
    output: str, *, schema: type[BaseModel], profile: ModelProfile, usage: Usage | None
) -> dict[str, JsonValue]:
    if usage and (
        (usage.input_tokens is not None and usage.input_tokens > profile.max_input_tokens)
        or (usage.output_tokens is not None and usage.output_tokens > profile.max_output_tokens)
    ):
        raise RuntimeFailure(ErrorCode.BUDGET_EXCEEDED)
    try:
        if len(output.encode("utf-8")) > profile.max_response_bytes:
            raise RuntimeFailure(ErrorCode.RESPONSE_TOO_LARGE)
        return schema.model_validate(decode_json(output)).model_dump(mode="json")
    except (ValueError, RecursionError):
        raise RuntimeFailure(ErrorCode.INVALID_OUTPUT) from None

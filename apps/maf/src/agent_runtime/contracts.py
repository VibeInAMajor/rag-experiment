"""Version 1 of the provider-neutral invocation protocol."""

import json
import math
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator, model_validator

MAX_REQUEST_BYTES = 16_384

type InvocationId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]
type TokenCount = Annotated[int, Field(ge=0, le=2**53 - 1)]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class InvocationRequest(_Contract):
    schema_version: Literal[1]
    request_id: InvocationId
    agent_id: InvocationId
    profile_id: InvocationId
    input: dict[str, JsonValue]

    @field_validator("schema_version", mode="before")
    @classmethod
    def _integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @field_validator("request_id", "agent_id", "profile_id")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        if value.lower().startswith(("sk-", "bearer")):
            raise ValueError("Use an opaque identifier")
        return value


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNKNOWN_AGENT = "UNKNOWN_AGENT"
    UNKNOWN_PROFILE = "UNKNOWN_PROFILE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    EGRESS_DISABLED = "EGRESS_DISABLED"
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    REFUSAL = "REFUSAL"
    INCOMPLETE_OUTPUT = "INCOMPLETE_OUTPUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    PRIVACY_POLICY = "PRIVACY_POLICY"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class Usage(_Contract):
    input_tokens: TokenCount | None = None
    output_tokens: TokenCount | None = None
    reasoning_tokens: TokenCount | None = None
    cached_input_tokens: TokenCount | None = None


class InvocationMetadata(_Contract):
    runtime_revision: str
    elapsed_ms: int
    provider: str | None = None
    configured_model: str | None = None
    model: str | None = None
    prompt_revision: str | None = None
    output_schema_revision: str | None = None
    correlation_id: str | None = None
    usage: Usage | None = None
    requests: int = 0
    retries: Literal[0] = 0
    pricing_version: str | None = None
    estimated_max_cost_usd: Decimal | None = None
    estimated_cost_usd: Decimal | None = None


class InvocationError(_Contract):
    code: ErrorCode


class InvocationResult(_Contract):
    schema_version: Literal[1] = 1
    request_id: InvocationId | None
    agent_id: InvocationId | None
    profile_id: InvocationId | None
    outcome: Literal["ok", "error"]
    output: dict[str, JsonValue] | None
    error: InvocationError | None
    metadata: InvocationMetadata

    @model_validator(mode="after")
    def _consistent_outcome(self) -> Self:
        if (self.output is not None) != (self.outcome == "ok") or (self.error is not None) != (self.outcome == "error"):
            raise ValueError("Outcome does not match output and error fields")
        return self


def decode_json(data: str) -> object:
    """Decode JSON while rejecting ambiguous keys and non-JSON constants."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise ValueError("Invalid JSON constant")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Invalid JSON number")
        return number

    result: object = json.loads(
        data, object_pairs_hook=unique_object, parse_constant=invalid_constant, parse_float=finite_float
    )
    return result

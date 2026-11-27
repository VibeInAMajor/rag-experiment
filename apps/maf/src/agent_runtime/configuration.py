"""Trusted model mappings, run policy and versioned cost estimates."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, get_args

from agent_runtime.contracts import Usage

type DataClassification = Literal["synthetic", "public"]
ReasoningEffort = Literal["low", "medium", "high", "xhigh"]

PRICING_VERSION = "openai-standard-2026-11-27"
SEMANTIC_REVIEW_PROFILE = "semantic-review"
MAX_RUN_COST_USD = Decimal("1.00")
INPUT_FRAMING_TOKENS = 1_024
_PER_MILLION = Decimal(1_000_000)
_INPUT_CACHE_WRITE_RATE = Decimal("2.50")
_CACHED_INPUT_RATE = Decimal("0.10")
_OUTPUT_RATE = Decimal("10")
_REGIONAL_ALLOWANCE = Decimal("1.10")
_MODEL_MAPPING = {SEMANTIC_REVIEW_PROFILE: "gpt-6.1-sol", "semantic-review-6.2": "gpt-6.2-sol"}


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelProfile:
    profile_id: str
    model: str
    reasoning_effort: ReasoningEffort = "medium"
    provider: str = "openai"
    credential_env_var: str = "OPENAI_API_KEY"
    capabilities: frozenset[str] = frozenset({"structured_output", "reasoning"})
    max_input_tokens: int = 8_192
    max_output_tokens: int = 2_048
    timeout_seconds: float = 45
    max_response_bytes: int = 131_072

    @property
    def estimated_max_cost_usd(self) -> Decimal:
        return _cost(self.max_input_tokens, self.max_output_tokens, 0)


@dataclass(frozen=True, slots=True, kw_only=True)
class RunPolicy:
    allow_external: bool = False
    data_classification: DataClassification | None = None
    max_cost_usd: Decimal = Decimal("0.10")


def load_profiles(environ: Mapping[str, str]) -> dict[str, ModelProfile]:
    """Resolve local model settings for a single CLI invocation."""
    effort = environ.get("MAF_OPENAI_REASONING_EFFORT", "medium")
    efforts: dict[str, ReasoningEffort] = {level: level for level in get_args(ReasoningEffort)}
    if effort not in efforts:
        raise ValueError("Unsupported reasoning effort")
    return {
        profile_id: ModelProfile(profile_id=profile_id, model=model, reasoning_effort=efforts[effort])
        for profile_id, model in _MODEL_MAPPING.items()
    }


def estimate_usage_cost(profile: ModelProfile, model: str | None, usage: Usage | None) -> Decimal | None:
    """Estimate using reported counts and an upper rate for uncategorized input."""
    if model != profile.model or usage is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    return _cost(usage.input_tokens, usage.output_tokens, usage.cached_input_tokens or 0)


def _cost(input_tokens: int, output_tokens: int, cached_tokens: int) -> Decimal:
    cached = min(cached_tokens, input_tokens)
    charge = (input_tokens - cached) * _INPUT_CACHE_WRITE_RATE + cached * _CACHED_INPUT_RATE
    return (charge + output_tokens * _OUTPUT_RATE) * _REGIONAL_ALLOWANCE / _PER_MILLION

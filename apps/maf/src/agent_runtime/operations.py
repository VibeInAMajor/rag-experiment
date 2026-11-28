"""Publish the authoritative Semantic Judge catalog and allowlisted invocation metadata."""

import json
import re
from collections.abc import Mapping
from decimal import Decimal
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import JsonValue

from agent_runtime.agents.semantic_judge.agent import AGENT_ID, JUDGE_MODES
from agent_runtime.configuration import (
    CACHE_MODE,
    CACHE_TTL_SECONDS,
    PRICING_VERSION,
    SEMANTIC_REVIEW_PROFILE,
    ModelProfile,
    standard_tariff_rates,
)
from agent_runtime.contracts import MAX_REQUEST_BYTES, ErrorCode, InvocationResult, decode_json
from agent_runtime.operations_journal import OPERATIONS_SCOPE, OperationsJournal, local_directory, read_operations_file

_PRICE_VERIFIED_AT = "2026-11-27T23:40:00Z"
_V8_VERIFIED_AT = "2026-11-27T22:26:15.469459Z"
_V8_FINGERPRINT = "eb6faa0198320869f3f6f8f73336ed653a78d9e5ef2fc84dea17ddb1cbd8dfe3"
_REVISION = re.compile(r"selection-[a-f0-9]{32}")
_BLOCKED_CODES = frozenset(
    {
        ErrorCode.EGRESS_DISABLED,
        ErrorCode.MISSING_CREDENTIALS,
        ErrorCode.PRIVACY_POLICY,
        ErrorCode.CONFIGURATION_ERROR,
        ErrorCode.BUDGET_EXCEEDED,
        ErrorCode.RATE_LIMITED,
    }
)


def tariff_snapshot(profile: ModelProfile) -> dict[str, object]:
    """Return the published OpenAI Standard short-context tariff for a Sol profile."""
    return {
        "version": PRICING_VERSION,
        "provider": profile.provider,
        "model": profile.model,
        "service_tier": "standard",
        "currency": "USD",
        "unit": "per_million_tokens",
        **standard_tariff_rates(),
        "source_url": "https://developers.openai.com/api/docs/pricing",
        "effective_at": "2026-11-27T00:00:00Z",
        "verified_at": _PRICE_VERIFIED_AT,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "status": "verified",
    }


def _agent_catalog(profiles: Mapping[str, ModelProfile]) -> dict[str, object]:
    modes = list(JUDGE_MODES)
    entries = []
    for profile in profiles.values():
        entries.append(
            {
                "profile_id": profile.profile_id,
                "model": profile.model,
                "provider": profile.provider,
                "modes": modes,
                "reasoning_effort": profile.reasoning_effort,
                "max_estimated_input_tokens": profile.max_input_tokens,
                "max_output_tokens": profile.max_output_tokens,
                "max_request_bytes": MAX_REQUEST_BYTES,
                "max_response_bytes": profile.max_response_bytes,
                "timeout_seconds": int(profile.timeout_seconds),
                "reserve_usd": _money(profile.estimated_max_cost_usd),
                "cache_mode": CACHE_MODE,
                "cache_ttl_seconds": CACHE_TTL_SECONDS,
                "qualification": _qualification(profile),
                "tariff": tariff_snapshot(profile),
            }
        )
    return {
        "agent_id": AGENT_ID,
        "display_name": "Semantic Judge",
        "runtime_revision": version("rag-maf-agent-runtime"),
        "modes": modes,
        "default_profile_id": SEMANTIC_REVIEW_PROFILE,
        "profiles": entries,
    }


def _qualification(profile: ModelProfile) -> dict[str, str | None]:
    historical = profile.profile_id == SEMANTIC_REVIEW_PROFILE and profile.reasoning_effort == "medium"
    return {
        "state": "qualified" if historical else "unqualified",
        "revision": _V8_FINGERPRINT if historical else None,
        "verified_at": _V8_VERIFIED_AT if historical else None,
        "reason": "historical_pass" if historical else "offline_only",
    }


def operations_catalog(profiles: Mapping[str, ModelProfile]) -> dict[str, object]:
    """Expose safe configured fields with qualification provenance, without creating a provider."""
    return {"schema_version": 1, "scope": OPERATIONS_SCOPE, "agents": [_agent_catalog(profiles)]}


def resolve_operations_selection(configured_path: str | None, profiles: Mapping[str, ModelProfile]) -> tuple[str, str]:
    """Bind the versioned local selection once at caller admission."""
    if not configured_path:
        raise ValueError("Agent operations is unavailable")
    directory = local_directory(Path(configured_path))
    catalog = operations_catalog(profiles)
    if _read_metadata(directory / "catalog.json") != catalog:
        raise ValueError("Agent operations catalog does not match current runtime")
    try:
        saved = _read_metadata(directory / "selection.json")
    except FileNotFoundError:
        saved = {"schema_version": 1, "scope": OPERATIONS_SCOPE, "selections": {}}
    if (
        type(saved.get("schema_version")) is not int
        or saved.get("schema_version") != 1
        or saved.get("scope") != OPERATIONS_SCOPE
        or not isinstance(selections := saved.get("selections"), dict)
    ):
        raise ValueError("Invalid agent operations selection")
    if AGENT_ID not in selections:
        if _qualification(profiles[SEMANTIC_REVIEW_PROFILE])["state"] != "qualified":
            raise ValueError("Default agent profile is ineligible")
        encoded = json.dumps(_agent_catalog(profiles), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return SEMANTIC_REVIEW_PROFILE, f"catalog-{sha256(encoded).hexdigest()}"
    selection = selections[AGENT_ID]
    if (
        not isinstance(selection, dict)
        or not isinstance(profile_id := selection.get("profile_id"), str)
        or profile_id not in profiles
        or not isinstance(revision := selection.get("revision"), str)
        or not _REVISION.fullmatch(revision)
        or _qualification(profiles[profile_id])["state"] != "qualified"
    ):
        raise ValueError("Selected agent profile is ineligible")
    return profile_id, revision


def _read_metadata(path: Path) -> dict[str, JsonValue]:
    item = decode_json(read_operations_file(path).decode("utf-8-sig"))
    if not isinstance(item, dict):
        raise ValueError("Invalid agent operations metadata")
    return item


def run_identity(
    profile: ModelProfile,
    *,
    origin: Literal["calibration", "evaluation"],
    mode: str,
    planned_cases: int,
    budget: Decimal,
    selection_revision: str | None = None,
) -> dict[str, object]:
    """Freeze the configured identity and tariff for one operation."""
    definition = JUDGE_MODES.get(mode)
    return {
        "agent_id": AGENT_ID,
        "origin": origin,
        "profile_id": profile.profile_id,
        "mode": mode,
        "model": profile.model,
        "provider": profile.provider,
        "runtime_revision": version("rag-maf-agent-runtime"),
        "prompt_revision": definition.prompt_revision if definition else None,
        "schema_revision": definition.output_schema_revision if definition else None,
        "cache_mode": CACHE_MODE,
        "tariff": tariff_snapshot(profile),
        "selection_revision": selection_revision,
        "planned_cases": planned_cases,
        "budget_usd": _money(budget),
    }


def begin_call(journal: OperationsJournal, *, mode: str, reserve: Decimal) -> dict[str, str]:
    """Mark invocation start before the caller can enter the provider boundary."""
    identity = {"call_id": uuid4().hex, "case_id": uuid4().hex, "mode": mode}
    journal.emit("call_pending", stage="admission", call={**identity, "reserve_usd": _money(reserve)})
    return identity


def call_status(error: ErrorCode | None) -> Literal["completed", "blocked", "cancelled", "failed"]:
    """Classify operational outcomes without inspecting any verdict."""
    if error is None:
        return "completed"
    if error is ErrorCode.CANCELLED:
        return "cancelled"
    return "blocked" if error in _BLOCKED_CODES else "failed"


def finish_call(
    journal: OperationsJournal, identity: Mapping[str, object], result: InvocationResult, *, stage: str | None = None
) -> None:
    """Publish only allowed terminal details from the validated invocation result."""
    error = result.error.code if result.error else None
    metadata = result.metadata
    usage = metadata.usage
    safe_call = {
        **identity,
        "actual_model": metadata.model,
        "provider_request_id": metadata.correlation_id,
        "requests": metadata.requests,
        "elapsed_ms": metadata.elapsed_ms,
        "usage": {
            "input_tokens": usage.input_tokens,
            "cached_read_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
        }
        if usage is not None
        else None,
        "estimated_cost_usd": _money(metadata.estimated_cost_usd),
        "reserve_usd": _money(metadata.estimated_max_cost_usd),
    }
    safe_stage = {"output_schema": "output_validation", "evidence_validation": "evidence_validation"}.get(stage or "")
    journal.emit("call_completed", call=safe_call, status=call_status(error), reason=error, stage=safe_stage)
    journal.emit("case_completed", case_id=identity["case_id"], status=call_status(error))


def _money(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None

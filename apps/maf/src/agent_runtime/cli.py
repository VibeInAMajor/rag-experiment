"""Single-invocation UTF-8 JSON transport for the installed application."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from agent_runtime.agents.semantic_judge.agent import AGENT_ID, JUDGE_MODES
from agent_runtime.agents.structured_smoke import SMOKE_EXPECTED_OUTPUT, SMOKE_REQUEST
from agent_runtime.composition import create_runtime
from agent_runtime.configuration import RunPolicy, load_profiles
from agent_runtime.contracts import MAX_REQUEST_BYTES, ErrorCode, InvocationError, InvocationRequest, decode_json
from agent_runtime.operations import (
    begin_call,
    call_status,
    finish_call,
    operations_catalog,
    resolve_operations_selection,
    run_identity,
)
from agent_runtime.operations_journal import OPERATIONS_DIR_ENV, OperationsJournal
from agent_runtime.runtime import AgentApplication, ProviderObservation, local_error


def main(argv: Sequence[str] | None = None) -> int:
    """Read one request, write one result, and return the corresponding exit code."""
    parser = argparse.ArgumentParser(description="Run one standalone agent invocation")
    parser.add_argument("--allow-external", action="store_true", help="Permit one direct OpenAI request")
    parser.add_argument("--data-classification", choices=("synthetic", "public"))
    parser.add_argument("--max-cost-usd", type=_decimal, default=RunPolicy().max_cost_usd)
    parser.add_argument("--smoke", action="store_true", help="Run the built-in synthetic marker fixture")
    parser.add_argument("--operations-catalog", action="store_true", help="Print the local operator metadata catalog")
    parser.add_argument("--use-operations-selection", action="store_true", help="Bind a profile-less Judge request")
    parser.add_argument("--record-operations", action="store_true", help="Record this standalone Judge invocation")
    args = parser.parse_args(argv)
    if args.operations_catalog:
        if args.allow_external or args.smoke or args.use_operations_selection or args.record_operations:
            parser.error("--operations-catalog must be used on its own")
        try:
            catalog = operations_catalog(load_profiles(os.environ))
        except ValueError:
            parser.error("Cannot resolve the agent operations catalog")
        sys.stdout.buffer.write(json.dumps(catalog, separators=(",", ":")).encode("utf-8") + b"\n")
        return 0
    if args.smoke and (args.use_operations_selection or args.record_operations):
        parser.error("The marker smoke is independent of Semantic Judge operations")
    request = None
    journal = None
    call = None
    observation = ProviderObservation()
    selection = None
    profile_id = None
    try:
        try:
            profiles = None
            if args.use_operations_selection:
                profiles = load_profiles(os.environ)
                profile_id, selection = resolve_operations_selection(os.environ.get(OPERATIONS_DIR_ENV), profiles)
        except (ValueError, OSError, RecursionError):
            result = local_error(ErrorCode.CONFIGURATION_ERROR)
        else:
            try:
                request = SMOKE_REQUEST if args.smoke else _read_request(profile_id=profile_id)
            except (ValueError, RecursionError, OSError):
                result = local_error(ErrorCode.INVALID_INPUT)
            else:
                if profiles is None:
                    profiles = load_profiles(os.environ)
                policy = RunPolicy(
                    allow_external=args.allow_external,
                    data_classification="synthetic" if args.smoke else args.data_classification,
                    max_cost_usd=args.max_cost_usd,
                )
                profile = profiles.get(request.profile_id)
                mode = request.input.get("mode")
                if (
                    (args.record_operations or args.use_operations_selection)
                    and request.agent_id == AGENT_ID
                    and profile is not None
                    and isinstance(mode, str)
                    and mode in JUDGE_MODES
                    and policy.max_cost_usd.is_finite()
                    and policy.max_cost_usd >= 0
                ):
                    journal = OperationsJournal.start(
                        os.environ.get(OPERATIONS_DIR_ENV),
                        run_identity(
                            profile,
                            origin="evaluation",
                            mode=mode,
                            planned_cases=1,
                            budget=policy.max_cost_usd,
                            selection_revision=selection,
                        ),
                    )
                    if journal:
                        call = begin_call(journal, mode=mode, reserve=profile.estimated_max_cost_usd)
                application = AgentApplication(create_runtime, profiles)
                result = asyncio.run(
                    application.invoke(request, policy=policy, environ=os.environ, observation=observation)
                )
    except ValueError:
        result = local_error(ErrorCode.CONFIGURATION_ERROR, request)
    except KeyboardInterrupt:
        result = local_error(ErrorCode.CANCELLED, request)

    if journal and call:
        finish_call(journal, call, result, stage=observation.failure_stage)
        code = result.error.code if result.error else None
        journal.emit("run_finished", stage="finalizing", status=call_status(code), reason=code)
    if args.smoke and result.outcome == "ok" and result.output != SMOKE_EXPECTED_OUTPUT:
        result = result.model_copy(
            update={"outcome": "error", "output": None, "error": InvocationError(code=ErrorCode.INVALID_OUTPUT)}
        )

    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8") + b"\n")
    if result.error is None:
        return 0
    return 130 if result.error.code == ErrorCode.CANCELLED else 1


def _read_request(*, profile_id: str | None = None) -> InvocationRequest:
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds byte limit")
    data = decode_json(payload.decode("utf-8"))
    if profile_id is not None:
        if not isinstance(data, dict) or "profile_id" in data or data.get("agent_id") != AGENT_ID:
            raise ValueError("Profile selection requires an unpinned Judge request")
        data["profile_id"] = profile_id
    return InvocationRequest.model_validate(data)


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("expected a decimal amount") from None

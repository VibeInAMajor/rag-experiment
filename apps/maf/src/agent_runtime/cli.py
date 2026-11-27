"""Single-invocation UTF-8 JSON transport for the installed application."""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from agent_runtime.agents.structured_smoke import SMOKE_EXPECTED_OUTPUT, SMOKE_REQUEST
from agent_runtime.configuration import RunPolicy, load_profiles
from agent_runtime.contracts import MAX_REQUEST_BYTES, ErrorCode, InvocationError, InvocationRequest, decode_json
from agent_runtime.runtime import AgentApplication, AgentRuntime, local_error


def main(argv: Sequence[str] | None = None) -> int:
    """Read one request, write one result, and return the corresponding exit code."""
    parser = argparse.ArgumentParser(description="Run one standalone agent invocation")
    parser.add_argument("--allow-external", action="store_true", help="Permit one direct OpenAI request")
    parser.add_argument("--data-classification", choices=("synthetic", "public"))
    parser.add_argument("--max-cost-usd", type=_decimal, default=RunPolicy().max_cost_usd)
    parser.add_argument("--smoke", action="store_true", help="Run the built-in synthetic marker fixture")
    args = parser.parse_args(argv)
    request = None
    try:
        request = SMOKE_REQUEST if args.smoke else _read_request()
    except (ValueError, RecursionError, OSError):
        result = local_error(ErrorCode.INVALID_INPUT)
    except KeyboardInterrupt:
        result = local_error(ErrorCode.CANCELLED)
    else:
        try:
            profiles = load_profiles(os.environ)
            policy = RunPolicy(
                allow_external=args.allow_external,
                data_classification="synthetic" if args.smoke else args.data_classification,
                max_cost_usd=args.max_cost_usd,
            )
            application = AgentApplication(_create_runtime, profiles)
            result = asyncio.run(application.invoke(request, policy=policy, environ=os.environ))
        except ValueError:
            result = local_error(ErrorCode.CONFIGURATION_ERROR, request)
        except KeyboardInterrupt:
            result = local_error(ErrorCode.CANCELLED, request)
        if args.smoke and result.outcome == "ok" and result.output != SMOKE_EXPECTED_OUTPUT:
            result = result.model_copy(
                update={"outcome": "error", "output": None, "error": InvocationError(code=ErrorCode.INVALID_OUTPUT)}
            )

    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8") + b"\n")
    if result.error is None:
        return 0
    return 130 if result.error.code == ErrorCode.CANCELLED else 1


def _read_request() -> InvocationRequest:
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds byte limit")
    return InvocationRequest.model_validate(decode_json(payload.decode("utf-8")))


def _create_runtime() -> AgentRuntime:
    from agent_runtime.adapters.maf_openai import MafOpenAIRuntime

    return MafOpenAIRuntime()


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("expected a decimal amount") from None

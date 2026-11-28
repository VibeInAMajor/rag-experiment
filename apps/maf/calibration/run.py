"""Run a frozen, bounded calibration through the standalone MAF application."""

import argparse
import asyncio
import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import TextIO

from agent_runtime.agents.semantic_judge.agent import AGENT_ID, JUDGE_MODES
from agent_runtime.agents.semantic_judge.contracts import MAX_CONTEXT_FRAGMENTS
from agent_runtime.agents.semantic_judge.instructions import INSTRUCTIONS
from agent_runtime.composition import create_runtime
from agent_runtime.configuration import PRICING_VERSION, SEMANTIC_REVIEW_PROFILE, ModelProfile, RunPolicy, load_profiles
from agent_runtime.contracts import MAX_REQUEST_BYTES, ErrorCode, InvocationRequest, InvocationResult
from agent_runtime.operations import begin_call, call_status, finish_call, run_identity
from agent_runtime.operations_journal import OPERATIONS_DIR_ENV, OperationsJournal
from agent_runtime.runtime import AgentApplication, ProviderObservation
from calibration.controls import CASES, DEVELOPMENT_CASES, CalibrationCase
from calibration.scoring import GRADE_PERCENT, OTHER_MODE_PERCENT, SUPPORT_PERCENT, score_case, summarize

_MAX_CASES = 36
_MIN_QUALIFICATION_CASES = 24
_MAX_RESERVED_COST = Decimal("15.00")
_DEADLINE_SECONDS = 420
_STOP_ERRORS = frozenset(
    {ErrorCode.MISSING_CREDENTIALS, ErrorCode.CONFIGURATION_ERROR, ErrorCode.RATE_LIMITED, ErrorCode.CANCELLED}
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the standalone Semantic Judge")
    run = parser.add_mutually_exclusive_group(required=True)
    run.add_argument("--check", action="store_true", help="Validate and fingerprint controls offline")
    run.add_argument("--allow-external", action="store_true", help="Execute the frozen controls against OpenAI")
    parser.add_argument("--development", action="store_true", help="Use the separate development controls")
    parser.add_argument("--report", type=Path, help="Write a new checkpointed JSONL report for a live run")
    args = parser.parse_args(argv)
    if args.allow_external and args.report is None:
        parser.error("--allow-external requires --report")
    if args.check and args.report is not None:
        parser.error("--report is only used for live runs")

    cases = DEVELOPMENT_CASES if args.development else CASES
    # The calibration freezes the same default profile independently of the caller's other runs.
    profiles = load_profiles({})
    profile = profiles[SEMANTIC_REVIEW_PROFILE]
    app = AgentApplication(create_runtime, profiles)
    try:
        manifest = asyncio.run(_preflight(cases, profile=profile, app=app, development=args.development))
    except ValueError as exc:
        _write({"status": "INVALID_CONTROLS", "detail": str(exc)})
        return 1
    if args.check:
        _write({"status": "FROZEN_OFFLINE", **manifest})
        return 0
    try:
        with args.report.open("x", encoding="utf-8", newline="\n") as report:
            _write({"event": "manifest", **manifest}, stream=report)
            journal = OperationsJournal.start(
                os.environ.get(OPERATIONS_DIR_ENV),
                run_identity(
                    profile, origin="calibration", mode="batch", planned_cases=len(cases), budget=_MAX_RESERVED_COST
                ),
            )
            try:
                summary = asyncio.run(
                    _run_live(
                        cases,
                        application=app,
                        report=report,
                        development=args.development,
                        journal=journal,
                        reserve=profile.estimated_max_cost_usd,
                    )
                )
            except KeyboardInterrupt:
                if journal:
                    journal.emit("run_finished", status="cancelled", reason="CANCELLED")
                raise
            except OSError:
                if journal:
                    journal.emit("run_finished", status="interrupted", reason="INTERRUPTED")
                raise
    except FileExistsError:
        _write({"status": "REPORT_EXISTS"})
        return 1
    except OSError:
        _write({"status": "REPORT_IO_ERROR"})
        return 1
    _write(summary)
    accepted = summary["status"] == "PASS" or (
        summary["status"] == "DEVELOPMENT_ONLY" and summary["all_controls_matched"] is True
    )
    return 0 if accepted and summary["stop_reason"] is None else 1


async def _preflight(
    cases: Sequence[CalibrationCase], *, profile: ModelProfile, app: AgentApplication, development: bool
) -> dict[str, object]:
    ids = {case.case_id for case in cases}
    distinct = {case.case_id for case in cases if case.repeat_of is None}
    repeats = [case for case in cases if case.repeat_of is not None]
    if not cases or len(cases) > _MAX_CASES or len(ids) != len(cases):
        raise ValueError("Controls exceed case limits or contain duplicate IDs")
    if any(case.repeat_of not in distinct for case in repeats):
        raise ValueError("A repeat must refer to a distinct control")
    if not development and (
        len(distinct) < _MIN_QUALIFICATION_CASES
        or {str(case.input.get("language")) for case in repeats} != {"en", "ru", "uk"}
    ):
        raise ValueError("Qualification requires 24 distinct controls and repeats in EN, RU and UK")
    reserved = profile.estimated_max_cost_usd * len(cases)
    if reserved > _MAX_RESERVED_COST:
        raise ValueError("Calibrating all cases would exceed the estimated run budget")
    for case in cases:
        request = _request(case)
        if len(request.model_dump_json().encode("utf-8")) > MAX_REQUEST_BYTES:
            raise ValueError(f"{case.case_id}: request exceeds the CLI envelope cap")
        offline = await app.invoke(request, policy=RunPolicy(), environ={})
        if offline.error is None or offline.error.code != ErrorCode.EGRESS_DISABLED:
            detail = offline.error.code.value if offline.error else "unexpected admission"
            raise ValueError(f"{case.case_id}: {detail}")

    manifest: dict[str, object] = {
        "phase": "development" if development else "qualification",
        "control_manifest_sha256": _fingerprint([asdict(case) for case in cases]),
        "case_count": len(cases),
        "distinct_cases": len(distinct),
        "repeat_count": len(repeats),
        "mode_counts": dict(Counter(str(case.input["mode"]) for case in cases)),
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "configured_model": profile.model,
        "reasoning_effort": profile.reasoning_effort,
        "runtime_revision": version("rag-maf-agent-runtime"),
        "pricing_version": PRICING_VERSION,
        "request_limit": len(cases),
        "concurrency": 1,
        "retries": 0,
        "deadline_seconds": _DEADLINE_SECONDS,
        "estimated_max_cost_usd": str(reserved),
        "budget_ceiling_usd": str(_MAX_RESERVED_COST),
        "limits": {
            "cli_request_bytes": MAX_REQUEST_BYTES,
            "judge_context_fragments": MAX_CONTEXT_FRAGMENTS,
            "estimated_input_tokens": profile.max_input_tokens,
            "output_tokens": profile.max_output_tokens,
            "provider_response_bytes": profile.max_response_bytes,
            "provider_timeout_seconds": profile.timeout_seconds,
        },
        "gates": {
            "grade_percent": GRADE_PERCENT,
            "binary_support_percent": SUPPORT_PERCENT,
            "other_mode_percent": OTHER_MODE_PERCENT,
            "critical_percent": 100,
            "unknown_percent": 100,
            "repeat_percent": 100,
            "allow_operational_errors": False,
            "allow_false_complete_scope": False,
        },
        "modes": {
            mode: {
                "prompt_revision": definition.prompt_revision,
                "prompt_sha256": INSTRUCTIONS[mode].sha256,
                "output_schema_revision": definition.output_schema_revision,
                "input_schema_sha256": _fingerprint(definition.input_schema.model_json_schema()),
                "output_schema_sha256": _fingerprint(definition.output_schema.model_json_schema()),
            }
            for mode, definition in JUDGE_MODES.items()
        },
    }
    return {**manifest, "calibration_sha256": _fingerprint(manifest)}


async def _run_live(
    cases: Sequence[CalibrationCase],
    *,
    application: AgentApplication,
    report: TextIO,
    development: bool,
    journal: OperationsJournal | None = None,
    reserve: Decimal | None = None,
) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _DEADLINE_SECONDS
    results: list[InvocationResult] = []
    stop_reason = None
    terminal_status = "completed"
    terminal_reason: ErrorCode | str | None = None
    for case in cases:
        if loop.time() >= deadline:
            stop_reason = "RUN_DEADLINE"
            terminal_status, terminal_reason = "interrupted", ErrorCode.TIMEOUT
            break
        observation = ProviderObservation()
        mode = str(case.input["mode"])
        call = begin_call(journal, mode=mode, reserve=reserve) if journal and reserve is not None else None
        try:
            async with asyncio.timeout_at(deadline):
                result = await application.invoke(
                    _request(case),
                    policy=RunPolicy(allow_external=True, data_classification=case.classification),
                    environ=os.environ,
                    observation=observation,
                )
        except TimeoutError:
            stop_reason = "RUN_DEADLINE"
            terminal_status, terminal_reason = "interrupted", ErrorCode.TIMEOUT
            break
        if journal and call:
            finish_call(journal, call, result, stage=observation.failure_stage)
        results.append(result)
        score = score_case(case, result)
        record = result.model_dump(mode="json")
        record["metadata"]["correlation_id"] = "[redacted]" if result.metadata.correlation_id else None
        _write(
            {
                "event": "case",
                "case_id": case.case_id,
                "classification": case.classification,
                "critical": case.critical,
                "repeat_of": case.repeat_of,
                "provenance": case.provenance,
                "mode": case.input["mode"],
                "language": case.input["language"],
                "failure_stage": observation.failure_stage,
                "failure_reason": observation.failure_reason,
                "failure_field": observation.failure_field,
                "expected": case.expected,
                "checks": {
                    "passed": score.passed,
                    "fields": score.fields,
                    "facts": score.facts,
                    "quotes": score.quotes,
                    "required_facts": score.required_facts,
                    "answer_support": score.answer_support,
                },
                "result": record,
            },
            stream=report,
        )
        if result.error is not None and result.error.code in _STOP_ERRORS:
            stop_reason = result.error.code.value
            terminal_status, terminal_reason = call_status(result.error.code), result.error.code
            break
        if result.metadata.requests and result.metadata.model not in {None, result.metadata.configured_model}:
            stop_reason = "UNEXPECTED_PROVIDER_MODEL"
            terminal_status, terminal_reason = "failed", "MODEL_MISMATCH"
            break

    scores = [score_case(case, results[index] if index < len(results) else None) for index, case in enumerate(cases)]
    summary = summarize(scores, development=development)
    if stop_reason is not None and summary["status"] == "PASS":
        summary["status"] = "NO_GO"
    costs = [result.metadata.estimated_cost_usd for result in results if result.metadata.requests]
    reported_costs = [cost for cost in costs if cost is not None]
    summary_record: dict[str, object] = {
        "event": "summary",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "stop_reason": stop_reason,
        "provider_requests": sum(result.metadata.requests for result in results),
        "provider_retries": sum(result.metadata.retries for result in results),
        "provider_models": sorted({result.metadata.model for result in results if result.metadata.model is not None}),
        "estimated_cost_usd_with_complete_usage": (
            str(sum(reported_costs, start=Decimal(0))) if costs and len(reported_costs) == len(costs) else None
        ),
        **summary,
    }
    _write(summary_record, stream=report)
    if journal:
        if summary["status"] == "NO_GO" and terminal_status == "completed":
            terminal_status = "failed"
        journal.emit("run_finished", stage="finalizing", status=terminal_status, reason=terminal_reason)
    return summary_record


def _request(case: CalibrationCase) -> InvocationRequest:
    return InvocationRequest(
        schema_version=1,
        request_id=case.case_id,
        agent_id=AGENT_ID,
        profile_id=SEMANTIC_REVIEW_PROFILE,
        input=case.input,
    )


def _fingerprint(data: object) -> str:
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _write(record: dict[str, object], *, stream: TextIO | None = None) -> None:
    serialized = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    if stream is None:
        print(serialized)
    else:
        stream.write(serialized + "\n")
        stream.flush()

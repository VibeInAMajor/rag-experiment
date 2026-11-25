"""Explicit local saturation calibration and observation of a real durable embedding backlog."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx

from apps.workbench.embedding.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingProfile,
    EmbeddingRequest,
    EmbeddingRuntimeIdentity,
)
from apps.workbench.embedding.embedding_adapters import TeiEmbeddingAdapter
from apps.workbench.embedding.embedding_capacity import MeasuredEmbeddingCapacityPolicy, ProductionEmbeddingGovernor
from apps.workbench.embedding.embedding_dispatch import QualificationCapacityPolicy, QualificationEmbeddingGovernor
from scripts.workbench_embedding_qualify import (
    _DEFAULT_CONTAINER,
    _DEFAULT_ENDPOINT,
    _MODEL_ID,
    _REVISION,
    LocalDeploymentVerifier,
    _digest,
    _distribution,
    _gpu,
)

_SCREEN_SECONDS = 12.0
_SUSTAIN_SECONDS = 120.0
_CANDIDATES = ((128, 8), (512, 1), (512, 4), (512, 8), (1024, 8), (2048, 8), (4096, 8))


def _text_with_tokens(verifier: LocalDeploymentVerifier, target: int, index: int) -> str:
    header = f"Capacity calibration item {index}: durable source versions and consistent search snapshots. "
    low, high = 0, target + 1
    while low + 1 < high:
        middle = (low + high) // 2
        candidate = header + "transaction " * middle
        if verifier.counter.count_tokens(candidate) <= target:
            low = middle
        else:
            high = middle
    result = header + "transaction " * low
    if not 1 <= verifier.counter.count_tokens(result) <= target:
        raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
    return result


def _calibration_request(profile: EmbeddingProfile, items: tuple[EmbeddingItem, ...]) -> EmbeddingRequest:
    return EmbeddingRequest(
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        task_kind="document",
        items=items,
        deadline=time.monotonic() + profile.timeout_seconds,
        workspace_id="capacity-calibration",
        trace_id="capacity-calibration",
    )


async def _measure_candidate(
    adapter: TeiEmbeddingAdapter,
    verifier: LocalDeploymentVerifier,
    profile: EmbeddingProfile,
    *,
    tokens_per_item: int,
    items: int,
    duration_seconds: float,
) -> dict[str, Any]:
    packet = tuple(
        EmbeddingItem(item_id=f"calibration-{index}", text=text, input_hash=hashlib.sha256(text.encode()).hexdigest())
        for index in range(items)
        for text in [_text_with_tokens(verifier, tokens_per_item, index)]
    )
    started = time.monotonic()
    completions = []
    durations = []
    total_tokens = 0
    while time.monotonic() < started + duration_seconds:
        output = await adapter.embed(_calibration_request(profile, packet))
        if output.usage_provenance != "provider_reported" or output.usage_tokens is None:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        total_tokens += output.usage_tokens
        durations.append(output.duration_ms)
        completions.append({"at": time.monotonic() - started, "tokens": output.usage_tokens})
    elapsed = time.monotonic() - started
    full_windows = [
        sum(row["tokens"] for row in completions if index * 60 <= row["at"] < (index + 1) * 60)
        for index in range(math.floor(duration_seconds / 60))
    ]
    return {
        "tokens_per_item_target": tokens_per_item,
        "items": items,
        "elapsed_seconds": elapsed,
        "provider_reported_tokens": total_tokens,
        "completed_requests": len(completions),
        "provider_reported_tpm": total_tokens * 60 / elapsed,
        "completed_rpm": len(completions) * 60 / elapsed,
        "adapter_latency_ms": _distribution(durations),
        "full_60_second_completed_tokens": full_windows,
        "sustainable_candidate_tpm": min(full_windows) if full_windows else None,
        "completions": completions,
        "failures": 0,
    }


def _calibration_profile(identity: EmbeddingRuntimeIdentity, query_instruction: str | None = None) -> EmbeddingProfile:
    profile = EmbeddingProfile(
        profile_id="qwen3-embedding-4b-local",
        profile_revision="qwen3-4b-capacity-32k-r1",
        provider_adapter_id="tei-openai",
        model_id=_MODEL_ID,
        model_revision=_REVISION,
        model_digest=identity.model_digest,
        tokenizer_digest=identity.tokenizer_digest,
        tokenizer_revision=identity.tokenizer_revision,
        dimensions=2560,
        max_tokens=8192,
        max_batch_tokens=32768,
        max_batch_items=8,
        timeout_seconds=60.0,
    )
    if query_instruction is None:
        return profile
    instruction_digest = hashlib.sha256(query_instruction.encode("utf-8")).hexdigest()[:16]
    return EmbeddingProfile.model_validate(
        {
            **profile.model_dump(),
            "query_instruction": query_instruction,
            "profile_revision": f"qwen3-4b-query-{instruction_digest}-r1",
        }
    )


async def calibrate_capacity(
    *,
    directory: Path,
    endpoint: str = _DEFAULT_ENDPOINT,
    container: str = _DEFAULT_CONTAINER,
    output: Path | None = None,
    query_instruction: str | None = None,
) -> tuple[EmbeddingProfile, MeasuredEmbeddingCapacityPolicy, dict[str, Any]]:
    """Measure capacity for the selected immutable input profile before fixing its denominator."""
    async with httpx.AsyncClient(base_url=endpoint, trust_env=False, follow_redirects=False, timeout=10) as client:
        verifier = LocalDeploymentVerifier(directory, container, client, endpoint=endpoint)
        identity = await verifier.initialize()
        profile = _calibration_profile(identity, query_instruction)
        qualification = QualificationEmbeddingGovernor(
            QualificationCapacityPolicy(
                profile_id=profile.profile_id,
                profile_revision=profile.profile_revision,
                deployment_id=identity.deployment_id,
                policy_revision="finite-capacity-calibration-r1",
                max_attempts=4096,
                max_total_tokens=10000000,
                max_request_tokens=32768,
                max_duration_seconds=1800.0,
            )
        )
        adapter = TeiEmbeddingAdapter(
            profile,
            endpoint=endpoint,
            token_counter=verifier.counter,
            governor=qualification,
            identity_verifier=verifier,
        )
        gpu = await asyncio.to_thread(_gpu)
        peak = gpu["used_mib"]
        stop = asyncio.Event()

        async def sample_gpu() -> None:
            nonlocal peak
            while not stop.is_set():
                peak = max(peak, (await asyncio.to_thread(_gpu))["used_mib"])
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=1.0)

        await qualification.warm_up_async()
        sampler = asyncio.create_task(sample_gpu())
        screens = []
        finalists = []
        try:
            await adapter.warm_up_async()
            for token_target, item_count in _CANDIDATES:
                screens.append(
                    await _measure_candidate(
                        adapter,
                        verifier,
                        profile,
                        tokens_per_item=token_target,
                        items=item_count,
                        duration_seconds=_SCREEN_SECONDS,
                    )
                )
            leaders = sorted(screens, key=lambda row: row["provider_reported_tpm"], reverse=True)[:2]
            for candidate in leaders:
                finalists.append(
                    await _measure_candidate(
                        adapter,
                        verifier,
                        profile,
                        tokens_per_item=candidate["tokens_per_item_target"],
                        items=candidate["items"],
                        duration_seconds=_SUSTAIN_SECONDS,
                    )
                )
        finally:
            stop.set()
            await sampler
            await adapter.close_async()
            accounting = qualification.summary()
            await qualification.close_async()
        await verifier.finalize()
        selected = max(finalists, key=lambda row: row["sustainable_candidate_tpm"])
        report = {
            "status": "MEASURED",
            "identity": identity.model_dump(),
            "profile_fingerprint": profile.fingerprint,
            "screen_duration_seconds": _SCREEN_SECONDS,
            "sustained_duration_per_finalist_seconds": _SUSTAIN_SECONDS,
            "screen_candidates": screens,
            "sustained_candidates": finalists,
            "selected": selected,
            "selection_rule": "highest minimum of two full 60-second windows among the two screened leaders",
            "denominator_frozen_before_validation": True,
            "usage_provenance": "provider_reported",
            "qualification_governor": accounting,
            "gpu": {**gpu, "sampled_device_peak_used_mib": peak},
            "gpu_scope": "shared physical GPU; observed workload and sharing conditions only",
            "model_and_cached_assets_full_hashes_unchanged": True,
            "per_item_limit_qualified_tokens": 8192,
            "max_batch_tokens_exercised": 32768,
            "max_in_flight": 1,
            "not_tested": ["concurrency2or4: server permits remain eight individual inputs"],
            "donor_implementation_copied": False,
        }
        stamp = time.time()
        policy = MeasuredEmbeddingCapacityPolicy(
            policy_revision=f"measured-{int(stamp)}",
            profile_id=profile.profile_id,
            profile_revision=profile.profile_revision,
            profile_fingerprint=profile.fingerprint,
            deployment_id=identity.deployment_id,
            runtime_evidence_digest=identity.evidence_digest,
            calibration_digest=_digest(report),
            sustainable_tpm=int(selected["sustainable_candidate_tpm"]),
            sustainable_rpm=max(1, math.floor(max(row["completed_rpm"] for row in screens + finalists))),
            measured_at_unix=stamp,
            expires_at_unix=stamp + 7200.0,
            max_request_tokens=profile.max_batch_tokens,
        )
        if output is not None:
            envelope = {
                "profile": profile.model_dump(mode="json"),
                "capacity": policy.model_dump(mode="json"),
                "report": report,
            }
            await asyncio.to_thread(_write_json, output, envelope)
        return profile, policy, report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _backlogged_fraction(samples: list[dict[str, Any]], start: float, end: float) -> float | None:
    rows = sorted((row for row in samples if start - 2 <= row["at"] <= end), key=lambda row: row["at"])
    if not rows or rows[0]["at"] > start + 1.5 or rows[-1]["at"] < end - 2:
        return None
    duration = 0.0
    for index, row in enumerate(rows):
        left = max(start, row["at"])
        right = min(end, rows[index + 1]["at"] if index + 1 < len(rows) else end)
        if index + 1 < len(rows) and rows[index + 1]["at"] - row["at"] > 2.5:
            return None
        if row.get("backlogged") is True:
            duration += max(0.0, right - left)
    return duration / (end - start)


def _trace_hard_violations(
    policy: MeasuredEmbeddingCapacityPolicy, events: list[dict[str, Any]], start: float
) -> list[dict[str, Any]]:
    charges: dict[str, dict[str, Any]] = {}
    violations = []
    for event in sorted(events, key=lambda row: row["at"]):
        kind, at = event["event"], event["at"]
        if kind == "ledger_snapshot":
            charges = {
                row["reservation_id"]: {
                    "tokens": row["tokens"],
                    "at": row["sent_at"] or row["reserved_at"],
                    "held": row["finished_at"] is None,
                }
                for row in event["charges"]
            }
        elif kind == "reserved":
            charges[event["reservation_id"]] = {"tokens": event["tokens"], "at": at, "held": True}
        elif kind == "sent":
            charges.setdefault(event["reservation_id"], {"tokens": event["tokens"], "held": True})["at"] = at
        elif kind == "finished" and event["reservation_id"] in charges:
            charges[event["reservation_id"]]["held"] = False
        if kind in {"reserved", "sent"} and at >= start:
            total = sum(row["tokens"] for row in charges.values() if row["held"] or row["at"] > at - 60)
            if total > policy.hard_token_budget:
                violations.append({"at": at, "event": kind, "estimated_tokens_including_held": total})
    return violations


def evaluate_capacity_run(
    policy: MeasuredEmbeddingCapacityPolicy,
    events: list[dict[str, Any]],
    *,
    start_monotonic: float,
    end_monotonic: float,
    demand_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate all sliding admissions and every full observation window without changing measured Q."""
    sends = sorted((row for row in events if row["event"] == "sent"), key=lambda row: row["at"])
    completed = [row for row in events if row["event"] == "finished"]
    hard_violations = _trace_hard_violations(policy, events, start_monotonic)
    windows = []
    stop = start_monotonic + 60
    while stop <= end_monotonic:
        begin = stop - 60
        finished = [row for row in completed if begin <= row["at"] < stop]
        known = sum(
            row["usage_tokens"]
            for row in finished
            if row["outcome"] == "success" and row["usage_provenance"] == "provider_reported"
        )
        unknown = sum(
            row["outcome"] == "success" and row["usage_provenance"] != "provider_reported" for row in finished
        )
        failures = sum(row["outcome"] != "success" for row in finished)
        saturation = _backlogged_fraction(demand_samples, begin, stop)
        state = (
            "NOT_MEASURABLE"
            if unknown or saturation is None
            else "RECOVERY"
            if failures
            else "INSUFFICIENT_DEMAND"
            if saturation < 0.99
            else "STEADY"
        )
        windows.append(
            {
                "start_seconds": begin - start_monotonic,
                "end_seconds": stop - start_monotonic,
                "state": state,
                "ready_backlog_fraction": saturation,
                "provider_reported_completed_tokens": known,
                "estimated_admitted_tokens": sum(row["tokens"] for row in sends if begin <= row["at"] < stop),
                "completed_utilization": known / policy.sustainable_tpm if not unknown else None,
                "failure_count": failures,
                "unknown_usage_attempts": unknown,
            }
        )
        stop += 10
    eligible = [row["completed_utilization"] for row in windows if row["state"] == "STEADY"]
    band_share = sum(0.90 <= value <= 0.95 for value in eligible) / len(eligible) if eligible else None
    enough = end_monotonic - start_monotonic >= 600
    median = statistics.median(eligible) if eligible else None
    band_passed = enough and not hard_violations and bool(eligible) and band_share is not None and band_share >= 0.90
    steady_target = median is not None and median >= policy.target_ratio
    measured = [row for row in completed if start_monotonic <= row["at"] < end_monotonic]
    reported = sum(
        row["usage_tokens"]
        for row in measured
        if row["outcome"] == "success" and row["usage_provenance"] == "provider_reported"
    )
    unknown_overall = sum(
        row["outcome"] == "success" and row["usage_provenance"] != "provider_reported" for row in measured
    )
    overall = (
        reported * 60 / ((end_monotonic - start_monotonic) * policy.sustainable_tpm) if not unknown_overall else None
    )
    run_backlog = _backlogged_fraction(demand_samples, start_monotonic, end_monotonic)
    failed_attempts = sum(row["outcome"] != "success" for row in measured)
    validated = (
        band_passed and steady_target and run_backlog is not None and run_backlog >= 0.99 and not failed_attempts
    )
    document_packets = [row["tokens"] for row in sends if row.get("task_kind") == "document"]
    return {
        "status": "PASS" if validated else "NOT_FEASIBLE" if eligible else "NOT_MEASURABLE",
        "whole_run_ready_backlog_fraction": run_backlog,
        "provider_error_attempts": failed_attempts,
        "band90to95_status": "PASS" if band_passed else "FAIL",
        "steady_median_target092_status": "AT_OR_ABOVE_TARGET"
        if steady_target
        else "BELOW_TARGET"
        if eligible
        else "NOT_MEASURABLE",
        "overall_target092_status": "NOT_MEASURABLE"
        if overall is None
        else "AT_OR_ABOVE_TARGET"
        if overall >= policy.target_ratio
        else "BELOW_TARGET",
        "overall_time_weighted_completed_utilization": overall,
        "overall_provider_reported_completed_tokens": reported,
        "overall_provider_reported_tpm": overall * policy.sustainable_tpm if overall is not None else None,
        "document_packet_tokens": {
            str(tokens): document_packets.count(tokens) for tokens in sorted(set(document_packets))
        },
        "document_packet_quantization_fraction_of_Q": math.gcd(*document_packets) / policy.sustainable_tpm
        if document_packets
        else None,
        "sustainable_tpm_fixed": policy.sustainable_tpm,
        "target_ratio": policy.target_ratio,
        "hard_ratio": policy.hard_ratio,
        "hard_admission_violations": hard_violations,
        "elapsed_seconds": end_monotonic - start_monotonic,
        "ten_minute_minimum_satisfied": enough,
        "windows": windows,
        "eligible_window_count": len(eligible),
        "band90to95_share": band_share,
        "eligible_utilization": _distribution(eligible) if eligible else None,
        "eligible_p10": sorted(eligible)[max(0, math.ceil(len(eligible) * 0.1) - 1)] if eligible else None,
        "eligible_p90": sorted(eligible)[max(0, math.ceil(len(eligible) * 0.9) - 1)] if eligible else None,
        "acceptance_rule": "600s,99%backlog,no errors/hard breaches,90%steady windows in band,steady median>=0.92",
        "queue_wait_ms": _distribution([row["queue_wait_ms"] for row in events if row["event"] == "reserved"])
        if any(row["event"] == "reserved" for row in events)
        else None,
    }


async def _finish_observers(stop: asyncio.Event, *tasks: asyncio.Task[Any]) -> list[str]:
    stop.set()
    errors = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, EmbeddingError):
            errors.append(result.code.value)
        elif isinstance(result, BaseException):
            errors.append(type(result).__name__[:64])
    return errors


async def observe_backlogged_run(
    *,
    governor: ProductionEmbeddingGovernor,
    process_one: Callable[[], Awaitable[bool]],
    demand_probe: Callable[[], Awaitable[bool]],
    duration_seconds: float = 600.0,
    query_probe: Callable[[], Awaitable[None]] | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Drive the caller's durable worker and independently sample its real eligible database backlog."""
    if duration_seconds < 600:
        raise ValueError("A sustained capacity proof requires at least600seconds")
    started = time.monotonic()
    events: list[dict[str, Any]] = governor.drain_events()
    events.append({"event": "ledger_snapshot", "at": started, "charges": governor.ledger_snapshot()})
    demand = []
    query_latencies = []
    failures: list[str] = []
    gpu_samples = []
    stop = asyncio.Event()

    async def sample() -> None:
        while not stop.is_set():
            demand.append({"at": time.monotonic(), "backlogged": await demand_probe()})
            events.extend(governor.drain_events())
            gpu_samples.append(await asyncio.to_thread(_gpu))
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1.0)

    async def queries() -> None:
        while not stop.is_set() and query_probe is not None:
            begin = time.monotonic()
            await query_probe()
            query_latencies.append((time.monotonic() - begin) * 1000)
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=10.0)

    sampler = asyncio.create_task(sample())
    query_task = asyncio.create_task(queries())
    try:
        while time.monotonic() < started + duration_seconds:
            if sampler.done():
                await sampler
            if query_task.done():
                await query_task
            if not await process_one():
                await asyncio.sleep(0.05)
    except EmbeddingError as error:
        failures.append(error.code.value)
    except asyncio.CancelledError:
        failures.append("CANCELLED")
    except Exception as error:
        failures.append(type(error).__name__[:64])
    finally:
        ended = time.monotonic()
        failures.extend(await _finish_observers(stop, sampler, query_task))
        events.extend(governor.drain_events())
    report = evaluate_capacity_run(
        governor.policy, events, start_monotonic=started, end_monotonic=ended, demand_samples=demand
    )
    report.update(
        {
            "governor": governor.summary(),
            "events": events,
            "demand_samples": demand,
            "query_latency_ms": _distribution(query_latencies) if query_latencies else None,
            "query_count": len(query_latencies),
            "errors": failures,
            "workload": "caller-owned real durable worker; independent persistent-ready-backlog probe",
            "gpu": {
                "sampled_device_peak_used_mib": max(row["used_mib"] for row in gpu_samples),
                "total_mib": gpu_samples[0]["total_mib"],
                "scope": "shared device-wide samples",
            }
            if gpu_samples
            else None,
            "post_send_wall_latency_ms": _distribution(
                [
                    row["post_send_duration_ms"]
                    for row in events
                    if row["event"] == "finished" and row.get("post_send_duration_ms") is not None
                ]
            )
            if any(row.get("post_send_duration_ms") is not None for row in events)
            else None,
        }
    )
    if failures:
        report["status"] = "FAIL"
    if output is not None:
        await asyncio.to_thread(_write_json, output, report)
    if "CANCELLED" in failures:
        raise asyncio.CancelledError
    return report


def main() -> int:
    """An explicit calibration flag is required before any local GPU traffic is dispatched."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--model-directory", type=Path, default=Path("A:/AI/TEI/qwen3-4b"))
    parser.add_argument("--endpoint", default=_DEFAULT_ENDPOINT)
    parser.add_argument("--container", default=_DEFAULT_CONTAINER)
    parser.add_argument("--output", type=Path, default=Path(".cache/workbench-capacity/calibration.json"))
    args = parser.parse_args()
    if not args.calibrate:
        parser.error("--calibrate explicitly authorizes the bounded real-model capacity experiment")
    try:
        _, policy, _ = asyncio.run(
            calibrate_capacity(
                directory=args.model_directory, endpoint=args.endpoint, container=args.container, output=args.output
            )
        )
    except EmbeddingError as error:
        print(json.dumps({"status": "FAIL", "code": error.code.value}))
        return 1
    print(json.dumps({"status": "MEASURED", "sustainable_tpm": policy.sustainable_tpm, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

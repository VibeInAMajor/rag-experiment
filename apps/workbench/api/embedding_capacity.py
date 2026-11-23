"""Measured deployment capacity, shared fair admission and durable rolling-window charges."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic, time
from typing import Any, Literal
from uuid import uuid4

from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.workbench.api.contracts import Identifier
from apps.workbench.api.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingProfile,
    EmbeddingReservation,
    EmbeddingRuntimeIdentity,
    UsageProvenance,
)
from apps.workbench.api.embedding_dispatch import _deployment_lease_path


class MeasuredEmbeddingCapacityPolicy(BaseModel):
    """A calibrated endpoint allowance; physical GPU sharing remains an explicit measurement condition."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    policy_id: Identifier = "measured-local-embedding"
    policy_revision: Identifier
    profile_id: Identifier
    profile_revision: Identifier
    profile_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    deployment_id: Identifier
    runtime_evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    calibration_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    capacity_source: Literal["local-saturation-benchmark"] = "local-saturation-benchmark"
    sustainable_tpm: int = Field(ge=1, le=100000000)
    sustainable_rpm: int = Field(ge=1, le=65536)
    measured_at_unix: float = Field(gt=0, allow_inf_nan=False)
    expires_at_unix: float = Field(gt=0, allow_inf_nan=False)
    target_ratio: float = Field(default=0.92, ge=0.92, le=0.92)
    hard_ratio: float = Field(default=0.95, ge=0.95, le=0.95)
    max_request_tokens: int = Field(default=8192, ge=1, le=32768)
    max_in_flight: Literal[1] = 1
    max_queued_packets: int = Field(default=32, ge=1, le=256)
    max_queued_tokens: int = Field(default=1048576, ge=1, le=8388608)
    max_workspace_queued_packets: int = Field(default=8, ge=1, le=64)
    max_requests_one_second: int = Field(default=16, ge=1, le=1024)
    max_requests_ten_seconds: int = Field(default=128, ge=1, le=16384)
    cooldown_seconds: float = Field(default=10.0, gt=0, le=120, allow_inf_nan=False)
    endpoint_ownership: Literal["exclusive-workbench-process"] = "exclusive-workbench-process"
    gpu_sharing: Literal["shared-observed-conditions"] = "shared-observed-conditions"

    @model_validator(mode="after")
    def _consistent_allowance(self) -> MeasuredEmbeddingCapacityPolicy:
        if not 0 < self.expires_at_unix - self.measured_at_unix <= 86400:
            raise ValueError("A measured allowance requires an explicit bounded validity period")
        if self.max_request_tokens > self.hard_token_budget:
            raise ValueError("A request must fit the independent hard rolling budget")
        if self.max_workspace_queued_packets > self.max_queued_packets:
            raise ValueError("Workspace queue bound must fit the shared queue")
        return self

    @property
    def target_tpm(self) -> float:
        """Apply the operating setpoint directly to measured Q, without a second hard-ratio scaling."""
        return self.sustainable_tpm * self.target_ratio

    @property
    def hard_token_budget(self) -> int:
        """Use integer arithmetic for the independent 95 percent rolling token ceiling."""
        return self.sustainable_tpm * 95 // 100

    @property
    def fingerprint(self) -> str:
        """Bind measured capacity and every scheduling setting to one immutable definition."""
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


@dataclass
class _Charge:
    reservation_id: str
    tokens: int
    task_kind: str
    workspace_id: str
    reserved_at: float
    deadline: float
    sent_at: float | None = None
    finished_at: float | None = None
    outcome: str | None = None
    usage_tokens: int | None = None
    usage_provenance: str = "unknown"


@dataclass
class _Waiter:
    identifier: str
    tokens: int
    task_kind: str
    workspace_id: str
    queued_at: float


def _rolling_tokens(charges: list[_Charge], now: float) -> int:
    return sum(
        row.tokens
        for row in charges
        if row.finished_at is None or (row.sent_at if row.sent_at is not None else row.reserved_at) > now - 60.0
    )


def _ledger_charge(fields: dict[str, Any]) -> _Charge:
    row = _Charge(**fields)
    times = (row.reserved_at, row.deadline, row.sent_at, row.finished_at)
    if (
        type(row.tokens) is not int
        or not 1 <= row.tokens <= 32768
        or row.task_kind not in {"query", "document"}
        or not isinstance(row.workspace_id, str)
        or not 1 <= len(row.workspace_id) <= 128
        or not isinstance(row.reservation_id, str)
        or not 1 <= len(row.reservation_id) <= 128
        or any(
            value is not None and (type(value) not in {int, float} or not math.isfinite(value) or value < 0)
            for value in times
        )
        or row.deadline <= row.reserved_at
        or (row.sent_at is not None and row.sent_at < row.reserved_at)
        or (row.finished_at is not None and row.finished_at < (row.sent_at or row.reserved_at))
        or row.outcome not in {None, "success", "failed", "ambiguous", "cancelled"}
        or (row.finished_at is None) != (row.outcome is None)
    ):
        raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
    return row


class ProductionEmbeddingGovernor:
    """Own one endpoint lease, persistent attempted-token ledger and bounded fair query/document queue."""

    def __init__(
        self,
        policy: MeasuredEmbeddingCapacityPolicy,
        *,
        profile: EmbeddingProfile,
        identity: EmbeddingRuntimeIdentity,
        lock_directory: Path | None = None,
        clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], float] = time,
    ) -> None:
        if (
            policy.profile_id != profile.profile_id
            or policy.profile_revision != profile.profile_revision
            or policy.profile_fingerprint != profile.fingerprint
            or policy.deployment_id != identity.deployment_id
            or policy.runtime_evidence_digest != identity.evidence_digest
            or policy.max_request_tokens != profile.max_batch_tokens
            or profile.model_digest != identity.model_digest
            or profile.tokenizer_digest != identity.tokenizer_digest
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        self._policy = policy
        self._clock = clock
        self._wall_clock = wall_clock
        self._lock_path = _deployment_lease_path(policy.deployment_id, lock_directory)
        self._lease = FileLock(self._lock_path, timeout=0, thread_local=False)
        self._ledger_path = self._lock_path.with_suffix(".capacity.json")
        self._condition = asyncio.Condition()
        self._lifecycle = asyncio.Lock()
        self._started = False
        self._closed = False
        self._blocked = False
        self._cooldown_until = 0.0
        self._next_token_at = 0.0
        self._next_request_at = 0.0
        self._charges: dict[str, _Charge] = {}
        self._queue: list[_Waiter] = []
        self._events: deque[dict[str, Any]] = deque(maxlen=65536)
        self._query_streak = 0
        self._last_workspace: dict[str, str] = {}
        self._ramp = 1.0
        self._last_recovery = 0.0
        self._consecutive_failures = 0
        self._attempts = self._successes = self._reported_tokens = self._proxy_tokens = self._unknown_usage = 0

    @property
    def policy(self) -> MeasuredEmbeddingCapacityPolicy:
        """Keep the calibrated denominator immutable for the lifetime of this owner."""
        return self._policy

    def _check_available(self) -> None:
        now = self._wall_clock()
        if (
            self._closed
            or self._blocked
            or not self._started
            or not self._lease.is_locked
            or now < self.policy.measured_at_unix - 5
            or now >= self.policy.expires_at_unix
        ):
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)

    def _acquire(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lease.acquire(timeout=0)

    def _read_ledger(self) -> None:
        if not self._ledger_path.exists():
            return
        if self._ledger_path.stat().st_size > 16777216:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        raw = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        recalibrated = (
            raw.get("calibration_digest") != self.policy.calibration_digest
            and self.policy.measured_at_unix > raw.get("recorded_at_unix", self.policy.measured_at_unix)
            and self._wall_clock() >= self.policy.measured_at_unix + 60
        )
        if (
            raw.get("schema_version") != 1
            or raw["deployment_id"] != self.policy.deployment_id
            or type(raw["requires_recalibration"]) is not bool
            or type(raw["last_monotonic"]) not in {int, float}
            or not math.isfinite(raw["last_monotonic"])
            or raw["last_monotonic"] < 0
            or (raw["last_monotonic"] > self._clock() + 1 and not recalibrated)
            or not isinstance(raw["charges"], list)
            or len(raw["charges"]) > 65536
        ):
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        self._blocked = raw["requires_recalibration"]
        for fields in raw["charges"]:
            row = _ledger_charge(fields)
            if row.reservation_id in self._charges:
                raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
            if row.finished_at is None:
                self._blocked = True
            self._charges[row.reservation_id] = row
        self._next_token_at = raw["next_token_at"]
        self._next_request_at = raw["next_request_at"]
        self._cooldown_until = raw["cooldown_until"]
        self._ramp = raw.get("effective_ramp", 1.0)
        self._last_recovery = raw.get("last_recovery", 0.0)
        self._consecutive_failures = raw.get("consecutive_failures", 0)
        if (
            any(
                type(value) not in {int, float} or not math.isfinite(value) or value < 0
                for value in (self._next_token_at, self._next_request_at, self._cooldown_until, self._last_recovery)
            )
            or type(self._ramp) not in {int, float}
            or not 0.5 <= self._ramp <= 1.0
            or type(self._consecutive_failures) is not int
            or not 0 <= self._consecutive_failures <= 65536
        ):
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        if recalibrated:
            self._charges.clear()
            self._blocked = False
            self._next_token_at = self._next_request_at = self._cooldown_until = 0.0
            self._ramp, self._last_recovery, self._consecutive_failures = 1.0, 0.0, 0

    def _write_ledger(self) -> None:
        self._prune()
        raw = {
            "schema_version": 1,
            "deployment_id": self.policy.deployment_id,
            "policy_fingerprint": self.policy.fingerprint,
            "calibration_digest": self.policy.calibration_digest,
            "recorded_at_unix": self._wall_clock(),
            "last_monotonic": self._clock(),
            "requires_recalibration": self._blocked,
            "next_token_at": self._next_token_at,
            "next_request_at": self._next_request_at,
            "cooldown_until": self._cooldown_until,
            "effective_ramp": self._ramp,
            "last_recovery": self._last_recovery,
            "consecutive_failures": self._consecutive_failures,
            "charges": [asdict(row) for row in self._charges.values()],
        }
        temporary = self._ledger_path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(raw, output, separators=(",", ":"), allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self._ledger_path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _persist(self) -> None:
        pending = asyncio.create_task(asyncio.to_thread(self._write_ledger))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            self._blocked = True
            await asyncio.to_thread(self._write_ledger)
            raise
        except (OSError, ValueError):
            self._blocked = True
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED) from None

    async def warm_up_async(self) -> None:
        """Acquire the exact same cross-process lease as qualification and restore conservative charges."""
        async with self._lifecycle:
            if self._started:
                self._check_available()
                return
            if self._closed:
                raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
            pending = asyncio.create_task(asyncio.to_thread(self._acquire))
            try:
                await asyncio.shield(pending)
                quiet = max(0.0, self.policy.measured_at_unix + 60 - self._wall_clock())
                if quiet:
                    await asyncio.sleep(quiet)
                await asyncio.to_thread(self._read_ledger)
                self._started = True
                self._check_available()
                await self._persist()
            except BaseException as error:
                with suppress(Timeout, OSError):
                    await pending
                self._lease.release()
                if isinstance(error, Timeout):
                    raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY) from None
                if isinstance(error, (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError)):
                    raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED) from None
                raise

    def _prune(self) -> None:
        cutoff = self._clock() - 60.0
        self._charges = {
            key: row
            for key, row in self._charges.items()
            if row.finished_at is None or (row.sent_at if row.sent_at is not None else row.reserved_at) > cutoff
        }

    def max_admissible_tokens(self) -> int:
        """Expose remaining rolling headroom for packet packing; reserve remains the authoritative check."""
        self._check_available()
        remaining = self.policy.hard_token_budget - _rolling_tokens(list(self._charges.values()), self._clock())
        return max(0, min(self.policy.max_request_tokens, remaining))

    def _selected(self) -> _Waiter | None:
        if not self._queue:
            return None
        ready = [row for row in self._queue if self._window_wait(tokens=row.tokens, now=self._clock()) <= 0]
        candidates = ready or self._queue
        queries = [row for row in candidates if row.task_kind == "query"]
        documents = [row for row in candidates if row.task_kind == "document"]
        candidates = queries if queries and (not documents or self._query_streak < 3) else documents
        previous = self._last_workspace.get(candidates[0].task_kind)
        return next((row for row in candidates if row.workspace_id != previous), candidates[0])

    def _window_wait(self, *, tokens: int, now: float) -> float:
        rows = list(self._charges.values())
        waits = [
            max(0.0, self._cooldown_until - now),
            max(0.0, self._next_token_at - now),
            max(0.0, self._next_request_at - now),
        ]
        if _rolling_tokens(rows, now) + tokens > self.policy.hard_token_budget:
            expirations = [
                max(0.001, (row.sent_at if row.sent_at is not None else row.reserved_at) + 60 - now)
                for row in rows
                if row.finished_at is not None
            ]
            waits.append(min(expirations, default=0.25))
        for seconds, limit in (
            (1, self.policy.max_requests_one_second),
            (10, self.policy.max_requests_ten_seconds),
            (60, self.policy.sustainable_rpm),
        ):
            recent = [row.sent_at for row in rows if row.sent_at is not None and row.sent_at > now - seconds]
            if len(recent) >= limit:
                waits.append(min(recent) + seconds - now)
        if sum(row.finished_at is None for row in rows) >= self.policy.max_in_flight:
            waits.append(0.25)
        return max(waits)

    def _validate_request(
        self,
        *,
        profile_id: str,
        profile_revision: str,
        deployment_id: str,
        task_kind: str,
        token_count: int,
        deadline: float,
        workspace_id: str,
    ) -> None:
        self._check_available()
        if (profile_id, profile_revision, deployment_id) != (
            self.policy.profile_id,
            self.policy.profile_revision,
            self.policy.deployment_id,
        ):
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        if task_kind not in {"query", "document"} or not workspace_id or len(workspace_id) > 128:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if type(token_count) is not int or not 1 <= token_count <= self.policy.max_request_tokens:
            raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
        if not math.isfinite(deadline) or deadline <= self._clock():
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)

    async def reserve(
        self,
        *,
        profile_id: str,
        profile_revision: str,
        deployment_id: str,
        task_kind: Literal["query", "document"],
        token_count: int,
        deadline: float,
        workspace_id: str = "development",
    ) -> EmbeddingReservation:
        """Wait within one bounded fair queue; account tokens before returning the send permission."""
        self._validate_request(
            profile_id=profile_id,
            profile_revision=profile_revision,
            deployment_id=deployment_id,
            task_kind=task_kind,
            token_count=token_count,
            deadline=deadline,
            workspace_id=workspace_id,
        )
        waiter = _Waiter(uuid4().hex, token_count, task_kind, workspace_id, self._clock())
        async with self._condition:
            if (
                len(self._queue) >= self.policy.max_queued_packets
                or sum(row.tokens for row in self._queue) + token_count > self.policy.max_queued_tokens
                or sum(row.workspace_id == workspace_id for row in self._queue)
                >= self.policy.max_workspace_queued_packets
            ):
                raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
            self._queue.append(waiter)
            try:
                return await self._wait_for_admission(waiter, deadline)
            finally:
                if waiter in self._queue:
                    self._queue.remove(waiter)
                self._condition.notify_all()

    async def _wait_for_admission(self, waiter: _Waiter, deadline: float) -> EmbeddingReservation:
        while True:
            self._check_available()
            now = self._clock()
            remaining = deadline - now
            if remaining <= 0:
                raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
            delay = self._window_wait(tokens=waiter.tokens, now=now)
            if self._selected() == waiter and delay <= 0:
                row = _Charge(waiter.identifier, waiter.tokens, waiter.task_kind, waiter.workspace_id, now, deadline)
                self._charges[row.reservation_id] = row
                self._query_streak = self._query_streak + 1 if waiter.task_kind == "query" else 0
                self._last_workspace[waiter.task_kind] = waiter.workspace_id
                self._events.append(
                    {
                        "event": "reserved",
                        "at": now,
                        "reservation_id": row.reservation_id,
                        "tokens": row.tokens,
                        "task_kind": row.task_kind,
                        "workspace_id": row.workspace_id,
                        "queue_wait_ms": (now - waiter.queued_at) * 1000,
                        "queue_depth": len(self._queue) - 1,
                    }
                )
                await self._persist()
                return EmbeddingReservation(reservation_id=row.reservation_id)
            if delay >= remaining:
                raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
            with suppress(TimeoutError):
                await asyncio.wait_for(self._condition.wait(), timeout=min(max(delay, 0.001), remaining, 0.25))

    def _owned(self, reservation: EmbeddingReservation) -> _Charge:
        row = self._charges.get(reservation.reservation_id)
        if row is None or row.finished_at is not None:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        return row

    async def mark_sent(self, reservation: EmbeddingReservation) -> None:
        """Revalidate held charges at the actual send time, including reservations older than 60 seconds."""
        async with self._condition:
            self._check_available()
            row = self._owned(reservation)
            now = self._clock()
            if row.sent_at is not None:
                raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
            if now >= row.deadline:
                raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
            if _rolling_tokens(list(self._charges.values()), now) > self.policy.hard_token_budget:
                raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
            row.sent_at = now
            # Retain the pacing phase across small disk/scheduler delays; idle periods never bank unbounded credit.
            token_base = self._next_token_at if 0 <= now - self._next_token_at <= 1.0 else now
            request_base = self._next_request_at if 0 <= now - self._next_request_at <= 1.0 else now
            self._next_token_at = token_base + row.tokens * 60 / (self.policy.target_tpm * self._ramp)
            self._next_request_at = request_base + 60 / self.policy.sustainable_rpm
            self._attempts += 1
            self._events.append(
                {
                    "event": "sent",
                    "at": now,
                    "tokens": row.tokens,
                    "reservation_id": row.reservation_id,
                    "task_kind": row.task_kind,
                    "workspace_id": row.workspace_id,
                }
            )
            await self._persist()

    async def finish(
        self,
        reservation: EmbeddingReservation,
        *,
        outcome: Literal["success", "failed", "ambiguous", "cancelled"],
        usage_tokens: int | None,
        usage_provenance: UsageProvenance,
        error_code: EmbeddingErrorCode | None = None,
    ) -> None:
        """Reconcile once, preserve attempted charges and quarantine uncertain remote execution."""
        async with self._condition:
            row = self._owned(reservation)
            if (
                outcome not in {"success", "failed", "ambiguous", "cancelled"}
                or usage_provenance not in {"provider_reported", "tokenizer_counted_proxy", "unknown"}
                or (usage_tokens is not None and (type(usage_tokens) is not int or usage_tokens < 0))
                or (usage_provenance == "unknown" and usage_tokens is not None)
                or (usage_provenance != "unknown" and usage_tokens is None)
                or (outcome == "success" and row.sent_at is None)
                or (error_code is not None and not isinstance(error_code, EmbeddingErrorCode))
            ):
                raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
            now = self._clock()
            row.finished_at, row.outcome = now, outcome
            row.usage_tokens, row.usage_provenance = usage_tokens, usage_provenance
            if row.sent_at is not None and outcome in {"ambiguous", "cancelled"}:
                self._blocked = True
            elif row.sent_at is not None and outcome != "success":
                self._consecutive_failures += 1
                delay = min(120.0, self.policy.cooldown_seconds * 2 ** min(self._consecutive_failures - 1, 6))
                self._cooldown_until = max(self._cooldown_until, now + delay)
                self._ramp = max(0.5, self._ramp * 0.8)
            elif outcome == "success" and now >= self._last_recovery + self.policy.cooldown_seconds:
                self._ramp = min(1.0, self._ramp + 0.05)
                self._last_recovery = now
                self._consecutive_failures = 0
            self._successes += int(outcome == "success")
            if outcome == "success" and usage_provenance == "provider_reported" and usage_tokens is not None:
                self._reported_tokens += usage_tokens
            elif outcome == "success" and usage_provenance == "tokenizer_counted_proxy" and usage_tokens is not None:
                self._proxy_tokens += usage_tokens
            else:
                self._unknown_usage += 1
            self._events.append(
                {
                    "event": "finished",
                    "at": now,
                    "reservation_id": row.reservation_id,
                    "tokens": row.tokens,
                    "usage_tokens": usage_tokens,
                    "usage_provenance": usage_provenance,
                    "outcome": outcome,
                    "error_code": error_code.value if error_code is not None else None,
                    "post_send_duration_ms": (now - row.sent_at) * 1000 if row.sent_at is not None else None,
                    "task_kind": row.task_kind,
                    "workspace_id": row.workspace_id,
                }
            )
            await self._persist()
            self._condition.notify_all()

    def drain_events(self) -> list[dict[str, Any]]:
        """Transfer bounded sanitized telemetry to an application-owned evidence sink."""
        result = list(self._events)
        self._events.clear()
        return result

    def ledger_snapshot(self) -> list[dict[str, Any]]:
        """Expose sanitized retained charges so an independent observer can verify overlapping windows."""
        return [asdict(row) for row in self._charges.values()]

    def summary(self) -> dict[str, Any]:
        """Keep measured provider completions, admission estimates and shared-GPU scope distinct."""
        return {
            "mode": "measured_production",
            "capacity_status": "NOT_QUALIFIED" if self._blocked else "MEASURED",
            "sustainable_tpm": self.policy.sustainable_tpm,
            "target_tpm": self.policy.target_tpm,
            "hard_token_budget": self.policy.hard_token_budget,
            "attempts_sent": self._attempts,
            "attempts_successful": self._successes,
            "provider_reported_tokens": self._reported_tokens,
            "tokenizer_counted_proxy_tokens": self._proxy_tokens,
            "unknown_usage_attempts": self._unknown_usage,
            "rolling_admitted_tokens": _rolling_tokens(list(self._charges.values()), self._clock()),
            "queue_depth": len(self._queue),
            "max_in_flight": self.policy.max_in_flight,
            "effective_ramp": self._ramp,
            "requires_recalibration": self._blocked,
            "global_physical_gpu_capacity_claimed": False,
        }

    async def close_async(self) -> None:
        """Persist final charges before releasing endpoint ownership; active work must reconcile first."""
        async with self._lifecycle:
            async with self._condition:
                if any(row.finished_at is None for row in self._charges.values()):
                    raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
                if self._started and self._lease.is_locked:
                    await self._persist()
                self._closed = True
                self._condition.notify_all()
            await asyncio.to_thread(self._lease.release)

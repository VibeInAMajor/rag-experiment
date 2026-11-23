"""TPM-owned qualification admission; production sustainable-capacity scheduling remains gated."""

import asyncio
import hashlib
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field

from apps.workbench.api.contracts import Identifier
from apps.workbench.api.embedding import EmbeddingError, EmbeddingErrorCode, EmbeddingReservation, UsageProvenance

_ROOT = Path(__file__).resolve().parents[3]


def _deployment_lease_path(deployment_id: str, lock_directory: Path | None) -> Path:
    directory = _ROOT / ".cache" / "workbench-embedding-admission" if lock_directory is None else lock_directory
    return directory / f"{hashlib.sha256(deployment_id.encode()).hexdigest()}.lock"


class QualificationCapacityPolicy(BaseModel):
    """A finite test allowance, never an estimate of sustainable or globally assigned TPM."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    profile_id: Identifier
    profile_revision: Identifier
    deployment_id: Identifier
    policy_id: Identifier = "local-embedding-qualification"
    policy_revision: Identifier = "qualification-budget-r1"
    max_attempts: int = Field(default=256, ge=1, le=4096)
    max_total_tokens: int = Field(default=250000, ge=1, le=10000000)
    max_request_tokens: int = Field(default=8192, ge=1, le=32768)
    max_duration_seconds: float = Field(default=600.0, gt=0, le=1800, allow_inf_nan=False)


@dataclass
class _Attempt:
    token_count: int
    deadline: float
    sent: bool = False
    finished: bool = False


class QualificationEmbeddingGovernor:
    """
    Share one finite query/document allowance and one Workbench deployment lease.

    This is the explicit TPM-001 J1 single-test exception. It neither estimates Q_TPM nor
    coordinates unrelated clients of a shared GPU endpoint. Production inference remains NOT_QUALIFIED.
    """

    def __init__(
        self,
        policy: QualificationCapacityPolicy,
        *,
        lock_directory: Path | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._policy = policy
        self._clock = clock
        self._lock_path = _deployment_lease_path(policy.deployment_id, lock_directory)
        self._lease = FileLock(self._lock_path, timeout=0, thread_local=False)
        self._started_at: float | None = None
        self._closed = False
        self._uncertain_execution = False
        self._lifecycle_lock = asyncio.Lock()
        self._attempts: dict[str, _Attempt] = {}
        self._active: str | None = None
        self._admitted_tokens = 0
        self._sent_attempts = 0
        self._finished_attempts = 0
        self._successful_attempts = 0
        self._reported_tokens = 0
        self._proxy_tokens = 0
        self._unknown_usage_attempts = 0

    def _acquire_lease(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lease.acquire(timeout=0)

    async def warm_up_async(self) -> None:
        """Acquire the cross-process Workbench test lease without implicit constructor I/O."""
        async with self._lifecycle_lock:
            await self._warm_up()

    async def _warm_up(self) -> None:
        if self._closed:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        if self._started_at is not None:
            return
        pending = asyncio.create_task(asyncio.to_thread(self._acquire_lease))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            with suppress(Timeout, OSError):
                await pending
            self._lease.release()
            raise
        except Timeout:
            raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY) from None
        except OSError:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED) from None
        self._started_at = self._clock()

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
        """Admit at most one bounded attempt; retries and both purposes spend the same budget."""
        now = self._clock()
        if not workspace_id:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if self._closed or self._uncertain_execution or self._started_at is None or not self._lease.is_locked:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        if (profile_id, profile_revision, deployment_id) != (
            self._policy.profile_id,
            self._policy.profile_revision,
            self._policy.deployment_id,
        ) or task_kind not in {"query", "document"}:
            raise EmbeddingError(EmbeddingErrorCode.IDENTITY_MISMATCH)
        if not math.isfinite(deadline) or deadline <= now:
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
        if now - self._started_at >= self._policy.max_duration_seconds:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        if type(token_count) is not int or not 1 <= token_count <= self._policy.max_request_tokens:
            raise EmbeddingError(EmbeddingErrorCode.REQUEST_TOO_LARGE)
        if self._active is not None:
            raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
        if (
            len(self._attempts) >= self._policy.max_attempts
            or self._admitted_tokens + token_count > self._policy.max_total_tokens
        ):
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        identifier = uuid4().hex
        self._attempts[identifier] = _Attempt(token_count=token_count, deadline=deadline)
        self._active = identifier
        self._admitted_tokens += token_count
        return EmbeddingReservation(reservation_id=identifier)

    def _owned_attempt(self, reservation: EmbeddingReservation) -> _Attempt:
        attempt = self._attempts.get(reservation.reservation_id)
        if attempt is None or attempt.finished or self._active != reservation.reservation_id:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        return attempt

    async def mark_sent(self, reservation: EmbeddingReservation) -> None:
        """Charge every dispatched attempt exactly once, including ambiguous paid failures."""
        attempt = self._owned_attempt(reservation)
        if attempt.sent:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        now = self._clock()
        if now >= attempt.deadline:
            raise EmbeddingError(EmbeddingErrorCode.TIMEOUT)
        if self._started_at is None or now - self._started_at >= self._policy.max_duration_seconds:
            raise EmbeddingError(EmbeddingErrorCode.NOT_QUALIFIED)
        attempt.sent = True
        self._sent_attempts += 1

    async def finish(
        self,
        reservation: EmbeddingReservation,
        *,
        outcome: Literal["success", "failed", "ambiguous", "cancelled"],
        usage_tokens: int | None,
        usage_provenance: UsageProvenance,
        error_code: EmbeddingErrorCode | None = None,
    ) -> None:
        """Reconcile once; attempted tokens are never refunded from the finite test allowance."""
        attempt = self._owned_attempt(reservation)
        if error_code is not None and not isinstance(error_code, EmbeddingErrorCode):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if outcome not in {"success", "failed", "ambiguous", "cancelled"}:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if usage_provenance not in {"provider_reported", "tokenizer_counted_proxy", "unknown"}:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if usage_tokens is not None and (type(usage_tokens) is not int or usage_tokens < 0):
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        if outcome == "success" and not attempt.sent:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_REQUEST)
        if usage_provenance == "unknown" and usage_tokens is not None:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        # A disconnected client cannot prove that the shared GPU stopped computing.
        if attempt.sent and outcome in {"ambiguous", "cancelled"}:
            self._uncertain_execution = True
        attempt.finished = True
        self._active = None
        self._finished_attempts += 1
        self._successful_attempts += int(outcome == "success")
        if usage_provenance == "provider_reported" and usage_tokens is not None:
            self._reported_tokens += usage_tokens
        elif usage_provenance == "tokenizer_counted_proxy" and usage_tokens is not None:
            self._proxy_tokens += usage_tokens
        else:
            self._unknown_usage_attempts += 1

    def summary(self) -> dict[str, str | int | bool]:
        """Report test accounting separately from unqualified production utilization."""
        return {
            "mode": "qualification_only",
            "production_capacity_status": "NOT_QUALIFIED",
            "global_external_share_confirmed": False,
            "max_in_flight": 1,
            "uncertain_execution": self._uncertain_execution,
            "attempts_reserved": len(self._attempts),
            "attempts_sent": self._sent_attempts,
            "attempts_finished": self._finished_attempts,
            "attempts_successful": self._successful_attempts,
            "admitted_token_estimates": self._admitted_tokens,
            "provider_reported_tokens": self._reported_tokens,
            "tokenizer_counted_proxy_tokens": self._proxy_tokens,
            "unknown_usage_attempts": self._unknown_usage_attempts,
        }

    async def close_async(self) -> None:
        """Release only an idle test owner; active/ambiguous work must be reconciled first."""
        async with self._lifecycle_lock:
            if self._active is not None:
                raise EmbeddingError(EmbeddingErrorCode.CAPACITY_BUSY)
            self._closed = True
            await asyncio.to_thread(self._lease.release)

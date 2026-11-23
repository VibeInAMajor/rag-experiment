"""The qualification exception shares a finite allowance without claiming production TPM."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from apps.workbench.api.embedding import EmbeddingError, EmbeddingErrorCode, EmbeddingReservation
from apps.workbench.api.embedding_dispatch import QualificationCapacityPolicy, QualificationEmbeddingGovernor


@dataclass
class _Clock:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now


def _policy(*, attempts: int = 4, tokens: int = 10) -> QualificationCapacityPolicy:
    return QualificationCapacityPolicy(
        profile_id="qualification-profile",
        profile_revision="qualification-r1",
        deployment_id="local-test-deployment",
        max_attempts=attempts,
        max_total_tokens=tokens,
        max_request_tokens=8,
        max_duration_seconds=10.0,
    )


async def _reserve(
    owner: QualificationEmbeddingGovernor,
    *,
    purpose: Literal["query", "document"] = "query",
    tokens: int = 3,
    deadline: float = 105.0,
) -> EmbeddingReservation:
    return await owner.reserve(
        profile_id="qualification-profile",
        profile_revision="qualification-r1",
        deployment_id="local-test-deployment",
        task_kind=purpose,
        token_count=tokens,
        deadline=deadline,
    )


async def _complete(owner: QualificationEmbeddingGovernor, reservation: EmbeddingReservation, *, tokens: int) -> None:
    await owner.mark_sent(reservation)
    await owner.finish(reservation, outcome="success", usage_tokens=tokens, usage_provenance="provider_reported")


@pytest.mark.asyncio
async def test_query_and_document_share_single_slot_and_exact_total_budget(tmp_path: Path) -> None:
    """Both purposes exhaust the same exact allowance without implying a production quota."""
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        query = await _reserve(owner)
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.CAPACITY_BUSY):
            await _reserve(owner, purpose="document")
        await _complete(owner, query, tokens=3)
        document = await _reserve(owner, purpose="document", tokens=7)
        await _complete(owner, document, tokens=7)
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
            await _reserve(owner, tokens=1)
        summary = owner.summary()
        assert summary["attempts_reserved"] == summary["attempts_sent"] == summary["attempts_finished"] == 2
        assert summary["admitted_token_estimates"] == summary["provider_reported_tokens"] == 10
        assert summary["production_capacity_status"] == "NOT_QUALIFIED"
        assert summary["global_external_share_confirmed"] is False
    finally:
        await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancelled", "ambiguous", "failed"])
async def test_sent_failures_retain_token_charge_and_finish_once(
    tmp_path: Path, outcome: Literal["cancelled", "ambiguous", "failed"]
) -> None:
    """Canceled or uncertain sends keep their full charge and cannot reconcile twice."""
    owner = QualificationEmbeddingGovernor(_policy(tokens=3), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        reservation = await _reserve(owner)
        await owner.mark_sent(reservation)
        await owner.finish(reservation, outcome=outcome, usage_tokens=None, usage_provenance="unknown")
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
            await owner.finish(reservation, outcome=outcome, usage_tokens=None, usage_provenance="unknown")
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
            await _reserve(owner, tokens=1)
        assert owner.summary()["admitted_token_estimates"] == 3
        assert owner.summary()["attempts_finished"] == 1
        assert owner.summary()["unknown_usage_attempts"] == 1
    finally:
        await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancelled", "ambiguous"])
async def test_uncertain_sent_work_disables_remaining_allowance(
    tmp_path: Path, outcome: Literal["cancelled", "ambiguous"]
) -> None:
    """A disconnected request may still occupy the GPU, so unused budget cannot admit another."""
    owner = QualificationEmbeddingGovernor(_policy(tokens=10), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        reservation = await _reserve(owner, tokens=1)
        await owner.mark_sent(reservation)
        await owner.finish(reservation, outcome=outcome, usage_tokens=None, usage_provenance="unknown")
        assert owner.summary()["admitted_token_estimates"] == 1
        assert owner.summary()["uncertain_execution"] is True
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
            await _reserve(owner, purpose="document", tokens=1)
        assert owner.summary()["attempts_reserved"] == 1
    finally:
        await owner.close_async()


@pytest.mark.asyncio
async def test_attempt_budget_bounds_unsent_failures_too(tmp_path: Path) -> None:
    """A caller cannot retry indefinitely by abandoning admitted work before send."""
    owner = QualificationEmbeddingGovernor(_policy(attempts=1), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        reservation = await _reserve(owner, tokens=1)
        await owner.finish(reservation, outcome="failed", usage_tokens=None, usage_provenance="unknown")
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
            await _reserve(owner, tokens=1)
        assert owner.summary()["attempts_reserved"] == 1
        assert owner.summary()["attempts_sent"] == 0
    finally:
        await owner.close_async()


@pytest.mark.asyncio
async def test_same_deployment_has_one_owner_and_idempotent_concurrent_warmup(tmp_path: Path) -> None:
    """Concurrent setup acquires one lease that fully releases for a subsequent owner."""
    first = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    second = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
        await _reserve(first)
    await asyncio.gather(first.warm_up_async(), first.warm_up_async(), first.warm_up_async())
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.CAPACITY_BUSY):
        await second.warm_up_async()
    await first.close_async()
    await first.close_async()
    await second.warm_up_async()
    await second.close_async()
    with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
        await first.warm_up_async()


@pytest.mark.asyncio
async def test_active_owner_cannot_release_lease_or_accept_forged_and_double_send(tmp_path: Path) -> None:
    """Ownership cannot be bypassed with invented handles, duplicate sends or premature close."""
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        reservation = await _reserve(owner)
        forged = EmbeddingReservation(reservation_id="forged-reservation")
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
            await owner.mark_sent(forged)
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.CAPACITY_BUSY):
            await owner.close_async()
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
            await owner.finish(reservation, outcome="success", usage_tokens=3, usage_provenance="provider_reported")
        await owner.mark_sent(reservation)
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.INVALID_REQUEST):
            await owner.mark_sent(reservation)
        await owner.finish(reservation, outcome="success", usage_tokens=3, usage_provenance="provider_reported")
    finally:
        await owner.close_async()


@pytest.mark.asyncio
async def test_request_and_run_deadlines_refuse_before_new_reservation(tmp_path: Path) -> None:
    """Expired caller deadlines and a spent run lifetime cannot admit new work."""
    clock = _Clock()
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=clock)
    await owner.warm_up_async()
    try:
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.TIMEOUT):
            await _reserve(owner, deadline=clock.now)
        clock.now = 110.0
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.NOT_QUALIFIED):
            await _reserve(owner, deadline=120.0)
        assert owner.summary()["attempts_reserved"] == 0
    finally:
        await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [0, -1, 9, True])
async def test_invalid_request_charge_never_spends_budget(tmp_path: Path, tokens: int) -> None:
    """A per-request bound and strict integer tokens apply before reservation accounting."""
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    try:
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.REQUEST_TOO_LARGE):
            await _reserve(owner, tokens=tokens)
        assert owner.summary()["attempts_reserved"] == 0
    finally:
        await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["profile_id", "profile_revision", "deployment_id"])
async def test_foreign_scope_cannot_spend_deployment_allowance(tmp_path: Path, field: str) -> None:
    """Admission is tied to the attested profile revision and deployment, not caller text."""
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=_Clock())
    await owner.warm_up_async()
    scope = {
        "profile_id": "qualification-profile",
        "profile_revision": "qualification-r1",
        "deployment_id": "local-test-deployment",
    }
    scope[field] = "other-scope"
    try:
        with pytest.raises(EmbeddingError, match=EmbeddingErrorCode.IDENTITY_MISMATCH):
            await owner.reserve(
                profile_id=scope["profile_id"],
                profile_revision=scope["profile_revision"],
                deployment_id=scope["deployment_id"],
                task_kind="query",
                token_count=1,
                deadline=105.0,
            )
        assert owner.summary()["attempts_reserved"] == 0
    finally:
        await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deadline", "sent_at", "expected"),
    [(101.0, 102.0, EmbeddingErrorCode.TIMEOUT), (120.0, 110.0, EmbeddingErrorCode.NOT_QUALIFIED)],
)
async def test_expired_reservation_cannot_be_sent_and_still_reconciles(
    tmp_path: Path, deadline: float, sent_at: float, expected: EmbeddingErrorCode
) -> None:
    """A reservation cannot outlive either its caller deadline or the bounded run lifetime."""
    clock = _Clock()
    owner = QualificationEmbeddingGovernor(_policy(), lock_directory=tmp_path, clock=clock)
    await owner.warm_up_async()
    try:
        reservation = await _reserve(owner, deadline=deadline)
        clock.now = sent_at
        with pytest.raises(EmbeddingError, match=expected):
            await owner.mark_sent(reservation)
        await owner.finish(reservation, outcome="failed", usage_tokens=None, usage_provenance="unknown")
        assert owner.summary()["attempts_sent"] == 0
        assert owner.summary()["admitted_token_estimates"] == 3
    finally:
        await owner.close_async()

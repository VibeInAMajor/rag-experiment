"""Independent deterministic safety checks for the measured shared embedding authority."""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from apps.workbench.api.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingProfile,
    EmbeddingRuntimeIdentity,
    UsageProvenance,
)
from apps.workbench.api.embedding_capacity import (
    MeasuredEmbeddingCapacityPolicy,
    ProductionEmbeddingGovernor,
    _Charge,
    _rolling_tokens,
)
from apps.workbench.api.embedding_dispatch import QualificationCapacityPolicy, QualificationEmbeddingGovernor


@dataclass
class _Clock:
    now: float = 100.0

    def __call__(self) -> float:
        return self.now


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="measured-profile",
        profile_revision="measured-r1",
        provider_adapter_id="tei-openai",
        model_id="Qwen/Qwen3-Embedding-4B",
        model_revision="a" * 40,
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision="native-counter-r1",
        dimensions=32,
        max_tokens=950,
        max_batch_tokens=950,
    )


def _identity() -> EmbeddingRuntimeIdentity:
    return EmbeddingRuntimeIdentity(
        deployment_id="measured-deployment",
        adapter_id="tei-openai",
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision="native-counter-r1",
        served_model_id="served-model",
        info_digest="d" * 64,
        runtime_revision="tei-1.9.4",
        evidence_digest="e" * 64,
    )


def _policy(**changes: Any) -> MeasuredEmbeddingCapacityPolicy:
    return MeasuredEmbeddingCapacityPolicy(
        **{
            "policy_revision": "measured-policy-r1",
            "profile_id": _profile().profile_id,
            "profile_revision": _profile().profile_revision,
            "profile_fingerprint": _profile().fingerprint,
            "deployment_id": _identity().deployment_id,
            "runtime_evidence_digest": _identity().evidence_digest,
            "calibration_digest": "f" * 64,
            "sustainable_tpm": 1000,
            "sustainable_rpm": 120,
            "measured_at_unix": 1000.0,
            "expires_at_unix": 4000.0,
            "max_request_tokens": 950,
            **changes,
        }
    )


def _owner(tmp_path: Path, clock: _Clock, **policy_changes: Any) -> ProductionEmbeddingGovernor:
    return ProductionEmbeddingGovernor(
        _policy(**policy_changes),
        profile=_profile(),
        identity=_identity(),
        lock_directory=tmp_path,
        clock=clock,
        wall_clock=lambda: 1101.0,
    )


async def _reserve(
    owner: ProductionEmbeddingGovernor,
    clock: _Clock,
    *,
    tokens: int = 100,
    purpose: Literal["query", "document"] = "document",
    workspace: str = "tenant-a",
    lifetime: float = 100.0,
) -> Any:
    return await owner.reserve(
        profile_id="measured-profile",
        profile_revision="measured-r1",
        deployment_id="measured-deployment",
        task_kind=purpose,
        token_count=tokens,
        deadline=clock.now + lifetime,
        workspace_id=workspace,
    )


async def _complete(owner: ProductionEmbeddingGovernor, reservation: Any, tokens: int) -> None:
    await owner.mark_sent(reservation)
    await owner.finish(reservation, outcome="success", usage_tokens=tokens, usage_provenance="provider_reported")


def test_independent_operating_target_and_integer_hard_limit() -> None:
    """The setpoint is 920, never the accidental double-scaled 874, for measured Q=1000."""
    policy = _policy()
    assert policy.target_tpm == 920.0
    assert policy.hard_token_budget == 950


@pytest.mark.parametrize(
    "changes",
    [
        {"sustainable_tpm": 0},
        {"target_ratio": 0.95},
        {"hard_ratio": 1.0},
        {"expires_at_unix": 900.0},
        {"max_request_tokens": 951},
    ],
)
def test_unknown_or_inconsistent_quota_is_not_dispatchable(changes: dict[str, Any]) -> None:
    """Missing evidence, invalid ratios and a packet above the rolling ceiling fail before any owner exists."""
    with pytest.raises(ValidationError):
        _policy(**changes)


@pytest.mark.parametrize("now,expected", [(159.999, 950), (160.0, 0), (160.001, 0)])
def test_true_sliding_window_exact_boundaries(now: float, expected: int) -> None:
    """A sent charge expires at exactly 60 seconds, without fixed-window reset bursts."""
    row = _Charge("charge", 950, "document", "tenant-a", 100.0, 200.0, sent_at=100.0, finished_at=101.0)
    assert _rolling_tokens([row], now) == expected


@pytest.mark.asyncio
async def test_old_inflight_reservation_is_held_and_refreshed_at_actual_send(tmp_path: Path) -> None:
    """A delayed send cannot use a charge which silently expired while its reservation remained held."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    reservation = await _reserve(owner, clock, tokens=900)
    clock.now = 161.0
    assert owner.max_admissible_tokens() == 50
    await _complete(owner, reservation, 900)
    assert owner.summary()["rolling_admitted_tokens"] == 900
    clock.now = 220.999
    assert owner.max_admissible_tokens() == 50
    clock.now = 221.0
    assert owner.max_admissible_tokens() == 950
    await owner.close_async()


@pytest.mark.asyncio
async def test_restart_cannot_refund_recent_sent_charges(tmp_path: Path) -> None:
    """A new process owner restores the same deployment's prior rolling ledger."""
    clock = _Clock()
    first = _owner(tmp_path, clock)
    await first.warm_up_async()
    await _complete(first, await _reserve(first, clock, tokens=900), 900)
    await first.close_async()
    second = _owner(tmp_path, clock)
    await second.warm_up_async()
    assert second.max_admissible_tokens() == 50
    await second.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ambiguous", "cancelled"])
async def test_sent_uncertainty_quarantines_owner_and_survives_restart(tmp_path: Path, outcome: Any) -> None:
    """Disconnects never return attempted quota or silently re-enable GPU execution in another process."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    reservation = await _reserve(owner, clock)
    await owner.mark_sent(reservation)
    await owner.finish(reservation, outcome=outcome, usage_tokens=None, usage_provenance="unknown")
    assert owner.summary()["rolling_admitted_tokens"] == 100
    with pytest.raises(EmbeddingError, match="NOT_QUALIFIED"):
        await _reserve(owner, clock)
    await owner.close_async()
    replacement = _owner(tmp_path, clock)
    with pytest.raises(EmbeddingError, match="NOT_QUALIFIED"):
        await replacement.warm_up_async()


@pytest.mark.asyncio
async def test_known_429_retains_charge_and_enforces_cooldown(tmp_path: Path) -> None:
    """A definitive overloaded response can recover after cooldown while its full estimate stays charged."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    reservation = await _reserve(owner, clock)
    await owner.mark_sent(reservation)
    await owner.finish(
        reservation,
        outcome="failed",
        usage_tokens=None,
        usage_provenance="unknown",
        error_code=EmbeddingErrorCode.RATE_LIMITED,
    )
    assert owner.summary()["rolling_admitted_tokens"] == 100
    with pytest.raises(EmbeddingError, match="TIMEOUT"):
        await _reserve(owner, clock, lifetime=1)
    clock.now += 10.0
    await _complete(owner, await _reserve(owner, clock), 100)
    assert owner.summary()["attempts_successful"] == 1
    assert owner.summary()["rolling_admitted_tokens"] == 200
    await owner.close_async()


@pytest.mark.asyncio
async def test_qualification_and_production_share_one_exclusive_deployment_lease(tmp_path: Path) -> None:
    """Neither another production owner nor the qualification exception can bypass an active endpoint owner."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    qualifier = QualificationEmbeddingGovernor(
        QualificationCapacityPolicy(
            profile_id="qualification", profile_revision="r1", deployment_id="measured-deployment"
        ),
        lock_directory=tmp_path,
    )
    try:
        with pytest.raises(EmbeddingError, match="CAPACITY_BUSY"):
            await qualifier.warm_up_async()
        with pytest.raises(EmbeddingError, match="CAPACITY_BUSY"):
            await _owner(tmp_path, clock).warm_up_async()
    finally:
        await qualifier.close_async()
        await owner.close_async()


@pytest.mark.asyncio
async def test_proxy_or_unknown_usage_never_becomes_provider_reported_tokens(tmp_path: Path) -> None:
    """Completed local counts and unavailable usage are explicit independent observations."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    cases: tuple[tuple[UsageProvenance, int | None], ...] = (("tokenizer_counted_proxy", 100), ("unknown", None))
    for provenance, usage in cases:
        reservation = await _reserve(owner, clock)
        await owner.mark_sent(reservation)
        await owner.finish(reservation, outcome="success", usage_tokens=usage, usage_provenance=provenance)
        clock.now += 10
    assert owner.summary()["provider_reported_tokens"] == 0
    assert owner.summary()["tokenizer_counted_proxy_tokens"] == 100
    assert owner.summary()["unknown_usage_attempts"] == 1
    await owner.close_async()


@pytest.mark.asyncio
async def test_fair_class_and_workspace_queue_prevents_ingestion_starvation(tmp_path: Path) -> None:
    """Continuous queued queries yield to a document after three sends, with workspace alternation."""
    clock = _Clock(time.monotonic())
    owner = ProductionEmbeddingGovernor(
        _policy(sustainable_tpm=6000000, sustainable_rpm=60000),
        profile=_profile(),
        identity=_identity(),
        lock_directory=tmp_path,
        wall_clock=lambda: 1101.0,
    )
    await owner.warm_up_async()
    initial = await _reserve(owner, clock, tokens=1)
    order = []

    async def queued(purpose: Literal["query", "document"], workspace: str) -> None:
        reservation = await _reserve(owner, _Clock(time.monotonic()), tokens=1, purpose=purpose, workspace=workspace)
        order.append((purpose, workspace))
        await _complete(owner, reservation, 1)

    tasks = [asyncio.create_task(queued("query", "tenant-a")) for _ in range(4)]
    tasks += [asyncio.create_task(queued("query", "tenant-b")), asyncio.create_task(queued("document", "tenant-c"))]
    await asyncio.sleep(0.01)
    await _complete(owner, initial, 1)
    await asyncio.gather(*tasks)
    assert [purpose for purpose, _ in order[:4]] == ["query", "query", "query", "document"]
    assert order[0][1] != order[1][1]
    await owner.close_async()


@pytest.mark.asyncio
async def test_profile_runtime_or_expired_measurement_cannot_enable_dispatch(tmp_path: Path) -> None:
    """Model policy edits and runtime restart evidence invalidate the calibrated allowance."""
    with pytest.raises(EmbeddingError, match="IDENTITY_MISMATCH"):
        ProductionEmbeddingGovernor(
            _policy(),
            profile=_profile().model_copy(update={"profile_revision": "changed"}),
            identity=_identity(),
            lock_directory=tmp_path,
        )
    owner = ProductionEmbeddingGovernor(
        _policy(), profile=_profile(), identity=_identity(), lock_directory=tmp_path, wall_clock=lambda: 4000.0
    )
    with pytest.raises(EmbeddingError, match="NOT_QUALIFIED"):
        await owner.warm_up_async()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("seconds", "limits"),
    [(1.0, {"max_requests_one_second": 1}), (10.0, {"max_requests_ten_seconds": 1}), (60.0, {"sustainable_rpm": 1})],
)
async def test_independent_rpm_and_microburst_boundaries(
    tmp_path: Path, seconds: float, limits: dict[str, int]
) -> None:
    """Token headroom does not bypass the independent one-second, ten-second or minute request bounds."""
    clock = _Clock()
    owner = _owner(tmp_path, clock, sustainable_tpm=6000000, **limits)
    await owner.warm_up_async()
    await _complete(owner, await _reserve(owner, clock, tokens=1), 1)
    clock.now += seconds - 0.001
    with pytest.raises(EmbeddingError, match="TIMEOUT"):
        await _reserve(owner, clock, tokens=1, lifetime=0.0001)
    clock.now = 100.0 + seconds
    await _complete(owner, await _reserve(owner, clock, tokens=1), 1)
    await owner.close_async()


@pytest.mark.asyncio
async def test_pending_queue_is_bounded_and_cancellation_does_not_create_paid_attempts(tmp_path: Path) -> None:
    """One workspace cannot fill unlimited pending memory, and abandoned queue entries release their slots."""
    clock = _Clock()
    owner = _owner(tmp_path, clock, max_workspace_queued_packets=2)
    await owner.warm_up_async()
    initial = await _reserve(owner, clock, tokens=1)
    tasks = [asyncio.create_task(_reserve(owner, clock, tokens=1)) for _ in range(2)]
    await asyncio.sleep(0.01)
    with pytest.raises(EmbeddingError, match="CAPACITY_BUSY"):
        await _reserve(owner, clock, tokens=1)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert owner.summary()["queue_depth"] == 0
    assert owner.summary()["attempts_sent"] == 0
    await _complete(owner, initial, 1)
    await owner.close_async()


@pytest.mark.asyncio
async def test_double_reconciliation_cannot_refund_or_recount_usage(tmp_path: Path) -> None:
    """An attempt is reconciled once and its admission charge remains intact until expiry."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    reservation = await _reserve(owner, clock, tokens=100)
    await _complete(owner, reservation, 100)
    with pytest.raises(EmbeddingError, match="INVALID_REQUEST"):
        await owner.finish(reservation, outcome="success", usage_tokens=100, usage_provenance="provider_reported")
    assert owner.summary()["provider_reported_tokens"] == 100
    assert owner.max_admissible_tokens() == 850
    await owner.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("tokens", [-1, True, 0, 32769])
async def test_corrupt_persistent_charges_fail_closed(tmp_path: Path, tokens: int) -> None:
    """A corrupt or negative replayed charge cannot increase available quota after restart."""
    clock = _Clock()
    first = _owner(tmp_path, clock)
    await first.warm_up_async()
    await _complete(first, await _reserve(first, clock), 100)
    await first.close_async()
    payload = json.loads(first._ledger_path.read_text(encoding="utf-8"))
    payload["charges"][0]["tokens"] = tokens
    first._ledger_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EmbeddingError, match="NOT_QUALIFIED"):
        await _owner(tmp_path, clock).warm_up_async()


@pytest.mark.asyncio
async def test_small_eligible_query_can_use_headroom_while_large_document_waits(tmp_path: Path) -> None:
    """An oversized head packet cannot stall a smaller eligible request in the shared fair queue."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    await _complete(owner, await _reserve(owner, clock, tokens=900), 900)
    clock.now = 159.0
    large = asyncio.create_task(_reserve(owner, clock, tokens=100))
    await asyncio.sleep(0.01)
    small = await asyncio.wait_for(_reserve(owner, clock, tokens=10, purpose="query"), timeout=0.5)
    large.cancel()
    await asyncio.gather(large, return_exceptions=True)
    await _complete(owner, small, 10)
    assert owner.summary()["rolling_admitted_tokens"] == 910
    await owner.close_async()


@pytest.mark.asyncio
async def test_fresh_calibration_holds_shared_lease_during_quiet_transition(tmp_path: Path) -> None:
    """A saturation benchmark cannot be followed by an empty-ledger production burst inside its last minute."""
    stamp = time.time()
    owner = ProductionEmbeddingGovernor(
        _policy(measured_at_unix=stamp, expires_at_unix=stamp + 3600),
        profile=_profile(),
        identity=_identity(),
        lock_directory=tmp_path,
    )
    pending = asyncio.create_task(owner.warm_up_async())
    await asyncio.sleep(0.03)
    assert not pending.done()
    qualifier = QualificationEmbeddingGovernor(
        QualificationCapacityPolicy(
            profile_id="qualification", profile_revision="r1", deployment_id="measured-deployment"
        ),
        lock_directory=tmp_path,
    )
    with pytest.raises(EmbeddingError, match="CAPACITY_BUSY"):
        await qualifier.warm_up_async()
    pending.cancel()
    await asyncio.gather(pending, return_exceptions=True)
    await qualifier.warm_up_async()
    await qualifier.close_async()


@pytest.mark.asyncio
async def test_only_new_successful_capacity_evidence_can_clear_persistent_quarantine(tmp_path: Path) -> None:
    """A later calibrated policy and completed quiet minute permit recovery without deleting the ledger."""
    clock = _Clock()
    owner = _owner(tmp_path, clock)
    await owner.warm_up_async()
    reservation = await _reserve(owner, clock)
    await owner.mark_sent(reservation)
    await owner.finish(reservation, outcome="ambiguous", usage_tokens=None, usage_provenance="unknown")
    await owner.close_async()
    clock.now = 200.0
    recovered = ProductionEmbeddingGovernor(
        _policy(calibration_digest="1" * 64, measured_at_unix=1200.0),
        profile=_profile(),
        identity=_identity(),
        lock_directory=tmp_path,
        clock=clock,
        wall_clock=lambda: 1301.0,
    )
    await recovered.warm_up_async()
    await _complete(recovered, await _reserve(recovered, clock), 100)
    assert recovered.summary()["requires_recalibration"] is False
    assert recovered.summary()["rolling_admitted_tokens"] == 100
    await recovered.close_async()

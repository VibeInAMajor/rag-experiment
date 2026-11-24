"""Synthetic telemetry tests never substitute for the separately gated measured ten-minute run."""

from typing import Any

from apps.workbench.embedding.embedding_capacity import MeasuredEmbeddingCapacityPolicy
from scripts.workbench_embedding_capacity_benchmark import evaluate_capacity_run


def _policy() -> MeasuredEmbeddingCapacityPolicy:
    return MeasuredEmbeddingCapacityPolicy(
        policy_revision="simulation-r1",
        profile_id="simulated-profile",
        profile_revision="r1",
        profile_fingerprint="a" * 64,
        deployment_id="simulated-deployment",
        runtime_evidence_digest="b" * 64,
        calibration_digest="c" * 64,
        sustainable_tpm=100000,
        sustainable_rpm=120,
        measured_at_unix=1000.0,
        expires_at_unix=2000.0,
        max_request_tokens=32768,
    )


def _events(tokens: int = 1534) -> list[dict[str, Any]]:
    result = []
    for index in range(600):
        base = {
            "reservation_id": f"simulation-{index}",
            "tokens": tokens,
            "task_kind": "document",
            "workspace_id": "simulated-tenant",
        }
        result.extend(
            [
                {**base, "event": "reserved", "at": float(index), "queue_wait_ms": 0.0},
                {**base, "event": "sent", "at": index + 0.1},
                {
                    **base,
                    "event": "finished",
                    "at": index + 0.5,
                    "outcome": "success",
                    "usage_tokens": tokens,
                    "usage_provenance": "provider_reported",
                },
            ]
        )
    return result


def _evaluate(events: list[dict[str, Any]], *, backlogged: bool = True) -> dict[str, Any]:
    return evaluate_capacity_run(
        _policy(),
        events,
        start_monotonic=0.0,
        end_monotonic=600.0,
        demand_samples=[{"at": float(index), "backlogged": backlogged} for index in range(601)],
    )


def test_simulated_above_target_trace_has_independent_admission_and_completion_proof() -> None:
    """A genuinely measured equivalent trace would need both safe arrivals and at least the fixed target."""
    report = _evaluate(_events())
    assert report["status"] == "PASS"
    assert report["hard_admission_violations"] == []
    assert report["eligible_window_count"] == 55
    assert report["overall_time_weighted_completed_utilization"] == 0.9204
    assert report["steady_median_target092_status"] == "AT_OR_ABOVE_TARGET"


def test_setting_target092_does_not_make_below_target_realized_band_trace_pass() -> None:
    """The90..95band test remains separate from actually reaching the92percent median setpoint."""
    report = _evaluate(_events(tokens=1520))
    assert report["band90to95_status"] == "PASS"
    assert report["status"] == "NOT_FEASIBLE"
    assert report["steady_median_target092_status"] == "BELOW_TARGET"
    assert report["overall_time_weighted_completed_utilization"] == 0.912


def test_source_starved_windows_are_visible_and_cannot_claim_saturation() -> None:
    """Even successful model traffic cannot prove the utilization SLO without independent ready backlog."""
    report = _evaluate(_events(), backlogged=False)
    assert report["status"] == "NOT_MEASURABLE"
    assert report["eligible_window_count"] == 0
    assert {row["state"] for row in report["windows"]} == {"INSUFFICIENT_DEMAND"}


def test_unknown_provider_usage_never_becomes_numeric_completed_utilization() -> None:
    """Locally estimated tokens cannot populate successful provider-reported window metrics."""
    events = _events()
    for row in events:
        if row["event"] == "finished":
            row["usage_provenance"], row["usage_tokens"] = "unknown", None
    report = _evaluate(events)
    assert report["status"] == "NOT_MEASURABLE"
    assert report["overall_time_weighted_completed_utilization"] is None
    assert all(row["completed_utilization"] is None for row in report["windows"])


def test_old_unreconciled_reservation_still_counts_towards_every_admission() -> None:
    """An independent observer catches the long-held-reservation bypass even after its send window expired."""
    events = [
        {"event": "reserved", "at": -100.0, "reservation_id": "held", "tokens": 95000, "queue_wait_ms": 0.0},
        {"event": "reserved", "at": 0.0, "reservation_id": "extra", "tokens": 1, "queue_wait_ms": 0.0},
    ]
    report = _evaluate(events)
    assert report["hard_admission_violations"] == [
        {"at": 0.0, "event": "reserved", "estimated_tokens_including_held": 95001}
    ]


def test_replayed_ledger_snapshot_is_included_in_independent_window_guard() -> None:
    """Starting observation in a replacement process cannot make its prior retained charges invisible."""
    events = [
        {
            "event": "ledger_snapshot",
            "at": 0.0,
            "charges": [
                {"reservation_id": "prior", "tokens": 95000, "sent_at": -1.0, "reserved_at": -2.0, "finished_at": -0.5}
            ],
        },
        {"event": "reserved", "at": 0.1, "reservation_id": "extra", "tokens": 1, "queue_wait_ms": 0.0},
    ]
    assert _evaluate(events)["hard_admission_violations"][0]["estimated_tokens_including_held"] == 95001

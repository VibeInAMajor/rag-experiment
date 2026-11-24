"""Integrity guards of the explicit real-model dense evaluator."""

from copy import deepcopy
from typing import Any

import pytest

from scripts.workbench_dense_evaluate import _audit_response, _distribution, _http_fixture
from scripts.workbench_embedding_evaluate import EvaluationIntegrityError


def test_dense_fixture_retains_originals_labels_and_required_counts() -> None:
    """The HTTP authorization adaptation changes only the main workspace identity."""
    fixture = _http_fixture()
    assert fixture.workspace_id == "development"
    assert len(fixture.queries) >= 30
    assert {query.language for query in fixture.queries} == {"en", "ru", "uk"}
    assert (
        sum(len(source.chunks) for source in fixture.sources if source.active and source.workspace_id == "development")
        >= 100
    )
    assert any(source.workspace_id != fixture.workspace_id for source in fixture.sources)
    assert any(not source.active for source in fixture.sources)


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")], [-1.0]])
def test_timing_distribution_refuses_missing_or_fabricated_values(values: list[float]) -> None:
    """Missing samples cannot become zero-latency performance claims."""
    with pytest.raises(EvaluationIntegrityError):
        _distribution(values)


def test_timing_distribution_uses_declared_nearest_rank_percentiles() -> None:
    """The report retains sample counts and ordinary measured percentile boundaries."""
    assert _distribution([float(value) for value in range(1, 101)]) == {
        "samples": 100,
        "min": 1.0,
        "p50": 50.0,
        "p95": 95.0,
        "max": 100.0,
    }


def _response() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    oracle = [{"chunk_id": "chunk", "source_id": "source", "source_version_id": "version", "score": 0.125}]
    return {
        "trace_id": "trace",
        "run_id": "run",
        "mode": "live",
        "results": [{**oracle[0], "rank": 1, "score_type": "cosine_distance"}],
    }, oracle


@pytest.mark.parametrize(
    "field,value",
    [
        ("chunk_id", "foreign"),
        ("source_id", "foreign"),
        ("source_version_id", "retired"),
        ("score", 0.9),
        ("score_type", "postgres_ts_rank_cd"),
        ("rank", 2),
    ],
)
def test_sql_oracle_refuses_result_identity_distance_and_semantics_drift(field: str, value: Any) -> None:
    """Every public hit must agree with independent exact SQL identities and raw distance."""
    payload, oracle = _response()
    payload["results"][0][field] = value
    with pytest.raises(EvaluationIntegrityError):
        _audit_response(payload, oracle, trace_id="trace")


def test_sql_oracle_checks_trace_count_and_zero_distance() -> None:
    """Model-request trace and real zero distances are preserved without percentage conversion."""
    payload, oracle = _response()
    payload["results"][0]["score"] = oracle[0]["score"] = 0.0
    _audit_response(payload, oracle, trace_id="trace")
    with pytest.raises(EvaluationIntegrityError):
        _audit_response(payload, oracle, trace_id="different")
    extra = deepcopy(payload)
    extra["results"].append(extra["results"][0])
    with pytest.raises(EvaluationIntegrityError):
        _audit_response(extra, oracle, trace_id="trace")

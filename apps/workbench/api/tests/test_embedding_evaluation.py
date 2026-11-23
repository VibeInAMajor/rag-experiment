"""Objective retrieval scores cannot replace original-source, generation or tenant verification."""

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from apps.workbench.api.embedding import (
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.api.embedding_jobs import EmbeddingCoverage, PersistedEmbeddingHit
from scripts.workbench_embedding_backfill import BackfillRuntime
from scripts.workbench_embedding_evaluate import (
    EvaluationFixture,
    EvaluationIntegrityError,
    EvaluationQuery,
    _disposable_evaluation_dsn,
    evaluate_persisted_vectors,
    evaluate_query,
    evaluate_retrieval,
    load_evaluation_fixture,
    score_ranking,
)

_PROFILE = "c" * 64


def _hit(fixture: EvaluationFixture, chunk_id: str, *, distance: float = 0.1) -> PersistedEmbeddingHit:
    source, chunk = fixture.chunk_index()[chunk_id]
    return PersistedEmbeddingHit(
        workspace_id=source.workspace_id,
        source_id=source.source_id,
        version_id=source.version_id,
        chunk_id=chunk.chunk_id,
        content=chunk.content,
        content_hash=chunk.content_hash,
        source_content_hash=source.content_hash,
        input_hash=hashlib.sha256(unicodedata.normalize("NFC", chunk.content).encode()).hexdigest(),
        profile_fingerprint=_PROFILE,
        index_generation=7,
        distance=distance,
    )


def test_fixed_fixture_has_real_ground_truth_and_negative_cohorts() -> None:
    """Prevent accidental dilution of the 100-plus-chunk multilingual/source-isolation cohort."""
    fixture = load_evaluation_fixture()
    main = [source for source in fixture.sources if source.workspace_id == fixture.workspace_id]
    assert sum(len(source.chunks) for source in main if source.active) == 102
    assert sum(len(source.chunks) for source in main if not source.active) == 12
    assert sum(len(source.chunks) for source in fixture.sources if source.workspace_id != fixture.workspace_id) == 12
    assert len(fixture.queries) == 52
    assert sum(query.cohort == "cross_language" for query in fixture.queries) == 12
    assert sum(query.cohort == "no_answer" for query in fixture.queries) == 6
    assert {source.language for source in fixture.sources} == {"en", "ru", "uk", "code"}


def test_known_ranking_distinguishes_partial_context_from_primary_evidence() -> None:
    """A related support passage at rank one is not direct evidence for the requested fact."""
    relevance = {"primary": 3, "support": 1}
    first = score_ranking(relevance, ["support", "negative", "primary"], cutoff=1)
    assert first["recall"] == 0.5 and first["primary_recall"] == 0.0
    assert first["reciprocal_rank"] == 1.0
    assert first["ndcg"] == pytest.approx(1 / 7)
    complete = score_ranking(relevance, ["support", "negative", "primary"], cutoff=3)
    assert complete["recall"] == complete["primary_recall"] == 1.0
    assert complete["ndcg"] == pytest.approx((1 + 7 / 2) / (7 + 1 / math.log2(3)))
    delayed = score_ranking({"primary": 3}, ["negative", "primary"], cutoff=10)
    assert delayed["reciprocal_rank"] == 0.5


@pytest.mark.parametrize("ranking", [["same", "same"], ["a"]])
def test_invalid_rankings_are_not_scored(ranking: list[str]) -> None:
    """Duplicate candidates and invalid cutoffs cannot inflate recall or reciprocal rank."""
    with pytest.raises(EvaluationIntegrityError, match="INVALID_EVALUATION_RANKING"):
        score_ranking({"same": 3}, ranking, cutoff=1 if len(ranking) > 1 else 0)


def test_no_answer_forced_neighbor_is_not_called_true_or_abstained() -> None:
    """Nearest-neighbor retrieval always returning a candidate is reported without a truth threshold."""
    fixture = load_evaluation_fixture()
    query = next(query for query in fixture.queries if query.cohort == "no_answer")
    chunk = fixture.sources[0].chunks[0]
    result = evaluate_query(
        fixture, query, [_hit(fixture, chunk.chunk_id)], profile_fingerprint=_PROFILE, index_generation=7
    )
    assert result["forced_neighbors_for_no_answer"] == 1
    assert result["top_similarity"] == pytest.approx(0.9)
    assert all(value is None for value in result["metrics"]["10"].values())


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("workspace_id", "another-workspace", "CROSS_WORKSPACE_EVALUATION_RESULT"),
        ("version_id", "superseded-version", "STALE_SOURCE_EVALUATION_RESULT"),
        ("content", "fabricated source text", "CHUNK_CONTENT_EVALUATION_MISMATCH"),
        ("content_hash", "b" * 64, "CHUNK_CONTENT_EVALUATION_MISMATCH"),
        ("source_content_hash", "b" * 64, "ORIGINAL_SOURCE_EVALUATION_MISMATCH"),
        ("input_hash", "b" * 64, "MODEL_INPUT_EVALUATION_MISMATCH"),
        ("profile_fingerprint", "b" * 64, "GENERATION_PROFILE_EVALUATION_MISMATCH"),
        ("index_generation", 8, "GENERATION_PROFILE_EVALUATION_MISMATCH"),
        ("distance", math.nan, "INVALID_EVALUATION_DISTANCE_ORDER"),
    ],
)
def test_provenance_mismatch_fails_before_quality_score(field: str, value: Any, code: str) -> None:
    """High similarity cannot conceal changed originals, wrong versions or foreign model state."""
    fixture = load_evaluation_fixture()
    query = fixture.queries[0]
    hit = _hit(fixture, next(iter(query.relevance))).model_copy(update={field: value})
    with pytest.raises(EvaluationIntegrityError, match=code):
        evaluate_query(fixture, query, [hit], profile_fingerprint=_PROFILE, index_generation=7)


@pytest.mark.parametrize("foreign", [True, False])
def test_existing_foreign_and_superseded_fixture_chunks_are_forbidden(foreign: bool) -> None:
    """Known fixture identities remain forbidden when tenant or active-version provenance is wrong."""
    fixture = load_evaluation_fixture()
    source = next(
        source
        for source in fixture.sources
        if (source.workspace_id != fixture.workspace_id if foreign else not source.active)
    )
    hit = _hit(fixture, source.chunks[0].chunk_id)
    code = "CROSS_WORKSPACE_EVALUATION_RESULT" if foreign else "STALE_SOURCE_EVALUATION_RESULT"
    with pytest.raises(EvaluationIntegrityError, match=code):
        evaluate_query(fixture, fixture.queries[0], [hit], profile_fingerprint=_PROFILE, index_generation=7)


def test_malformed_original_fixture_is_redacted(tmp_path: Path) -> None:
    """A corrupted source oracle is rejected offline without leaking its contents or path."""
    fixture = load_evaluation_fixture().model_dump(mode="json")
    fixture["sources"][0]["original"] = "private malformed oracle"
    target = tmp_path / "fixture.json"
    target.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(EvaluationIntegrityError, match="INVALID_EVALUATION_FIXTURE") as failure:
        load_evaluation_fixture(target)
    assert "private" not in str(failure.value) and str(target) not in str(failure.value)


@pytest.mark.asyncio
async def test_report_is_objective_grouped_and_does_not_expose_raw_inputs_or_vectors() -> None:
    """The same scorer covers all cohorts while keeping no-answer and primary-evidence limits explicit."""
    fixture = load_evaluation_fixture()

    async def search(query: EvaluationQuery, limit: int) -> tuple[PersistedEmbeddingHit, ...]:
        assert limit == 10
        selected = list(query.relevance) or [fixture.sources[0].chunks[0].chunk_id]
        return tuple(_hit(fixture, identifier, distance=0.1 + index * 0.1) for index, identifier in enumerate(selected))

    report = await evaluate_retrieval(fixture, search, profile_fingerprint=_PROFILE)
    assert report["overall"]["queries"] == 52
    assert report["overall"]["answerable_queries"] == 46
    assert report["overall"]["metrics"]["5"]["recall"] == 1.0
    assert report["overall"]["metrics"]["5"]["primary_recall"] == 1.0
    assert report["overall"]["no_answer_with_forced_neighbors"] == 6
    assert report["groups"]["cohort:cross_language"]["answerable_queries"] == 12
    assert report["answer_generation"] == "NOT_IMPLEMENTED"
    assert report["overall"]["abstention_status"] == "NOT_IMPLEMENTED_RAW_NEAREST_NEIGHBORS"
    wire = json.dumps(report)
    assert fixture.sources[0].original not in wire and fixture.queries[0].text not in wire
    assert '"vectors"' not in wire and '"content"' not in wire


@pytest.mark.asyncio
async def test_generation_drift_during_evaluation_never_produces_a_pass() -> None:
    """Results from two persisted generations cannot be combined into a single scored run."""
    fixture = load_evaluation_fixture()
    calls = 0

    async def search(query: EvaluationQuery, limit: int) -> tuple[PersistedEmbeddingHit, ...]:
        nonlocal calls
        assert limit == 10
        calls += 1
        return (_hit(fixture, next(iter(query.relevance))).model_copy(update={"index_generation": 7 + int(calls > 1)}),)

    with pytest.raises(EvaluationIntegrityError, match="GENERATION_PROFILE_EVALUATION_MISMATCH"):
        await evaluate_retrieval(fixture, search, profile_fingerprint=_PROFILE)


class _Counter:
    counter_revision = "evaluation-test-counter-r1"

    def count_tokens(self, text: str) -> int:
        return len(text)


def _runtime(fixture: EvaluationFixture, *, proxy_usage: bool = False) -> BackfillRuntime:
    runtime = Mock(spec=BackfillRuntime)
    runtime.profile = EmbeddingProfile(
        profile_id="eval-profile",
        profile_revision="eval-profile-r1",
        provider_adapter_id="offline-test",
        model_id="offline-test",
        model_revision="a" * 40,
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision=_Counter.counter_revision,
        dimensions=32,
    )
    runtime.counter = _Counter()
    runtime.adapter = Mock()
    runtime.persistence = Mock()
    runtime.governor = Mock()
    runtime.governor.summary.return_value = {"mode": "offline-test"}
    coverage = EmbeddingCoverage(
        workspace_id=fixture.workspace_id,
        profile_id=runtime.profile.profile_id,
        profile_revision=runtime.profile.profile_revision,
        profile_fingerprint=runtime.profile.fingerprint,
        index_generation=7,
        eligible_active_chunks=102,
        ready_embeddings=102,
        stale_embeddings=0,
        coverage_fraction=1.0,
        ready=True,
    )
    runtime.persistence.embedding_coverage = AsyncMock(return_value=coverage)
    cases = iter(fixture.queries)

    async def embed(request: EmbeddingRequest) -> Any:
        prepared = prepare_embedding_request(runtime.profile, request, runtime.counter)
        return validate_embedding_batch(
            runtime.profile,
            request,
            prepared,
            vectors=[(1.0, *([0.0] * 31))],
            usage_tokens=sum(item.token_count for item in prepared),
            usage_provenance="tokenizer_counted_proxy" if proxy_usage else "provider_reported",
            duration_ms=1.0,
        )

    async def search(
        context: Any, profile: EmbeddingProfile, vector: Any, *, limit: int
    ) -> tuple[PersistedEmbeddingHit, ...]:
        assert context.workspace_id == fixture.workspace_id and profile == runtime.profile
        assert len(vector) == 32 and limit == 10
        case = next(cases)
        identifiers = list(case.relevance) or [fixture.sources[0].chunks[0].chunk_id]
        return tuple(
            _hit(fixture, identifier, distance=0.1 + index * 0.1).model_copy(
                update={"profile_fingerprint": profile.fingerprint}
            )
            for index, identifier in enumerate(identifiers)
        )

    runtime.adapter.embed = AsyncMock(side_effect=embed)
    runtime.persistence.exact_embedding_search = AsyncMock(side_effect=search)
    return runtime


@pytest.mark.asyncio
async def test_live_composition_uses_shared_runtime_queries_then_actual_persistence_seam() -> None:
    """The CLI composition uses its injected owner/adapter and exact SQL seam, without a second client."""
    fixture = load_evaluation_fixture()
    runtime = _runtime(fixture)
    result = await evaluate_persisted_vectors(runtime, fixture)
    assert result["status"] == "EVALUATED"
    assert result["overall"]["metrics"]["10"]["mrr"] == 1.0
    assert len(result["query_embeddings"]) == 52
    assert result["query_provider_reported_tokens"] > 0
    assert result["production_trust_established"] is False


@pytest.mark.asyncio
async def test_query_proxy_usage_cannot_be_relabelled_provider_reported() -> None:
    """A provider-side count must actually be present before the quality report uses that provenance."""
    fixture = load_evaluation_fixture()
    with pytest.raises(EvaluationIntegrityError, match="QUERY_EMBEDDING_EVALUATION_MISMATCH"):
        await evaluate_persisted_vectors(_runtime(fixture, proxy_usage=True), fixture)


@pytest.mark.parametrize(
    ("dsn", "allowed"),
    [
        pytest.param("dbname=rag_test_quality host=127.0.0.1", True, id="disposable"),
        pytest.param("dbname=workbench host=127.0.0.1", False, id="application-database"),
        pytest.param("not-a-connection-string", False, id="malformed"),
    ],
)
def test_live_evaluation_database_guard_is_local_explicit_and_redacted(
    monkeypatch: pytest.MonkeyPatch, dsn: str, allowed: bool
) -> None:
    """Fixture setup refuses ordinary databases and malformed credentials before any connection opens."""
    monkeypatch.setenv("WORKBENCH_EVALUATION_TEST_DSN", dsn)
    if allowed:
        assert _disposable_evaluation_dsn("WORKBENCH_EVALUATION_TEST_DSN") == dsn
    else:
        with pytest.raises(EvaluationIntegrityError) as error:
            _disposable_evaluation_dsn("WORKBENCH_EVALUATION_TEST_DSN")
        assert dsn not in str(error.value)

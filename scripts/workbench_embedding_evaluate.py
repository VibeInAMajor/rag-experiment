"""Objective exact-retrieval evaluation against fixed originals; no generative model judge."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from apps.workbench.contracts.schemas import Identifier
from apps.workbench.embedding.embedding import (
    EmbeddingError,
    EmbeddingItem,
    EmbeddingRequest,
    prepare_embedding_request,
)
from apps.workbench.embedding.embedding_jobs import PersistedEmbeddingHit
from apps.workbench.persistence.models import (
    Chunk,
    PersistenceError,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
    WorkspaceNotFound,
)
from apps.workbench.postgres.postgres import PostgresPersistence
from scripts.workbench_embedding_backfill import BackfillRuntime, open_backfill_runtime, run_backfill

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _ROOT / "apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json"
_CUTOFFS = (1, 5, 10)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EvaluationIntegrityError(ValueError):
    """Expose only a safe integrity category, without source text or model inputs."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _FixtureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class EvaluationChunk(_FixtureRecord):
    """An exact character span of the fixture's original UTF-8 source."""

    chunk_id: Identifier
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=32768, repr=False)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    role: Literal["primary", "support", "hard_negative"]


class EvaluationSource(_FixtureRecord):
    """Original content and explicit active/superseded/tenant identity for publication."""

    workspace_id: Identifier
    source_id: Identifier
    version_id: Identifier
    title: str = Field(min_length=1, max_length=500)
    language: Literal["en", "ru", "uk", "code"]
    active: bool
    original: str = Field(min_length=1, max_length=131072, repr=False)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    chunks: tuple[EvaluationChunk, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _original_spans(self) -> EvaluationSource:
        if _sha256(self.original) != self.content_hash:
            raise ValueError("Original source digest mismatch")
        previous_end = 0
        for chunk in self.chunks:
            if (
                chunk.start < previous_end
                or chunk.end > len(self.original)
                or self.original[chunk.start : chunk.end] != chunk.content
                or _sha256(chunk.content) != chunk.content_hash
            ):
                raise ValueError("Chunk is not its declared original-source span")
            previous_end = chunk.end
        return self


class EvaluationQuery(_FixtureRecord):
    """Fixed explicit relevance labels, with no runtime generative correctness judgment."""

    query_id: Identifier
    text: str = Field(min_length=1, max_length=4096, repr=False)
    language: Literal["en", "ru", "uk"]
    cohort: Literal["same_language", "cross_language", "code", "no_answer"]
    relevance: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _labels(self) -> EvaluationQuery:
        if not self.text.strip() or "\0" in self.text:
            raise ValueError("Evaluation query requires nonempty Unicode")
        try:
            self.text.encode("utf-8")
        except UnicodeError:
            raise ValueError("Evaluation query requires valid Unicode") from None
        if (self.cohort == "no_answer") != (not self.relevance):
            raise ValueError("Only no-answer queries may have no relevant passages")
        if any(type(grade) is not int or not 1 <= grade <= 3 for grade in self.relevance.values()):
            raise ValueError("Relevance grades must be integers from one to three")
        return self


class EvaluationFixture(_FixtureRecord):
    """Independent source/label oracle for a dedicated, explicitly seeded workspace."""

    schema_version: Literal["embedding-retrieval-eval-v1"]
    fixture_id: Identifier
    workspace_id: Identifier
    sources: tuple[EvaluationSource, ...] = Field(min_length=1, max_length=100)
    queries: tuple[EvaluationQuery, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _identities(self) -> EvaluationFixture:
        versions: set[tuple[str, str, str]] = set()
        active_sources: set[tuple[str, str]] = set()
        chunks: dict[str, tuple[EvaluationSource, EvaluationChunk]] = {}
        for source in self.sources:
            key = (source.workspace_id, source.source_id, source.version_id)
            source_key = key[:2]
            if key in versions or (source.active and source_key in active_sources):
                raise ValueError("Fixture source/version identity is ambiguous")
            versions.add(key)
            if source.active:
                active_sources.add(source_key)
            for chunk in source.chunks:
                if chunk.chunk_id in chunks:
                    raise ValueError("Fixture chunk identities must be globally unique")
                chunks[chunk.chunk_id] = (source, chunk)
        if len({query.query_id for query in self.queries}) != len(self.queries):
            raise ValueError("Fixture query identities must be unique")
        for query in self.queries:
            for identifier in query.relevance:
                if identifier not in chunks:
                    raise ValueError("Relevant chunk is absent from the fixture")
                source, chunk = chunks[identifier]
                if source.workspace_id != self.workspace_id or not source.active or chunk.role == "hard_negative":
                    raise ValueError("Relevant chunk must be active, in scope and nonnegative")
                if query.cohort == "cross_language" and source.language == query.language:
                    raise ValueError("Cross-language labels must require a different document language")
        return self

    def chunk_index(self) -> dict[str, tuple[EvaluationSource, EvaluationChunk]]:
        """Return the original-source oracle keyed by immutable fixture chunk identity."""
        return {chunk.chunk_id: (source, chunk) for source in self.sources for chunk in source.chunks}


def load_evaluation_fixture(path: Path = _FIXTURE) -> EvaluationFixture:
    """Load a bounded local fixture without database access, inference or downloads."""
    try:
        with path.open("rb") as source:
            raw = source.read(1_048_577)
    except OSError:
        raise EvaluationIntegrityError("INVALID_EVALUATION_FIXTURE") from None
    if len(raw) > 1_048_576:
        raise EvaluationIntegrityError("INVALID_EVALUATION_FIXTURE")
    try:
        return EvaluationFixture.model_validate_json(raw)
    except (ValueError, UnicodeError):
        raise EvaluationIntegrityError("INVALID_EVALUATION_FIXTURE") from None


def score_ranking(relevance: Mapping[str, int], ranked_ids: Sequence[str], *, cutoff: int) -> dict[str, float | None]:
    """Compute recall, hit rate, reciprocal rank and exponential-gain nDCG at the stated cutoff."""
    if (
        type(cutoff) is not int
        or cutoff < 1
        or len(set(ranked_ids)) != len(ranked_ids)
        or any(type(grade) is not int or not 1 <= grade <= 3 for grade in relevance.values())
    ):
        raise EvaluationIntegrityError("INVALID_EVALUATION_RANKING")
    if not relevance:
        return dict.fromkeys(("recall", "primary_recall", "hit_rate", "reciprocal_rank", "ndcg"))
    selected = ranked_ids[:cutoff]
    found = [index for index, identifier in enumerate(selected, 1) if identifier in relevance]
    dcg = sum(
        (2 ** relevance.get(identifier, 0) - 1) / math.log2(index + 1) for index, identifier in enumerate(selected, 1)
    )
    ideal = sum(
        (2**grade - 1) / math.log2(index + 1)
        for index, grade in enumerate(sorted(relevance.values(), reverse=True)[:cutoff], 1)
    )
    return {
        "recall": len(found) / len(relevance),
        "primary_recall": sum(identifier in selected for identifier, grade in relevance.items() if grade == 3)
        / sum(grade == 3 for grade in relevance.values())
        if 3 in relevance.values()
        else None,
        "hit_rate": float(bool(found)),
        "reciprocal_rank": 1 / found[0] if found else 0.0,
        "ndcg": dcg / ideal,
    }


def evaluate_query(
    fixture: EvaluationFixture,
    query: EvaluationQuery,
    hits: Sequence[PersistedEmbeddingHit],
    *,
    profile_fingerprint: str,
    index_generation: int,
) -> dict[str, Any]:
    """Audit exact originals/tenant/version/input provenance before calculating relevance metrics."""
    originals = fixture.chunk_index()
    seen: set[str] = set()
    previous_distance = -math.inf
    audit = []
    for hit in hits:
        if hit.chunk_id in seen or hit.chunk_id not in originals:
            raise EvaluationIntegrityError("UNKNOWN_OR_DUPLICATE_EVALUATION_CHUNK")
        seen.add(hit.chunk_id)
        source, chunk = originals[hit.chunk_id]
        if hit.workspace_id != fixture.workspace_id or source.workspace_id != fixture.workspace_id:
            raise EvaluationIntegrityError("CROSS_WORKSPACE_EVALUATION_RESULT")
        if not source.active or (hit.source_id, hit.version_id) != (source.source_id, source.version_id):
            raise EvaluationIntegrityError("STALE_SOURCE_EVALUATION_RESULT")
        if (
            hit.content != chunk.content
            or hit.content_hash != chunk.content_hash
            or _sha256(hit.content) != chunk.content_hash
        ):
            raise EvaluationIntegrityError("CHUNK_CONTENT_EVALUATION_MISMATCH")
        if hit.source_content_hash != source.content_hash:
            raise EvaluationIntegrityError("ORIGINAL_SOURCE_EVALUATION_MISMATCH")
        if hit.input_hash != _sha256(unicodedata.normalize("NFC", chunk.content)):
            raise EvaluationIntegrityError("MODEL_INPUT_EVALUATION_MISMATCH")
        if hit.profile_fingerprint != profile_fingerprint or hit.index_generation != index_generation:
            raise EvaluationIntegrityError("GENERATION_PROFILE_EVALUATION_MISMATCH")
        if not math.isfinite(hit.distance) or not 0 <= hit.distance <= 2 or hit.distance + 1e-12 < previous_distance:
            raise EvaluationIntegrityError("INVALID_EVALUATION_DISTANCE_ORDER")
        previous_distance = hit.distance
        audit.append(
            {
                "chunk_id": hit.chunk_id,
                "source_id": hit.source_id,
                "version_id": hit.version_id,
                "content_hash": hit.content_hash,
                "source_content_hash": hit.source_content_hash,
                "input_hash": hit.input_hash,
                "distance": hit.distance,
                "relevance_grade": query.relevance.get(hit.chunk_id, 0),
                "hard_negative": chunk.role == "hard_negative",
            }
        )
    ranked = [hit.chunk_id for hit in hits]
    return {
        "query_id": query.query_id,
        "query_hash": _sha256(query.text),
        "language": query.language,
        "cohort": query.cohort,
        "answerable": bool(query.relevance),
        "expected_chunk_ids": sorted(query.relevance),
        "metrics": {str(cutoff): score_ranking(query.relevance, ranked, cutoff=cutoff) for cutoff in _CUTOFFS},
        "provenance_verified_hits": len(audit),
        "hits": audit,
        "forced_neighbors_for_no_answer": len(hits) if not query.relevance else 0,
        "top_similarity": 1 - hits[0].distance if hits else None,
    }


def summarize_evaluation(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate answerable cases separately from forced-neighbor no-answer diagnostics."""
    answerable = [record for record in records if record["answerable"]]
    metrics: dict[str, dict[str, float | None]] = {}
    for cutoff in _CUTOFFS:
        metrics[str(cutoff)] = {}
        for name in ("recall", "primary_recall", "hit_rate", "reciprocal_rank", "ndcg"):
            values = [
                record["metrics"][str(cutoff)][name]
                for record in answerable
                if record["metrics"][str(cutoff)][name] is not None
            ]
            metrics[str(cutoff)]["mrr" if name == "reciprocal_rank" else name] = (
                sum(values) / len(values) if values else None
            )
    no_answer = [record for record in records if not record["answerable"]]
    return {
        "queries": len(records),
        "answerable_queries": len(answerable),
        "metrics": metrics,
        "no_answer_queries": len(no_answer),
        "no_answer_with_forced_neighbors": sum(bool(record["forced_neighbors_for_no_answer"]) for record in no_answer),
        "no_answer_top_similarities": [record["top_similarity"] for record in no_answer],
        "answerable_hard_negative_at_rank_one": sum(
            bool(record["hits"] and record["hits"][0]["hard_negative"]) for record in answerable
        ),
        "abstention_status": "NOT_IMPLEMENTED_RAW_NEAREST_NEIGHBORS",
    }


async def evaluate_retrieval(
    fixture: EvaluationFixture,
    search: Callable[[EvaluationQuery, int], Awaitable[tuple[PersistedEmbeddingHit, ...]]],
    *,
    profile_fingerprint: str,
) -> dict[str, Any]:
    """Evaluate a real governed-query/exact-SQL callback without constructing another model client."""
    records = []
    index_generation: int | None = None
    started = time.monotonic()
    for query in fixture.queries:
        hits = await search(query, max(_CUTOFFS))
        if hits and index_generation is None:
            index_generation = hits[0].index_generation
        if index_generation is None:
            raise EvaluationIntegrityError("EMPTY_QUALIFIED_EVALUATION_CORPUS")
        records.append(
            evaluate_query(
                fixture, query, hits, profile_fingerprint=profile_fingerprint, index_generation=index_generation
            )
        )
    groups = {
        **{
            f"language:{language}": [record for record in records if record["language"] == language]
            for language in ("en", "ru", "uk")
        },
        **{
            f"cohort:{cohort}": [record for record in records if record["cohort"] == cohort]
            for cohort in ("same_language", "cross_language", "code", "no_answer")
        },
    }
    return {
        "fixture_id": fixture.fixture_id,
        "fixture_digest": _sha256(fixture.model_dump_json()),
        "workspace_id": fixture.workspace_id,
        "profile_fingerprint": profile_fingerprint,
        "index_generation": index_generation,
        "elapsed_seconds": time.monotonic() - started,
        "integrity_status": "PASS",
        "quality_status": "MEASURED_NO_PRODUCTION_THRESHOLD",
        "overall": summarize_evaluation(records),
        "groups": {name: summarize_evaluation(group) for name, group in groups.items()},
        "cases": records,
        "judgment_method": "fixed relevance labels and exact original-source provenance; no generative model",
        "answer_generation": "NOT_IMPLEMENTED",
        "production_trust_established": False,
    }


async def _ensure_fixture_workspace(
    repository: PostgresPersistence, fixture: EvaluationFixture, workspace_id: str
) -> None:
    context = WorkspaceContext(workspace_id=workspace_id, trace_id="evaluation-fixture-setup")
    identity: dict[str, JsonValue] = {
        "evaluation_fixture_id": fixture.fixture_id,
        "fixture_digest": _sha256(fixture.model_dump_json()),
    }
    try:
        workspaces = await repository.list_workspaces(context)
    except WorkspaceNotFound:
        await repository.create_workspace(
            context, Workspace(workspace_id=workspace_id, name="Controlled retrieval evaluation", metadata=identity)
        )
        return
    if len(workspaces) != 1 or workspaces[0].metadata != identity:
        raise EvaluationIntegrityError("EVALUATION_WORKSPACE_CONFLICT")


async def _publish_fixture_sources(
    repository: PostgresPersistence,
    fixture: EvaluationFixture,
    sources: Sequence[EvaluationSource],
    *,
    allow_current: bool = False,
) -> int:
    published = 0
    fixture_digest = _sha256(fixture.model_dump_json())
    active = {(source.workspace_id, source.source_id): source.version_id for source in fixture.sources if source.active}
    for source in sources:
        context = WorkspaceContext(workspace_id=source.workspace_id, trace_id="evaluation-fixture-publication")
        snapshot = await repository.corpus_snapshot(context)
        existing = next((document for document in snapshot.documents if document.source_id == source.source_id), None)
        if existing is not None and existing.active_version_id == source.version_id:
            if existing.chunk_count != len(source.chunks):
                raise EvaluationIntegrityError("EVALUATION_SOURCE_CONFLICT")
            for chunk in source.chunks:
                stored = await repository.get_chunk(context, chunk.chunk_id)
                if stored is None or stored.content_hash != chunk.content_hash or stored.content != chunk.content:
                    raise EvaluationIntegrityError("EVALUATION_SOURCE_CONFLICT")
            continue
        if (
            existing is not None
            and allow_current
            and existing.active_version_id == active[(source.workspace_id, source.source_id)]
        ):
            continue
        known_versions = {
            candidate.version_id
            for candidate in fixture.sources
            if (candidate.workspace_id, candidate.source_id) == (source.workspace_id, source.source_id)
        }
        if existing is not None and existing.active_version_id not in known_versions:
            raise EvaluationIntegrityError("EVALUATION_SOURCE_CONFLICT")
        metadata: dict[str, JsonValue] = {"evaluation_fixture_id": fixture.fixture_id, "fixture_digest": fixture_digest}
        version_metadata: dict[str, JsonValue] = {
            **metadata,
            "format_id": "text",
            "parser_id": "evaluation-source-spans",
            "parser_revision": "evaluation-source-spans-r1",
            "normalization_policy": "unicode-nfc",
            "processing_profile_fingerprint": _sha256("evaluation-source-spans-r1"),
        }
        await repository.publish_source(
            context,
            source=Source(
                workspace_id=source.workspace_id, source_id=source.source_id, title=source.title, metadata=metadata
            ),
            version=SourceVersion(
                workspace_id=source.workspace_id,
                source_id=source.source_id,
                version_id=source.version_id,
                content_hash=source.content_hash,
                metadata=version_metadata,
            ),
            chunks=[
                Chunk(
                    workspace_id=source.workspace_id,
                    source_id=source.source_id,
                    version_id=source.version_id,
                    chunk_id=chunk.chunk_id,
                    title=source.title,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    metadata={"original_start": chunk.start, "original_end": chunk.end, "fixture_role": chunk.role},
                )
                for chunk in source.chunks
            ],
        )
        published += 1
    return published


async def _backfill_fixture_phase(runtime: BackfillRuntime, context: WorkspaceContext, *, name: str) -> dict[str, Any]:
    before = runtime.worker.statistics()
    result = await run_backfill(runtime, context, max_steps=10000)
    if result["status"] != "READY":
        raise EvaluationIntegrityError("EVALUATION_EMBEDDING_COVERAGE_INCOMPLETE")
    result["phase"] = name
    result["statistics_delta"] = {key: value - before[key] for key, value in runtime.worker.statistics().items()}
    return result


async def prepare_evaluation_vectors(runtime: BackfillRuntime, fixture: EvaluationFixture) -> list[dict[str, Any]]:
    """Publish originals through the existing port, with real stale/foreign vectors and safe same-tenant reuse."""
    for workspace_id in sorted({source.workspace_id for source in fixture.sources}):
        await _ensure_fixture_workspace(runtime.persistence, fixture, workspace_id)
    main_context = WorkspaceContext(workspace_id=fixture.workspace_id, trace_id="evaluation-main-backfill")
    superseded = {(source.workspace_id, source.source_id): source for source in fixture.sources if not source.active}
    current = [source for source in fixture.sources if source.active and source.workspace_id == fixture.workspace_id]
    initial = [superseded.get((source.workspace_id, source.source_id), source) for source in current]
    await _publish_fixture_sources(runtime.persistence, fixture, initial, allow_current=True)
    phases = [await _backfill_fixture_phase(runtime, main_context, name="initial-main-with-old-versions")]
    for workspace_id in sorted({source.workspace_id for source in fixture.sources} - {fixture.workspace_id}):
        foreign = [source for source in fixture.sources if source.workspace_id == workspace_id and source.active]
        published = await _publish_fixture_sources(runtime.persistence, fixture, foreign)
        phase = await _backfill_fixture_phase(
            runtime,
            WorkspaceContext(workspace_id=workspace_id, trace_id="evaluation-foreign-backfill"),
            name="foreign-workspace",
        )
        if published == len(foreign) and phase["statistics_delta"]["generated_inputs"] != sum(
            len(source.chunks) for source in foreign
        ):
            raise EvaluationIntegrityError("CROSS_WORKSPACE_EMBEDDING_CACHE_REUSE")
        phases.append(phase)
    changed = await _publish_fixture_sources(runtime.persistence, fixture, current)
    phase = await _backfill_fixture_phase(runtime, main_context, name="current-main-after-source-replacement")
    if changed == 4 and (
        phase["statistics_delta"]["generated_inputs"] != 4 or phase["statistics_delta"]["reused_chunks"] != 8
    ):
        raise EvaluationIntegrityError("EXPECTED_SAME_TENANT_DELTA_REUSE_MISSING")
    phases.append(phase)
    return phases


async def evaluate_persisted_vectors(runtime: BackfillRuntime, fixture: EvaluationFixture) -> dict[str, Any]:
    """Embed every query through the shared governor and rank actual durable vectors with exact cosine SQL."""
    context = WorkspaceContext(workspace_id=fixture.workspace_id, trace_id="objective-retrieval-evaluation")
    coverage = await runtime.persistence.embedding_coverage(context, runtime.profile)
    expected_chunks = sum(
        len(source.chunks)
        for source in fixture.sources
        if source.active and source.workspace_id == fixture.workspace_id
    )
    if (
        not coverage.ready
        or coverage.eligible_active_chunks != expected_chunks
        or coverage.ready_embeddings != expected_chunks
    ):
        raise EvaluationIntegrityError("EVALUATION_EMBEDDING_COVERAGE_INCOMPLETE")
    query_tokens = 0
    query_audits = []

    async def search(query: EvaluationQuery, limit: int) -> tuple[PersistedEmbeddingHit, ...]:
        nonlocal query_tokens
        request = EmbeddingRequest(
            profile_id=runtime.profile.profile_id,
            profile_revision=runtime.profile.profile_revision,
            task_kind="query",
            workspace_id=context.workspace_id,
            trace_id=query.query_id,
            items=(EmbeddingItem(item_id=query.query_id, text=query.text, input_hash=_sha256(query.text)),),
            deadline=time.monotonic() + runtime.profile.timeout_seconds,
        )
        prepared = prepare_embedding_request(runtime.profile, request, runtime.counter)
        batch = await runtime.adapter.embed(request)
        if (
            batch.item_ids != (query.query_id,)
            or batch.source_hashes != (_sha256(query.text),)
            or batch.input_hashes != (prepared[0].input_hash,)
            or batch.model_digest != runtime.profile.model_digest
            or batch.tokenizer_digest != runtime.profile.tokenizer_digest
            or batch.usage_provenance != "provider_reported"
            or batch.usage_tokens is None
            or len(batch.vectors) != 1
        ):
            raise EvaluationIntegrityError("QUERY_EMBEDDING_EVALUATION_MISMATCH")
        query_tokens += batch.usage_tokens
        query_audits.append(
            {
                "query_id": query.query_id,
                "source_hash": batch.source_hashes[0],
                "sent_input_hash": batch.input_hashes[0],
                "usage_provenance": batch.usage_provenance,
                "usage_tokens": batch.usage_tokens,
            }
        )
        return await runtime.persistence.exact_embedding_search(context, runtime.profile, batch.vectors[0], limit=limit)

    report = await evaluate_retrieval(fixture, search, profile_fingerprint=runtime.profile.fingerprint)
    after = await runtime.persistence.embedding_coverage(context, runtime.profile)
    if after != coverage:
        raise EvaluationIntegrityError("EVALUATION_GENERATION_CHANGED")
    report["coverage"] = coverage.model_dump(mode="json")
    report["query_provider_reported_tokens"] = query_tokens
    report["query_embeddings"] = query_audits
    report["admission"] = runtime.governor.summary()
    report["retrieval_method"] = "persisted PostgreSQL exact cosine; no ANN or dense HTTP"
    report["status"] = "EVALUATED"
    return report


def _disposable_evaluation_dsn(environment_name: str) -> str:
    value = os.environ.get(environment_name)
    if not value:
        raise EvaluationIntegrityError("MISSING_EVALUATION_DATABASE")
    try:
        database_name = conninfo_to_dict(value).get("dbname", "")
    except (ValueError, ProgrammingError):
        raise EvaluationIntegrityError("INVALID_EVALUATION_DATABASE") from None
    if not isinstance(database_name, str) or not database_name.startswith("rag_test_"):
        raise EvaluationIntegrityError("EVALUATION_REQUIRES_DISPOSABLE_DATABASE")
    return value


async def _run_live(args: argparse.Namespace, fixture: EvaluationFixture) -> dict[str, Any]:
    if args.capacity_config is None:
        raise EvaluationIntegrityError("MEASURED_CAPACITY_CONFIGURATION_REQUIRED")
    dsn = _disposable_evaluation_dsn(args.dsn_env)
    if args.prepare_fixture:
        repository = PostgresPersistence(dsn=dsn)
        await repository.start()
        try:
            for workspace_id in sorted({source.workspace_id for source in fixture.sources}):
                await _ensure_fixture_workspace(repository, fixture, workspace_id)
        finally:
            await repository.close()
    context = WorkspaceContext(workspace_id=fixture.workspace_id, trace_id="objective-retrieval-evaluation")
    async with open_backfill_runtime(
        dsn=dsn,
        model_directory=args.model_directory,
        capacity_config=args.capacity_config,
        context=context,
        endpoint=args.endpoint,
        container=args.container,
    ) as runtime:
        phases = await prepare_evaluation_vectors(runtime, fixture) if args.prepare_fixture else []
        report = await evaluate_persisted_vectors(runtime, fixture)
        report["fixture_publication_method"] = "existing lexical publication port; not HTTP upload"
        report["preparation_phases"] = phases
        return report


def main() -> int:
    """Validate offline by default; explicit live mode uses one real shared worker/runtime on a disposable DB."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=_FIXTURE)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--prepare-fixture", action="store_true")
    parser.add_argument("--capacity-config", type=Path)
    parser.add_argument("--dsn-env", default="WORKBENCH_TEST_APP_DSN")
    parser.add_argument(
        "--model-directory",
        type=Path,
        default=Path(os.environ.get("WORKBENCH_EMBEDDING_MODEL_DIRECTORY", "A:/AI/TEI/qwen3-4b")),
    )
    parser.add_argument("--endpoint", default="http://127.0.0.1:8082")
    parser.add_argument("--container", default="rag-workbench-embedding-1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.prepare_fixture and not args.run:
        print(json.dumps({"status": "FAIL", "code": "LIVE_EVALUATION_OPT_IN_REQUIRED"}))
        return 1
    try:
        fixture = load_evaluation_fixture(args.fixture)
        if args.run:
            factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
            with asyncio.Runner(loop_factory=factory) as runner:
                report = runner.run(_run_live(args, fixture))
        else:
            report = {
                "status": "FIXTURE_VALIDATED",
                "fixture_id": fixture.fixture_id,
                "sources": len(fixture.sources),
                "chunks": len(fixture.chunk_index()),
                "queries": len(fixture.queries),
                "inference_requests": 0,
            }
    except (EvaluationIntegrityError, EmbeddingError, PersistenceError, ValueError) as error:
        code = error.code if isinstance(error, EvaluationIntegrityError) else "EVALUATION_UNAVAILABLE"
        print(json.dumps({"status": "FAIL", "code": code}))
        return 1
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "fixture_id")}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

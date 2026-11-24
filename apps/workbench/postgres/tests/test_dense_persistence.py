"""Disposable SQL oracle and adversarial fences; vectors here are synthetic test inputs."""

import asyncio
import hashlib
import math
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql

from apps.workbench.embedding.embedding import (
    EmbeddingBatch,
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.embedding.embedding_jobs import EmbeddingWrite
from apps.workbench.persistence.models import (
    Chunk,
    CorpusNotReady,
    InvalidEmbedding,
    ProfileNotAvailable,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
    WorkspaceNotFound,
)
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.postgres.postgres_profiles import promote_profile, sync_registry, transition_profile
from apps.workbench.retrieval.dense import DenseService
from apps.workbench.retrieval.lexical import LexicalService
from apps.workbench.retrieval.profile_registry import ProfileDefinition, ProfileRegistry, ProfileRollout
from apps.workbench.retrieval.services import RetrievalService
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="dense-sql-oracle")
_PROFILE = EmbeddingProfile(
    profile_id="dense-test-model",
    profile_revision="dense-test-model-r1",
    provider_adapter_id="tei-openai",
    model_id="Qwen/Qwen3-Embedding-4B",
    model_revision="a" * 40,
    model_digest="b" * 64,
    tokenizer_digest="c" * 64,
    tokenizer_revision="test-counter",
    dimensions=32,
)
_DEFINITION = ProfileDefinition(
    profile_id="dense-test",
    profile_revision="dense-test-r1",
    label="Exact dense test",
    kind="dense",
    composition="exact_dense",
    workspace_ids=("development",),
    model_profile_id=_PROFILE.profile_id,
    model_profile_revision=_PROFILE.profile_revision,
    dimensions=32,
    index_dimensions=32,
    normalization="l2",
    vector_representation="vector",
    capacity_policy_id="measured-test-capacity",
    score_type="cosine_distance",
    score_direction="lower_is_better",
    capability_requirements=("schema", "source_generation", "embedding_model", "embedding_coverage", "capacity_policy"),
)


@pytest_asyncio.fixture(loop_scope="function")
async def dense_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Create a separate migrated database; no configured corpus is modified."""
    migrate(disposable_database.admin_dsn)
    store = PostgresPersistence(disposable_database.app_dsn)
    await store.start()
    await store.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Dense SQL oracle"))
    await store.create_workspace(
        WorkspaceContext(workspace_id="foreign"), Workspace(workspace_id="foreign", name="Foreign tenant")
    )
    try:
        yield store
    finally:
        await store.close()


async def _publish(store: PostgresPersistence, *, version: str = "original", count: int = 100) -> None:
    source = Source(workspace_id="development", source_id="evidence", title="Exact evidence")
    chunks = [
        Chunk(
            workspace_id="development",
            source_id=source.source_id,
            version_id=version,
            chunk_id=f"{version}-{index:03}",
            title=source.title,
            content=f"Evidence passage {index}",
            content_hash=hashlib.sha256(f"{version}-{index}".encode()).hexdigest(),
            page=index + 1 if index % 2 else None,
        )
        for index in range(count)
    ]
    await store.publish_source(
        _CONTEXT,
        source=source,
        version=SourceVersion(
            workspace_id="development", source_id=source.source_id, version_id=version, content_hash=version
        ),
        chunks=chunks,
    )


async def _complete(store: PostgresPersistence) -> int:
    await store.register_embedding_profile(_CONTEXT, _PROFILE)
    await store.enqueue_embedding_backfill(_CONTEXT, _PROFILE)
    job = await store.lease_embedding_job(_CONTEXT, _PROFILE)
    assert job is not None
    page = await store.embedding_job_chunks(_CONTEXT, job, limit=128)
    records = tuple(
        EmbeddingWrite(
            source_id=item.source_id,
            version_id=item.version_id,
            chunk_id=item.chunk_id,
            expected_content_hash=item.content_hash,
            processing_digest="d" * 64,
            input_hash=hashlib.sha256(item.content.encode()).hexdigest(),
            vector=(math.cos(index / 100 * math.pi), math.sin(index / 100 * math.pi), *([0.0] * 30)),
        )
        for index, item in enumerate(page)
    )
    await store.commit_embedding_batch(
        _CONTEXT, job, _PROFILE, records=records, cursor=page[-1].chunk_id, complete=True
    )
    coverage = await store.embedding_coverage(_CONTEXT, _PROFILE)
    assert coverage.ready and coverage.index_generation is not None
    return coverage.index_generation


def _activate(database: DisposableDatabase) -> ProfileRollout:
    sync_registry(database.admin_dsn, ProfileRegistry(profiles=(_DEFINITION,)))
    return promote_profile(
        database.admin_dsn,
        workspace_id="development",
        profile_id=_DEFINITION.profile_id,
        profile_revision=_DEFINITION.profile_revision,
    )


async def test_exact_dense_agrees_with_independent_sql_for_100_vectors_and_two_queries(
    dense_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Independent SQL and Python cosine oracles agree on actual stored identities and distance direction."""
    store = dense_repository
    await _publish(store)
    generation = await _complete(store)
    rollout = _activate(disposable_database)
    with pytest.raises(CorpusNotReady):
        await store.vector_search_snapshot(
            _CONTEXT,
            embedding=[1.0, *([0.0] * 31)],
            embedding_profile=_PROFILE.model_copy(update={"model_digest": "f" * 64}),
            expected_index_generation=generation,
            profile_fence=rollout,
            profile_definition=_DEFINITION,
        )
    with pytest.raises(WorkspaceNotFound):
        await store.vector_search_snapshot(
            WorkspaceContext(workspace_id="absent"),
            embedding=[1.0, *([0.0] * 31)],
            embedding_profile=_PROFILE,
            expected_index_generation=generation,
            profile_fence=rollout,
            profile_definition=_DEFINITION.model_copy(update={"workspace_ids": ("development", "absent")}),
        )
    first_ids = []
    for angle in (0.0, math.pi / 2):
        vector = [math.cos(angle), math.sin(angle), *([0.0] * 30)]
        snapshot = await store.vector_search_snapshot(
            _CONTEXT,
            embedding=vector,
            embedding_profile=_PROFILE,
            expected_index_generation=generation,
            profile_fence=rollout,
            profile_definition=_DEFINITION,
            top_k=10,
        )
        with psycopg.connect(disposable_database.admin_dsn) as connection:
            rows = connection.execute(
                "SELECT m.chunk_id,e.vector <=> %s::vector AS distance FROM workbench.chunk_embeddings m "
                "JOIN workbench.embedding_vectors e "
                "USING(workspace_id,profile_fingerprint,processing_digest,input_hash) "
                "WHERE m.workspace_id='development' AND m.profile_fingerprint=%s "
                'ORDER BY distance,m.chunk_id COLLATE "C" LIMIT 10',
                (str(vector), _PROFILE.fingerprint),
            ).fetchall()
        assert [hit.chunk.chunk_id for hit in snapshot.hits] == [row[0] for row in rows]
        assert [hit.distance for hit in snapshot.hits] == pytest.approx([row[1] for row in rows])
        for hit in snapshot.hits:
            index = int(hit.chunk.chunk_id.rsplit("-", 1)[1])
            assert hit.distance == pytest.approx(1 - math.cos(index / 100 * math.pi - angle), abs=2e-7)
            assert hit.chunk.version_id == "original" and hit.score_type == "cosine_distance"
            assert hit.chunk.page == (index + 1 if index % 2 else None)
        assert [hit.rank for hit in snapshot.hits] == list(range(1, 11))
        assert snapshot.embedding_profile_fingerprint == _PROFILE.fingerprint
        assert snapshot.embedding_profile_revision == _PROFILE.profile_revision
        assert snapshot.index_generation_id == generation and snapshot.chunk_count == 100
        first_ids.append(snapshot.hits[0].chunk.chunk_id)
    assert first_ids[0] != first_ids[1]
    with psycopg.connect(disposable_database.app_dsn) as connection:
        connection.execute("SELECT set_config('workbench.workspace_id','foreign',true)")
        # No caller WHERE clause: forced tenant RLS must still hide every local candidate and vector.
        for table in ("chunks", "chunk_embeddings", "embedding_vectors", "embedding_generations"):
            assert connection.execute(
                sql.SQL("SELECT count(*) FROM workbench.{}").format(sql.Identifier(table))
            ).fetchone() == (0,)


async def test_dense_rejects_partial_generation_profile_drift_and_source_swap(
    dense_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """No retired rollout, incomplete coverage or stale generation can reach live SQL retrieval."""
    store = dense_repository
    await _publish(store, count=2)
    sync_registry(disposable_database.admin_dsn, ProfileRegistry(profiles=(_DEFINITION,)))
    with pytest.raises(CorpusNotReady):
        _activate(disposable_database)
    generation = await _complete(store)
    rollout = _activate(disposable_database)

    async def search(fence: ProfileRollout = rollout) -> None:
        await store.vector_search_snapshot(
            _CONTEXT,
            embedding=[1.0, *([0.0] * 31)],
            embedding_profile=_PROFILE,
            expected_index_generation=generation,
            profile_fence=fence,
            profile_definition=_DEFINITION,
        )

    with pytest.raises(ProfileNotAvailable):
        await search(rollout.model_copy(update={"rollout_version": rollout.rollout_version + 1}))
    await _publish(store, version="replacement", count=2)
    with pytest.raises(CorpusNotReady):
        await search()
    await _complete(store)
    with pytest.raises(CorpusNotReady):
        await search()
    transition_profile(
        disposable_database.admin_dsn,
        workspace_id="development",
        profile_id=_DEFINITION.profile_id,
        profile_revision=_DEFINITION.profile_revision,
        state="retired",
    )
    with pytest.raises(ProfileNotAvailable):
        await search()


@pytest.mark.parametrize("vector", [[1.0], [0.0] * 32, [float("nan")] * 32, [float("inf")] * 32])
async def test_invalid_query_vector_fails_before_database(vector: list[float]) -> None:
    """Wrong dimension, nonfinite and unnormalized provider outputs never touch SQL."""
    store = PostgresPersistence("host=invalid.invalid dbname=unused")
    with pytest.raises(InvalidEmbedding):
        await store.vector_search_snapshot(
            _CONTEXT,
            embedding=vector,
            embedding_profile=_PROFILE,
            expected_index_generation=1,
            profile_fence=ProfileRollout(
                workspace_id="development",
                profile_id=_DEFINITION.profile_id,
                profile_revision=_DEFINITION.profile_revision,
                state="active",
                policy_hash=_DEFINITION.policy_hash,
                rollout_version=1,
            ),
            profile_definition=_DEFINITION,
        )


class _Counter:
    counter_revision = "test-counter"

    def count_tokens(self, text: str) -> int:
        """Count deterministic fixture tokens, without claiming native model measurements."""
        return len(text.split())


class _SuspendedEmbedding:
    def __init__(self) -> None:
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def warm_up_async(self) -> None:
        """No setup is needed for this synthetic race injector."""

    async def close_async(self) -> None:
        """The injector owns no resources."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Hold the model boundary open until a real SQL change commits."""
        self.started.set()
        await self.release.wait()
        return validate_embedding_batch(
            _PROFILE,
            request,
            prepare_embedding_request(_PROFILE, request, _Counter()),
            vectors=((1.0, *([0.0] * 31)),),
            usage_tokens=None,
            usage_provenance="unknown",
            duration_ms=0.0,
        )


@pytest.mark.parametrize("change", ["source_swap", "retire_profile"])
async def test_model_inflight_changes_cannot_return_stale_dense_hits(
    dense_repository: PostgresPersistence, disposable_database: DisposableDatabase, change: str
) -> None:
    """Commit a source or rollout change while Haystack awaits query output; retrieval must refuse it."""
    store = dense_repository
    await _publish(store, count=2)
    await _complete(store)
    _activate(disposable_database)
    provider = _SuspendedEmbedding()
    service = DenseService(
        store,
        embedding=provider,
        profile=_PROFILE,
        counter=_Counter(),
        registry=ProfileRegistry(profiles=(_DEFINITION,)),
        capacity_policy_id=_DEFINITION.capacity_policy_id or "",
        readiness=provider.warm_up_async,
    )
    search = asyncio.create_task(
        service.search(
            _CONTEXT,
            query="What evidence exists?",
            top_k=2,
            profile_id=_DEFINITION.profile_id,
            expected_profile_revision=_DEFINITION.profile_revision,
        )
    )
    try:
        await asyncio.wait_for(provider.started.wait(), timeout=5)
        if change == "source_swap":
            await _publish(store, version="replacement", count=2)
        else:
            transition_profile(
                disposable_database.admin_dsn,
                workspace_id="development",
                profile_id=_DEFINITION.profile_id,
                profile_revision=_DEFINITION.profile_revision,
                state="retired",
            )
        provider.release.set()
        with pytest.raises(CorpusNotReady if change == "source_swap" else ProfileNotAvailable):
            await asyncio.wait_for(search, timeout=5)
    finally:
        search.cancel()
        await asyncio.gather(search, return_exceptions=True)


async def test_slow_model_discovery_preserves_healthy_lexical_profile(
    dense_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A blocked provider health probe cannot hide independently qualified keyword execution."""
    store = dense_repository
    await _publish(store, count=2)
    await _complete(store)
    _activate(disposable_database)
    provider = _SuspendedEmbedding()
    wait = asyncio.Event()

    async def delayed_readiness() -> None:
        await wait.wait()

    service = RetrievalService(
        LexicalService(store),
        registry=ProfileRegistry(profiles=(_DEFINITION,)),
        dense=DenseService(
            store,
            embedding=provider,
            profile=_PROFILE,
            counter=_Counter(),
            registry=ProfileRegistry(profiles=(_DEFINITION,)),
            capacity_policy_id=_DEFINITION.capacity_policy_id or "",
            readiness=delayed_readiness,
        ),
    )
    snapshot = await asyncio.wait_for(service.snapshot(_CONTEXT), timeout=0.9)
    assert [profile.profile_id for profile in snapshot.profiles] == ["postgres-fts-baseline"]

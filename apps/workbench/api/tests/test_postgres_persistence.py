"""Container-backed storage, isolation and publication tests with synthetic-only vectors."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import psycopg
import pytest
import pytest_asyncio

from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.persistence import (
    Chunk,
    DatabaseUnavailable,
    InvalidEmbedding,
    RecordConflict,
    SchemaIncompatible,
    SeedConflict,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
    WorkspaceNotFound,
)
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_DEVELOPMENT = WorkspaceContext(workspace_id="development")
_OTHER = WorkspaceContext(workspace_id="other-owner")


@pytest_asyncio.fixture(loop_scope="function")
async def empty_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Use real app-role connections after explicit admin migration."""
    migrate(disposable_database.admin_dsn)
    store = PostgresPersistence(disposable_database.app_dsn)
    await store.start()
    try:
        yield store
    finally:
        await store.close()


@pytest_asyncio.fixture(loop_scope="function")
async def repository(empty_repository: PostgresPersistence) -> AsyncIterator[PostgresPersistence]:
    """Create two owner scopes for positive and negative storage tests."""
    for context in (_DEVELOPMENT, _OTHER):
        await empty_repository.create_workspace(
            context, Workspace(workspace_id=context.workspace_id, name=context.workspace_id)
        )
    yield empty_repository


async def _publish(
    repository: PostgresPersistence, context: WorkspaceContext, identifier: str, content: str, **overrides: Any
) -> Chunk:
    source = Source(workspace_id=context.workspace_id, source_id=f"source-{identifier}", title=f"Source {identifier}")
    version = SourceVersion(
        workspace_id=context.workspace_id,
        source_id=source.source_id,
        version_id=f"version-{identifier}",
        content_hash=f"hash-{identifier}",
    )
    chunk = Chunk(
        workspace_id=context.workspace_id,
        source_id=source.source_id,
        version_id=version.version_id,
        chunk_id=f"chunk-{identifier}",
        title=source.title,
        content=content,
        content_hash=version.content_hash,
        **overrides,
    )
    await repository.publish_source(context, source=source, version=version, chunks=[chunk])
    return chunk


async def test_committed_passages_are_fts_searchable_and_survive_a_new_pool(
    repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Actual PostgreSQL FTS uses persisted text and truthful rank types."""
    chunk = await _publish(repository, _DEVELOPMENT, "english", "Reliable PostgreSQL publication and recovery.")
    await _publish(repository, _DEVELOPMENT, "unicode", "Український документ про ізоляцію пошуку. Invoice INV_2026_A.")
    for query in ["PostgreSQL", "Український", "INV_2026_A"]:
        hits = await repository.lexical_search(_DEVELOPMENT, query=query)
        assert hits
        assert hits[0].score > 0
        assert hits[0].score_type == "postgres_ts_rank_cd"
        assert hits[0].rank == 1
    assert await repository.lexical_search(_DEVELOPMENT, query="definitelyabsentterm") == []
    await repository.lexical_search(_DEVELOPMENT, query="'); DROP TABLE workbench.chunks; --")
    assert await repository.get_chunk(_DEVELOPMENT, chunk.chunk_id) == chunk
    ready = await repository.readiness(_DEVELOPMENT)
    assert ready.source_count == 2
    assert ready.chunk_count == 2
    other_pool = PostgresPersistence(disposable_database.app_dsn)
    await other_pool.start()
    try:
        assert await other_pool.get_chunk(_DEVELOPMENT, chunk.chunk_id) == chunk
        assert (await other_pool.lexical_search(_DEVELOPMENT, query="PostgreSQL"))[0].chunk.chunk_id == chunk.chunk_id
    finally:
        await other_pool.close()


async def test_foreign_identifiers_and_database_reference_mistakes_fail_closed(
    repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Guessed source/chunk IDs cannot bypass SQL scope, RLS or composite references."""
    foreign = await _publish(repository, _OTHER, "foreign", "foreignprivateidentifier")
    await _publish(repository, _DEVELOPMENT, "local", "public development passage")
    assert await repository.get_chunk(_DEVELOPMENT, foreign.chunk_id) is None
    assert await repository.lexical_search(_DEVELOPMENT, query="foreignprivateidentifier") == []
    assert {item.workspace_id for item in await repository.list_workspaces(_DEVELOPMENT)} == {"development"}
    assert foreign.source_id not in {item.source_id for item in await repository.list_sources(_DEVELOPMENT)}
    with psycopg.connect(disposable_database.app_dsn) as connection:
        connection.execute("SELECT set_config('workbench.workspace_id', 'development', true)")
        assert (
            connection.execute(
                "SELECT chunk_id FROM workbench.chunks WHERE chunk_id = %s", (foreign.chunk_id,)
            ).fetchall()
            == []
        )
    with (
        psycopg.connect(disposable_database.admin_dsn) as connection,
        pytest.raises(psycopg.errors.ForeignKeyViolation),
    ):
        connection.execute(
            "INSERT INTO workbench.source_versions (workspace_id, source_id, version_id, content_hash, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("development", foreign.source_id, "guessed-version", "hash", "staged"),
        )
    with pytest.raises(WorkspaceNotFound):
        await repository.create_workspace(_DEVELOPMENT, Workspace(workspace_id="other-owner", name="Not authorized"))


@pytest.mark.parametrize("dimensions", [3, 2560])
async def test_exact_synthetic_vectors_preserve_configured_dimensions(
    repository: PostgresPersistence, disposable_database: DisposableDatabase, dimensions: int
) -> None:
    """Exact pgvector cosine search works without a model or an unsupported ANN index."""
    profile_id = f"synthetic-{dimensions}"
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "INSERT INTO workbench.embedding_profiles (profile_id, dimensions, enabled, purpose) "
            "VALUES (%s, %s, true, 'synthetic')",
            (profile_id, dimensions),
        )
    vector = [1.0] + [0.0] * (dimensions - 1)
    chunk = await _publish(
        repository,
        _DEVELOPMENT,
        "vector",
        "Synthetic vector passage",
        embedding=vector,
        embedding_profile_id=profile_id,
        dimensions=dimensions,
    )
    await _publish(repository, _DEVELOPMENT, "null-vector", "Lexical-only passage")
    hits = await repository.vector_search(_DEVELOPMENT, embedding=vector, profile_id=profile_id)
    assert hits[0].chunk.chunk_id == chunk.chunk_id
    assert hits[0].distance == pytest.approx(0.0)
    assert hits[0].chunk.dimensions == dimensions
    with pytest.raises(InvalidEmbedding):
        await repository.vector_search(_DEVELOPMENT, embedding=[1.0], profile_id=profile_id)
    with pytest.raises(InvalidEmbedding):
        await _publish(
            repository,
            _DEVELOPMENT,
            "wrong-dimension",
            "No partial writes",
            embedding=[1.0],
            embedding_profile_id=profile_id,
            dimensions=1,
        )
    assert await repository.get_chunk(_DEVELOPMENT, "chunk-wrong-dimension") is None


async def test_failed_publication_preserves_previous_complete_version(
    repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A failure after writing some new chunks rolls back the whole publication."""
    original = await _publish(repository, _DEVELOPMENT, "atomic", "Original complete version")
    source = Source(workspace_id="development", source_id=original.source_id, title="Replacement")
    version = SourceVersion(
        workspace_id="development", source_id=original.source_id, version_id="replacement", content_hash="replacement"
    )
    first = original.model_copy(update={"version_id": "replacement", "chunk_id": "first-new", "content": "Partial"})
    second = first.model_copy(update={"chunk_id": "trigger-failure"})
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "CREATE FUNCTION workbench.fail_publication_test() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.chunk_id = 'trigger-failure' THEN "
            "RAISE EXCEPTION 'Deliberate publication failure' USING ERRCODE = '23514'; "
            "END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER publication_test BEFORE INSERT ON workbench.chunks "
            "FOR EACH ROW EXECUTE FUNCTION workbench.fail_publication_test()"
        )
    with pytest.raises(RecordConflict):
        await repository.publish_source(_DEVELOPMENT, source=source, version=version, chunks=[first, second])
    assert await repository.get_chunk(_DEVELOPMENT, original.chunk_id) == original
    assert await repository.get_chunk(_DEVELOPMENT, "first-new") is None
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM workbench.source_versions WHERE source_id = %s", (original.source_id,)
        ).fetchone() == (1,)


async def test_explicit_seed_is_idempotent_and_refuses_changed_demo_data(
    empty_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A second seed does not duplicate or overwrite an existing corpus."""
    await seed_development(empty_repository)
    before = await empty_repository.list_sources(_DEVELOPMENT)
    assert 5 <= len(before) <= 10
    await seed_development(empty_repository)
    assert await empty_repository.list_sources(_DEVELOPMENT) == before
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.sources SET title = 'User-owned edit' WHERE workspace_id = 'development'")
    with pytest.raises(SeedConflict):
        await seed_development(empty_repository)


async def test_explicit_seed_refuses_a_non_demo_workspace(repository: PostgresPersistence) -> None:
    """A deterministic seed command never claims or overwrites an unrelated existing workspace."""
    original = await _publish(repository, _DEVELOPMENT, "non-demo", "User-authored stored content")
    with pytest.raises(SeedConflict):
        await seed_development(repository)
    assert await repository.get_chunk(_DEVELOPMENT, original.chunk_id) == original
    assert len(await repository.list_sources(_DEVELOPMENT)) == 1


@pytest.mark.parametrize(
    "corruption", ["DROP EXTENSION vector CASCADE", "UPDATE workbench.alembic_version SET version_num = 'future'"]
)
async def test_schema_or_extension_drift_fails_adapter_readiness(
    repository: PostgresPersistence, disposable_database: DisposableDatabase, corruption: str
) -> None:
    """Readiness rechecks real extension state instead of trusting startup success."""
    await _publish(repository, _DEVELOPMENT, "ready", "Known committed passage")
    assert await repository.readiness(_DEVELOPMENT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(corruption)
    with pytest.raises(SchemaIncompatible):
        await repository.readiness(_DEVELOPMENT)


async def test_cancelled_query_releases_connection_for_a_later_operation(
    repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Cancellation of a genuinely blocked SQL query leaves the pool usable."""
    original = await _publish(repository, _DEVELOPMENT, "cancel", "Cancellation recovery passage")
    with psycopg.connect(disposable_database.admin_dsn) as blocker:
        blocker.execute("LOCK TABLE workbench.chunks IN ACCESS EXCLUSIVE MODE")
        pending = asyncio.create_task(repository.lexical_search(_DEVELOPMENT, query="recovery"))
        await asyncio.sleep(0.05)
        pending.cancel()
        with suppress(asyncio.CancelledError):
            await pending
        assert pending.cancelled()
        blocker.rollback()
    assert await repository.get_chunk(_DEVELOPMENT, original.chunk_id) == original


async def test_terminated_connections_are_replaced_without_losing_persisted_data(
    repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A real backend failure is recovered through the bounded pool's connection checks."""
    original = await _publish(repository, _DEVELOPMENT, "reconnect", "Durable reconnection passage")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        terminated = connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND usename = 'workbench_app'"
        ).fetchall()
        assert terminated
        assert all(row[0] for row in terminated)
    try:
        recovered = await repository.get_chunk(_DEVELOPMENT, original.chunk_id)
    except DatabaseUnavailable as failure:
        assert str(failure) == "The database operation is unavailable."
        recovered = await repository.get_chunk(_DEVELOPMENT, original.chunk_id)
    assert recovered == original
    assert (await repository.lexical_search(_DEVELOPMENT, query="reconnection"))[0].chunk.chunk_id == original.chunk_id


async def test_persistence_logs_correlate_operations_without_content_or_credentials(
    repository: PostgresPersistence, disposable_database: DisposableDatabase, caplog: pytest.LogCaptureFixture
) -> None:
    """Real database activity emits operation metadata while omitting sensitive inputs."""
    caplog.set_level(logging.INFO, logger="workbench.persistence")
    context = WorkspaceContext(workspace_id="development", trace_id="safe-test-trace")
    content = "Private-passage-sentinel-2026"
    await _publish(repository, context, "logging", content)
    await repository.lexical_search(context, query=content)
    records = [record for record in caplog.records if record.name == "workbench.persistence"]
    assert records
    for record in records:
        metadata = json.loads(record.getMessage())
        assert metadata["trace_id"] == context.trace_id
        assert metadata["workspace_id"] == "development"
        assert metadata["duration_ms"] >= 0
        assert record.exc_info is None
    log_output = "\n".join(record.getMessage() for record in records)
    redacted = content not in log_output and disposable_database.app_dsn not in log_output
    assert redacted


async def test_privileged_connection_is_not_accepted_as_an_application_pool(
    disposable_database: DisposableDatabase,
) -> None:
    """Administrator credentials cannot silently bypass the adapter's RLS boundary."""
    migrate(disposable_database.admin_dsn)
    privileged = PostgresPersistence(disposable_database.admin_dsn)
    try:
        with pytest.raises(SchemaIncompatible):
            await privileged.start()
    finally:
        await privileged.close()

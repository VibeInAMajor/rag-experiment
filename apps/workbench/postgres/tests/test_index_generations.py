"""Durable workspace revisions and concurrent snapshot invariants on real PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from psycopg import AsyncConnection
from sqlalchemy import text

from apps.workbench.persistence.models import (
    Chunk,
    CorpusNotReady,
    IndexGeneration,
    RecordConflict,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.postgres import db_migrations
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.postgres.tests.test_ingestion_persistence import _complete, _created, _request
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="index-generation-test")
_FOREIGN = WorkspaceContext(workspace_id="foreign")


@pytest_asyncio.fixture(loop_scope="function")
async def index_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Migrate only a fixture-owned database and access it through the restricted app role."""
    db_migrations.migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        for context in (_CONTEXT, _FOREIGN):
            await repository.create_workspace(context, Workspace(workspace_id=context.workspace_id, name="Test"))
        yield repository
    finally:
        await repository.close()


async def _publish(repository: PostgresPersistence, identifier: str, *, source_id: str = "source") -> None:
    source = Source(workspace_id="development", source_id=source_id, title="Revision test")
    version = SourceVersion(
        workspace_id="development", source_id=source_id, version_id=f"version-{identifier}", content_hash=identifier
    )
    chunk = Chunk(
        workspace_id="development",
        source_id=source_id,
        version_id=version.version_id,
        chunk_id=f"chunk-{identifier}",
        title=source.title,
        content=f"sharedterm {identifier}",
        content_hash=identifier,
    )
    await repository.publish_source(_CONTEXT, source=source, version=version, chunks=[chunk])


async def test_publication_advances_once_and_persists_in_another_pool(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Replacement advances one generation and retains old chunks without exposing them."""
    repository = index_repository
    empty = await repository.current_index_generation(_CONTEXT)
    assert empty.generation_id == 0 and empty.active_chunk_count == 0
    await _publish(repository, "first")
    first = await repository.current_index_generation(_CONTEXT)
    assert first.generation_id == 1 and first.active_source_count == first.active_chunk_count == 1
    await _publish(repository, "second")
    second = await repository.current_index_generation(_CONTEXT)
    assert second.generation_id == 2 and second.previous_generation == first.generation_id
    assert second.corpus_revision != first.corpus_revision
    assert second.active_chunk_count == 1
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM workbench.index_generations WHERE workspace_id='development'"
        ).fetchone() == (3,)
        assert connection.execute("SELECT count(*) FROM workbench.chunks").fetchone() == (2,)
    other = PostgresPersistence(disposable_database.app_dsn)
    await other.start()
    try:
        assert await other.current_index_generation(_CONTEXT) == second
        hit = (await other.lexical_search_snapshot(_CONTEXT, query="sharedterm")).hits[0]
        assert hit.chunk.version_id == "version-second"
        assert hit.score_type == "postgres_ts_rank_cd"
    finally:
        await other.close()


async def test_ingestion_replay_and_verified_unchanged_preserve_generation(
    index_repository: PostgresPersistence,
) -> None:
    """Terminal retry and content-identical replacement retain the committed revision."""
    repository = index_repository
    initial = await _created(repository)
    generation = await repository.current_index_generation(_CONTEXT)
    assert initial.corpus_revision == generation.corpus_revision
    async with repository.reserve_ingestion(_CONTEXT, **_request("initial_create", "originaluniqueterm")) as replay:
        assert replay.job == initial and not replay.newly_reserved
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "unchanged_revision",
            "originaluniqueterm",
            source_id=initial.source_id,
            expected=initial.effective_version_id,
        ),
    ) as reservation:
        unchanged = await _complete(repository, reservation, "originaluniqueterm")
    assert unchanged.outcome == "unchanged"
    assert unchanged.corpus_revision == generation.corpus_revision
    assert await repository.current_index_generation(_CONTEXT) == generation


async def test_failed_publication_rolls_back_generation_and_can_retry(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A mid-publication database failure cannot commit a revision or poison its retry."""
    repository = index_repository
    await _publish(repository, "initial")
    before = await repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "CREATE FUNCTION workbench.reject_index_test() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.chunk_id='chunk-retry' THEN RAISE EXCEPTION 'deliberate failure' "
            "USING ERRCODE='23514'; END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER reject_index_test BEFORE INSERT ON workbench.chunks "
            "FOR EACH ROW EXECUTE FUNCTION workbench.reject_index_test()"
        )
    with pytest.raises(RecordConflict):
        await _publish(repository, "retry")
    assert await repository.current_index_generation(_CONTEXT) == before
    assert (await repository.lexical_search(_CONTEXT, query="sharedterm"))[0].chunk.version_id == "version-initial"
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("DROP TRIGGER reject_index_test ON workbench.chunks")
    await _publish(repository, "retry")
    assert (await repository.current_index_generation(_CONTEXT)).generation_id == before.generation_id + 1


async def test_concurrent_publications_are_serialized_per_workspace(index_repository: PostgresPersistence) -> None:
    """Independent sources cannot lose a workspace generation update."""
    repository = index_repository
    await asyncio.gather(
        _publish(repository, "concurrent-a", source_id="source-a"),
        _publish(repository, "concurrent-b", source_id="source-b"),
    )
    generation = await repository.current_index_generation(_CONTEXT)
    assert generation.generation_id == 2 and generation.active_source_count == generation.active_chunk_count == 2
    assert {hit.chunk.source_id for hit in await repository.lexical_search(_CONTEXT, query="sharedterm")} == {
        "source-a",
        "source-b",
    }


async def test_unmanaged_other_source_write_cannot_be_cleared_by_publication(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rogue update waits for publication, then leaves its own source mutation dirty."""
    repository = index_repository
    await _publish(repository, "source-a-initial", source_id="source-a")
    await _publish(repository, "source-b-initial", source_id="source-b")
    checked = asyncio.Event()
    proceed = asyncio.Event()
    original = repository._prepare_generation

    async def pause_after_precheck(connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> bool:
        result = await original(connection, context)
        checked.set()
        await asyncio.wait_for(proceed.wait(), timeout=10)
        return result

    monkeypatch.setattr(repository, "_prepare_generation", pause_after_precheck)
    publication = asyncio.create_task(_publish(repository, "source-a-replacement", source_id="source-a"))
    async with await psycopg.AsyncConnection.connect(disposable_database.admin_dsn) as rogue_connection:
        try:
            await asyncio.wait_for(checked.wait(), timeout=10)
            rogue_update = asyncio.create_task(
                rogue_connection.execute(
                    "UPDATE workbench.chunks SET content='unmanaged write' WHERE chunk_id='chunk-source-b-initial'"
                )
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(rogue_update), timeout=0.2)
            with psycopg.connect(disposable_database.admin_dsn) as observer:
                assert observer.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (rogue_connection.info.backend_pid,)
                ).fetchone() == ("Lock",)
        finally:
            proceed.set()
        await asyncio.wait_for(publication, timeout=10)
        await asyncio.wait_for(rogue_update, timeout=10)
    with pytest.raises(CorpusNotReady):
        await repository.current_index_generation(_CONTEXT)
    with pytest.raises(CorpusNotReady):
        await repository.lexical_search_snapshot(_CONTEXT, query="unmanaged")


async def test_search_pins_manifest_and_hits_across_a_concurrent_commit(
    index_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A committed replacement between metadata and ranking cannot mix generations."""
    repository = index_repository
    await _publish(repository, "before")
    before = await repository.current_index_generation(_CONTEXT)
    observed = asyncio.Event()
    proceed = asyncio.Event()
    original = repository._index_generation

    async def paused_read(connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> IndexGeneration:
        generation = await original(connection, context)
        if not observed.is_set():
            observed.set()
            await asyncio.wait_for(proceed.wait(), timeout=10)
        return generation

    monkeypatch.setattr(repository, "_index_generation", paused_read)
    search = asyncio.create_task(repository.lexical_search_snapshot(_CONTEXT, query="sharedterm"))
    try:
        await asyncio.wait_for(observed.wait(), timeout=10)
        await _publish(repository, "after")
    finally:
        proceed.set()
    result = await asyncio.wait_for(search, timeout=10)
    assert result.corpus_revision == before.corpus_revision
    assert [hit.chunk.version_id for hit in result.hits] == ["version-before"]
    monkeypatch.setattr(repository, "_index_generation", original)
    current = await repository.lexical_search_snapshot(_CONTEXT, query="sharedterm")
    assert current.corpus_revision != before.corpus_revision
    assert [hit.chunk.version_id for hit in current.hits] == ["version-after"]


async def test_search_readiness_and_ingestion_do_not_enumerate_the_corpus(
    index_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Search, readiness and successful ingestion use the constant metadata path."""

    async def forbidden_scan(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("The persisted fast path called the corpus enumeration path")

    monkeypatch.setattr(index_repository, "_corpus_snapshot", forbidden_scan)
    monkeypatch.setattr(index_repository, "_legacy_corpus_snapshot", forbidden_scan)
    job = await _created(index_repository)
    assert job.corpus_revision == (await index_repository.current_index_generation(_CONTEXT)).corpus_revision
    assert (await index_repository.readiness(_CONTEXT)).chunk_count == 1
    assert (await index_repository.lexical_search_snapshot(_CONTEXT, query="originaluniqueterm")).hits


async def test_manifest_rls_and_application_write_privileges(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Manifest rows remain scoped and their counters cannot be forged by the app role."""
    await _publish(index_repository, "isolation")
    with psycopg.connect(disposable_database.app_dsn) as connection:
        connection.execute("SELECT set_config('workbench.workspace_id','foreign',true)")
        for table in ("corpus_index_state", "index_generations", "corpus_source_state"):
            rows = connection.execute(
                f"SELECT workspace_id FROM workbench.{table} WHERE workspace_id='development'"
            ).fetchall()
            assert rows == []
    with (
        psycopg.connect(disposable_database.app_dsn) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("UPDATE workbench.corpus_index_state SET generation_id=generation_id+1")
    assert (await index_repository.current_index_generation(_FOREIGN)).active_chunk_count == 0


async def test_out_of_band_source_mutation_invalidates_snapshot(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """An audited manifest never stays ready after an unmanaged active-row mutation."""
    await _publish(index_repository, "drift")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.chunks SET content='unaudited mutation' WHERE chunk_id='chunk-drift'")
    with pytest.raises(CorpusNotReady):
        await index_repository.current_index_generation(_CONTEXT)
    with pytest.raises(CorpusNotReady):
        await index_repository.lexical_search_snapshot(_CONTEXT, query="unaudited")


async def test_staged_only_version_keeps_committed_active_generation(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Preparing an unpublished source version cannot invalidate active retrieval."""
    await _publish(index_repository, "active")
    before = await index_repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "INSERT INTO workbench.source_versions(workspace_id,source_id,version_id,status,content_hash) "
            "VALUES('development','source','future-staged','staged','new')"
        )
    assert await index_repository.current_index_generation(_CONTEXT) == before


async def test_stale_or_malformed_generation_selection_fails_closed(index_repository: PostgresPersistence) -> None:
    """The adapter cannot imply that retained metadata permits historical chunk retrieval."""
    await _publish(index_repository, "selected")
    current = await index_repository.current_index_generation(_CONTEXT)
    assert (
        await index_repository.current_index_generation(_CONTEXT, expected_generation_id=current.generation_id)
        == current
    )
    with pytest.raises(RecordConflict):
        await index_repository.current_index_generation(_CONTEXT, expected_generation_id=0)
    with pytest.raises(ValueError):
        await index_repository.current_index_generation(_CONTEXT, expected_generation_id=-1)


async def test_state_corruption_and_immutable_ledger_are_detected(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A ledger mismatch never qualifies counters, and committed generation history rejects mutation."""
    await _publish(index_repository, "corruption")
    with psycopg.connect(disposable_database.admin_dsn) as connection, pytest.raises(psycopg.Error):
        connection.execute("UPDATE workbench.index_generations SET active_chunk_count=99")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "UPDATE workbench.corpus_index_state SET active_chunk_count=99 WHERE workspace_id='development'"
        )
    with pytest.raises(CorpusNotReady):
        await index_repository.current_index_generation(_CONTEXT)


async def test_populated_0002_backfill_preserves_records_and_migration_checksums(
    disposable_database: DisposableDatabase,
) -> None:
    """The additive migration backfills existing active rows without altering historical SQL."""
    database = disposable_database
    with db_migrations._connection(database.admin_dsn, transaction=True) as connection:
        db_migrations._ensure_role(connection)
        connection.execute(text("CREATE SCHEMA workbench"))
        command.upgrade(db_migrations._configuration(connection), "0002")
        db_migrations._grant_application(connection)
    legacy = PostgresPersistence(database.app_dsn, snapshot_mode="legacy")
    await legacy.start()
    try:
        await legacy.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Existing workspace"))
        await _publish(legacy, "before-migration")
        before = await legacy.corpus_snapshot(_CONTEXT)
    finally:
        await legacy.close()
    checksums = [db_migrations.migration_checksum(revision=revision) for revision in ("0001", "0002")]
    assert db_migrations.migrate(database.admin_dsn).compatible
    assert checksums == [db_migrations.migration_checksum(revision=revision) for revision in ("0001", "0002")]
    repository = PostgresPersistence(database.app_dsn)
    await repository.start()
    try:
        after = await repository.corpus_snapshot(_CONTEXT)
        generation = await repository.current_index_generation(_CONTEXT)
        assert generation.generation_id == 1
        assert after.documents == before.documents
        assert after.chunk_count == before.chunk_count == generation.active_chunk_count
        assert after.content_bytes == before.content_bytes == generation.content_bytes
        assert (await repository.lexical_search(_CONTEXT, query="sharedterm"))[
            0
        ].chunk.version_id == "version-before-migration"
    finally:
        await repository.close()

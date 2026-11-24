"""Offline repair and explicit rollback cannot silently qualify a dirty corpus."""

import asyncio

import httpx
import psycopg
import pytest
from psycopg import sql

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.persistence.models import CorpusNotReady, SchemaIncompatible
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.postgres.postgres_indexes import reconcile_index
from apps.workbench.postgres.tests.test_index_generations import _CONTEXT, _publish
from apps.workbench.postgres.tests.test_index_generations import index_repository as index_repository
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]


def _stored_state(database: DisposableDatabase) -> tuple[int, str]:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT generation_id,status FROM workbench.corpus_index_state WHERE workspace_id='development'"
        ).fetchone()
        assert row is not None
        return row


async def test_dirty_manifest_disables_http_and_failed_publication_does_not_clear_it(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Unmanaged metadata edits disable readiness/search and cannot ride along with a later write."""
    repository = index_repository
    await _publish(repository, "dirty-http")
    generation = await repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            'UPDATE workbench.chunks SET metadata=metadata||\'{"private":"repair-secret"}\'::jsonb '
            "WHERE chunk_id='chunk-dirty-http'"
        )
    assert _stored_state(disposable_database) == (generation.generation_id, "dirty")
    with pytest.raises(CorpusNotReady):
        await _publish(repository, "must-not-publish", source_id="another-source")
    assert _stored_state(disposable_database) == (generation.generation_id, "dirty")
    app = create_app(settings=ApiSettings(), persistence=repository)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        readiness = await client.get("/api/v1/health/ready")
        assert readiness.status_code == 503
        assert (await client.get("/api/v1/capabilities")).json()["profiles"] == []
        search = await client.post(
            "/api/v1/workspaces/development/search",
            json={
                "query": "sharedterm",
                "top_k": 5,
                "profile_id": "postgres-fts-baseline",
                "expected_profile_revision": "postgres-fts-baseline-r1",
            },
        )
        assert search.status_code == 503
        for response in (readiness, search):
            payload = response.json()
            assert payload["request_id"] == response.headers["x-request-id"]
            assert payload["trace_id"]
            assert "results" not in payload
            assert "repair-secret" not in response.text
    assert _stored_state(disposable_database) == (generation.generation_id, "dirty")


async def test_reconciliation_requires_explicit_repair_and_preserves_ranked_rows(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Check-only leaves drift untouched; one repair advances once and the next is a no-op."""
    repository = index_repository
    await _publish(repository, "repair")
    generation = await repository.current_index_generation(_CONTEXT)
    hits = await repository.lexical_search(_CONTEXT, query="sharedterm")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.sources SET title='Operator metadata edit' WHERE source_id='source'")
    checked = await asyncio.to_thread(reconcile_index, disposable_database.admin_dsn, workspace_id="development")
    assert checked["consistent"] is False and checked["repaired"] is False
    assert _stored_state(disposable_database) == (generation.generation_id, "dirty")
    with pytest.raises(CorpusNotReady):
        await repository.current_index_generation(_CONTEXT)
    repaired = await asyncio.to_thread(
        reconcile_index, disposable_database.admin_dsn, workspace_id="development", repair=True
    )
    assert repaired["consistent"] is False and repaired["repaired"] is True
    current = await repository.current_index_generation(_CONTEXT)
    assert current.generation_id == generation.generation_id + 1
    assert current.previous_generation == generation.generation_id
    assert current.corpus_revision != generation.corpus_revision
    assert current.active_chunk_count == generation.active_chunk_count
    assert await repository.lexical_search(_CONTEXT, query="sharedterm") == hits
    repeated = await asyncio.to_thread(
        reconcile_index, disposable_database.admin_dsn, workspace_id="development", repair=True
    )
    assert repeated["consistent"] is True and repeated["repaired"] is False
    assert await repository.current_index_generation(_CONTEXT) == current
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.chunks").fetchone() == (1,)
        assert connection.execute(
            "SELECT event_kind FROM workbench.index_generations WHERE workspace_id='development' AND generation_id=%s",
            (current.generation_id,),
        ).fetchone() == ("reconciliation",)


async def test_reconciliation_refuses_application_credentials(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """The restricted application role cannot run an offline repair command."""
    await _publish(index_repository, "restricted")
    before = await index_repository.current_index_generation(_CONTEXT)
    with pytest.raises(ValueError, match="separate migration administrator"):
        await asyncio.to_thread(reconcile_index, disposable_database.app_dsn, workspace_id="development", repair=True)
    assert await index_repository.current_index_generation(_CONTEXT) == before


@pytest.mark.parametrize(
    ("table", "trigger"), [("chunks", "dirty_chunk_index"), ("index_generations", "immutable_index_generation")]
)
async def test_disabled_generation_protection_refuses_snapshot(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase, table: str, trigger: str
) -> None:
    """A disabled dirty/immutability trigger is schema drift even when counts still match."""
    await _publish(index_repository, "protection")
    before = await index_repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE workbench.{} DISABLE TRIGGER {}").format(
                sql.Identifier(table), sql.Identifier(trigger)
            )
        )
    with pytest.raises(CorpusNotReady):
        await index_repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE workbench.{} ENABLE TRIGGER {}").format(sql.Identifier(table), sql.Identifier(trigger))
        )
    assert await index_repository.current_index_generation(_CONTEXT) == before


async def test_stale_manifest_pointer_cannot_requalify_an_older_valid_generation(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A valid historical ledger row cannot masquerade as the latest workspace state."""
    await _publish(index_repository, "stale-pointer")
    before = await index_repository.current_index_generation(_CONTEXT)
    assert before.generation_id == 1
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("DELETE FROM workbench.corpus_index_state WHERE workspace_id='development'")
        connection.execute(
            "INSERT INTO workbench.corpus_index_state SELECT * FROM workbench.index_generations "
            "WHERE workspace_id='development' AND generation_id=0"
        )
    assert _stored_state(disposable_database) == (0, "ready")
    with pytest.raises(CorpusNotReady):
        await index_repository.current_index_generation(_CONTEXT)
    with pytest.raises(CorpusNotReady):
        await index_repository.lexical_search_snapshot(_CONTEXT, query="sharedterm")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT max(generation_id) FROM workbench.index_generations WHERE workspace_id='development'"
        ).fetchone() == (before.generation_id,)


async def test_reconciliation_refuses_repair_while_generation_protection_is_disabled(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Offline repair never certifies a schema that would miss the next unmanaged mutation."""
    await _publish(index_repository, "disabled-repair")
    before = await index_repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("ALTER TABLE workbench.chunks DISABLE TRIGGER dirty_chunk_index")
    with pytest.raises(SchemaIncompatible, match="current compatible migration"):
        await asyncio.to_thread(reconcile_index, disposable_database.admin_dsn, workspace_id="development", repair=True)
    assert _stored_state(disposable_database) == (before.generation_id, "ready")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("ALTER TABLE workbench.chunks ENABLE TRIGGER dirty_chunk_index")
    assert await index_repository.current_index_generation(_CONTEXT) == before


async def test_committed_ledger_rows_are_immutable_even_for_administrator(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """An accidental administrator edit cannot rewrite committed revision history."""
    await _publish(index_repository, "immutable")
    before = await index_repository.current_index_generation(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection, pytest.raises(psycopg.errors.RaiseException):
        connection.execute(
            "UPDATE workbench.index_generations SET content_bytes=content_bytes+1 WHERE workspace_id='development'"
        )
    assert await index_repository.current_index_generation(_CONTEXT) == before


async def test_explicit_legacy_reads_keep_writes_generation_aware(
    index_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Rollback may scan real data, but cannot disable generation maintenance or heal dirty writes."""
    await _publish(index_repository, "legacy-start")
    before = await index_repository.current_index_generation(_CONTEXT)
    legacy = PostgresPersistence(disposable_database.app_dsn, snapshot_mode="legacy")
    await legacy.start()
    try:
        assert (await legacy.lexical_search(_CONTEXT, query="sharedterm"))[0].chunk.version_id == "version-legacy-start"
        await _publish(legacy, "legacy-write")
        after = await index_repository.current_index_generation(_CONTEXT)
        assert after.generation_id == before.generation_id + 1
        assert (await index_repository.lexical_search(_CONTEXT, query="sharedterm"))[
            0
        ].chunk.version_id == "version-legacy-write"
        with psycopg.connect(disposable_database.admin_dsn) as connection:
            connection.execute(
                "UPDATE workbench.chunks SET content='unmanagedterm' WHERE chunk_id='chunk-legacy-write'"
            )
        assert (await legacy.lexical_search(_CONTEXT, query="unmanagedterm"))[0].chunk.chunk_id == "chunk-legacy-write"
        with pytest.raises(CorpusNotReady):
            await _publish(legacy, "legacy-must-refuse", source_id="another-source")
        assert _stored_state(disposable_database) == (after.generation_id, "dirty")
    finally:
        await legacy.close()

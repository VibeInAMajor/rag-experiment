"""Durable ingestion invariants run only in fixture-owned disposable PostgreSQL databases."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text

from apps.workbench.api import db_migrations, postgres_ingestion
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.persistence import (
    Chunk,
    CorpusLimitExceeded,
    DatabaseUnavailable,
    IdempotencyConflict,
    IngestionInProgress,
    IngestionJob,
    IngestionOwnershipLost,
    IngestionTiming,
    RecordConflict,
    Source,
    SourceVersion,
    UploadReservation,
    VersionConflict,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.postgres_indexes import reconcile_index
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development")
_FOREIGN = WorkspaceContext(workspace_id="foreign")
_PROFILE = "a" * 64


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request(key: str, content: str, *, source_id: str | None = None, expected: str | None = None) -> dict[str, Any]:
    return {
        "idempotency_key": key,
        "request_fingerprint": _sha(f"{content}:{source_id}:{expected}"),
        "source_content_sha256": _sha(content),
        "source_id": source_id,
        "expected_active_version_id": expected,
    }


@pytest_asyncio.fixture(loop_scope="function")
async def ingestion_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Create head schema and scoped app-role access without touching the development database."""
    db_migrations.migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        for context in (_CONTEXT, _FOREIGN):
            await repository.create_workspace(
                context, Workspace(workspace_id=context.workspace_id, name="Test workspace")
            )
        yield repository
    finally:
        await repository.close()


async def _stage(repository: PostgresPersistence, reservation: UploadReservation) -> str:
    assert reservation.owner_token is not None
    for stage in ("parsing", "chunking", "publishing"):
        await repository.transition_ingestion(
            _CONTEXT, job_id=reservation.job.job_id, owner_token=reservation.owner_token, stage=stage
        )
    return reservation.owner_token


def _records(
    reservation: UploadReservation, content: str, *, count: int = 1
) -> tuple[Source, SourceVersion, list[Chunk]]:
    source = Source(workspace_id="development", source_id=reservation.job.source_id, title="Uploaded source.txt")
    version = SourceVersion(
        workspace_id="development",
        source_id=source.source_id,
        version_id=reservation.job.reserved_version_id,
        content_hash=_sha(content),
        metadata={"processing_profile_fingerprint": _PROFILE},
    )
    chunks = [
        Chunk(
            workspace_id="development",
            source_id=source.source_id,
            version_id=version.version_id,
            chunk_id=f"{version.version_id}-{count - index:03}",
            title=source.title,
            content=content,
            content_hash=_sha(content),
            metadata={"ordinal": index},
        )
        for index in range(count)
    ]
    return source, version, chunks


async def _complete(
    repository: PostgresPersistence, reservation: UploadReservation, content: str, *, count: int = 1
) -> IngestionJob:
    owner = await _stage(repository, reservation)
    source, version, chunks = _records(reservation, content, count=count)
    return await repository.complete_ingestion_with_publication(
        _CONTEXT,
        job_id=reservation.job.job_id,
        owner_token=owner,
        source=source,
        version=version,
        chunks=chunks,
        stages=[IngestionTiming(stage="parsing", duration_ms=1.0), IngestionTiming(stage="chunking", duration_ms=2.0)],
    )


async def _created(
    repository: PostgresPersistence, content: str = "originaluniqueterm", *, count: int = 1
) -> IngestionJob:
    async with repository.reserve_ingestion(_CONTEXT, **_request("initial_create", content)) as reservation:
        return await _complete(repository, reservation, content, count=count)


async def test_reservation_has_stable_opaque_ids_but_no_source_stub(ingestion_repository: PostgresPersistence) -> None:
    """A durable job exists before parsing without making an empty source visible to lexical discovery."""
    repository = ingestion_repository
    assert await repository.ingestion_ready(_CONTEXT)
    async with repository.reserve_ingestion(_CONTEXT, **_request("reserved_once", "text")) as reservation:
        assert reservation.newly_reserved and reservation.owner_token
        assert reservation.job.status == reservation.job.stage == "pending"
        assert reservation.job.effective_version_id is None
        assert await repository.list_sources(_CONTEXT) == []
        assert await repository.get_source_detail(_CONTEXT, source_id=reservation.job.source_id) is None
        assert await repository.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id) == reservation.job


async def test_publication_and_job_completion_are_one_durable_outcome(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Committed job, actual chunks, raw byte hash and lexical results survive another pool."""
    repository = ingestion_repository
    job = await _created(repository)
    assert job.status == job.stage == "completed" and job.outcome == "created"
    assert job.effective_version_id == job.reserved_version_id and job.chunk_count == 1
    assert [timing.stage for timing in job.stages] == ["parsing", "chunking", "publication"]
    assert job.stages[-1].duration_ms >= 0
    hits = await repository.lexical_search(_CONTEXT, query="originaluniqueterm")
    assert hits[0].chunk.source_id == job.source_id
    assert hits[0].chunk.version_id == job.effective_version_id
    assert hits[0].chunk.embedding is hits[0].chunk.page is None
    other = PostgresPersistence(disposable_database.app_dsn)
    await other.start()
    try:
        assert await other.get_ingestion_job(_CONTEXT, job_id=job.job_id) == job
        assert (await other.corpus_snapshot(_CONTEXT)).corpus_revision == job.corpus_revision
    finally:
        await other.close()


async def test_same_key_replay_and_conflicting_replay_do_not_duplicate_rows(
    ingestion_repository: PostgresPersistence,
) -> None:
    """The database owns immutable key/request identity and never reruns a terminal reservation."""
    repository = ingestion_repository
    completed = await _created(repository)
    async with repository.reserve_ingestion(_CONTEXT, **_request("initial_create", "originaluniqueterm")) as replay:
        assert replay.job == completed and not replay.newly_reserved and replay.owner_token is None
    with pytest.raises(IdempotencyConflict):
        async with repository.reserve_ingestion(_CONTEXT, **_request("initial_create", "different")):
            pytest.fail("Conflicting request was accepted")
    assert len(await repository.list_sources(_CONTEXT)) == 1


async def test_replay_precedes_stale_expected_version_validation(ingestion_repository: PostgresPersistence) -> None:
    """A once-successful guarded request remains replayable after another successful replacement."""
    repository = ingestion_repository
    initial = await _created(repository)
    first_request = _request(
        "update_first", "newfirstterm", source_id=initial.source_id, expected=initial.effective_version_id
    )
    async with repository.reserve_ingestion(_CONTEXT, **first_request) as reservation:
        updated = await _complete(repository, reservation, "newfirstterm")
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "update_second", "newsecondterm", source_id=initial.source_id, expected=updated.effective_version_id
        ),
    ) as reservation:
        await _complete(repository, reservation, "newsecondterm")
    async with repository.reserve_ingestion(_CONTEXT, **first_request) as replay:
        assert replay.job == updated
        assert not replay.newly_reserved


async def test_unchanged_content_keeps_current_version_and_actual_chunk_count(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """An unchanged job reports active count while inserting zero versions or chunks."""
    repository = ingestion_repository
    initial = await _created(repository, count=3)
    before = await repository.corpus_snapshot(_CONTEXT)
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "unchanged_key", "originaluniqueterm", source_id=initial.source_id, expected=initial.effective_version_id
        ),
    ) as reservation:
        unchanged = await _complete(repository, reservation, "originaluniqueterm")
    assert unchanged.outcome == "unchanged" and unchanged.chunk_count == 3
    assert unchanged.effective_version_id == initial.effective_version_id
    assert before == await repository.corpus_snapshot(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.source_versions").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM workbench.chunks").fetchone() == (3,)


async def test_live_owner_blocks_same_key_and_is_not_failed_by_another_pool_recovery(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Startup recovery uses actual advisory ownership rather than assuming another process is stale."""
    repository = ingestion_repository
    other = PostgresPersistence(disposable_database.app_dsn)
    await other.start()
    try:
        request = _request("live_owner_key", "text")
        async with repository.reserve_ingestion(_CONTEXT, **request) as reservation:
            assert await other.recover_ingestions(_CONTEXT) == 0
            with pytest.raises(IngestionInProgress) as busy:
                async with other.reserve_ingestion(_CONTEXT, **request):
                    pytest.fail("Two live owners were admitted")
            assert busy.value.job_id == reservation.job.job_id
            visible = await other.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id)
            assert visible is not None and visible.status == "pending"
    finally:
        await other.close()


async def test_abandoned_job_recovers_terminally_and_old_owner_cannot_publish(
    ingestion_repository: PostgresPersistence,
) -> None:
    """Releasing the owning session leaves diagnosable durable state without any content replay."""
    repository = ingestion_repository
    async with repository.reserve_ingestion(_CONTEXT, **_request("abandoned_key", "text")) as reservation:
        owner = reservation.owner_token
        assert owner is not None
        await repository.transition_ingestion(
            _CONTEXT, job_id=reservation.job.job_id, owner_token=owner, stage="parsing"
        )
    with pytest.raises(IngestionOwnershipLost):
        await repository.transition_ingestion(
            _CONTEXT, job_id=reservation.job.job_id, owner_token=owner, stage="chunking"
        )
    assert await repository.recover_ingestions(_CONTEXT) == 1
    failed = await repository.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id)
    assert failed is not None and failed.status == "failed" and failed.stage == "parsing"
    assert failed.error_code == "INTERRUPTED" and failed.retryable
    async with repository.reserve_ingestion(_CONTEXT, **_request("abandoned_key", "text")) as replay:
        assert replay.job == failed and not replay.newly_reserved
    assert await repository.list_sources(_CONTEXT) == []


async def test_guarded_competing_updates_have_one_winner(ingestion_repository: PostgresPersistence) -> None:
    """Distinct requests may parse concurrently but cannot both replace the same expected version."""
    repository = ingestion_repository
    initial = await _created(repository)
    first = _request(
        "competing_first", "winnerterm", source_id=initial.source_id, expected=initial.effective_version_id
    )
    second = _request(
        "competing_second", "loserterm", source_id=initial.source_id, expected=initial.effective_version_id
    )
    async with (
        repository.reserve_ingestion(_CONTEXT, **first) as a,
        repository.reserve_ingestion(_CONTEXT, **second) as b,
    ):
        owner_a, owner_b = await _stage(repository, a), await _stage(repository, b)
        source_a, version_a, chunks_a = _records(a, "winnerterm")
        source_b, version_b, chunks_b = _records(b, "loserterm")
        arguments = [(a, owner_a, source_a, version_a, chunks_a), (b, owner_b, source_b, version_b, chunks_b)]
        results = await asyncio.gather(
            *(
                repository.complete_ingestion_with_publication(
                    _CONTEXT, job_id=r.job.job_id, owner_token=o, source=s, version=v, chunks=c, stages=[]
                )
                for r, o, s, v, c in arguments
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, IngestionJob) for result in results) == 1
        assert sum(isinstance(result, VersionConflict) for result in results) == 1
        loser = 0 if isinstance(results[0], VersionConflict) else 1
        failed = await repository.fail_ingestion(
            _CONTEXT,
            job_id=arguments[loser][0].job.job_id,
            owner_token=arguments[loser][1],
            error_code="VERSION_CONFLICT",
            retryable=False,
            stages=[],
        )
        assert failed.status == "failed"
    assert await repository.lexical_search(_CONTEXT, query="originaluniqueterm") == []
    assert bool(await repository.lexical_search(_CONTEXT, query="winnerterm")) != bool(
        await repository.lexical_search(_CONTEXT, query="loserterm")
    )


async def test_failure_after_real_publication_sql_rolls_back_source_and_job(
    ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fault after the shared writer cannot expose new chunks or leave a false completed job."""
    repository = ingestion_repository
    initial = await _created(repository)
    original = repository._publish

    async def broken(*args: Any, **kwargs: Any) -> None:
        await original(*args, **kwargs)
        raise DatabaseUnavailable("Publication interrupted.")

    monkeypatch.setattr(repository, "_publish", broken)
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request("atomic_failure", "partialterm", source_id=initial.source_id, expected=initial.effective_version_id),
    ) as reservation:
        with pytest.raises(DatabaseUnavailable):
            await _complete(repository, reservation, "partialterm")
        visible = await repository.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id)
        assert visible is not None and visible.status == "publishing"
        assert reservation.owner_token is not None
        failed = await repository.fail_ingestion(
            _CONTEXT,
            job_id=reservation.job.job_id,
            owner_token=reservation.owner_token,
            error_code="DEPENDENCY_UNAVAILABLE",
            retryable=True,
            stages=[
                IngestionTiming(stage="parsing", duration_ms=1.0),
                IngestionTiming(stage="chunking", duration_ms=1.0),
                IngestionTiming(stage="publication", duration_ms=1.0),
            ],
        )
        assert failed.status == "failed" and failed.stage == "publishing"
        assert len(failed.stages) == 3
    assert (await repository.lexical_search(_CONTEXT, query="originaluniqueterm"))[
        0
    ].chunk.version_id == initial.effective_version_id
    assert await repository.lexical_search(_CONTEXT, query="partialterm") == []


async def test_jobs_force_rls_without_pool_scope_leakage(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """The application cannot read another scope or use an unscoped pooled session to inspect jobs."""
    repository = ingestion_repository
    job = await _created(repository)
    assert await repository.get_ingestion_job(_FOREIGN, job_id=job.job_id) is None
    assert await repository.get_source_detail(_FOREIGN, source_id=job.source_id) is None
    assert await repository.list_active_chunks(_FOREIGN, source_id=job.source_id) is None
    with psycopg.connect(disposable_database.app_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.ingestion_jobs").fetchone() == (0,)
        connection.execute("SELECT set_config('workbench.workspace_id','foreign',true)")
        assert connection.execute("SELECT count(*) FROM workbench.ingestion_jobs").fetchone() == (0,)
    with (
        psycopg.connect(disposable_database.app_dsn) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("DELETE FROM workbench.ingestion_jobs")


async def test_chunk_pages_use_actual_ordinal_and_reject_stale_or_foreign_anchors(
    ingestion_repository: PostgresPersistence,
) -> None:
    """Hash-like chunk IDs never scramble source order, and cursors cannot cross a source or publication."""
    repository = ingestion_repository
    initial = await _created(repository, count=5)
    page = await repository.list_active_chunks(_CONTEXT, source_id=initial.source_id, limit=2)
    assert page is not None and page.next_after
    assert [item.metadata["ordinal"] for item in page.items] == [0, 1]
    second = await repository.list_active_chunks(
        _CONTEXT,
        source_id=initial.source_id,
        limit=2,
        after_chunk_id=page.next_after,
        expected_corpus_revision=page.corpus_revision,
    )
    assert second is not None and [item.metadata["ordinal"] for item in second.items] == [2, 3]
    with pytest.raises(RecordConflict):
        await repository.list_active_chunks(_CONTEXT, source_id=initial.source_id, after_chunk_id="foreign-chunk")
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "paging_update", "replacementterm", source_id=initial.source_id, expected=initial.effective_version_id
        ),
    ) as reservation:
        await _complete(repository, reservation, "replacementterm")
    with pytest.raises(RecordConflict):
        await repository.list_active_chunks(
            _CONTEXT,
            source_id=initial.source_id,
            after_chunk_id=page.next_after,
            expected_corpus_revision=page.corpus_revision,
        )


async def test_workspace_serialization_prevents_concurrent_corpus_limit_breach(
    ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small controlled test budget proves admission occurs under the same workspace publication lock."""
    repository = ingestion_repository
    monkeypatch.setattr(postgres_ingestion, "_MAX_CORPUS_CHUNKS", 1)
    async with (
        repository.reserve_ingestion(_CONTEXT, **_request("limit_create_a", "firstterm")) as a,
        repository.reserve_ingestion(_CONTEXT, **_request("limit_create_b", "secondterm")) as b,
    ):
        results = await asyncio.gather(
            _complete(repository, a, "firstterm"), _complete(repository, b, "secondterm"), return_exceptions=True
        )
        assert sum(isinstance(result, IngestionJob) for result in results) == 1
        assert sum(isinstance(result, CorpusLimitExceeded) for result in results) == 1
    assert (await repository.corpus_snapshot(_CONTEXT)).chunk_count == 1


async def test_populated_0001_upgrade_preserves_seed_and_lexical_readiness(
    disposable_database: DisposableDatabase,
) -> None:
    """The historical migration is applied as-is, then additive jobs upgrade preserves every corpus identity."""
    with db_migrations._connection(disposable_database.admin_dsn, transaction=True) as connection:
        db_migrations._ensure_role(connection)
        connection.execute(text("CREATE SCHEMA workbench"))
        command.upgrade(db_migrations._configuration(connection), "0001")
        db_migrations._grant_application(connection)
    repository = PostgresPersistence(disposable_database.app_dsn, snapshot_mode="legacy")
    await repository.start()
    try:
        await seed_development(repository)
        before = await repository.corpus_snapshot(_CONTEXT)
        assert len(before.documents) == 8
        assert (await repository.readiness(_CONTEXT)).schema_revision == "0001"
        assert not await repository.ingestion_ready(_CONTEXT)
        checksum = db_migrations.migration_checksum()
        upgraded = db_migrations.migrate(disposable_database.admin_dsn)
        assert upgraded.revision == db_migrations.HEAD_REVISION and upgraded.compatible
        assert db_migrations.migration_checksum() == checksum
        assert await repository.corpus_snapshot(_CONTEXT) == before
        assert (await repository.readiness(_CONTEXT)).schema_revision == db_migrations.HEAD_REVISION
        assert await repository.ingestion_ready(_CONTEXT)
        assert db_migrations.migrate(disposable_database.admin_dsn) == upgraded
    finally:
        await repository.close()


async def test_real_owner_connection_loss_is_fenced_before_recovery(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A dead PostgreSQL session cannot authorize late publication using only a still-live Python token."""
    repository = ingestion_repository
    async with repository.reserve_ingestion(_CONTEXT, **_request("killed_session", "text")) as reservation:
        assert reservation.owner_token is not None
        owner = reservation.owner_token
        pid = repository._ingestion_owners[owner][2]
        with psycopg.connect(disposable_database.admin_dsn) as connection:
            assert connection.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone() == (True,)
        with pytest.raises(IngestionOwnershipLost):
            await repository.transition_ingestion(
                _CONTEXT, job_id=reservation.job.job_id, owner_token=owner, stage="parsing"
            )
        failed = await repository.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id)
        assert failed is not None and failed.error_code == "INTERRUPTED"
        assert await repository.recover_ingestions(_CONTEXT) == 0


async def test_cancellation_releases_owned_lock_for_durable_recovery(ingestion_repository: PostgresPersistence) -> None:
    """Request cancellation cannot return a session to the pool with an unaccounted ingestion lock."""
    repository = ingestion_repository
    entered = asyncio.Event()
    request = _request("cancelled_session", "text")

    async def interrupted() -> None:
        async with repository.reserve_ingestion(_CONTEXT, **request):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(interrupted())
    await asyncio.wait_for(entered.wait(), timeout=3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await repository.recover_ingestions(_CONTEXT) == 1
    async with repository.reserve_ingestion(_CONTEXT, **request) as replay:
        assert not replay.newly_reserved and replay.job.error_code == "INTERRUPTED"


async def test_source_annotations_survive_update_without_reusing_old_local_original(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Upload replacement retains source annotations while original-file pointers stay version-bound."""
    repository = ingestion_repository
    initial = await _created(repository)
    assert initial.effective_version_id is not None
    await repository.register_local_original(
        _CONTEXT,
        source_id=initial.source_id,
        version_id=initial.effective_version_id,
        relative_path="original.txt",
        sha256=_sha("originaluniqueterm"),
    )
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "UPDATE workbench.sources SET metadata='{" + '"annotation":"retained"' + "}'::jsonb WHERE source_id=%s",
            (initial.source_id,),
        )
    # The trusted fixture mutation follows the same explicit repair rule as offline operators.
    await asyncio.to_thread(reconcile_index, disposable_database.admin_dsn, workspace_id="development", repair=True)
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "annotation_update", "replacementterm", source_id=initial.source_id, expected=initial.effective_version_id
        ),
    ) as reservation:
        updated = await _complete(repository, reservation, "replacementterm")
    detail = await repository.get_source_detail(_CONTEXT, source_id=initial.source_id)
    assert detail is not None and detail.version is not None
    assert detail.source.metadata["annotation"] == "retained"
    assert "local_original" not in detail.version.metadata
    assert detail.version.version_id == updated.effective_version_id


async def test_database_enforces_immutable_reservations_and_stage_transitions(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Direct app-role SQL cannot skip parsing or mutate a reserved request fingerprint."""
    repository = ingestion_repository
    async with repository.reserve_ingestion(_CONTEXT, **_request("transition_test", "text")) as reservation:
        for statement in (
            "UPDATE workbench.ingestion_jobs SET status='publishing',stage='publishing' WHERE job_id=%s",
            "UPDATE workbench.ingestion_jobs SET request_fingerprint=repeat('0',64) WHERE job_id=%s",
        ):
            with (
                psycopg.connect(disposable_database.app_dsn) as connection,
                pytest.raises(psycopg.errors.RaiseException),
            ):
                connection.execute("SELECT set_config('workbench.workspace_id','development',true)")
                connection.execute(statement, (reservation.job.job_id,))
        visible = await repository.get_ingestion_job(_CONTEXT, job_id=reservation.job.job_id)
        assert visible == reservation.job


async def test_broken_job_protection_disables_upload_without_breaking_lexical_reads(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Ingestion capability is qualified separately from the unchanged lexical storage contract."""
    repository = ingestion_repository
    await _created(repository)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("ALTER TABLE workbench.ingestion_jobs DISABLE ROW LEVEL SECURITY")
    assert not await repository.ingestion_ready(_CONTEXT)
    assert (await repository.readiness(_CONTEXT)).chunk_count == 1
    assert (await repository.lexical_search(_CONTEXT, query="originaluniqueterm"))[
        0
    ].score_type == "postgres_ts_rank_cd"


@pytest.mark.parametrize("field", ["workspace_id", "source_id"])
async def test_unchanged_publication_still_checks_all_version_references(
    field: str, ingestion_repository: PostgresPersistence
) -> None:
    """The no-write optimization cannot bypass the same reference guards as a changed publication."""
    repository = ingestion_repository
    initial = await _created(repository)
    async with repository.reserve_ingestion(
        _CONTEXT,
        **_request(
            "unchanged_invalid",
            "originaluniqueterm",
            source_id=initial.source_id,
            expected=initial.effective_version_id,
        ),
    ) as reservation:
        owner = await _stage(repository, reservation)
        source, version, chunks = _records(reservation, "originaluniqueterm")
        version = version.model_copy(update={field: "foreign-owner"})
        with pytest.raises(RecordConflict):
            await repository.complete_ingestion_with_publication(
                _CONTEXT,
                job_id=reservation.job.job_id,
                owner_token=owner,
                source=source,
                version=version,
                chunks=chunks,
                stages=[],
            )
    assert (await repository.lexical_search(_CONTEXT, query="originaluniqueterm"))[
        0
    ].chunk.version_id == initial.effective_version_id


async def test_create_identity_collision_never_replaces_an_existing_source(
    ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even an injected UUID collision cannot turn a create request into an unguarded replacement."""
    repository = ingestion_repository
    initial = await _created(repository)
    identifiers = iter([UUID(initial.source_id), uuid4(), uuid4(), uuid4()])
    monkeypatch.setattr(postgres_ingestion, "uuid4", lambda: next(identifiers))
    async with repository.reserve_ingestion(_CONTEXT, **_request("collision_create", "replacementterm")) as reservation:
        with pytest.raises(RecordConflict):
            await _complete(repository, reservation, "replacementterm")
    assert (await repository.lexical_search(_CONTEXT, query="originaluniqueterm"))[
        0
    ].chunk.version_id == initial.effective_version_id
    assert await repository.lexical_search(_CONTEXT, query="replacementterm") == []

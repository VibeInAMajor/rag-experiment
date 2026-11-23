"""Real PostgreSQL tests for leased embedding work, atomic coverage and tenant-local reuse."""

import hashlib
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from pydantic import ValidationError
from sqlalchemy import text

from apps.workbench.api import db_migrations
from apps.workbench.api.embedding import EmbeddingProfile
from apps.workbench.api.embedding_jobs import EmbeddingCandidate, EmbeddingOwnershipLost, EmbeddingWrite
from apps.workbench.api.persistence import (
    Chunk,
    CorpusNotReady,
    RecordConflict,
    SchemaIncompatible,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="embedding-persistence-test")
_FOREIGN = WorkspaceContext(workspace_id="foreign", trace_id="embedding-foreign-test")


def _profile(*, revision: str = "embedding-r1") -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="test-embedding",
        profile_revision=revision,
        provider_adapter_id="tei-openai",
        model_id="Qwen/Qwen3-Embedding-4B",
        model_revision="a" * 40,
        model_digest="b" * 64,
        tokenizer_digest="c" * 64,
        tokenizer_revision="test-counter",
        dimensions=32,
    )


@pytest_asyncio.fixture(loop_scope="function")
async def embedding_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Only fixture-owned databases receive the additive migration and test sources."""
    assert db_migrations.migrate(disposable_database.admin_dsn).revision == "0005"
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        for context in (_CONTEXT, _FOREIGN):
            await repository.create_workspace(
                context, Workspace(workspace_id=context.workspace_id, name="Embedding test")
            )
        yield repository
    finally:
        await repository.close()


async def _publish(
    repository: PostgresPersistence,
    version: str,
    *,
    context: WorkspaceContext = _CONTEXT,
    texts: tuple[str, ...] = ("First evidence", "Second evidence"),
) -> None:
    source = Source(workspace_id=context.workspace_id, source_id="source", title="Embedding evidence")
    source_version = SourceVersion(
        workspace_id=context.workspace_id,
        source_id=source.source_id,
        version_id=version,
        content_hash=hashlib.sha256("\n".join(texts).encode()).hexdigest(),
    )
    chunks = [
        Chunk(
            workspace_id=context.workspace_id,
            source_id=source.source_id,
            version_id=version,
            chunk_id=f"{version}-{index}",
            title=source.title,
            content=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            metadata={"ordinal": index},
        )
        for index, text in enumerate(texts)
    ]
    await repository.publish_source(context, source=source, version=source_version, chunks=chunks)


def _write(candidate: EmbeddingCandidate) -> EmbeddingWrite:
    return EmbeddingWrite(
        source_id=candidate.source_id,
        version_id=candidate.version_id,
        chunk_id=candidate.chunk_id,
        expected_content_hash=candidate.content_hash,
        processing_digest="d" * 64,
        input_hash=hashlib.sha256(candidate.content.encode()).hexdigest(),
        vector=(1.0, *([0.0] * 31)),
    )


async def test_partial_batches_never_publish_false_ready_and_complete_lookup_has_provenance(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Publication stays lexical-only while durable semantic coverage advances atomically."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    assert await repository.enqueue_embedding_backfill(_CONTEXT, profile) == 0
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None and job.attempts == 1
    page = await repository.embedding_job_chunks(_CONTEXT, job)
    assert len(page) == 2
    job = await repository.commit_embedding_batch(
        _CONTEXT, job, profile, records=(_write(page[0]),), cursor=page[0].chunk_id
    )
    partial = await repository.embedding_coverage(_CONTEXT, profile)
    assert partial.eligible_active_chunks == 2 and partial.ready_embeddings == 1 and not partial.ready
    with pytest.raises(CorpusNotReady):
        await repository.exact_embedding_search(_CONTEXT, profile, _write(page[0]).vector)
    with pytest.raises(RecordConflict):
        await repository.commit_embedding_batch(_CONTEXT, job, profile, records=(), cursor=None, complete=True)
    job = await repository.commit_embedding_batch(
        _CONTEXT, job, profile, records=(_write(page[1]),), cursor=page[1].chunk_id, complete=True
    )
    assert job.status == "completed"
    coverage = await repository.embedding_coverage(_CONTEXT, profile)
    assert coverage.ready and coverage.coverage_fraction == 1.0 and coverage.checkpoint
    hits = await repository.exact_embedding_search(_CONTEXT, profile, _write(page[0]).vector)
    assert len(hits) == 2 and all(hit.version_id == "version-one" for hit in hits)
    assert all(hit.profile_fingerprint == profile.fingerprint and len(hit.source_content_hash) == 64 for hit in hits)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.chunks WHERE embedding IS NOT NULL").fetchone() == (
            0,
        )


async def test_active_version_swap_fences_late_result_and_reuses_only_compatible_cache(
    embedding_repository: PostgresPersistence,
) -> None:
    """Old jobs lose ownership; unchanged model input reuses the same tenant-local vector namespace."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one", texts=("Same evidence",))
    first = await repository.lease_embedding_job(_CONTEXT, profile)
    assert first is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, first))[0]
    write = _write(candidate)
    await repository.commit_embedding_batch(
        _CONTEXT, first, profile, records=(write,), cursor=candidate.chunk_id, complete=True
    )
    await _publish(repository, "version-two", texts=("Same evidence",))
    assert not (await repository.embedding_coverage(_CONTEXT, profile)).ready
    second = await repository.lease_embedding_job(_CONTEXT, profile)
    assert second is not None
    page = await repository.embedding_job_chunks(_CONTEXT, second)
    cache = await repository.lookup_embedding_cache(
        _CONTEXT, profile, keys=((write.processing_digest, write.input_hash),)
    )
    assert len(cache) == 1 and cache[(write.processing_digest, write.input_hash)] == write.vector
    await _publish(repository, "version-three", texts=("Changed evidence",))
    with pytest.raises(EmbeddingOwnershipLost):
        await repository.commit_embedding_batch(
            _CONTEXT, second, profile, records=(_write(page[0]),), cursor=page[0].chunk_id
        )
    stale = await repository.get_embedding_job(_CONTEXT, second.job_id)
    assert stale is not None and stale.status == "stale"


async def test_tenant_profile_and_cache_boundaries_are_enforced(embedding_repository: PostgresPersistence) -> None:
    """Identical inputs/profile pins in another workspace cannot reuse private vectors or leases."""
    repository, profile = embedding_repository, _profile()
    for context in (_CONTEXT, _FOREIGN):
        await repository.register_embedding_profile(context, profile)
    await _publish(repository, "version-one", texts=("Private evidence",))
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, job))[0]
    write = _write(candidate)
    await repository.commit_embedding_batch(
        _CONTEXT, job, profile, records=(write,), cursor=candidate.chunk_id, complete=True
    )
    assert await repository.get_embedding_job(_FOREIGN, job.job_id) is None
    assert (
        await repository.lookup_embedding_cache(_FOREIGN, profile, keys=((write.processing_digest, write.input_hash),))
        == {}
    )
    with pytest.raises(RecordConflict):
        await repository.embedding_job_chunks(_FOREIGN, job)


async def test_expired_lease_recovers_progress_and_old_owner_cannot_write(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A replacement worker gets a new token and keeps the exact committed cursor."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    first = await repository.lease_embedding_job(_CONTEXT, profile)
    assert first is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, first))[0]
    first = await repository.commit_embedding_batch(
        _CONTEXT, first, profile, records=(_write(candidate),), cursor=candidate.chunk_id
    )
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.embedding_jobs SET lease_expires_at=clock_timestamp()-interval '1 second'")
    second = await repository.lease_embedding_job(_CONTEXT, profile)
    assert second is not None and second.job_id == first.job_id and second.owner_token != first.owner_token
    assert second.attempts == 2 and second.cursor == first.cursor
    with pytest.raises(EmbeddingOwnershipLost):
        await repository.renew_embedding_job(_CONTEXT, first)
    renewed = await repository.renew_embedding_job(_CONTEXT, second)
    assert renewed.lease_expires_at is not None and second.lease_expires_at is not None
    assert renewed.lease_expires_at >= second.lease_expires_at
    failed = await repository.fail_embedding_job(
        _CONTEXT, renewed, error_code="MODEL_UNAVAILABLE", retryable=True, retry_after_seconds=60
    )
    assert failed.status == "retryable_failed" and failed.cursor == first.cursor
    assert await repository.lease_embedding_job(_CONTEXT, profile) is None


async def test_same_revision_cannot_change_definition_and_preview_has_no_write_effect(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """An immutable pin cannot be silently upgraded and dry-run does not register or queue anything."""
    repository, profile = embedding_repository, _profile()
    await _publish(repository, "version-one")
    preview = await repository.preview_embedding_backfill(_CONTEXT, profile)
    assert preview.eligible_active_chunks == 2 and preview.ready_embeddings == 0 and not preview.ready
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.embedding_model_profiles").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM workbench.embedding_jobs").fetchone() == (0,)
    await repository.register_embedding_profile(_CONTEXT, profile)
    with pytest.raises(RecordConflict):
        await repository.register_embedding_profile(_CONTEXT, profile.model_copy(update={"model_digest": "f" * 64}))
    assert await repository.enqueue_embedding_backfill(_CONTEXT, profile) == 1
    assert await repository.enqueue_embedding_backfill(_CONTEXT, profile) == 0


async def test_changed_chunk_and_invalid_content_hash_refuse_atomic_write(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Hash mismatch rolls back the whole batch; direct source edits revoke an in-flight owner."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None
    page = await repository.embedding_job_chunks(_CONTEXT, job)
    bad = _write(page[1]).model_copy(update={"expected_content_hash": "wrong"})
    with pytest.raises(RecordConflict):
        await repository.commit_embedding_batch(
            _CONTEXT, job, profile, records=(_write(page[0]), bad), cursor=page[1].chunk_id
        )
    assert (await repository.embedding_coverage(_CONTEXT, profile)).ready_embeddings == 0
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("UPDATE workbench.chunks SET content='Changed' WHERE chunk_id=%s", (page[0].chunk_id,))
    with pytest.raises(EmbeddingOwnershipLost):
        await repository.commit_embedding_batch(
            _CONTEXT, job, profile, records=(_write(page[0]),), cursor=page[0].chunk_id
        )


async def test_invalid_vector_is_rejected_before_storage() -> None:
    """Poison vectors never enter the persistence adapter."""
    with pytest.raises(ValidationError):
        EmbeddingWrite(
            source_id="source",
            version_id="version",
            chunk_id="chunk",
            expected_content_hash="hash",
            processing_digest="d" * 64,
            input_hash="e" * 64,
            vector=(0.0,) * 32,
        )


async def test_progress_cannot_skip_first_uncommitted_chunk(embedding_repository: PostgresPersistence) -> None:
    """A bad checkpoint leaves both vectors and cursor unchanged so a later worker can recover."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None
    page = await repository.embedding_job_chunks(_CONTEXT, job)
    with pytest.raises(RecordConflict):
        await repository.commit_embedding_batch(
            _CONTEXT, job, profile, records=(_write(page[1]),), cursor=page[1].chunk_id
        )
    unchanged = await repository.get_embedding_job(_CONTEXT, job.job_id)
    assert unchanged is not None and unchanged.cursor is None
    assert (await repository.embedding_coverage(_CONTEXT, profile)).ready_embeddings == 0


async def test_poison_requires_explicit_operator_retry_and_keeps_progress(
    embedding_repository: PostgresPersistence,
) -> None:
    """Ordinary backfill cannot reopen quarantined work, while an explicit retry preserves its cursor."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, job))[0]
    job = await repository.commit_embedding_batch(
        _CONTEXT, job, profile, records=(_write(candidate),), cursor=candidate.chunk_id
    )
    poisoned = await repository.fail_embedding_job(
        _CONTEXT, job, error_code="REQUEST_TOO_LARGE", retryable=False, retry_after_seconds=0
    )
    assert poisoned.status == "poisoned"
    assert await repository.enqueue_embedding_backfill(_CONTEXT, profile) == 0
    assert await repository.lease_embedding_job(_CONTEXT, profile) is None
    retried = await repository.retry_embedding_job(_CONTEXT, poisoned.job_id)
    assert retried.status == "queued" and retried.attempts == 0 and retried.cursor == candidate.chunk_id
    recovered = await repository.lease_embedding_job(_CONTEXT, profile)
    assert recovered is not None and recovered.attempts == 1
    assert [item.chunk_id for item in await repository.embedding_job_chunks(_CONTEXT, recovered)] == ["version-one-1"]


async def test_missing_vector_revokes_coverage_and_completed_job_can_repair(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """Deleting a cache row cascades its link and cannot preserve a false ready generation."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one", texts=("Evidence",))
    job = await repository.lease_embedding_job(_CONTEXT, profile)
    assert job is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, job))[0]
    await repository.commit_embedding_batch(
        _CONTEXT, job, profile, records=(_write(candidate),), cursor=candidate.chunk_id, complete=True
    )
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("DELETE FROM workbench.embedding_vectors")
    coverage = await repository.embedding_coverage(_CONTEXT, profile)
    assert coverage.ready_embeddings == 0 and not coverage.ready
    with pytest.raises(CorpusNotReady):
        await repository.exact_embedding_search(_CONTEXT, profile, _write(candidate).vector)
    assert await repository.enqueue_embedding_backfill(_CONTEXT, profile) == 1
    repaired = await repository.lease_embedding_job(_CONTEXT, profile)
    assert repaired is not None and repaired.cursor is None


async def test_disabled_semantic_trigger_prevents_any_qualification(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """An audited revision number cannot qualify a database whose scheduling fence is disabled."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute("ALTER TABLE workbench.chunks DISABLE TRIGGER schedule_chunk_embeddings")
    with pytest.raises(SchemaIncompatible):
        await repository.embedding_coverage(_CONTEXT, profile)
    assert not db_migrations.migration_status(disposable_database.admin_dsn).compatible


async def test_profile_revision_change_uses_a_new_vector_namespace(embedding_repository: PostgresPersistence) -> None:
    """Tokenizer/model contract changes preserve historical rows while refusing incompatible reuse."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one", texts=("Stable evidence",))
    first = await repository.lease_embedding_job(_CONTEXT, profile)
    assert first is not None
    candidate = (await repository.embedding_job_chunks(_CONTEXT, first))[0]
    record = _write(candidate)
    await repository.commit_embedding_batch(
        _CONTEXT, first, profile, records=(record,), cursor=candidate.chunk_id, complete=True
    )
    changed = _profile(revision="embedding-r2").model_copy(update={"tokenizer_digest": "e" * 64})
    await repository.register_embedding_profile(_CONTEXT, changed)
    assert not (await repository.embedding_coverage(_CONTEXT, profile)).ready
    assert not (await repository.embedding_coverage(_CONTEXT, changed)).ready
    assert (
        await repository.lookup_embedding_cache(
            _CONTEXT, changed, keys=((record.processing_digest, record.input_hash),)
        )
        == {}
    )
    assert await repository.enqueue_embedding_backfill(_CONTEXT, changed) == 1
    second = await repository.lease_embedding_job(_CONTEXT, changed)
    assert second is not None and second.profile_fingerprint != first.profile_fingerprint


async def test_database_rls_hides_all_semantic_tables_from_another_scope(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """The restricted role cannot bypass scope by explicitly requesting another workspace ID."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _publish(repository, "version-one", texts=("Private evidence",))
    with psycopg.connect(disposable_database.app_dsn) as connection:
        connection.execute("SELECT set_config('workbench.workspace_id','foreign',true)")
        for table in (
            "embedding_model_profiles",
            "embedding_jobs",
            "embedding_vectors",
            "chunk_embeddings",
            "embedding_generations",
        ):
            assert connection.execute(
                psycopg.sql.SQL("SELECT count(*) FROM workbench.{} WHERE workspace_id='development'").format(
                    psycopg.sql.Identifier(table)
                )
            ).fetchone() == (0,)


async def test_profile_schema_upgrade_keeps_lexical_records_and_historical_checksums(
    disposable_database: DisposableDatabase,
) -> None:
    """The prior schema remains lexical-ready; applying 0005 adds empty semantic state without rewrites."""
    database = disposable_database
    with db_migrations._connection(database.admin_dsn, transaction=True) as connection:
        db_migrations._ensure_role(connection)
        connection.execute(text("CREATE SCHEMA workbench"))
        command.upgrade(db_migrations._configuration(connection), "0004")
        db_migrations._grant_application(connection)
    historical = {
        revision: db_migrations.migration_checksum(revision=revision) for revision in ("0001", "0002", "0003", "0004")
    }
    repository = PostgresPersistence(database.app_dsn)
    await repository.start()
    try:
        await repository.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Before embedding"))
        await _publish(repository, "version-one")
        assert (await repository.readiness(_CONTEXT)).schema_revision == "0004"
        assert db_migrations.migrate(database.admin_dsn).revision == "0005"
        assert (await repository.readiness(_CONTEXT)).chunk_count == 2
        assert (await repository.embedding_coverage(_CONTEXT, _profile())).ready_embeddings == 0
    finally:
        await repository.close()
    assert historical == {revision: db_migrations.migration_checksum(revision=revision) for revision in historical}

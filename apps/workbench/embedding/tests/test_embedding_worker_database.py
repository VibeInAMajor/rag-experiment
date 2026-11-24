"""Exercise the actual worker and PostgreSQL together; fake vectors remain explicitly test-only."""

import psycopg
import pytest

from apps.workbench.embedding.embedding_ingestion import EmbeddingIngestionService
from apps.workbench.embedding.tests import test_embedding_persistence as _database
from apps.workbench.embedding.tests.test_embedding_ingestion import _Counter, _profile, _Provider
from apps.workbench.persistence.models import WorkspaceContext
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.testing.database import DisposableDatabase

embedding_repository = _database.embedding_repository
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="worker-database-test")


async def _drain(worker: EmbeddingIngestionService) -> None:
    for _ in range(20):
        if not await worker.process_one(_CONTEXT):
            return
    raise AssertionError("The small controlled queue did not drain")


async def test_actual_worker_commits_coverage_and_reuses_only_compatible_changed_version_chunks(
    embedding_repository: PostgresPersistence,
) -> None:
    """A one-chunk edit preserves the compatible vector while the active generation changes atomically."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _database._publish(repository, "first-version", texts=("Unchanged evidence", "Old evidence"))
    provider = _Provider(profile)
    worker = EmbeddingIngestionService(repository, provider, profile=profile, counter=_Counter())
    await _drain(worker)
    first = await repository.embedding_coverage(_CONTEXT, profile)
    assert first.ready and first.ready_embeddings == first.eligible_active_chunks == 2
    await _database._publish(repository, "next-version", texts=("Unchanged evidence", "New evidence"))
    changed = await repository.embedding_coverage(_CONTEXT, profile)
    assert not changed.ready
    await _drain(worker)
    final = await repository.embedding_coverage(_CONTEXT, profile)
    assert final.ready and final.index_generation != first.index_generation
    assert worker.statistics()["generated_inputs"] == 3
    assert worker.statistics()["reused_chunks"] == 1
    hits = await repository.exact_embedding_search(_CONTEXT, profile, (1.0,) + (0.0,) * 31)
    assert len(hits) == 2 and {hit.version_id for hit in hits} == {"next-version"}


async def test_worker_process_restart_resumes_committed_cursor_without_new_inference(
    embedding_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A crash after a committed batch but before terminal completion retains vectors and checkpoints."""
    repository, profile = embedding_repository, _profile()
    await repository.register_embedding_profile(_CONTEXT, profile)
    await _database._publish(repository, "restart-version")
    provider = _Provider(profile)
    before = EmbeddingIngestionService(repository, provider, profile=profile, counter=_Counter())
    assert await before.process_one(_CONTEXT)
    assert len(provider.requests) == 1
    after = EmbeddingIngestionService(repository, provider, profile=profile, counter=_Counter())
    assert not await after.process_one(_CONTEXT)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "UPDATE workbench.embedding_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE workspace_id=%s AND status='running'",
            (_CONTEXT.workspace_id,),
        )
    await _drain(after)
    assert len(provider.requests) == 1
    assert (await repository.embedding_coverage(_CONTEXT, profile)).ready

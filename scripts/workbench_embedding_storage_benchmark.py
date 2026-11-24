"""Synthetic PostgreSQL embedding storage benchmark; no provider, GPU, HTTP or TPM measurement."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.embedding.embedding_jobs import EmbeddingWrite
from apps.workbench.persistence.models import (
    Chunk,
    PersistenceError,
    Source,
    SourceVersion,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.postgres.db_migrations import MigrationError, migrate
from apps.workbench.postgres.postgres import PostgresPersistence

_TEXT = "Synthetic storage benchmark: unchanged tenant-local input."
_INPUT_HASH = hashlib.sha256(_TEXT.encode()).hexdigest()
_VECTOR = (1.0, *([0.0] * 31))
_ROOT = Path(__file__).resolve().parents[1]
_logger = logging.getLogger("workbench.storage_benchmark")


def _progress(phase: str, context: WorkspaceContext, *, chunks: int, started: float) -> None:
    _logger.info(
        json.dumps(
            {
                "phase": phase,
                "workspace_id": context.workspace_id,
                "chunks": chunks,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
            separators=(",", ":"),
        )
    )


class StorageBenchmarkError(ValueError):
    """Refuse benchmark targets or inconsistent observed counts without exposing connection strings."""


def _validate_target(admin_dsn: str, app_dsn: str) -> str:
    try:
        admin, app = conninfo_to_dict(admin_dsn), conninfo_to_dict(app_dsn)
    except (ValueError, psycopg.Error):
        raise StorageBenchmarkError("INVALID_DISPOSABLE_BENCHMARK_TARGET") from None
    identity = ("host", "port", "dbname")
    name = admin.get("dbname", "")
    if (
        not isinstance(name, str)
        or re.fullmatch(r"rag_test_[a-f0-9]{32}", name) is None
        or admin.get("host") not in {"localhost", "127.0.0.1", "::1"}
        or any(admin.get(key) != app.get(key) for key in identity)
    ):
        raise StorageBenchmarkError("INVALID_DISPOSABLE_BENCHMARK_TARGET")
    return name


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="synthetic-storage-benchmark",
        profile_revision="synthetic-storage-r1",
        provider_adapter_id="synthetic-storage-only",
        model_id="SYNTHETIC-NOT-MODEL-OUTPUT",
        model_revision="0" * 40,
        model_digest=hashlib.sha256(b"synthetic-vector32-r1").hexdigest(),
        tokenizer_digest=hashlib.sha256(b"synthetic-no-tokenizer").hexdigest(),
        tokenizer_revision="synthetic-no-tokenizer",
        dimensions=32,
    )


def _counts(admin_dsn: str) -> dict[str, int]:
    with psycopg.connect(admin_dsn) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        row = connection.execute(
            "SELECT (SELECT count(*) FROM workbench.workspaces),"
            "(SELECT count(*) FROM workbench.chunks),"
            "(SELECT count(*) FROM workbench.embedding_vectors),"
            "(SELECT count(*) FROM workbench.chunk_embeddings),"
            "(SELECT count(*) FROM workbench.embedding_jobs WHERE status='completed'),"
            "(SELECT count(*) FROM workbench.chunks WHERE embedding IS NOT NULL)"
        ).fetchone()
    if row is None:
        raise StorageBenchmarkError("BENCHMARK_COUNTS_UNAVAILABLE")
    return dict(
        zip(
            ("workspaces", "chunks", "cache_vectors", "chunk_mappings", "completed_jobs", "legacy_nonnull_vectors"),
            row,
            strict=True,
        )
    )


def _server_started_at(admin_dsn: str) -> str:
    with psycopg.connect(admin_dsn) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        row = connection.execute("SELECT pg_postmaster_start_time()").fetchone()
    if row is None:
        raise StorageBenchmarkError("BENCHMARK_SERVER_IDENTITY_UNAVAILABLE")
    return row[0].isoformat()


async def _publish(repository: PostgresPersistence, context: WorkspaceContext, *, version: str, count: int) -> None:
    source = Source(
        workspace_id=context.workspace_id,
        source_id="benchmark-source",
        title="Synthetic storage only",
        metadata={"synthetic": True},
    )
    source_version = SourceVersion(
        workspace_id=context.workspace_id,
        source_id=source.source_id,
        version_id=version,
        content_hash=hashlib.sha256(((_TEXT + "\n") * count).encode()).hexdigest(),
        metadata={"synthetic": True},
    )
    chunks = [
        Chunk(
            workspace_id=context.workspace_id,
            source_id=source.source_id,
            version_id=version,
            chunk_id=f"{version}-{index:06d}",
            title=source.title,
            content=_TEXT,
            content_hash=_INPUT_HASH,
            metadata={"ordinal": index, "synthetic": True},
        )
        for index in range(count)
    ]
    await repository.publish_source(context, source=source, version=source_version, chunks=chunks)


async def _drain(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    profile: EmbeddingProfile,
    *,
    reconnect: Callable[[], Awaitable[PostgresPersistence]] | None = None,
) -> dict[str, Any]:
    job = await repository.lease_embedding_job(context, profile, lease_seconds=600)
    if job is None:
        raise StorageBenchmarkError("BENCHMARK_JOB_MISSING")
    processing_digest = hashlib.sha256(f"synthetic-plain-document-r1:{profile.fingerprint}".encode()).hexdigest()
    key = (processing_digest, _INPUT_HASH)
    result: dict[str, Any] = {"mappings_written": 0, "cache_hit_occurrences": 0, "batches": 0}
    started = time.monotonic()
    next_progress = 1024
    while True:
        candidates = await repository.embedding_job_chunks(context, job, limit=128)
        if not candidates:
            await repository.commit_embedding_batch(context, job, profile, records=(), cursor=job.cursor, complete=True)
            break
        cached = await repository.lookup_embedding_cache(context, profile, keys=(key,))
        if key in cached:
            result["cache_hit_occurrences"] += len(candidates)
        vector = cached.get(key, _VECTOR)
        records = tuple(
            EmbeddingWrite(
                source_id=item.source_id,
                version_id=item.version_id,
                chunk_id=item.chunk_id,
                expected_content_hash=item.content_hash,
                processing_digest=processing_digest,
                input_hash=_INPUT_HASH,
                vector=vector,
            )
            for item in candidates
        )
        job = await repository.commit_embedding_batch(
            context, job, profile, records=records, cursor=candidates[-1].chunk_id
        )
        result["mappings_written"] += len(records)
        result["batches"] += 1
        if result["mappings_written"] >= next_progress:
            _progress("mapping_progress", context, chunks=result["mappings_written"], started=started)
            next_progress += 1024
        if reconnect is not None:
            before = await repository.embedding_coverage(context, profile)
            repository = await reconnect()
            restored = await repository.get_embedding_job(context, job.job_id)
            after = await repository.embedding_coverage(context, profile)
            if restored is None or restored.cursor != job.cursor or after.ready_embeddings != before.ready_embeddings:
                raise StorageBenchmarkError("BENCHMARK_CHECKPOINT_LOST")
            result["pool_restart_checkpoint"] = {
                "cursor": restored.cursor,
                "mappings_before": before.ready_embeddings,
                "mappings_after": after.ready_embeddings,
                "same_persisted_lease": restored.owner_token == job.owner_token,
            }
            job = restored
            reconnect = None
            _progress("checkpoint_pool_reopened", context, chunks=after.ready_embeddings, started=started)
    coverage = await repository.embedding_coverage(context, profile)
    if not coverage.ready or coverage.coverage_fraction != 1.0:
        raise StorageBenchmarkError("BENCHMARK_COVERAGE_INCOMPLETE")
    result["elapsed_seconds"] = time.monotonic() - started
    result["coverage"] = coverage.model_dump(mode="json")
    _progress("source_complete", context, chunks=result["mappings_written"], started=started)
    return result


async def run_storage_benchmark(
    *,
    admin_dsn: str,
    app_dsn: str,
    workspaces: int = 10,
    chunks_per_workspace: int = 10000,
    before_restart_audit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Populate only an empty explicitly disposable target, verify restart and compatible source update."""
    database = _validate_target(admin_dsn, app_dsn)
    if (
        type(workspaces) is not int
        or type(chunks_per_workspace) is not int
        or not 1 <= workspaces <= 10
        or not 1 <= chunks_per_workspace <= 10000
    ):
        raise StorageBenchmarkError("INVALID_BENCHMARK_SCALE")
    started = time.monotonic()
    await asyncio.to_thread(migrate, admin_dsn)
    initial = await asyncio.to_thread(_counts, admin_dsn)
    if initial["workspaces"] or initial["chunks"] or initial["chunk_mappings"]:
        raise StorageBenchmarkError("BENCHMARK_REQUIRES_EMPTY_DATABASE")
    profile = _profile()
    repository = PostgresPersistence(app_dsn, statement_timeout_ms=30000)

    async def reconnect() -> PostgresPersistence:
        nonlocal repository
        await repository.close()
        repository = PostgresPersistence(app_dsn, statement_timeout_ms=30000)
        await repository.start()
        return repository

    await repository.start()
    reports = []
    publication_seconds = 0.0
    contexts = [
        WorkspaceContext(workspace_id=f"storage-benchmark-{index:02d}", trace_id="synthetic-storage-benchmark")
        for index in range(workspaces)
    ]
    try:
        for index, context in enumerate(contexts):
            await repository.create_workspace(
                context, Workspace(workspace_id=context.workspace_id, name="Synthetic storage benchmark")
            )
            await repository.register_embedding_profile(context, profile)
            publication_started = time.monotonic()
            _progress("publication_started", context, chunks=chunks_per_workspace, started=publication_started)
            await _publish(repository, context, version="benchmark-v1", count=chunks_per_workspace)
            publication_seconds += time.monotonic() - publication_started
            _progress("publication_complete", context, chunks=chunks_per_workspace, started=publication_started)
            reports.append(await _drain(repository, context, profile, reconnect=reconnect if index == 0 else None))
        before = await asyncio.to_thread(_counts, admin_dsn)
        server_restart: dict[str, Any] | None = None
        if before_restart_audit is not None:
            before_start = await asyncio.to_thread(_server_started_at, admin_dsn)
            await repository.close()
            await before_restart_audit({"database": database, "counts": before, "server_started_at": before_start})
        await reconnect()
        restored = [await repository.embedding_coverage(context, profile) for context in contexts]
        after = await asyncio.to_thread(_counts, admin_dsn)
        if before != after or not all(item.ready for item in restored):
            raise StorageBenchmarkError("BENCHMARK_RESTART_LOST_VECTORS")
        if before_restart_audit is not None:
            after_start = await asyncio.to_thread(_server_started_at, admin_dsn)
            if after_start == before_start:
                raise StorageBenchmarkError("BENCHMARK_SERVER_DID_NOT_RESTART")
            server_restart = {"before": before_start, "after": after_start, "changed": True, "counts_unchanged": True}
        await _publish(repository, contexts[0], version="benchmark-v2", count=chunks_per_workspace)
        updated = await _drain(repository, contexts[0], profile)
        final = await asyncio.to_thread(_counts, admin_dsn)
        expected = workspaces * chunks_per_workspace
        if (
            before["chunk_mappings"] != expected
            or before["cache_vectors"] != workspaces
            or final["chunk_mappings"] != expected + chunks_per_workspace
            or final["cache_vectors"] != workspaces
            or final["legacy_nonnull_vectors"] != 0
            or updated["cache_hit_occurrences"] != chunks_per_workspace
        ):
            raise StorageBenchmarkError("BENCHMARK_STORAGE_INVARIANT_FAILED")
        return {
            "status": "PASS",
            "kind": "SYNTHETIC_STORAGE_ONLY",
            "database": database,
            "real_model_calls": 0,
            "gpu_inference": False,
            "tpm_claim": "NOT_MEASURED",
            "vector_dimensions": 32,
            "commit_batch_bound": 128,
            "initial_active_chunks": expected,
            "workspaces": workspaces,
            "initial": reports,
            "pool_reopen_counts_before": before,
            "pool_reopen_counts_after": after,
            "server_restart": server_restart,
            "updated_source": updated,
            "final_counts": final,
            "publication_seconds": publication_seconds,
            "total_seconds": time.monotonic() - started,
            "execution_scope": (
                "Direct bounded persistence pages with fake vectors; no embedding worker or provider throughput claim"
            ),
            "restart_scope": (
                "Connection-pool close/reopen; continued persisted lease and cursor, then checked completed coverage"
            ),
            "benchmark_isolation": "Dedicated disposable database; host CPU and storage are not exclusive",
        }
    finally:
        await repository.close()


def main() -> int:
    """Require explicit test DSNs; creation/deletion of the fixture database belongs to the caller."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspaces", type=int, default=10)
    parser.add_argument("--chunks-per-workspace", type=int, default=10000)
    parser.add_argument(
        "--output", type=Path, default=_ROOT / "tasks/evidence/embedding-2026-11-24/storage-benchmark.json"
    )
    arguments = parser.parse_args()
    try:
        report = asyncio.run(
            run_storage_benchmark(
                admin_dsn=os.environ.get("WORKBENCH_TEST_ADMIN_DSN", ""),
                app_dsn=os.environ.get("WORKBENCH_TEST_APP_DSN", ""),
                workspaces=arguments.workspaces,
                chunks_per_workspace=arguments.chunks_per_workspace,
            )
        )
    except (StorageBenchmarkError, PersistenceError, MigrationError, psycopg.Error):
        print(json.dumps({"status": "FAIL", "code": "STORAGE_BENCHMARK_REFUSED"}))
        return 1
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "initial_active_chunks": report["initial_active_chunks"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Short scoped transactions for semantic work; provider calls never enter this adapter."""

import re
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import uuid4

from pgvector import Vector
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.embedding.embedding_jobs import (
    EmbeddingCache,
    EmbeddingCacheKey,
    EmbeddingCandidate,
    EmbeddingCoverage,
    EmbeddingJob,
    EmbeddingOwnershipLost,
    EmbeddingVector,
    EmbeddingWrite,
    PersistedEmbeddingHit,
)
from apps.workbench.persistence.models import (
    CorpusNotReady,
    InvalidEmbedding,
    RecordConflict,
    SchemaIncompatible,
    WorkspaceContext,
)

_TABLES = (
    "embedding_model_profiles",
    "embedding_jobs",
    "embedding_vectors",
    "chunk_embeddings",
    "embedding_generations",
)
_ACTIVE = (
    "EXISTS(SELECT 1 FROM workbench.source_versions v WHERE v.workspace_id=j.workspace_id "
    "AND v.source_id=j.source_id AND v.version_id=j.version_id AND v.status='active')"
)


def _job(row: dict[str, Any] | None) -> EmbeddingJob:
    if row is None:
        raise RecordConflict("Embedding work is stale or no longer owned.")
    return EmbeddingJob.model_validate({name: row[name] for name in EmbeddingJob.model_fields})


def _bound(value: int, *, maximum: int, minimum: int = 1) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RecordConflict("Embedding operation exceeds its bounds.")


async def _profile(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, profile: EmbeddingProfile
) -> None:
    row = await (
        await connection.execute(
            "SELECT profile_fingerprint,enabled FROM workbench.embedding_model_profiles "
            "WHERE workspace_id=%s AND profile_id=%s AND profile_revision=%s",
            (context.workspace_id, profile.profile_id, profile.profile_revision),
        )
    ).fetchone()
    if row != {"profile_fingerprint": profile.fingerprint, "enabled": True}:
        raise RecordConflict("The immutable embedding profile is not enabled.")


async def _owned(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, job: EmbeddingJob, *, lock: bool = False
) -> EmbeddingJob:
    if job.workspace_id != context.workspace_id or job.owner_token is None:
        raise RecordConflict("Embedding work is outside this workspace or ownership.")
    row = await (
        await connection.execute(
            "SELECT j.* FROM workbench.embedding_jobs j JOIN workbench.embedding_model_profiles p "
            "USING(workspace_id,profile_fingerprint) WHERE j.workspace_id=%s AND j.job_id=%s "
            "AND j.owner_token=%s AND j.status='running' AND j.lease_expires_at>clock_timestamp() AND p.enabled AND "
            + _ACTIVE
            + (" FOR UPDATE OF j" if lock else ""),
            (context.workspace_id, job.job_id, job.owner_token),
        )
    ).fetchone()
    if row is None:
        raise EmbeddingOwnershipLost("Embedding ownership expired or its source was superseded.")
    if (row["profile_fingerprint"], row["source_id"], row["version_id"]) != (
        job.profile_fingerprint,
        job.source_id,
        job.version_id,
    ):
        raise RecordConflict("Embedding ownership cannot be transferred to a different immutable identity.")
    return _job(row)


async def _coverage(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, profile: EmbeddingProfile
) -> EmbeddingCoverage:
    row = await (
        await connection.execute(
            "SELECT s.generation_id,s.status,count(c.chunk_id) AS eligible,count(m.chunk_id) AS covered,"
            "EXISTS(SELECT 1 FROM workbench.embedding_generations g WHERE g.workspace_id=s.workspace_id "
            "AND g.profile_fingerprint=%s AND g.index_generation=s.generation_id) AS published,"
            "EXISTS(SELECT 1 FROM workbench.embedding_model_profiles p WHERE p.workspace_id=s.workspace_id "
            "AND p.profile_fingerprint=%s AND p.enabled) AS enabled,"
            "(SELECT count(*) FROM workbench.chunk_embeddings old LEFT JOIN workbench.source_versions v "
            "ON v.workspace_id=old.workspace_id AND v.source_id=old.source_id AND v.version_id=old.version_id "
            "AND v.status='active' WHERE old.workspace_id=s.workspace_id AND old.profile_fingerprint=%s "
            "AND v.version_id IS NULL) AS stale FROM workbench.corpus_index_state s "
            "LEFT JOIN workbench.source_versions v ON v.workspace_id=s.workspace_id AND v.status='active' "
            "LEFT JOIN workbench.chunks c ON c.workspace_id=v.workspace_id "
            "AND c.source_id=v.source_id AND c.version_id=v.version_id "
            "LEFT JOIN workbench.chunk_embeddings m ON m.workspace_id=c.workspace_id AND m.chunk_id=c.chunk_id "
            "AND m.profile_fingerprint=%s AND m.expected_content_hash=c.content_hash "
            "WHERE s.workspace_id=%s GROUP BY s.workspace_id,s.generation_id,s.status",
            (profile.fingerprint, profile.fingerprint, profile.fingerprint, profile.fingerprint, context.workspace_id),
        )
    ).fetchone()
    if row is None:
        raise CorpusNotReady("Embedding coverage requires a committed corpus manifest.")
    eligible, covered = row["eligible"], row["covered"]
    ready = eligible > 0 and covered == eligible and row["status"] == "ready" and row["published"] and row["enabled"]
    return EmbeddingCoverage(
        workspace_id=context.workspace_id,
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_fingerprint=profile.fingerprint,
        index_generation=row["generation_id"],
        eligible_active_chunks=eligible,
        ready_embeddings=covered,
        stale_embeddings=row["stale"],
        coverage_fraction=covered / eligible if eligible else 0.0,
        ready=ready,
        checkpoint=f"{profile.fingerprint}:{row['generation_id']}" if ready else None,
    )


async def _publish_ready(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, profile: EmbeddingProfile
) -> None:
    pending = await (
        await connection.execute(
            "SELECT 1 FROM workbench.embedding_jobs j WHERE workspace_id=%s AND profile_fingerprint=%s "
            "AND status<>'completed' AND " + _ACTIVE + " LIMIT 1",
            (context.workspace_id, profile.fingerprint),
        )
    ).fetchone()
    if pending is not None:
        return
    await connection.execute(
        "INSERT INTO workbench.embedding_generations(workspace_id,profile_fingerprint,index_generation,"
        "eligible_active_chunks,ready_embeddings) SELECT s.workspace_id,%s,s.generation_id,count(c.chunk_id),"
        "count(m.chunk_id) FROM workbench.corpus_index_state s JOIN workbench.source_versions v "
        "ON v.workspace_id=s.workspace_id AND v.status='active' JOIN workbench.chunks c "
        "ON c.workspace_id=v.workspace_id AND c.source_id=v.source_id AND c.version_id=v.version_id "
        "LEFT JOIN workbench.chunk_embeddings m "
        "ON m.workspace_id=c.workspace_id AND m.chunk_id=c.chunk_id AND m.profile_fingerprint=%s "
        "AND m.expected_content_hash=c.content_hash WHERE s.workspace_id=%s AND s.status='ready' "
        "GROUP BY s.workspace_id,s.generation_id HAVING count(c.chunk_id)>0 AND count(c.chunk_id)=count(m.chunk_id) "
        "ON CONFLICT DO NOTHING",
        (profile.fingerprint, profile.fingerprint, context.workspace_id),
    )


class PostgresEmbeddingMixin:
    """Compose semantic persistence with the existing connection and workspace transaction owner."""

    def _transaction(
        self, context: WorkspaceContext, *, operation: str, repeatable_read: bool = False
    ) -> AbstractAsyncContextManager[AsyncConnection[dict[str, Any]]]:
        raise NotImplementedError

    async def _verify_schema(self, connection: AsyncConnection[dict[str, Any]]) -> str:
        raise NotImplementedError

    async def _require_workspace(self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> None:
        raise NotImplementedError

    async def _embedding_schema(self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> None:
        if await self._verify_schema(connection) < "0005":
            raise SchemaIncompatible("Durable embeddings require their explicit migration.")
        await self._require_workspace(connection, context)
        row = await (
            await connection.execute(
                "SELECT count(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='workbench' AND c.relname=ANY(%s) AND c.relrowsecurity AND c.relforcerowsecurity",
                (list(_TABLES),),
            )
        ).fetchone()
        if row != {"count": 5}:
            raise SchemaIncompatible("Embedding workspace protections are unavailable.")
        protected = await (
            await connection.execute(
                "SELECT count(*) AS count FROM pg_trigger WHERE tgenabled IN ('O','A') AND (tgrelid,tgname) IN "
                "(('workbench.embedding_model_profiles'::regclass,'immutable_embedding_profile'),"
                "('workbench.embedding_vectors'::regclass,'immutable_embedding_vector'),"
                "('workbench.embedding_generations'::regclass,'immutable_embedding_generation'),"
                "('workbench.source_versions'::regclass,'schedule_version_embeddings'),"
                "('workbench.chunks'::regclass,'schedule_chunk_embeddings'))"
            )
        ).fetchone()
        if protected != {"count": 5}:
            raise SchemaIncompatible("Embedding publication protections are unavailable.")

    async def register_embedding_profile(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, enabled: bool = True
    ) -> None:
        """Pin a complete profile; enabling a revision retires other workers for the same model identity."""
        async with self._transaction(context, operation="embedding_profile_register") as connection:
            await self._embedding_schema(connection, context)
            await connection.execute(
                "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE",
                (context.workspace_id,),
            )
            await connection.execute(
                "INSERT INTO workbench.embedding_model_profiles(workspace_id,profile_id,profile_revision,"
                "profile_fingerprint,dimensions,definition) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    context.workspace_id,
                    profile.profile_id,
                    profile.profile_revision,
                    profile.fingerprint,
                    profile.dimensions,
                    Jsonb(profile.model_dump(mode="json")),
                ),
            )
            row = await (
                await connection.execute(
                    "SELECT profile_fingerprint FROM workbench.embedding_model_profiles WHERE workspace_id=%s "
                    "AND profile_id=%s AND profile_revision=%s",
                    (context.workspace_id, profile.profile_id, profile.profile_revision),
                )
            ).fetchone()
            if row != {"profile_fingerprint": profile.fingerprint}:
                raise RecordConflict("The profile revision already belongs to another immutable definition.")
            if enabled:
                await connection.execute(
                    "UPDATE workbench.embedding_model_profiles SET enabled=(profile_fingerprint=%s) "
                    "WHERE workspace_id=%s AND profile_id=%s",
                    (profile.fingerprint, context.workspace_id, profile.profile_id),
                )
            else:
                await connection.execute(
                    "UPDATE workbench.embedding_model_profiles SET enabled=false WHERE "
                    "workspace_id=%s AND profile_fingerprint=%s",
                    (context.workspace_id, profile.fingerprint),
                )

    async def enqueue_embedding_backfill(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, limit: int = 1000
    ) -> int:
        """Enqueue missing active versions and repair completed jobs whose durable vectors disappeared."""
        _bound(limit, maximum=10000)
        async with self._transaction(context, operation="embedding_enqueue") as connection:
            await self._embedding_schema(connection, context)
            await _profile(connection, context, profile)
            result = await connection.execute(
                "INSERT INTO "
                "workbench.embedding_jobs(workspace_id,source_id,version_id,"
                "profile_id,profile_revision,profile_fingerprint) "
                "SELECT v.workspace_id,v.source_id,v.version_id,%s,%s,%s FROM workbench.source_versions v "
                "LEFT JOIN workbench.embedding_jobs j ON j.workspace_id=v.workspace_id AND j.source_id=v.source_id "
                "AND j.version_id=v.version_id AND j.profile_fingerprint=%s WHERE v.workspace_id=%s "
                "AND v.status='active' "
                "AND (j.job_id IS NULL OR (j.status='completed' AND EXISTS(SELECT 1 FROM workbench.chunks c "
                "LEFT JOIN workbench.chunk_embeddings m ON m.workspace_id=c.workspace_id AND m.chunk_id=c.chunk_id "
                "AND m.profile_fingerprint=%s AND m.expected_content_hash=c.content_hash "
                "WHERE c.workspace_id=v.workspace_id AND c.source_id=v.source_id AND "
                "c.version_id=v.version_id AND m.chunk_id IS NULL))) "
                "ORDER BY v.source_id LIMIT %s ON "
                "CONFLICT(workspace_id,source_id,version_id,profile_fingerprint) DO UPDATE "
                "SET status='queued',cursor=NULL,attempts=0,error_code=NULL,available_at=clock_timestamp()",
                (
                    profile.profile_id,
                    profile.profile_revision,
                    profile.fingerprint,
                    profile.fingerprint,
                    context.workspace_id,
                    profile.fingerprint,
                    limit,
                ),
            )
            await _publish_ready(connection, context, profile)
            return result.rowcount

    async def lease_embedding_job(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, lease_seconds: int = 120
    ) -> EmbeddingJob | None:
        """Recover expired work with a new fencing token, bounded attempts and no inference transaction."""
        _bound(lease_seconds, minimum=10, maximum=600)
        async with self._transaction(context, operation="embedding_lease") as connection:
            await self._embedding_schema(connection, context)
            await _profile(connection, context, profile)
            await connection.execute(
                "UPDATE workbench.embedding_jobs j SET status='stale',owner_token=NULL,lease_expires_at=NULL "
                "WHERE workspace_id=%s AND profile_fingerprint=%s AND status NOT IN ('stale','poisoned') AND NOT "
                + _ACTIVE,
                (context.workspace_id, profile.fingerprint),
            )
            await connection.execute(
                "UPDATE workbench.embedding_jobs SET "
                "status='poisoned',owner_token=NULL,lease_expires_at=NULL,error_code='ATTEMPTS_EXHAUSTED' "
                "WHERE workspace_id=%s AND profile_fingerprint=%s AND status='running' AND "
                "lease_expires_at<=clock_timestamp() AND attempts>=5",
                (context.workspace_id, profile.fingerprint),
            )
            row = await (
                await connection.execute(
                    "SELECT j.* FROM workbench.embedding_jobs j WHERE workspace_id=%s AND "
                    "profile_fingerprint=%s AND attempts<5 "
                    "AND ((status IN ('queued','retryable_failed') AND available_at<=clock_timestamp()) OR "
                    "(status='running' AND lease_expires_at<=clock_timestamp())) AND "
                    + _ACTIVE
                    + " ORDER BY created_at,job_id LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (context.workspace_id, profile.fingerprint),
                )
            ).fetchone()
            if row is None:
                return None
            return _job(
                await (
                    await connection.execute(
                        "UPDATE workbench.embedding_jobs SET "
                        "status='running',attempts=attempts+1,owner_token=%s,lease_seconds=%s,"
                        "lease_expires_at=clock_timestamp()+make_interval(secs=>%s),updated_at=clock_timestamp() "
                        "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                        (uuid4().hex, lease_seconds, lease_seconds, context.workspace_id, row["job_id"]),
                    )
                ).fetchone()
            )

    async def renew_embedding_job(
        self, context: WorkspaceContext, job: EmbeddingJob, *, lease_seconds: int = 120
    ) -> EmbeddingJob:
        """Extend only current ownership, including quota waiting without a long transaction."""
        _bound(lease_seconds, minimum=10, maximum=600)
        async with self._transaction(context, operation="embedding_renew") as connection:
            await self._embedding_schema(connection, context)
            await _owned(connection, context, job, lock=True)
            return _job(
                await (
                    await connection.execute(
                        "UPDATE workbench.embedding_jobs SET "
                        "lease_seconds=%s,lease_expires_at=clock_timestamp()+make_interval(secs=>%s) "
                        "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                        (lease_seconds, lease_seconds, context.workspace_id, job.job_id),
                    )
                ).fetchone()
            )

    async def embedding_job_chunks(
        self, context: WorkspaceContext, job: EmbeddingJob, *, limit: int = 8
    ) -> tuple[EmbeddingCandidate, ...]:
        """Read a stable bounded page; active-version and owner fences apply before model work."""
        _bound(limit, maximum=128)
        async with self._transaction(context, operation="embedding_chunks", repeatable_read=True) as connection:
            await self._embedding_schema(connection, context)
            current = await _owned(connection, context, job)
            rows = await (
                await connection.execute(
                    "SELECT c.workspace_id,c.source_id,c.version_id,c.chunk_id,c.content,c.content_hash,c.metadata,"
                    "v.metadata AS version_metadata FROM workbench.chunks c JOIN workbench.source_versions v "
                    "USING(workspace_id,source_id,version_id) WHERE c.workspace_id=%s AND c.source_id=%s "
                    'AND c.version_id=%s AND c.chunk_id COLLATE "C">%s '
                    'ORDER BY c.chunk_id COLLATE "C" LIMIT %s',
                    (context.workspace_id, current.source_id, current.version_id, current.cursor or "", limit),
                )
            ).fetchall()
            return tuple(EmbeddingCandidate.model_validate(row) for row in rows)

    async def lookup_embedding_cache(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, keys: tuple[EmbeddingCacheKey, ...]
    ) -> EmbeddingCache:
        """Read compatible same-tenant input vectors without scanning another profile namespace."""
        _bound(len(keys), minimum=0, maximum=128)
        if not keys:
            return {}
        if any(re.fullmatch(r"[a-f0-9]{64}", value) is None for key in keys for value in key):
            raise RecordConflict("Invalid embedding cache identity.")
        async with self._transaction(context, operation="embedding_cache", repeatable_read=True) as connection:
            await self._embedding_schema(connection, context)
            await _profile(connection, context, profile)
            rows = await (
                await connection.execute(
                    "SELECT v.processing_digest,v.input_hash,v.vector::text AS vector FROM "
                    "workbench.embedding_vectors v "
                    "JOIN unnest(%s::text[],%s::text[]) AS k(processing_digest,input_hash) "
                    "USING(processing_digest,input_hash) "
                    "WHERE v.workspace_id=%s AND v.profile_fingerprint=%s",
                    ([key[0] for key in keys], [key[1] for key in keys], context.workspace_id, profile.fingerprint),
                )
            ).fetchall()
            return {
                (row["processing_digest"], row["input_hash"]): tuple(Vector.from_text(row["vector"]).to_list())
                for row in rows
            }

    async def commit_embedding_batch(
        self,
        context: WorkspaceContext,
        job: EmbeddingJob,
        profile: EmbeddingProfile,
        *,
        records: tuple[EmbeddingWrite, ...],
        cursor: str | None,
        complete: bool = False,
    ) -> EmbeddingJob:
        """Save vector/cache links and a cursor atomically after active-version/lease/content rechecks."""
        _bound(len(records), minimum=0, maximum=128)
        if (
            len({record.chunk_id for record in records}) != len(records)
            or job.profile_fingerprint != profile.fingerprint
        ):
            raise RecordConflict("Embedding batch identity does not match the leased profile.")
        async with self._transaction(context, operation="embedding_commit") as connection:
            await self._embedding_schema(connection, context)
            await connection.execute(
                "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE",
                (context.workspace_id,),
            )
            current = await _owned(connection, context, job, lock=True)
            await _profile(connection, context, profile)
            if records and (cursor != max(record.chunk_id for record in records) or cursor <= (current.cursor or "")):
                raise RecordConflict("Embedding progress must advance through its persisted chunk page.")
            if records:
                expected = await (
                    await connection.execute(
                        "SELECT chunk_id FROM workbench.chunks WHERE workspace_id=%s AND source_id=%s "
                        'AND version_id=%s AND chunk_id COLLATE "C">%s '
                        'ORDER BY chunk_id COLLATE "C" LIMIT %s FOR SHARE',
                        (
                            context.workspace_id,
                            current.source_id,
                            current.version_id,
                            current.cursor or "",
                            len(records),
                        ),
                    )
                ).fetchall()
                if sorted(record.chunk_id for record in records) != [row["chunk_id"] for row in expected]:
                    raise RecordConflict("Embedding progress cannot skip an uncommitted chunk.")
            for record in records:
                await self._write_embedding(connection, context, current, profile, record)
            if complete:
                missing = await (
                    await connection.execute(
                        "SELECT count(*) AS count FROM workbench.chunks c LEFT JOIN workbench.chunk_embeddings m "
                        "ON m.workspace_id=c.workspace_id AND m.chunk_id=c.chunk_id AND m.profile_fingerprint=%s "
                        "AND m.expected_content_hash=c.content_hash WHERE c.workspace_id=%s AND c.source_id=%s "
                        "AND c.version_id=%s AND m.chunk_id IS NULL",
                        (profile.fingerprint, context.workspace_id, current.source_id, current.version_id),
                    )
                ).fetchone()
                if missing != {"count": 0}:
                    raise RecordConflict("Embedding work cannot complete with missing vectors.")
            row = await (
                await connection.execute(
                    "UPDATE workbench.embedding_jobs SET cursor=%s,status=%s,owner_token=CASE WHEN "
                    "%s THEN NULL ELSE owner_token END,"
                    "lease_expires_at=CASE WHEN %s THEN NULL ELSE "
                    "clock_timestamp()+make_interval(secs=>lease_seconds) END,"
                    "error_code=NULL,updated_at=clock_timestamp() WHERE workspace_id=%s AND job_id=%s RETURNING *",
                    (
                        cursor if records else current.cursor,
                        "completed" if complete else "running",
                        complete,
                        complete,
                        context.workspace_id,
                        current.job_id,
                    ),
                )
            ).fetchone()
            if complete:
                await _publish_ready(connection, context, profile)
            return _job(row)

    async def _write_embedding(
        self,
        connection: AsyncConnection[dict[str, Any]],
        context: WorkspaceContext,
        job: EmbeddingJob,
        profile: EmbeddingProfile,
        record: EmbeddingWrite,
    ) -> None:
        if (record.source_id, record.version_id) != (job.source_id, job.version_id) or len(
            record.vector
        ) != profile.dimensions:
            raise InvalidEmbedding("Embedding dimensions or source identity do not match.")
        row = await (
            await connection.execute(
                "SELECT content_hash FROM workbench.chunks WHERE workspace_id=%s AND source_id=%s "
                "AND version_id=%s AND chunk_id=%s FOR SHARE",
                (context.workspace_id, record.source_id, record.version_id, record.chunk_id),
            )
        ).fetchone()
        if row != {"content_hash": record.expected_content_hash}:
            raise RecordConflict("The chunk changed before its embedding could commit.")
        await connection.execute(
            "INSERT INTO "
            "workbench.embedding_vectors(workspace_id,profile_fingerprint,"
            "processing_digest,input_hash,dimensions,vector) "
            "VALUES(%s,%s,%s,%s,%s,%s::vector) ON CONFLICT DO NOTHING",
            (
                context.workspace_id,
                profile.fingerprint,
                record.processing_digest,
                record.input_hash,
                profile.dimensions,
                Vector(list(record.vector)).to_text(),
            ),
        )
        await connection.execute(
            "INSERT INTO "
            "workbench.chunk_embeddings(workspace_id,chunk_id,source_id,version_id,"
            "profile_fingerprint,processing_digest,input_hash,expected_content_hash) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,chunk_id,profile_fingerprint) DO UPDATE "
            "SET "
            "processing_digest=EXCLUDED.processing_digest,input_hash=EXCLUDED.input_hash,expected_content_hash=EXCLUDED.expected_content_hash",
            (
                context.workspace_id,
                record.chunk_id,
                record.source_id,
                record.version_id,
                profile.fingerprint,
                record.processing_digest,
                record.input_hash,
                record.expected_content_hash,
            ),
        )

    async def fail_embedding_job(
        self,
        context: WorkspaceContext,
        job: EmbeddingJob,
        *,
        error_code: str,
        retryable: bool,
        retry_after_seconds: int,
    ) -> EmbeddingJob:
        """Persist bounded cooldown or poison state without erasing successfully committed progress."""
        _bound(retry_after_seconds, minimum=0, maximum=3600)
        if re.fullmatch(r"[A-Z0-9_]{1,64}", error_code) is None:
            raise RecordConflict("Embedding errors must use safe bounded categories.")
        async with self._transaction(context, operation="embedding_fail") as connection:
            await self._embedding_schema(connection, context)
            current = await _owned(connection, context, job, lock=True)
            status = "retryable_failed" if retryable and current.attempts < 5 else "poisoned"
            return _job(
                await (
                    await connection.execute(
                        "UPDATE workbench.embedding_jobs SET "
                        "status=%s,error_code=%s,available_at=clock_timestamp()+make_interval(secs=>%s),"
                        "owner_token=NULL,lease_expires_at=NULL,updated_at=clock_timestamp() WHERE "
                        "workspace_id=%s AND job_id=%s RETURNING *",
                        (status, error_code, retry_after_seconds, context.workspace_id, current.job_id),
                    )
                ).fetchone()
            )

    async def get_embedding_job(self, context: WorkspaceContext, job_id: str) -> EmbeddingJob | None:
        """Read only this workspace's safe durable status."""
        async with self._transaction(context, operation="embedding_job") as connection:
            await self._embedding_schema(connection, context)
            row = await (
                await connection.execute(
                    "SELECT * FROM workbench.embedding_jobs WHERE workspace_id=%s AND job_id=%s",
                    (context.workspace_id, job_id),
                )
            ).fetchone()
            return None if row is None else _job(row)

    async def retry_embedding_job(self, context: WorkspaceContext, job_id: str) -> EmbeddingJob:
        """Require operator-selected failed work and preserve the cursor while resetting the finite allowance."""
        async with self._transaction(context, operation="embedding_retry") as connection:
            await self._embedding_schema(connection, context)
            row = await (
                await connection.execute(
                    "SELECT j.* FROM workbench.embedding_jobs j JOIN workbench.embedding_model_profiles p "
                    "USING(workspace_id,profile_fingerprint) WHERE j.workspace_id=%s AND j.job_id=%s AND p.enabled "
                    "AND j.status IN ('poisoned','retryable_failed') AND " + _ACTIVE + " FOR UPDATE OF j",
                    (context.workspace_id, job_id),
                )
            ).fetchone()
            if row is None:
                raise RecordConflict("Only failed active embedding work can be explicitly retried.")
            return _job(
                await (
                    await connection.execute(
                        "UPDATE workbench.embedding_jobs SET status='queued',attempts=0,error_code=NULL,"
                        "available_at=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s "
                        "AND job_id=%s RETURNING *",
                        (context.workspace_id, job_id),
                    )
                ).fetchone()
            )

    async def embedding_coverage(self, context: WorkspaceContext, profile: EmbeddingProfile) -> EmbeddingCoverage:
        """Use one consistent snapshot for active eligibility, vector mappings and readiness checkpoint."""
        async with self._transaction(context, operation="embedding_coverage", repeatable_read=True) as connection:
            await self._embedding_schema(connection, context)
            return await _coverage(connection, context, profile)

    async def preview_embedding_backfill(
        self, context: WorkspaceContext, profile: EmbeddingProfile
    ) -> EmbeddingCoverage:
        """Inspect current eligibility without registering, enabling or enqueuing work."""
        return await self.embedding_coverage(context, profile)

    async def exact_embedding_search(
        self, context: WorkspaceContext, profile: EmbeddingProfile, query_vector: EmbeddingVector, *, limit: int = 10
    ) -> tuple[PersistedEmbeddingHit, ...]:
        """Search the complete current generation internally; this does not expose a dense HTTP profile."""
        _bound(limit, maximum=100)
        try:
            EmbeddingWrite(
                source_id="query",
                version_id="query",
                chunk_id="query",
                expected_content_hash="query",
                processing_digest="0" * 64,
                input_hash="0" * 64,
                vector=query_vector,
            )
        except ValueError:
            raise InvalidEmbedding("The query vector must be finite and normalized.") from None
        if len(query_vector) != profile.dimensions:
            raise InvalidEmbedding("The query vector dimension does not match the pinned profile.")
        async with self._transaction(context, operation="embedding_exact_search", repeatable_read=True) as connection:
            await self._embedding_schema(connection, context)
            coverage = await _coverage(connection, context, profile)
            if not coverage.ready:
                raise CorpusNotReady("The current embedding generation is incomplete.")
            rows = await (
                await connection.execute(
                    "SELECT "
                    "c.workspace_id,c.source_id,c.version_id,c.chunk_id,c.content,c.content_hash,"
                    "v.content_hash AS source_content_hash,"
                    "m.input_hash,m.profile_fingerprint,%s::bigint AS index_generation,e.vector <=> "
                    "%s::vector AS distance "
                    "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "JOIN workbench.chunk_embeddings m ON m.workspace_id=c.workspace_id AND m.chunk_id=c.chunk_id "
                    "AND m.profile_fingerprint=%s AND m.expected_content_hash=c.content_hash JOIN "
                    "workbench.embedding_vectors e "
                    "ON e.workspace_id=m.workspace_id AND e.profile_fingerprint=m.profile_fingerprint "
                    "AND e.processing_digest=m.processing_digest AND e.input_hash=m.input_hash "
                    "WHERE c.workspace_id=%s AND v.status='active' "
                    'ORDER BY distance,c.chunk_id COLLATE "C" LIMIT %s',
                    (
                        coverage.index_generation,
                        Vector(list(query_vector)).to_text(),
                        profile.fingerprint,
                        context.workspace_id,
                        limit,
                    ),
                )
            ).fetchall()
            return tuple(PersistedEmbeddingHit.model_validate(row) for row in rows)

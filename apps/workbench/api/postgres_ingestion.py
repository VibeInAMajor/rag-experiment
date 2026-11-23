"""Durable ingestion SQL behind the existing PostgreSQL persistence adapter."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from psycopg import AsyncConnection, Error, errors
from psycopg.types.json import Jsonb
from psycopg_pool import PoolClosed, PoolTimeout

from apps.workbench.api.persistence import (
    ActiveChunkPage,
    Chunk,
    CorpusLimitExceeded,
    DatabaseUnavailable,
    DocumentNotFound,
    IdempotencyConflict,
    IngestionInProgress,
    IngestionJob,
    IngestionOwnershipLost,
    IngestionTiming,
    PersistenceError,
    RecordConflict,
    SchemaIncompatible,
    Source,
    SourceDetail,
    SourceVersion,
    UploadReservation,
    VersionConflict,
    WorkspaceContext,
)

if TYPE_CHECKING:
    from apps.workbench.api.postgres import PostgresPersistence

_SHA256 = re.compile(r"[a-f0-9]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
_MAX_CORPUS_CHUNKS = 10000
_MAX_CORPUS_BYTES = 52428800
_ORDER = (
    "CASE WHEN jsonb_typeof(c.metadata->'ordinal')='number' "
    "AND c.metadata->>'ordinal' ~ '^[0-9]{1,6}$' THEN (c.metadata->>'ordinal')::integer ELSE 0 END"
)


def _require_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise RecordConflict("The durable operation returned no record.")
    return row


def _job(row: dict[str, Any] | None) -> IngestionJob:
    row = _require_row(row)
    fields = {
        name: row[name]
        for name in IngestionJob.model_fields
        if name not in {"source_id", "stages", "created_at", "updated_at", "finished_at"}
    }
    fields["source_id"] = row["reserved_source_id"]
    fields["stages"] = [IngestionTiming.model_validate(item) for item in row["stage_timings_jsonb"]]
    for name in ("created_at", "updated_at", "finished_at"):
        fields[name] = row[name].astimezone(UTC).isoformat().replace("+00:00", "Z") if row[name] is not None else None
    return IngestionJob.model_validate(fields)


def _lock_key(workspace_id: str, idempotency_key: str) -> int:
    digest = hashlib.sha256(f"workbench-ingestion-v1\0{workspace_id}\0{idempotency_key}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _verify_ingestion_schema(
    repository: PostgresPersistence, connection: AsyncConnection[dict[str, Any]]
) -> None:
    if await repository._verify_schema(connection) not in {"0002", "0003"}:
        raise SchemaIncompatible("Durable ingestion requires the explicit ingestion migration.")
    protected = await (
        await connection.execute(
            "SELECT c.relrowsecurity AND c.relforcerowsecurity AS protected FROM pg_class c "
            "WHERE c.oid=to_regclass('workbench.ingestion_jobs')"
        )
    ).fetchone()
    trigger = await (
        await connection.execute(
            "SELECT count(*) AS count FROM pg_trigger WHERE tgrelid=to_regclass('workbench.ingestion_jobs') "
            "AND tgname='ingestion_transition' AND tgenabled <> 'D'"
        )
    ).fetchone()
    if protected != {"protected": True} or trigger != {"count": 1}:
        raise SchemaIncompatible("The durable ingestion protections are unavailable.")
    await connection.execute(
        "SELECT reserved_source_id,reserved_version_id,owner_token,lock_key FROM workbench.ingestion_jobs WHERE false"
    )


async def ingestion_ready(repository: PostgresPersistence, context: WorkspaceContext) -> bool:
    """Keep upload unavailable on supported lexical-only installations or dependency failures."""
    try:
        async with repository._transaction(context, operation="ingestion_readiness") as connection:
            await _verify_ingestion_schema(repository, connection)
            await repository._require_workspace(connection, context)
            return True
    except PersistenceError:
        return False


async def _workspace_lock(
    repository: PostgresPersistence, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
) -> None:
    await repository._require_workspace(connection, context)
    await connection.execute(
        "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE", (context.workspace_id,)
    )


async def _active_version(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, source_id: str
) -> dict[str, Any] | None:
    return await (
        await connection.execute(
            "SELECT version_id,content_hash,metadata FROM workbench.source_versions "
            "WHERE workspace_id=%s AND source_id=%s AND status='active'",
            (context.workspace_id, source_id),
        )
    ).fetchone()


async def _check_expected(
    connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext, source_id: str, expected: str
) -> dict[str, Any]:
    source = await (
        await connection.execute(
            "SELECT metadata FROM workbench.sources WHERE workspace_id=%s AND source_id=%s FOR UPDATE",
            (context.workspace_id, source_id),
        )
    ).fetchone()
    if source is None:
        raise DocumentNotFound("Document is not available.")
    active = await _active_version(connection, context, source_id)
    if active is None or active["version_id"] != expected:
        raise VersionConflict("The active version no longer matches the expected version.")
    return source


async def _reserve_row(
    repository: PostgresPersistence,
    connection: AsyncConnection[dict[str, Any]],
    context: WorkspaceContext,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    source_content_sha256: str,
    source_id: str | None,
    expected_active_version_id: str | None,
    lock_key: int,
) -> UploadReservation:
    existing = await (
        await connection.execute(
            "SELECT * FROM workbench.ingestion_jobs WHERE workspace_id=%s AND idempotency_key=%s FOR UPDATE",
            (context.workspace_id, idempotency_key),
        )
    ).fetchone()
    if existing is not None:
        if (
            existing["request_fingerprint"] != request_fingerprint
            or existing["source_content_sha256"] != source_content_sha256
            or (
                existing["reserved_source_id"] if existing["operation"] == "update" else None,
                existing["expected_active_version_id"],
            )
            != (source_id, expected_active_version_id)
        ):
            raise IdempotencyConflict("The idempotency key belongs to a different request.")
        if existing["status"] not in ("completed", "failed"):
            existing = await (
                await connection.execute(
                    "UPDATE workbench.ingestion_jobs SET status='failed',error_code='INTERRUPTED',retryable=true,"
                    "updated_at=clock_timestamp(),finished_at=clock_timestamp() "
                    "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                    (context.workspace_id, existing["job_id"]),
                )
            ).fetchone()
        return UploadReservation(job=_job(existing), newly_reserved=False)
    await _workspace_lock(repository, connection, context)
    if source_id is not None:
        await _check_expected(connection, context, source_id, expected_active_version_id or "")
    source_id = source_id or uuid4().hex
    owner_token, job_id, version_id = uuid4().hex, uuid4().hex, uuid4().hex
    row = await (
        await connection.execute(
            "INSERT INTO workbench.ingestion_jobs(workspace_id,job_id,reserved_source_id,source_id,reserved_version_id,"
            "idempotency_key,request_fingerprint,source_content_sha256,operation,"
            "expected_active_version_id,owner_token,lock_key) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                context.workspace_id,
                job_id,
                source_id,
                source_id if expected_active_version_id is not None else None,
                version_id,
                idempotency_key,
                request_fingerprint,
                source_content_sha256,
                "update" if expected_active_version_id is not None else "create",
                expected_active_version_id,
                owner_token,
                lock_key,
            ),
        )
    ).fetchone()
    if row is None:
        raise RecordConflict("Reservation was not recorded.")
    return UploadReservation(job=_job(row), newly_reserved=True, owner_token=owner_token)


@asynccontextmanager
async def reserve_ingestion(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    *,
    idempotency_key: str,
    request_fingerprint: str,
    source_content_sha256: str,
    source_id: str | None,
    expected_active_version_id: str | None,
) -> AsyncIterator[UploadReservation]:
    """Hold a session advisory lock before committing reservation, releasing it on every exit or process death."""
    if (
        re.fullmatch(r"[A-Za-z0-9_-]{8,128}", idempotency_key) is None
        or _SHA256.fullmatch(request_fingerprint) is None
        or _SHA256.fullmatch(source_content_sha256) is None
        or (source_id is None) != (expected_active_version_id is None)
        or any(
            value is not None and _IDENTIFIER.fullmatch(value) is None
            for value in (source_id, expected_active_version_id)
        )
    ):
        raise RecordConflict("Invalid ingestion reservation.")
    key = _lock_key(context.workspace_id, idempotency_key)
    acquired, owner_token = False, None
    try:
        async with repository._pool.connection(timeout=repository._timeout) as connection:
            try:
                async with connection.transaction():
                    await repository._check_role(connection)
                    await connection.execute(
                        "SELECT set_config('workbench.workspace_id',%s,true)", (context.workspace_id,)
                    )
                    await connection.execute(
                        "SELECT set_config('statement_timeout',%s,true)", (str(repository._statement_timeout_ms),)
                    )
                    await connection.execute(
                        "SELECT set_config('lock_timeout',%s,true)", (str(repository._statement_timeout_ms),)
                    )
                    await _verify_ingestion_schema(repository, connection)
                    await repository._require_workspace(connection, context)
                    acquired = _require_row(
                        await (await connection.execute("SELECT pg_try_advisory_lock(%s) AS owned", (key,))).fetchone()
                    )["owned"]
                    if not acquired:
                        row = await (
                            await connection.execute(
                                "SELECT * FROM workbench.ingestion_jobs WHERE workspace_id=%s AND idempotency_key=%s",
                                (context.workspace_id, idempotency_key),
                            )
                        ).fetchone()
                        if row is not None and row["request_fingerprint"] != request_fingerprint:
                            raise IdempotencyConflict("The idempotency key belongs to a different request.")
                        if row is not None and row["status"] in ("completed", "failed"):
                            reservation = UploadReservation(job=_job(row), newly_reserved=False)
                        else:
                            raise IngestionInProgress(row["job_id"] if row else None)
                    else:
                        reservation = await _reserve_row(
                            repository,
                            connection,
                            context,
                            idempotency_key=idempotency_key,
                            request_fingerprint=request_fingerprint,
                            source_content_sha256=source_content_sha256,
                            source_id=source_id,
                            expected_active_version_id=expected_active_version_id,
                            lock_key=key,
                        )
                owner_token = reservation.owner_token
                if owner_token is not None:
                    repository._ingestion_owners[owner_token] = (
                        context.workspace_id,
                        reservation.job.job_id,
                        connection.info.backend_pid,
                    )
                yield reservation
            finally:
                if owner_token is not None:
                    repository._ingestion_owners.pop(owner_token, None)
                if acquired:
                    try:
                        async with asyncio.timeout(repository._timeout), connection.transaction():
                            await connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                    except (Error, TimeoutError):
                        await connection.close()
                    except BaseException:
                        await connection.close()
                        raise
    except (errors.UndefinedTable, errors.UndefinedColumn, errors.UndefinedObject):
        raise SchemaIncompatible("Durable ingestion schema is unavailable.") from None
    except errors.IntegrityError:
        raise RecordConflict("Ingestion conflicts with existing durable records.") from None
    except (Error, PoolTimeout, PoolClosed):
        raise DatabaseUnavailable("Ingestion database connection is unavailable.") from None


async def _owned_job(
    repository: PostgresPersistence,
    connection: AsyncConnection[dict[str, Any]],
    context: WorkspaceContext,
    *,
    job_id: str,
    owner_token: str,
) -> dict[str, Any]:
    owner = repository._ingestion_owners.get(owner_token)
    if owner is None or owner[:2] != (context.workspace_id, job_id):
        raise IngestionOwnershipLost("Ingestion ownership is unavailable.")
    row = await (
        await connection.execute(
            "SELECT * FROM workbench.ingestion_jobs WHERE workspace_id=%s AND job_id=%s FOR UPDATE",
            (context.workspace_id, job_id),
        )
    ).fetchone()
    if row is None or row["owner_token"] != owner_token:
        raise IngestionOwnershipLost("Ingestion ownership is unavailable.")
    key = row["lock_key"]
    lock = await (
        await connection.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=%s AND granted "
            "AND classid::bigint=%s AND objid::bigint=%s AND objsubid=1) AS owned",
            (owner[2], (key >> 32) & 0xFFFFFFFF, key & 0xFFFFFFFF),
        )
    ).fetchone()
    if lock != {"owned": True}:
        raise IngestionOwnershipLost("The ingestion session owner was interrupted.")
    return row


async def transition_ingestion(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    *,
    job_id: str,
    owner_token: str,
    stage: Literal["parsing", "chunking", "publishing"],
) -> IngestionJob:
    """Persist only the next legal stage owned by the still-live request."""
    previous = {"parsing": "pending", "chunking": "parsing", "publishing": "chunking"}.get(stage)
    async with repository._transaction(context, operation="transition_ingestion") as connection:
        row = await _owned_job(repository, connection, context, job_id=job_id, owner_token=owner_token)
        if previous is None or row["status"] != previous:
            raise IngestionOwnershipLost("Ingestion checkpoint is no longer current.")
        updated = await (
            await connection.execute(
                "UPDATE workbench.ingestion_jobs SET status=%s,stage=%s,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                (stage, stage, context.workspace_id, job_id),
            )
        ).fetchone()
        return _job(updated)


async def recover_ingestions(repository: PostgresPersistence, context: WorkspaceContext) -> int:
    """Diagnose only reservations without any live session-lock holder; never replay unavailable bytes."""
    async with repository._transaction(context, operation="recover_ingestions") as connection:
        if await repository._verify_schema(connection) not in {"0002", "0003"}:
            return 0
        await _verify_ingestion_schema(repository, connection)
        await repository._require_workspace(connection, context)
        rows = await (
            await connection.execute(
                "SELECT job_id,lock_key FROM workbench.ingestion_jobs WHERE workspace_id=%s "
                "AND status NOT IN ('completed','failed') ORDER BY created_at LIMIT 10000 FOR UPDATE SKIP LOCKED",
                (context.workspace_id,),
            )
        ).fetchall()
        recovered = 0
        for row in rows:
            locked = await (
                await connection.execute("SELECT pg_try_advisory_xact_lock(%s) AS owned", (row["lock_key"],))
            ).fetchone()
            if locked != {"owned": True}:
                continue
            await connection.execute(
                "UPDATE workbench.ingestion_jobs SET status='failed',error_code='INTERRUPTED',retryable=true,"
                "finished_at=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s AND job_id=%s",
                (context.workspace_id, row["job_id"]),
            )
            recovered += 1
        return recovered


def _timings(stages: list[IngestionTiming], *, allow_publication: bool = False) -> list[dict[str, Any]]:
    allowed = ("parsing", "chunking", "publication") if allow_publication else ("parsing", "chunking")
    if (
        len(stages) > len(allowed)
        or any(item.stage not in allowed for item in stages)
        or len({item.stage for item in stages}) != len(stages)
    ):
        raise RecordConflict("Invalid ingestion timing records.")
    return [item.model_dump() for item in stages]


async def fail_ingestion(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    *,
    job_id: str,
    owner_token: str,
    error_code: str,
    retryable: bool,
    stages: list[IngestionTiming],
) -> IngestionJob:
    """Persist only a safe failure code while preserving the previous active source version."""
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code) is None or type(retryable) is not bool:
        raise RecordConflict("Invalid ingestion failure metadata.")
    timings = _timings(stages, allow_publication=True)
    async with repository._transaction(context, operation="fail_ingestion") as connection:
        row = await _owned_job(repository, connection, context, job_id=job_id, owner_token=owner_token)
        if row["status"] in ("completed", "failed"):
            return _job(row)
        updated = await (
            await connection.execute(
                "UPDATE workbench.ingestion_jobs SET status='failed',error_code=%s,retryable=%s,stage_timings_jsonb=%s,"
                "updated_at=clock_timestamp(),finished_at=clock_timestamp() "
                "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                (error_code, retryable, Jsonb(timings), context.workspace_id, job_id),
            )
        ).fetchone()
        return _job(updated)


async def complete_ingestion_with_publication(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    *,
    job_id: str,
    owner_token: str,
    source: Source,
    version: SourceVersion,
    chunks: list[Chunk],
    stages: list[IngestionTiming],
) -> IngestionJob:
    """Reuse the existing publisher inside the same transaction as the guarded terminal job."""
    started = monotonic()
    timings = _timings(stages)
    fingerprint = version.metadata.get("processing_profile_fingerprint")
    if (
        not isinstance(fingerprint, str)
        or _SHA256.fullmatch(fingerprint) is None
        or any(chunk.embedding is not None for chunk in chunks)
        or (version.workspace_id, version.source_id) != (context.workspace_id, source.source_id)
    ):
        raise RecordConflict("Invalid lexical ingestion publication.")
    async with repository._transaction(context, operation="complete_ingestion") as connection:
        await _workspace_lock(repository, connection, context)
        row = await _owned_job(repository, connection, context, job_id=job_id, owner_token=owner_token)
        if row["status"] != "publishing" or (
            source.workspace_id,
            source.source_id,
            version.version_id,
            version.content_hash,
        ) != (
            context.workspace_id,
            row["reserved_source_id"],
            row["reserved_version_id"],
            row["source_content_sha256"],
        ):
            raise IngestionOwnershipLost("Ingestion publication does not match its reservation.")
        source_metadata: dict[str, Any] = {}
        if row["operation"] == "create":
            existing_source = await (
                await connection.execute(
                    "SELECT source_id FROM workbench.sources WHERE workspace_id=%s AND source_id=%s FOR UPDATE",
                    (context.workspace_id, source.source_id),
                )
            ).fetchone()
            if existing_source is not None:
                raise RecordConflict("The newly reserved source identity already exists.")
        if row["operation"] == "update":
            existing = await _check_expected(connection, context, source.source_id, row["expected_active_version_id"])
            source_metadata = existing["metadata"]
        active = await _active_version(connection, context, source.source_id)
        unchanged = (
            active is not None
            and active["content_hash"] == version.content_hash
            and active["metadata"].get("processing_profile_fingerprint") == fingerprint
        )
        if unchanged:
            effective_version = _require_row(active)["version_id"]
            count = await (
                await connection.execute(
                    "SELECT count(*) AS count FROM workbench.chunks "
                    "WHERE workspace_id=%s AND source_id=%s AND version_id=%s",
                    (context.workspace_id, source.source_id, effective_version),
                )
            ).fetchone()
            chunk_count = _require_row(count)["count"]
            outcome = "unchanged"
        else:
            summary = await repository._corpus_summary(connection, context)
            old_source = await (
                await connection.execute(
                    "SELECT count(*) AS count,COALESCE(sum(octet_length(c.content)),0) AS bytes "
                    "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "WHERE c.workspace_id=%s AND c.source_id=%s AND v.status='active'",
                    (context.workspace_id, source.source_id),
                )
            ).fetchone()
            previous = _require_row(old_source)
            if (
                summary.chunk_count - previous["count"] + len(chunks) > _MAX_CORPUS_CHUNKS
                or summary.content_bytes
                - previous["bytes"]
                + sum(len(chunk.content.encode("utf-8")) for chunk in chunks)
                > _MAX_CORPUS_BYTES
            ):
                raise CorpusLimitExceeded("Publication exceeds the lexical corpus limits.")
            source = source.model_copy(update={"metadata": {**source_metadata, **source.metadata}})
            await repository._publish(connection, context=context, source=source, version=version, chunks=chunks)
            effective_version, chunk_count = version.version_id, len(chunks)
            outcome = "created" if row["operation"] == "create" else "updated"
        corpus = await repository._corpus_summary(connection, context)
        timings.append(IngestionTiming(stage="publication", duration_ms=(monotonic() - started) * 1000).model_dump())
        updated = await (
            await connection.execute(
                "UPDATE workbench.ingestion_jobs SET status='completed',stage='completed',source_id=reserved_source_id,"
                "effective_version_id=%s,processing_profile_fingerprint=%s,chunk_count=%s,outcome=%s,corpus_revision=%s,"
                "stage_timings_jsonb=%s,updated_at=clock_timestamp(),finished_at=clock_timestamp() "
                "WHERE workspace_id=%s AND job_id=%s RETURNING *",
                (
                    effective_version,
                    fingerprint,
                    chunk_count,
                    outcome,
                    corpus.corpus_revision,
                    Jsonb(timings),
                    context.workspace_id,
                    job_id,
                ),
            )
        ).fetchone()
        return _job(updated)


async def get_ingestion_job(
    repository: PostgresPersistence, context: WorkspaceContext, *, job_id: str
) -> IngestionJob | None:
    """Read scoped state and diagnose an orphan after reconnect, without disturbing any live owner."""
    async with repository._transaction(context, operation="get_ingestion_job") as connection:
        await _verify_ingestion_schema(repository, connection)
        await repository._require_workspace(connection, context)
        row = await (
            await connection.execute(
                "SELECT * FROM workbench.ingestion_jobs WHERE workspace_id=%s AND job_id=%s",
                (context.workspace_id, job_id),
            )
        ).fetchone()
        if row is not None and row["status"] not in ("completed", "failed"):
            lock = await (
                await connection.execute("SELECT pg_try_advisory_xact_lock(%s) AS owned", (row["lock_key"],))
            ).fetchone()
            if lock == {"owned": True}:
                interrupted = await (
                    await connection.execute(
                        "UPDATE workbench.ingestion_jobs SET status='failed',error_code='INTERRUPTED',retryable=true,"
                        "updated_at=clock_timestamp(),finished_at=clock_timestamp() "
                        "WHERE workspace_id=%s AND job_id=%s "
                        "AND status NOT IN ('completed','failed') RETURNING *",
                        (context.workspace_id, job_id),
                    )
                ).fetchone()
                row = (
                    interrupted
                    or await (
                        await connection.execute(
                            "SELECT * FROM workbench.ingestion_jobs WHERE workspace_id=%s AND job_id=%s",
                            (context.workspace_id, job_id),
                        )
                    ).fetchone()
                )
        return _job(row) if row else None


async def get_source_detail(
    repository: PostgresPersistence, context: WorkspaceContext, *, source_id: str
) -> SourceDetail | None:
    """Read actual source and active-version metadata without inventing original-file availability."""
    async with repository._transaction(context, operation="get_source_detail", repeatable_read=True) as connection:
        corpus = await repository._corpus_summary(connection, context)
        row = await (
            await connection.execute(
                "SELECT workspace_id,source_id,title,media_type,metadata,updated_at "
                "FROM workbench.sources WHERE workspace_id=%s AND source_id=%s",
                (context.workspace_id, source_id),
            )
        ).fetchone()
        if row is None:
            return None
        active = await (
            await connection.execute(
                "SELECT workspace_id,source_id,version_id,status,content_hash,metadata "
                "FROM workbench.source_versions WHERE workspace_id=%s AND source_id=%s AND status='active'",
                (context.workspace_id, source_id),
            )
        ).fetchone()
        return SourceDetail(
            source=Source.model_validate({name: row[name] for name in Source.model_fields}),
            version=SourceVersion.model_validate(active) if active else None,
            chunk_count=(
                _require_row(
                    await (
                        await connection.execute(
                            "SELECT count(*) AS count FROM workbench.chunks "
                            "WHERE workspace_id=%s AND source_id=%s AND version_id=%s",
                            (context.workspace_id, source_id, active["version_id"]),
                        )
                    ).fetchone()
                )["count"]
                if active
                else 0
            ),
            corpus_revision=corpus.corpus_revision,
            updated_at=row["updated_at"].astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )


async def list_active_chunks(
    repository: PostgresPersistence,
    context: WorkspaceContext,
    *,
    source_id: str,
    limit: int,
    after_chunk_id: str | None,
    expected_corpus_revision: str | None,
) -> ActiveChunkPage | None:
    """Use ordinal then ID keysets, with identity/corpus guards instead of offset pagination."""
    from apps.workbench.api.postgres import _CHUNK_COLUMNS, _chunk

    if type(limit) is not int or not 1 <= limit <= 100:
        raise RecordConflict("Invalid chunk pagination bounds.")
    async with repository._transaction(context, operation="list_active_chunks", repeatable_read=True) as connection:
        corpus = await repository._corpus_summary(connection, context)
        if expected_corpus_revision is not None and corpus.corpus_revision != expected_corpus_revision:
            raise RecordConflict("The chunk cursor belongs to an expired corpus snapshot.")
        active = await _active_version(connection, context, source_id)
        if active is None:
            return None
        after_order = -1
        if after_chunk_id is not None:
            anchor = await (
                await connection.execute(
                    f"SELECT ({_ORDER}) AS ordinal FROM workbench.chunks c "
                    "WHERE workspace_id=%s AND source_id=%s AND version_id=%s AND chunk_id=%s",
                    (context.workspace_id, source_id, active["version_id"], after_chunk_id),
                )
            ).fetchone()
            if anchor is None:
                raise RecordConflict("The chunk cursor is not valid for this source version.")
            after_order = anchor["ordinal"]
        rows = await (
            await connection.execute(
                f"SELECT {_CHUNK_COLUMNS} FROM workbench.chunks c "
                "WHERE workspace_id=%s AND source_id=%s AND version_id=%s "
                f'AND (({_ORDER}),c.chunk_id COLLATE "C")>(%s,%s COLLATE "C") '
                f'ORDER BY ({_ORDER}),c.chunk_id COLLATE "C" LIMIT %s',
                (context.workspace_id, source_id, active["version_id"], after_order, after_chunk_id or "", limit + 1),
            )
        ).fetchall()
        items = [_chunk(row) for row in rows[:limit]]
        return ActiveChunkPage(
            source_id=source_id,
            source_version_id=active["version_id"],
            corpus_revision=corpus.corpus_revision,
            items=items,
            next_after=items[-1].chunk_id if len(rows) > limit else None,
        )

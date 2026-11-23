"""Bounded PostgreSQL repository; all application data operations carry workspace scope."""

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC
from math import isfinite
from time import monotonic
from typing import Any, Literal

from pgvector import Vector
from psycopg import AsyncConnection, Error, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolClosed, PoolTimeout
from pydantic import ValidationError

from apps.workbench.api.persistence import (
    ActiveChunkPage,
    Chunk,
    CorpusNotReady,
    CorpusSnapshot,
    DatabaseUnavailable,
    DocumentRecord,
    IndexGeneration,
    IngestionJob,
    IngestionTiming,
    InvalidEmbedding,
    LexicalHit,
    LexicalSearchSnapshot,
    LocalOriginalRecord,
    LocalOriginalRegistration,
    PersistenceError,
    PersistenceReady,
    ProfileNotAvailable,
    RecordConflict,
    SchemaIncompatible,
    SeedConflict,
    Source,
    SourceDetail,
    SourceVersion,
    UploadReservation,
    VectorHit,
    Workspace,
    WorkspaceContext,
    WorkspaceNotFound,
)
from apps.workbench.api.profile_registry import ProfileDefinition, ProfileRollout

_CHUNK_COLUMNS = (
    "c.workspace_id,c.source_id,c.version_id,c.chunk_id,c.title,c.content,c.content_hash,"
    "c.page,c.metadata,c.embedding::text AS embedding,c.embedding_profile_id,c.dimensions"
)
_LEXICAL_INDEX_QUERY = (
    "SELECT i.indisvalid AND i.indisready AND i.indnkeyatts=1 AND am.amname='gin' "
    "AND pg_get_indexdef(i.indexrelid,1,true)='search_vector' AS usable "
    "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am am ON am.oid=c.relam "
    "WHERE i.indexrelid=to_regclass('workbench.chunks_search_vector') "
    "AND i.indrelid=to_regclass('workbench.chunks')"
)
_logger = logging.getLogger("workbench.persistence")


class _PoolLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Connector diagnostics can include endpoint/role or server-controlled text.
        record.msg = "Database pool state changed."
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


_POOL_LOG_FILTER = _PoolLogFilter()


def _chunk(row: dict[str, Any]) -> Chunk:
    fields = {name: row[name] for name in Chunk.model_fields}
    fields["embedding"] = None if row["embedding"] is None else Vector.from_text(row["embedding"]).to_list()
    return Chunk.model_validate(fields)


def _demo_original(source_id: str, source_metadata: dict[str, Any], version_metadata: dict[str, Any]) -> bool:
    return source_id.startswith("demo-") or any(
        "development_seed" in metadata or metadata.get("synthetic", False) is not False
        for metadata in (source_metadata, version_metadata)
    )


class PostgresPersistence:
    """Use an application role and short transactions; never run migrations on startup."""

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 4,
        timeout: float = 3.0,
        statement_timeout_ms: int = 3000,
        snapshot_mode: Literal["persisted", "legacy"] = "persisted",
    ) -> None:
        if not 1 <= min_size <= max_size <= 16 or not 0 < timeout <= 30 or not 1 <= statement_timeout_ms <= 30000:
            raise ValueError("Invalid database pool bounds.")
        self._timeout = timeout
        if snapshot_mode not in {"persisted", "legacy"}:
            raise ValueError("Invalid corpus snapshot mode.")
        self._snapshot_mode = snapshot_mode
        self._statement_timeout_ms = statement_timeout_ms
        self._ingestion_owners: dict[str, tuple[str, str, int]] = {}
        logging.getLogger("psycopg.pool").addFilter(_POOL_LOG_FILTER)
        self._pool = AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            max_waiting=16,
            open=False,
            kwargs={"row_factory": dict_row, "connect_timeout": max(1, int(timeout))},
            check=AsyncConnectionPool.check_connection,
        )

    async def start(self) -> None:
        """Open connections while allowing a failed initial connection to recover."""
        try:
            await self._pool.open()
            async with self._pool.connection() as connection:
                await self._check_role(connection)
        except (Error, PoolTimeout, PoolClosed):
            raise DatabaseUnavailable("Database connection is unavailable.") from None

    async def close(self) -> None:
        """Close the pool and its owned connection workers."""
        await self._pool.close()

    async def _check_role(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        row = await (
            await connection.execute(
                "SELECT r.rolsuper,r.rolbypassrls,r.rolcreatedb,r.rolcreaterole,"
                "COALESCE(has_schema_privilege(current_user,to_regnamespace('workbench'),'CREATE'),false) "
                "AS can_create,"
                "EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='workbench' AND pg_has_role(current_user,c.relowner,'USAGE')) AS owns_tables "
                "FROM pg_roles r WHERE r.rolname=current_user"
            )
        ).fetchone()
        if row is None or any(row.values()):
            raise SchemaIncompatible("An unprivileged application role is required.")

    @asynccontextmanager
    async def _transaction(
        self, context: WorkspaceContext, *, operation: str, repeatable_read: bool = False
    ) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
        started = monotonic()
        outcome = "interrupted"
        try:
            async with self._pool.connection(timeout=self._timeout) as connection, connection.transaction():
                if repeatable_read:
                    await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                await self._check_role(connection)
                await connection.execute("SELECT set_config('workbench.workspace_id',%s,true)", (context.workspace_id,))
                await connection.execute(
                    "SELECT set_config('statement_timeout',%s,true)", (str(self._statement_timeout_ms),)
                )
                await connection.execute(
                    "SELECT set_config('lock_timeout',%s,true)", (str(self._statement_timeout_ms),)
                )
                yield connection
            outcome = "success"
        except (errors.UndefinedTable, errors.UndefinedColumn, errors.UndefinedObject):
            outcome = "schema_incompatible"
            raise SchemaIncompatible("The database schema is incompatible.") from None
        except errors.IntegrityError:
            outcome = "record_conflict"
            raise RecordConflict("The records conflict with stored identities.") from None
        except (Error, PoolTimeout, PoolClosed):
            outcome = "database_unavailable"
            raise DatabaseUnavailable("The database operation is unavailable.") from None
        except PersistenceError as error:
            outcome = type(error).__name__
            raise
        finally:
            _logger.info(
                json.dumps(
                    {
                        "event": "database_operation",
                        "operation": operation,
                        "workspace_id": context.workspace_id,
                        "trace_id": context.trace_id,
                        "status": outcome,
                        "duration_ms": round((monotonic() - started) * 1000, 3),
                    },
                    separators=(",", ":"),
                )
            )

    async def _require_workspace(self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> None:
        row = await (
            await connection.execute(
                "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s", (context.workspace_id,)
            )
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound("Workspace is not available.")

    async def _verify_schema(self, connection: AsyncConnection[dict[str, Any]]) -> str:
        from apps.workbench.api.db_migrations import MigrationError, migration_ledger

        revision = await (await connection.execute("SELECT version_num FROM workbench.alembic_version")).fetchall()
        ledger = await (
            await connection.execute(
                "SELECT revision,checksum,tool_version FROM workbench.schema_migrations ORDER BY revision"
            )
        ).fetchall()
        extension = await (
            await connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).fetchone()
        protected = await (
            await connection.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='workbench' AND c.relname IN ('workspaces','sources','source_versions','chunks') "
                "AND c.relrowsecurity AND c.relforcerowsecurity ORDER BY c.relname"
            )
        ).fetchall()
        applied = revision[0]["version_num"] if len(revision) == 1 else ""
        try:
            expected_ledger = [
                dict(zip(("revision", "checksum", "tool_version"), row, strict=True))
                for row in migration_ledger(applied)
            ]
        except MigrationError:
            raise SchemaIncompatible("Required database revision or extension is unavailable.") from None
        if (
            ledger != expected_ledger
            or extension != {"extversion": "0.8.2"}
            or protected
            != [
                {"relname": "chunks"},
                {"relname": "source_versions"},
                {"relname": "sources"},
                {"relname": "workspaces"},
            ]
        ):
            raise SchemaIncompatible("Required database revision or extension is unavailable.")
        return applied

    async def readiness(self, context: WorkspaceContext) -> PersistenceReady:
        """Verify exact migration/extension versions and an active persisted corpus."""
        async with self._transaction(context, operation="readiness", repeatable_read=True) as connection:
            revision = await self._verify_schema(connection)
            await self._require_workspace(connection, context)
            if self._snapshot_mode == "persisted":
                generation = await self._index_generation(connection, context)
                if generation.active_chunk_count == 0:
                    raise DatabaseUnavailable("No committed active corpus is available.")
                return PersistenceReady(
                    schema_revision=revision,
                    workspace_id=context.workspace_id,
                    source_count=generation.active_source_count,
                    chunk_count=generation.active_chunk_count,
                )
            counts = await (
                await connection.execute(
                    "SELECT count(DISTINCT c.source_id) AS source_count,count(*) AS chunk_count "
                    "FROM workbench.chunks c JOIN workbench.source_versions v "
                    "USING(workspace_id,source_id,version_id) WHERE c.workspace_id=%s AND v.status='active'",
                    (context.workspace_id,),
                )
            ).fetchone()
            if counts is None or counts["chunk_count"] == 0:
                raise DatabaseUnavailable("No committed active corpus is available.")
            return PersistenceReady(schema_revision=revision, workspace_id=context.workspace_id, **counts)

    async def create_workspace(self, context: WorkspaceContext, workspace: Workspace) -> None:
        """Create a workspace matching the server-resolved scope."""
        if workspace.workspace_id != context.workspace_id:
            raise WorkspaceNotFound("Workspace is not available.")
        async with self._transaction(context, operation="create_workspace") as connection:
            await connection.execute(
                "INSERT INTO workbench.workspaces(workspace_id,name,metadata) VALUES(%s,%s,%s)",
                (workspace.workspace_id, workspace.name, Jsonb(workspace.metadata)),
            )

    async def list_workspaces(self, context: WorkspaceContext) -> list[Workspace]:
        """Return the single authorized workspace."""
        async with self._transaction(context, operation="list_workspaces") as connection:
            await self._require_workspace(connection, context)
            rows = await (
                await connection.execute(
                    "SELECT workspace_id,name,metadata FROM workbench.workspaces WHERE workspace_id=%s",
                    (context.workspace_id,),
                )
            ).fetchall()
            return [Workspace.model_validate(row) for row in rows]

    async def list_sources(self, context: WorkspaceContext) -> list[Source]:
        """Return source metadata in stable source identity order."""
        async with self._transaction(context, operation="list_sources") as connection:
            await self._require_workspace(connection, context)
            rows = await (
                await connection.execute(
                    "SELECT workspace_id,source_id,title,media_type,metadata FROM workbench.sources "
                    "WHERE workspace_id=%s ORDER BY source_id LIMIT 10000",
                    (context.workspace_id,),
                )
            ).fetchall()
            return [Source.model_validate(row) for row in rows]

    async def get_local_original(
        self, context: WorkspaceContext, *, source_id: str, version_id: str
    ) -> LocalOriginalRecord | None:
        """Look up an active registered original without relaxing workspace isolation."""
        async with self._transaction(context, operation="get_local_original") as connection:
            await self._require_workspace(connection, context)
            row = await (
                await connection.execute(
                    "SELECT s.metadata AS source_metadata,v.metadata AS version_metadata "
                    "FROM workbench.source_versions v JOIN workbench.sources s USING(workspace_id,source_id) "
                    "WHERE v.workspace_id=%s AND v.source_id=%s AND v.version_id=%s AND v.status='active'",
                    (context.workspace_id, source_id, version_id),
                )
            ).fetchone()
            if row is None:
                return None
            registration = None
            if "local_original" in row["version_metadata"]:
                # Corrupt or pre-contract metadata never grants a filesystem action.
                with suppress(ValidationError):
                    registration = LocalOriginalRegistration.model_validate(row["version_metadata"]["local_original"])
            return LocalOriginalRecord(
                source_id=source_id,
                version_id=version_id,
                is_demo=_demo_original(source_id, row["source_metadata"], row["version_metadata"]),
                registration=registration,
            )

    async def register_local_original(
        self, context: WorkspaceContext, *, source_id: str, version_id: str, relative_path: str, sha256: str
    ) -> None:
        """Attach an immutable original registration to an existing real active version."""
        registration = LocalOriginalRegistration(relative_path=relative_path, sha256=sha256)
        async with self._transaction(context, operation="register_local_original") as connection:
            await self._require_workspace(connection, context)
            await connection.execute(
                "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE",
                (context.workspace_id,),
            )
            indexed = await self._prepare_generation(connection, context)
            source = await (
                await connection.execute(
                    "SELECT metadata FROM workbench.sources WHERE workspace_id=%s AND source_id=%s FOR UPDATE",
                    (context.workspace_id, source_id),
                )
            ).fetchone()
            if source is None:
                raise RecordConflict("The original cannot be registered for this source version.")
            version = await (
                await connection.execute(
                    "SELECT metadata,status FROM workbench.source_versions "
                    "WHERE workspace_id=%s AND source_id=%s AND version_id=%s FOR UPDATE",
                    (context.workspace_id, source_id, version_id),
                )
            ).fetchone()
            if (
                version is None
                or version["status"] != "active"
                or _demo_original(source_id, source["metadata"], version["metadata"])
            ):
                raise RecordConflict("The original cannot be registered for this source version.")
            if "local_original" in version["metadata"]:
                if version["metadata"]["local_original"] != registration.model_dump():
                    raise RecordConflict("The original registration is already bound to this source version.")
                return
            await connection.execute(
                "UPDATE workbench.source_versions SET metadata=jsonb_set(metadata,'{local_original}',%s::jsonb),"
                "updated_at=now() WHERE workspace_id=%s AND source_id=%s AND version_id=%s",
                (Jsonb(registration.model_dump()), context.workspace_id, source_id, version_id),
            )
            if indexed:
                from apps.workbench.api.postgres_indexes import commit_source_generation

                await commit_source_generation(connection, context, source_id=source_id, event_kind="metadata")

    async def _require_lexical_index(self, connection: AsyncConnection[dict[str, Any]]) -> None:
        index = await (await connection.execute(_LEXICAL_INDEX_QUERY)).fetchone()
        if index != {"usable": True}:
            raise SchemaIncompatible("The required lexical index is unavailable.")

    async def _legacy_corpus_snapshot(
        self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
    ) -> CorpusSnapshot:
        await self._verify_schema(connection)
        await self._require_workspace(connection, context)
        await self._require_lexical_index(connection)
        counts = await (
            await connection.execute(
                "SELECT count(*) AS chunk_count, COALESCE(sum(octet_length(c.content)),0)::bigint AS content_bytes "
                "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                "WHERE c.workspace_id=%s AND v.status='active'",
                (context.workspace_id,),
            )
        ).fetchone()
        if counts is None or counts["chunk_count"] > 10000 or counts["content_bytes"] > 52428800:
            raise CorpusNotReady("The complete corpus exceeds the approved profile bounds.")
        documents = await self._document_records(connection, context)
        chunks = await (
            await connection.execute(
                "SELECT c.chunk_id,c.source_id,c.version_id,c.title,c.page, "
                "encode(sha256(convert_to(c.content,'UTF8')),'hex') AS content_sha256, "
                "encode(sha256(convert_to(c.metadata::text,'UTF8')),'hex') AS metadata_sha256, "
                "v.content_hash AS version_content_hash, "
                "encode(sha256(convert_to(v.metadata::text,'UTF8')),'hex') AS version_metadata_sha256 "
                "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                "WHERE c.workspace_id=%s AND v.status='active' ORDER BY c.chunk_id",
                (context.workspace_id,),
            )
        ).fetchall()
        fingerprint = json.dumps(
            {
                "workspace_id": context.workspace_id,
                "documents": [document.model_dump() for document in documents],
                "chunks": chunks,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return CorpusSnapshot(
            corpus_revision=f"corpus-{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()}",
            documents=documents,
            **counts,
        )

    async def _document_records(
        self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
    ) -> list[DocumentRecord]:
        rows = await (
            await connection.execute(
                "SELECT s.source_id,s.title,s.media_type,active.version_id AS active_version_id, "
                "COALESCE(active.chunk_count,0)::bigint AS chunk_count, "
                "greatest(s.updated_at,COALESCE(latest.updated_at,s.updated_at)) AS updated_at, "
                "CASE WHEN latest.status='error' THEN 'error' WHEN latest.status='staged' THEN 'processing' "
                "WHEN active.version_id IS NOT NULL THEN 'ready' ELSE 'processing' END AS status "
                "FROM workbench.sources s LEFT JOIN LATERAL ("
                "SELECT v.version_id,count(c.chunk_id) AS chunk_count FROM workbench.source_versions v "
                "LEFT JOIN workbench.chunks c USING(workspace_id,source_id,version_id) "
                "WHERE v.workspace_id=s.workspace_id AND v.source_id=s.source_id AND v.status='active' "
                "GROUP BY v.workspace_id,v.source_id,v.version_id) active ON true "
                "LEFT JOIN LATERAL (SELECT status,updated_at FROM workbench.source_versions v "
                "WHERE v.workspace_id=s.workspace_id AND v.source_id=s.source_id "
                "ORDER BY updated_at DESC,version_id DESC LIMIT 1) latest ON true "
                "WHERE s.workspace_id=%s ORDER BY s.source_id LIMIT 10001",
                (context.workspace_id,),
            )
        ).fetchall()
        if len(rows) > 10000:
            raise CorpusNotReady("The complete corpus exceeds the approved profile bounds.")
        return [
            DocumentRecord(
                **{
                    **row,
                    "updated_at": row["updated_at"].astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "error_code": "PROCESSING_FAILED" if row["status"] == "error" else None,
                }
            )
            for row in rows
        ]

    async def _index_generation(
        self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
    ) -> IndexGeneration:
        from apps.workbench.api.postgres_indexes import read_index_state

        return IndexGeneration.model_validate(await read_index_state(connection, context))

    async def _prepare_generation(self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> bool:
        revision = await self._verify_schema(connection)
        if revision >= "0003":
            await self._index_generation(connection, context)
            return True
        if self._snapshot_mode != "legacy":
            raise SchemaIncompatible("Persisted corpus snapshots require the explicit generation migration.")
        return False

    async def current_index_generation(
        self, context: WorkspaceContext, *, expected_generation_id: int | None = None
    ) -> IndexGeneration:
        """Read the current committed generation; historical snapshots cannot be selected."""
        if expected_generation_id is not None and (
            type(expected_generation_id) is not int or expected_generation_id < 0
        ):
            raise ValueError("Invalid generation identity.")
        async with self._transaction(context, operation="index_generation", repeatable_read=True) as connection:
            await self._verify_schema(connection)
            await self._require_workspace(connection, context)
            await self._require_lexical_index(connection)
            generation = await self._index_generation(connection, context)
            if expected_generation_id is not None and generation.generation_id != expected_generation_id:
                raise RecordConflict("The requested generation is no longer current.")
            return generation

    async def _corpus_summary(
        self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
    ) -> CorpusSnapshot:
        if self._snapshot_mode == "legacy":
            return await self._legacy_corpus_snapshot(connection, context)
        await self._verify_schema(connection)
        await self._require_workspace(connection, context)
        await self._require_lexical_index(connection)
        generation = await self._index_generation(connection, context)
        if generation.active_chunk_count > 10000 or generation.content_bytes > 52428800:
            raise CorpusNotReady("The complete corpus exceeds the approved profile bounds.")
        return CorpusSnapshot(
            corpus_id=generation.corpus_id,
            corpus_revision=generation.corpus_revision,
            documents=[],
            chunk_count=generation.active_chunk_count,
            content_bytes=generation.content_bytes,
            index_generation_id=generation.generation_id,
        )

    async def _corpus_snapshot(
        self, connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext
    ) -> CorpusSnapshot:
        summary = await self._corpus_summary(connection, context)
        if self._snapshot_mode == "legacy":
            return summary
        return summary.model_copy(update={"documents": await self._document_records(connection, context)})

    async def corpus_summary(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Qualify corpus metadata without enumerating documents or active chunks."""
        async with self._transaction(context, operation="corpus_summary", repeatable_read=True) as connection:
            return await self._corpus_summary(connection, context)

    async def corpus_snapshot(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Read document metadata alongside its committed repeatable-read generation."""
        async with self._transaction(context, operation="corpus_snapshot", repeatable_read=True) as connection:
            return await self._corpus_snapshot(connection, context)

    async def get_chunk(self, context: WorkspaceContext, chunk_id: str) -> Chunk | None:
        """Read an active-version chunk in the authorized workspace."""
        async with self._transaction(context, operation="get_chunk") as connection:
            await self._require_workspace(connection, context)
            row = await (
                await connection.execute(
                    f"SELECT {_CHUNK_COLUMNS} FROM workbench.chunks c JOIN workbench.source_versions v "
                    "USING(workspace_id,source_id,version_id) WHERE c.workspace_id=%s AND c.chunk_id=%s "
                    "AND v.status='active'",
                    (context.workspace_id, chunk_id),
                )
            ).fetchone()
            return None if row is None else _chunk(row)

    async def _validate_embedding(
        self, connection: AsyncConnection[dict[str, Any]], *, embedding: list[float], profile_id: str
    ) -> None:
        profile = await (
            await connection.execute(
                "SELECT dimensions,enabled FROM workbench.embedding_profiles WHERE profile_id=%s", (profile_id,)
            )
        ).fetchone()
        if (
            profile is None
            or not profile["enabled"]
            or len(embedding) != profile["dimensions"]
            or not all(isfinite(value) for value in embedding)
            or not any(embedding)
        ):
            raise InvalidEmbedding("Embedding is incompatible with the registered profile.")

    async def publish_source(
        self, context: WorkspaceContext, *, source: Source, version: SourceVersion, chunks: list[Chunk]
    ) -> None:
        """Insert all replacement chunks and atomically switch the active version."""
        async with self._transaction(context, operation="publish_source") as connection:
            await self._require_workspace(connection, context)
            await self._publish(connection, context=context, source=source, version=version, chunks=chunks)

    async def _publish(
        self,
        connection: AsyncConnection[dict[str, Any]],
        *,
        context: WorkspaceContext,
        source: Source,
        version: SourceVersion,
        chunks: list[Chunk],
    ) -> None:
        await connection.execute(
            "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE", (context.workspace_id,)
        )
        indexed = await self._prepare_generation(connection, context)
        if source.workspace_id != context.workspace_id or version.workspace_id != context.workspace_id:
            raise WorkspaceNotFound("Workspace is not available.")
        if version.source_id != source.source_id or not 1 <= len(chunks) <= 10000:
            raise RecordConflict("Source publication has invalid references.")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise RecordConflict("Chunk identities must be unique.")
        for chunk in chunks:
            if (chunk.workspace_id, chunk.source_id, chunk.version_id) != (
                context.workspace_id,
                source.source_id,
                version.version_id,
            ):
                raise RecordConflict("Chunk references do not match the source version.")
            if chunk.embedding is not None:
                await self._validate_embedding(
                    connection, embedding=chunk.embedding, profile_id=chunk.embedding_profile_id or ""
                )
        await connection.execute(
            "INSERT INTO workbench.sources(workspace_id,source_id,title,media_type,metadata) VALUES(%s,%s,%s,%s,%s) "
            "ON CONFLICT(workspace_id,source_id) DO UPDATE SET title=EXCLUDED.title,media_type=EXCLUDED.media_type,"
            "metadata=EXCLUDED.metadata,updated_at=now()",
            (source.workspace_id, source.source_id, source.title, source.media_type, Jsonb(source.metadata)),
        )
        # Serialize publication of replacements for this source before touching its active version.
        await connection.execute(
            "SELECT source_id FROM workbench.sources WHERE workspace_id=%s AND source_id=%s FOR UPDATE",
            (context.workspace_id, source.source_id),
        )
        await connection.execute(
            "INSERT INTO workbench.source_versions(workspace_id,source_id,version_id,status,content_hash,metadata) "
            "VALUES(%s,%s,%s,'staged',%s,%s)",
            (
                version.workspace_id,
                version.source_id,
                version.version_id,
                version.content_hash,
                Jsonb(version.metadata),
            ),
        )
        for chunk in chunks:
            await connection.execute(
                "INSERT INTO workbench.chunks(workspace_id,source_id,version_id,chunk_id,title,content,content_hash,"
                "page,metadata,embedding,embedding_profile_id,dimensions) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s,%s)",
                (
                    chunk.workspace_id,
                    chunk.source_id,
                    chunk.version_id,
                    chunk.chunk_id,
                    chunk.title,
                    chunk.content,
                    chunk.content_hash,
                    chunk.page,
                    Jsonb(chunk.metadata),
                    None if chunk.embedding is None else Vector(chunk.embedding).to_text(),
                    chunk.embedding_profile_id,
                    chunk.dimensions,
                ),
            )
        await connection.execute(
            "UPDATE workbench.source_versions SET status='superseded',updated_at=now() "
            "WHERE workspace_id=%s AND source_id=%s AND status='active'",
            (context.workspace_id, source.source_id),
        )
        await connection.execute(
            "UPDATE workbench.source_versions SET status='active',updated_at=now() "
            "WHERE workspace_id=%s AND source_id=%s AND version_id=%s",
            (context.workspace_id, source.source_id, version.version_id),
        )
        if indexed:
            from apps.workbench.api.postgres_indexes import commit_source_generation

            await commit_source_generation(connection, context, source_id=source.source_id)

    async def ingestion_ready(self, context: WorkspaceContext) -> bool:
        """Qualify additive ingestion independently from the compatible lexical-only schema."""
        from apps.workbench.api.postgres_ingestion import ingestion_ready

        return await ingestion_ready(self, context)

    async def recover_ingestions(self, context: WorkspaceContext) -> int:
        """Diagnose abandoned jobs without interrupting any live session owner."""
        from apps.workbench.api.postgres_ingestion import recover_ingestions

        return await recover_ingestions(self, context)

    @asynccontextmanager
    async def reserve_ingestion(
        self,
        context: WorkspaceContext,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        source_content_sha256: str,
        source_id: str | None = None,
        expected_active_version_id: str | None = None,
    ) -> AsyncIterator[UploadReservation]:
        """Reserve once while holding crash-released exclusive ownership through publication or failure."""
        from apps.workbench.api.postgres_ingestion import reserve_ingestion

        async with reserve_ingestion(
            self,
            context,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            source_content_sha256=source_content_sha256,
            source_id=source_id,
            expected_active_version_id=expected_active_version_id,
        ) as reservation:
            yield reservation

    async def transition_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        stage: Literal["parsing", "chunking", "publishing"],
    ) -> IngestionJob:
        """Commit one ordered processing checkpoint belonging to a live reservation."""
        from apps.workbench.api.postgres_ingestion import transition_ingestion

        return await transition_ingestion(self, context, job_id=job_id, owner_token=owner_token, stage=stage)

    async def complete_ingestion_with_publication(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        source: Source,
        version: SourceVersion,
        chunks: list[Chunk],
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        """Publish a guarded version and COMPLETE atomically, preserving unchanged active content."""
        from apps.workbench.api.postgres_ingestion import complete_ingestion_with_publication

        return await complete_ingestion_with_publication(
            self,
            context,
            job_id=job_id,
            owner_token=owner_token,
            source=source,
            version=version,
            chunks=chunks,
            stages=stages,
        )

    async def fail_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        error_code: str,
        retryable: bool,
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        """Persist a safe terminal failure while retaining the last confirmed processing stage."""
        from apps.workbench.api.postgres_ingestion import fail_ingestion

        return await fail_ingestion(
            self,
            context,
            job_id=job_id,
            owner_token=owner_token,
            error_code=error_code,
            retryable=retryable,
            stages=stages,
        )

    async def get_ingestion_job(self, context: WorkspaceContext, *, job_id: str) -> IngestionJob | None:
        """Read a scoped durable job without exposing reservation keys or ownership tokens."""
        from apps.workbench.api.postgres_ingestion import get_ingestion_job

        return await get_ingestion_job(self, context, job_id=job_id)

    async def get_source_detail(self, context: WorkspaceContext, *, source_id: str) -> SourceDetail | None:
        """Read source metadata and its current active processing version in one snapshot."""
        from apps.workbench.api.postgres_ingestion import get_source_detail

        return await get_source_detail(self, context, source_id=source_id)

    async def list_active_chunks(
        self,
        context: WorkspaceContext,
        *,
        source_id: str,
        limit: int = 50,
        after_chunk_id: str | None = None,
        expected_corpus_revision: str | None = None,
    ) -> ActiveChunkPage | None:
        """Read only the active version through a bounded stable keyset page."""
        from apps.workbench.api.postgres_ingestion import list_active_chunks

        return await list_active_chunks(
            self,
            context,
            source_id=source_id,
            limit=limit,
            after_chunk_id=after_chunk_id,
            expected_corpus_revision=expected_corpus_revision,
        )

    async def lexical_search(self, context: WorkspaceContext, *, query: str, top_k: int = 10) -> list[LexicalHit]:
        """Run native full-text ranking over persisted active chunks."""
        return (await self.lexical_search_snapshot(context, query=query, top_k=top_k)).hits

    async def get_profile_rollouts(self, context: WorkspaceContext) -> tuple[ProfileRollout, ...]:
        """Read the authorized durable profile selection and immutable policy identity."""
        from apps.workbench.api.postgres_profiles import read_profile_rollouts

        async with self._transaction(context, operation="profile_rollouts", repeatable_read=True) as connection:
            await self._verify_schema(connection)
            await self._require_workspace(connection, context)
            return await read_profile_rollouts(connection, context)

    async def lexical_search_snapshot(
        self,
        context: WorkspaceContext,
        *,
        query: str,
        top_k: int = 10,
        profile_fence: ProfileRollout | None = None,
        profile_definition: ProfileDefinition | None = None,
    ) -> LexicalSearchSnapshot:
        """Read corpus revision and real ranks in the same read-only SQL snapshot."""
        if (
            not isinstance(query, str)
            or not 1 <= len(query.strip()) <= 4096
            or type(top_k) is not int
            or not 1 <= top_k <= 50
        ):
            raise ValueError("Invalid lexical search parameters.")
        started = monotonic()
        if (profile_fence is None) != (profile_definition is None):
            raise ProfileNotAvailable("An approved revision requires its complete policy fence.")
        async with self._transaction(context, operation="lexical_search", repeatable_read=True) as connection:
            if profile_fence is not None:
                from apps.workbench.api.postgres_profiles import read_profile_rollouts

                current_rollouts = await read_profile_rollouts(connection, context)
                if profile_fence.state != "active" or profile_fence not in current_rollouts:
                    raise ProfileNotAvailable("The approved profile changed before retrieval.")
            corpus = await self._corpus_summary(connection, context)
            if profile_definition is not None and profile_fence is not None:
                from apps.workbench.api.profiles import qualify_profile, validate_search_policy

                if (
                    profile_definition.profile_id,
                    profile_definition.profile_revision,
                    profile_definition.policy_hash,
                ) != (
                    profile_fence.profile_id,
                    profile_fence.profile_revision,
                    profile_fence.policy_hash,
                ) or context.workspace_id not in profile_definition.workspace_ids:
                    raise ProfileNotAvailable("The selected policy differs from its approved revision.")
                validate_search_policy(profile_definition, query=query, top_k=top_k)
                qualify_profile(profile_definition, corpus)
            loaded = monotonic()
            rows = await (
                await connection.execute(
                    f"SELECT {_CHUNK_COLUMNS},ts_rank_cd(c.search_vector,q.query)::double precision AS score "
                    "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "CROSS JOIN plainto_tsquery('simple',%s) AS q(query) WHERE c.workspace_id=%s "
                    "AND v.status='active' AND c.search_vector @@ q.query "
                    'ORDER BY score DESC,c.chunk_id COLLATE "C" LIMIT %s',
                    (query.strip(), context.workspace_id, top_k),
                )
            ).fetchall()
            retrieved = monotonic()
            return LexicalSearchSnapshot(
                corpus_revision=corpus.corpus_revision,
                chunk_count=corpus.chunk_count,
                content_bytes=corpus.content_bytes,
                hits=[
                    LexicalHit(chunk=_chunk(row), rank=index, score=row["score"]) for index, row in enumerate(rows, 1)
                ],
                corpus_load_duration_ms=(loaded - started) * 1000,
                retrieval_duration_ms=(retrieved - loaded) * 1000,
                index_generation_id=corpus.index_generation_id,
            )

    async def vector_search(
        self, context: WorkspaceContext, *, embedding: list[float], profile_id: str, top_k: int = 10
    ) -> list[VectorHit]:
        """Use exact cosine distance over a single registered embedding profile."""
        if type(top_k) is not int or not 1 <= top_k <= 50:
            raise ValueError("Invalid vector search parameters.")
        async with self._transaction(context, operation="vector_search") as connection:
            await self._require_workspace(connection, context)
            await self._validate_embedding(connection, embedding=embedding, profile_id=profile_id)
            rows = await (
                await connection.execute(
                    f"SELECT {_CHUNK_COLUMNS},c.embedding <=> %s::vector AS distance FROM workbench.chunks c "
                    "JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "WHERE c.workspace_id=%s AND v.status='active' AND c.embedding_profile_id=%s "
                    "AND c.embedding IS NOT NULL ORDER BY distance,c.chunk_id LIMIT %s",
                    (Vector(embedding).to_text(), context.workspace_id, profile_id, top_k),
                )
            ).fetchall()
            return [
                VectorHit(chunk=_chunk(row), rank=index, distance=row["distance"]) for index, row in enumerate(rows, 1)
            ]

    async def seed_development(
        self,
        context: WorkspaceContext,
        *,
        workspace: Workspace,
        documents: list[tuple[Source, SourceVersion, list[Chunk]]],
    ) -> int:
        """Publish the complete demo corpus once; refuse mismatched or non-demo content."""
        if context.workspace_id != "development" or workspace.workspace_id != context.workspace_id:
            raise SeedConflict("Development seed cannot target this workspace.")
        async with self._transaction(context, operation="seed_development") as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(73192741)")
            existing = await (
                await connection.execute(
                    "SELECT name,metadata FROM workbench.workspaces WHERE workspace_id=%s", (context.workspace_id,)
                )
            ).fetchone()
            if existing is not None:
                rows = await (
                    await connection.execute(
                        f"SELECT {_CHUNK_COLUMNS} FROM workbench.chunks c WHERE c.workspace_id=%s ORDER BY c.chunk_id",
                        (context.workspace_id,),
                    )
                ).fetchall()
                expected = sorted(
                    (chunk.model_dump() for _source, _version, chunks in documents for chunk in chunks),
                    key=lambda item: item["chunk_id"],
                )
                sources = await (
                    await connection.execute(
                        "SELECT workspace_id,source_id,title,media_type,metadata FROM workbench.sources "
                        "WHERE workspace_id=%s ORDER BY source_id",
                        (context.workspace_id,),
                    )
                ).fetchall()
                versions = await (
                    await connection.execute(
                        "SELECT workspace_id,source_id,version_id,status,content_hash,metadata "
                        "FROM workbench.source_versions WHERE workspace_id=%s ORDER BY source_id,version_id",
                        (context.workspace_id,),
                    )
                ).fetchall()
                expected_sources = sorted(
                    (source.model_dump() for source, _version, _chunks in documents), key=lambda item: item["source_id"]
                )
                expected_versions = sorted(
                    (
                        version.model_copy(update={"status": "active"}).model_dump()
                        for _source, version, _chunks in documents
                    ),
                    key=lambda item: (item["source_id"], item["version_id"]),
                )
                if (
                    existing != {"name": workspace.name, "metadata": workspace.metadata}
                    or [_chunk(row).model_dump() for row in rows] != expected
                    or sources != expected_sources
                    or versions != expected_versions
                ):
                    raise SeedConflict("Existing workspace is not the unchanged development corpus.")
                return 0
            await connection.execute(
                "INSERT INTO workbench.workspaces(workspace_id,name,metadata) VALUES(%s,%s,%s)",
                (workspace.workspace_id, workspace.name, Jsonb(workspace.metadata)),
            )
            for source, version, chunks in documents:
                await self._publish(connection, context=context, source=source, version=version, chunks=chunks)
            return len(documents)

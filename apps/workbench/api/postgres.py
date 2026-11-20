"""Bounded PostgreSQL repository; all application data operations carry workspace scope."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from math import isfinite
from time import monotonic
from typing import Any

from pgvector import Vector
from psycopg import AsyncConnection, Error, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolClosed, PoolTimeout

from apps.workbench.api.persistence import (
    Chunk,
    DatabaseUnavailable,
    InvalidEmbedding,
    LexicalHit,
    PersistenceError,
    PersistenceReady,
    RecordConflict,
    SchemaIncompatible,
    SeedConflict,
    Source,
    SourceVersion,
    VectorHit,
    Workspace,
    WorkspaceContext,
    WorkspaceNotFound,
)

_CHUNK_COLUMNS = (
    "c.workspace_id,c.source_id,c.version_id,c.chunk_id,c.title,c.content,c.content_hash,"
    "c.page,c.metadata,c.embedding::text AS embedding,c.embedding_profile_id,c.dimensions"
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


class PostgresPersistence:
    """Use an application role and short transactions; never run migrations on startup."""

    def __init__(
        self, dsn: str, *, min_size: int = 1, max_size: int = 4, timeout: float = 3.0, statement_timeout_ms: int = 3000
    ) -> None:
        if not 1 <= min_size <= max_size <= 16 or not 0 < timeout <= 30 or not 1 <= statement_timeout_ms <= 30000:
            raise ValueError("Invalid database pool bounds.")
        self._timeout = timeout
        self._statement_timeout_ms = statement_timeout_ms
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
        self, context: WorkspaceContext, *, operation: str
    ) -> AsyncIterator[AsyncConnection[dict[str, Any]]]:
        started = monotonic()
        outcome = "interrupted"
        try:
            async with self._pool.connection(timeout=self._timeout) as connection, connection.transaction():
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

    async def readiness(self, context: WorkspaceContext) -> PersistenceReady:
        """Verify exact migration/extension versions and an active persisted corpus."""
        from apps.workbench.api.db_migrations import migration_checksum

        async with self._transaction(context, operation="readiness") as connection:
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
            if (
                revision != [{"version_num": "0001"}]
                or ledger != [{"revision": "0001", "checksum": migration_checksum(), "tool_version": "alembic-1.20.1"}]
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
            await self._require_workspace(connection, context)
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
            return PersistenceReady(schema_revision="0001", workspace_id=context.workspace_id, **counts)

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

    async def lexical_search(self, context: WorkspaceContext, *, query: str, top_k: int = 10) -> list[LexicalHit]:
        """Run native full-text ranking over persisted active chunks."""
        if (
            not isinstance(query, str)
            or not 1 <= len(query.strip()) <= 4096
            or type(top_k) is not int
            or not 1 <= top_k <= 50
        ):
            raise ValueError("Invalid lexical search parameters.")
        async with self._transaction(context, operation="lexical_search") as connection:
            await self._require_workspace(connection, context)
            rows = await (
                await connection.execute(
                    f"SELECT {_CHUNK_COLUMNS},ts_rank_cd(c.search_vector,q.query)::double precision AS score "
                    "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
                    "CROSS JOIN plainto_tsquery('simple',%s) AS q(query) WHERE c.workspace_id=%s "
                    "AND v.status='active' AND c.search_vector @@ q.query ORDER BY score DESC,c.chunk_id LIMIT %s",
                    (query.strip(), context.workspace_id, top_k),
                )
            ).fetchall()
            return [LexicalHit(chunk=_chunk(row), rank=index, score=row["score"]) for index, row in enumerate(rows, 1)]

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

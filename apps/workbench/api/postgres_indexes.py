"""Committed corpus manifests and explicit offline drift reconciliation."""

import argparse
import json
import logging
from datetime import UTC
from typing import Any, Literal

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from apps.workbench.api.db_migrations import HEAD_REVISION, migration_status
from apps.workbench.api.persistence import CorpusNotReady, SchemaIncompatible, WorkspaceContext, WorkspaceNotFound

_logger = logging.getLogger("workbench.persistence")

_PUBLIC_COLUMNS = (
    "workspace_id",
    "corpus_id",
    "generation_id",
    "corpus_revision",
    "committed_at",
    "active_source_count",
    "active_chunk_count",
    "content_bytes",
    "active_source_manifest_hash",
    "lexical_index_revision",
    "status",
    "previous_generation",
    "event_id",
)


_INDEX_STATE_QUERY = (
    "SELECT s.* FROM workbench.corpus_index_state s JOIN workbench.index_generations g "
    "USING(workspace_id,generation_id) WHERE s.workspace_id=%s AND s.status='ready' "
    "AND to_jsonb(s)=to_jsonb(g) "
    "AND NOT EXISTS(SELECT 1 FROM workbench.index_generations newer "
    "WHERE newer.workspace_id=s.workspace_id AND newer.generation_id>s.generation_id) "
    "AND (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname='workbench' AND c.relname IN "
    "('corpus_index_state','index_generations','corpus_source_state') "
    "AND c.relrowsecurity AND c.relforcerowsecurity)=3 "
    "AND (SELECT count(*) FROM pg_trigger t WHERE t.tgrelid IN "
    "('workbench.sources'::regclass,'workbench.source_versions'::regclass,"
    "'workbench.chunks'::regclass,'workbench.workspaces'::regclass) "
    "AND t.tgname IN ('dirty_source_index','dirty_version_index','dirty_chunk_index',"
    "'initialize_corpus_index') AND t.tgenabled IN ('O','A'))=4 "
    "AND EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='workbench.index_generations'::regclass "
    "AND tgname='immutable_index_generation' AND tgenabled IN ('O','A')) "
    "AND EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='workbench.corpus_index_state'::regclass "
    "AND tgname='corpus_generation_transition' AND tgenabled IN ('O','A'))"
)


async def read_index_state(connection: AsyncConnection[dict[str, Any]], context: WorkspaceContext) -> dict[str, Any]:
    """Read one workspace manifest and its matching immutable ledger row."""
    row = await (await connection.execute(_INDEX_STATE_QUERY, (context.workspace_id,))).fetchone()
    if row is None:
        _logger.warning(
            json.dumps(
                {
                    "event": "corpus_manifest_unavailable",
                    "workspace_id": context.workspace_id,
                    "trace_id": context.trace_id,
                    "code": "INDEX_MANIFEST_UNAVAILABLE",
                },
                separators=(",", ":"),
            )
        )
        raise CorpusNotReady("The committed corpus manifest requires reconciliation.")
    result = {name: row[name] for name in _PUBLIC_COLUMNS}
    result["committed_at"] = row["committed_at"].astimezone(UTC).isoformat().replace("+00:00", "Z")
    return result


async def commit_source_generation(
    connection: AsyncConnection[dict[str, Any]],
    context: WorkspaceContext,
    *,
    source_id: str,
    event_kind: Literal["publication", "metadata"] = "publication",
) -> dict[str, Any]:
    """Commit one changed source projection inside the caller's publication transaction."""
    await connection.execute(
        "SELECT workbench.commit_source_generation(%s,%s,%s)", (context.workspace_id, source_id, event_kind)
    )
    return await read_index_state(connection, context)


def reconcile_index(dsn: str, *, workspace_id: str, repair: bool = False) -> dict[str, Any]:
    """Compare actual active rows with the projection; repair only when explicitly requested."""
    context = WorkspaceContext(workspace_id=workspace_id)
    schema = migration_status(dsn)
    if not schema.compatible or schema.revision != HEAD_REVISION:
        raise SchemaIncompatible("Offline reconciliation requires the current compatible migration.")
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        role = connection.execute("SELECT current_user AS name").fetchone()
        if role is None or role["name"] == "workbench_app":
            raise ValueError("Offline reconciliation requires the separate migration administrator.")
        connection.execute("SELECT set_config('statement_timeout','120000',true)")
        connection.execute("SELECT set_config('lock_timeout','5000',true)")
        connection.execute("SELECT set_config('workbench.workspace_id',%s,true)", (context.workspace_id,))
        workspace = connection.execute(
            "SELECT workspace_id FROM workbench.workspaces WHERE workspace_id=%s FOR UPDATE", (workspace_id,)
        ).fetchone()
        if workspace is None:
            raise WorkspaceNotFound("Workspace is not available.")
        connection.execute(
            "CREATE TEMP TABLE index_reconciliation ON COMMIT DROP AS "
            "SELECT s.workspace_id,s.source_id,p.* FROM workbench.sources s CROSS JOIN LATERAL "
            "workbench.index_source_projection(s.workspace_id,s.source_id) p WHERE s.workspace_id=%s",
            (workspace_id,),
        )
        actual = connection.execute(
            "SELECT count(*) AS sources,COALESCE(sum(chunk_count),0)::bigint AS chunks,"
            "COALESCE(sum(content_bytes),0)::bigint AS bytes,"
            "COALESCE(bit_xor(source_hash),repeat('0',256)::bit(256)) AS manifest_xor, "
            "encode(sha256(convert_to(COALESCE(bit_xor(source_hash),repeat('0',256)::bit(256))::text,"
            "'UTF8')),'hex') AS root "
            "FROM index_reconciliation"
        ).fetchone()
        state = connection.execute(
            "SELECT s.*,to_jsonb(s)=to_jsonb(g) AND NOT EXISTS(SELECT 1 FROM workbench.index_generations newer "
            "WHERE newer.workspace_id=s.workspace_id AND newer.generation_id>s.generation_id) AS ledger_matches "
            "FROM workbench.corpus_index_state s "
            "LEFT JOIN workbench.index_generations g USING(workspace_id,generation_id) "
            "WHERE s.workspace_id=%s FOR UPDATE OF s",
            (workspace_id,),
        ).fetchone()
        differences = connection.execute(
            "SELECT EXISTS((SELECT * FROM index_reconciliation EXCEPT "
            "SELECT * FROM workbench.corpus_source_state WHERE workspace_id=%s) UNION ALL "
            "(SELECT * FROM workbench.corpus_source_state WHERE workspace_id=%s EXCEPT "
            "SELECT * FROM index_reconciliation)) AS drift",
            (workspace_id, workspace_id),
        ).fetchone()
        if actual is None or state is None or differences is None:
            raise CorpusNotReady("The committed corpus manifest is unavailable.")
        consistent = (
            not differences["drift"]
            and state["status"] == "ready"
            and state["ledger_matches"]
            and state["active_source_count"] == actual["sources"]
            and state["active_chunk_count"] == actual["chunks"]
            and state["content_bytes"] == actual["bytes"]
            and state["source_manifest_xor"] == actual["manifest_xor"]
            and state["active_source_manifest_hash"] == actual["root"]
        )
        if repair and not consistent:
            latest = connection.execute(
                "SELECT * FROM workbench.index_generations WHERE workspace_id=%s ORDER BY generation_id DESC LIMIT 1",
                (workspace_id,),
            ).fetchone()
            if latest is None:
                raise CorpusNotReady("The committed generation ledger is unavailable.")
            state = latest
            _repair_index(connection, workspace_id=workspace_id, actual=actual, state=state)
        return {
            "workspace_id": workspace_id,
            "consistent": consistent,
            "repaired": repair and not consistent,
            "generation_id": state["generation_id"] + (1 if repair and not consistent else 0),
            "active_source_count": actual["sources"],
            "active_chunk_count": actual["chunks"],
            "content_bytes": actual["bytes"],
        }


def _repair_index(
    connection: psycopg.Connection[dict[str, Any]], *, workspace_id: str, actual: dict[str, Any], state: dict[str, Any]
) -> None:
    connection.execute("DELETE FROM workbench.corpus_source_state WHERE workspace_id=%s", (workspace_id,))
    connection.execute("INSERT INTO workbench.corpus_source_state SELECT * FROM index_reconciliation")
    connection.execute(
        "INSERT INTO workbench.index_generations(workspace_id,generation_id,corpus_id,corpus_revision,"
        "active_source_count,active_chunk_count,content_bytes,active_source_manifest_hash,source_manifest_xor,"
        "lexical_index_revision,status,previous_generation,event_id,event_kind) "
        "SELECT %s,%s,%s,'corpus-'||encode(sha256(convert_to(%s||':'||%s::text||':'||"
        "encode(sha256(convert_to(%s,'UTF8')),'hex'),'UTF8')),'hex'),%s,%s,%s,"
        "encode(sha256(convert_to(%s,'UTF8')),'hex'),%s::bit(256),%s,'ready',%s,gen_random_uuid()::text,"
        "'reconciliation'",
        (
            workspace_id,
            state["generation_id"] + 1,
            state["corpus_id"],
            workspace_id,
            state["generation_id"] + 1,
            actual["manifest_xor"],
            actual["sources"],
            actual["chunks"],
            actual["bytes"],
            actual["manifest_xor"],
            actual["manifest_xor"],
            state["lexical_index_revision"],
            state["generation_id"],
        ),
    )
    connection.execute("DELETE FROM workbench.corpus_index_state WHERE workspace_id=%s", (workspace_id,))
    connection.execute(
        "INSERT INTO workbench.corpus_index_state SELECT * FROM workbench.index_generations "
        "WHERE workspace_id=%s AND generation_id=%s",
        (workspace_id, state["generation_id"] + 1),
    )


def main() -> None:
    """Run the explicit operator reconciliation command without printing connection details."""
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-id", default="development")
    parser.add_argument("--repair", action="store_true", help="Commit a repair generation if drift is found")
    args = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_ADMIN_DSN")
    if not dsn:
        parser.error("WORKBENCH_DB_ADMIN_DSN is required")
    try:
        result = reconcile_index(dsn, workspace_id=args.workspace_id, repair=args.repair)
    except Exception:
        parser.exit(1, "Corpus reconciliation failed.\n")
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()

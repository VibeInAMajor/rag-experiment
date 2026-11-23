"""Measure persisted revision lookup against the historical scan in owned temporary databases."""

import argparse
import asyncio
import json
import math
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import psycopg
from alembic import command
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from sqlalchemy import text

from apps.workbench.api import db_migrations
from apps.workbench.api.persistence import WorkspaceContext
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.postgres_indexes import _INDEX_STATE_QUERY

_CONTEXT = WorkspaceContext(workspace_id="benchmark", trace_id="index-benchmark-r1")
_ACTIVE = (
    "FROM workbench.chunks c JOIN workbench.source_versions v USING(workspace_id,source_id,version_id) "
    "WHERE c.workspace_id=%s AND v.status='active'"
)
_COUNTS = "SELECT count(*) AS chunk_count,COALESCE(sum(octet_length(c.content)),0)::bigint AS content_bytes " + _ACTIVE
_CHUNKS = (
    "SELECT c.chunk_id,c.source_id,c.version_id,c.title,c.page,"
    "encode(sha256(convert_to(c.content,'UTF8')),'hex') AS content_sha256,"
    "encode(sha256(convert_to(c.metadata::text,'UTF8')),'hex') AS metadata_sha256,"
    "v.content_hash AS version_content_hash,"
    "encode(sha256(convert_to(v.metadata::text,'UTF8')),'hex') AS version_metadata_sha256 "
    + _ACTIVE
    + " ORDER BY c.chunk_id"
)
_MANIFEST = "SELECT * FROM workbench.corpus_index_state WHERE workspace_id=%s"


@contextmanager
def _database() -> Iterator[tuple[str, str]]:
    admin = os.environ["WORKBENCH_TEST_ADMIN_DSN"]
    application = os.environ["WORKBENCH_TEST_APP_DSN"]
    name = f"rag_test_index_{uuid4().hex}"
    control = make_conninfo(admin, dbname="postgres")
    with psycopg.connect(control, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(admin, dbname=name), make_conninfo(application, dbname=name)
    finally:
        if not name.startswith("rag_test_index_"):
            raise RuntimeError("Refusing to drop a database outside this benchmark.")
        with psycopg.connect(control, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def _populate(admin: str, count: int) -> None:
    with db_migrations._connection(admin, transaction=True) as connection:
        db_migrations._ensure_role(connection)
        connection.execute(text("CREATE SCHEMA workbench"))
        command.upgrade(db_migrations._configuration(connection), "0002")
        db_migrations._grant_application(connection)
    with psycopg.connect(admin) as connection:
        connection.execute("INSERT INTO workbench.workspaces(workspace_id,name) VALUES('benchmark','Benchmark')")
        connection.execute(
            "INSERT INTO workbench.sources(workspace_id,source_id,title) "
            "VALUES('benchmark','source','Synthetic source')"
        )
        connection.execute(
            "INSERT INTO workbench.source_versions(workspace_id,source_id,version_id,status,content_hash) "
            "VALUES('benchmark','source','version','active','synthetic')"
        )
        connection.execute(
            "INSERT INTO workbench.chunks(workspace_id,source_id,version_id,chunk_id,title,content,content_hash) "
            "SELECT 'benchmark','source','version','chunk-'||n,'Synthetic passage',"
            "'Synthetic benchmark passage with deterministic token '||n,'hash-'||n "
            "FROM generate_series(1,%s) AS n",
            (count,),
        )
        connection.execute("ANALYZE workbench.chunks")


def _legacy_snapshot(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
    counts = connection.execute(_COUNTS, (_CONTEXT.workspace_id,)).fetchone()
    documents = connection.execute(
        "SELECT s.source_id,s.title,s.media_type,v.version_id AS active_version_id,count(c.chunk_id) AS chunk_count "
        "FROM workbench.sources s JOIN workbench.source_versions v USING(workspace_id,source_id) "
        "JOIN workbench.chunks c USING(workspace_id,source_id,version_id) "
        "WHERE s.workspace_id=%s AND v.status='active' "
        "GROUP BY s.source_id,s.title,s.media_type,v.version_id ORDER BY s.source_id",
        (_CONTEXT.workspace_id,),
    ).fetchall()
    chunks = connection.execute(_CHUNKS, (_CONTEXT.workspace_id,)).fetchall()
    fingerprint = json.dumps(
        {"workspace_id": _CONTEXT.workspace_id, "documents": documents, "chunks": chunks},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return {"counts": counts, "digest": sha256(fingerprint.encode()).hexdigest(), "metadata_rows": len(chunks) + 2}


def _quantiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        label: round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1)], 4)
        for label, quantile in (("p50_ms", 0.5), ("p95_ms", 0.95), ("p99_ms", 0.99))
    }


def _plan(connection: psycopg.Connection[dict[str, Any]], query: str) -> Any:
    row = connection.execute("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + query, (_CONTEXT.workspace_id,)).fetchone()
    if row is None:
        raise RuntimeError("The benchmark query produced no execution plan.")
    return row["QUERY PLAN"]


async def _measure(count: int, samples: int) -> dict[str, Any]:
    with _database() as (admin, application):
        _populate(admin, count)
        started = perf_counter()
        migration = db_migrations.migrate(admin)
        migration_ms = (perf_counter() - started) * 1000
        with psycopg.connect(application, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SELECT set_config('workbench.workspace_id',%s,false)", (_CONTEXT.workspace_id,))
            versions = connection.execute(
                "SELECT current_setting('server_version') AS postgres,"
                "(SELECT extversion FROM pg_extension WHERE extname='vector') AS pgvector"
            ).fetchone()
            legacy_samples = []
            manifest_samples = []
            legacy = _legacy_snapshot(connection)
            state = connection.execute(_MANIFEST, (_CONTEXT.workspace_id,)).fetchone()
            if state is None or legacy["counts"] is None:
                raise RuntimeError("The backfilled corpus state is missing.")
            assert state["active_chunk_count"] == legacy["counts"]["chunk_count"] == count
            assert state["content_bytes"] == legacy["counts"]["content_bytes"]
            for _ in range(samples):
                started = perf_counter()
                _legacy_snapshot(connection)
                legacy_samples.append((perf_counter() - started) * 1000)
                started = perf_counter()
                connection.execute(_MANIFEST, (_CONTEXT.workspace_id,)).fetchone()
                manifest_samples.append((perf_counter() - started) * 1000)
            plans = {
                label: _plan(connection, query)
                for label, query in (
                    ("legacy_counts", _COUNTS),
                    ("legacy_chunks", _CHUNKS),
                    ("manifest", _MANIFEST),
                    ("guarded_manifest", _INDEX_STATE_QUERY),
                )
            }
        repository = PostgresPersistence(application)
        await repository.start()
        try:
            runtime_samples = []
            for _ in range(samples):
                started = perf_counter()
                generation = await repository.current_index_generation(_CONTEXT)
                runtime_samples.append((perf_counter() - started) * 1000)
            assert generation.active_chunk_count == count
        finally:
            await repository.close()
        return {
            "chunk_count": count,
            "samples": samples,
            "versions": versions,
            "migration_revision": migration.revision,
            "migration_checksums": db_migrations.migration_ledger(db_migrations.HEAD_REVISION),
            "guarded_query_sha256": sha256(_INDEX_STATE_QUERY.encode()).hexdigest(),
            "backfill_ms": round(migration_ms, 3),
            "legacy_scan": {**_quantiles(legacy_samples), "metadata_rows": legacy["metadata_rows"]},
            "manifest_lookup": {**_quantiles(manifest_samples), "metadata_rows": 1},
            "current_generation_runtime": _quantiles(runtime_samples),
            "generation": generation.model_dump(mode="json"),
            "manifest_present": state is not None,
            "legacy_manifest_counts_and_bytes_match": True,
            "plans": plans,
        }


async def _run(arguments: argparse.Namespace) -> None:
    report: dict[str, Any] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "kind": "real-postgresql-synthetic-corpus",
        "trace_id": _CONTEXT.trace_id,
        "scope": "metadata establishment only; no lexical ranking or semantic inference claim",
        "baseline": (
            "historical count/chunk hash scans and Python SHA reconstructed with simplified document projection; "
            "legacy 10k admission cap omitted; not a byte-for-byte replay of the old complete snapshot"
        ),
        "queries": {
            "legacy_counts": _COUNTS,
            "legacy_chunks": _CHUNKS,
            "manifest": _MANIFEST,
            "guarded_manifest": _INDEX_STATE_QUERY,
        },
        "cases": [],
    }
    for count in arguments.sizes:
        report["cases"].append(await _measure(count, arguments.samples))
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Measured {count} synthetic chunks; evidence written.", flush=True)


def main() -> None:
    """Run an explicit bounded benchmark and retain sanitized evidence outside the temporary database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[8, 10000, 100000])
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("tasks/evidence/index-2026-11-23/benchmark.json"))
    arguments = parser.parse_args()
    if not all(1 <= count <= 1000000 for count in arguments.sizes) or not 5 <= arguments.samples <= 100:
        parser.error("Sizes must be 1..1000000 and samples 5..100.")
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(_run(arguments))
    else:
        asyncio.run(_run(arguments))


if __name__ == "__main__":
    main()

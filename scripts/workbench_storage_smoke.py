"""Record persisted corpus fingerprints across explicit API and database restarts."""

import argparse
import asyncio
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
import psycopg
from psycopg.rows import dict_row

from apps.workbench.persistence.models import WorkspaceContext
from apps.workbench.postgres.postgres import PostgresPersistence

_EVIDENCE = Path("tasks/evidence/postgresql-restart-2026-11-21.json")


async def _application_snapshot(dsn: str) -> dict[str, object]:
    repository = PostgresPersistence(dsn)
    trace_id = uuid4().hex
    context = WorkspaceContext(workspace_id="development", trace_id=trace_id)
    try:
        await repository.start()
        ready = await repository.readiness(context)
        sources = await repository.list_sources(context)
        queries = []
        for index, query in enumerate(("publication", "пошук"), 1):
            started = monotonic()
            hits = await repository.lexical_search(context, query=query, top_k=5)
            assert hits and all(hit.score_type == "postgres_ts_rank_cd" for hit in hits)
            queries.append(
                {
                    "query_case": index,
                    "source_ids": [hit.chunk.source_id for hit in hits],
                    "scores": [hit.score for hit in hits],
                    "score_type": "postgres_ts_rank_cd",
                    "duration_ms": (monotonic() - started) * 1000,
                }
            )
        assert queries[0]["source_ids"] != queries[1]["source_ids"]
        return {
            "ready": ready.model_dump(),
            "source_ids": [source.source_id for source in sources],
            "queries": queries,
            "trace_id": trace_id,
        }
    finally:
        await repository.close()


def main() -> None:
    """Compare actual committed rows and SQL results without printing document bodies."""
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "after-api", "after-database"))
    arguments = parser.parse_args()
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    admin_dsn = os.environ.get("WORKBENCH_DB_ADMIN_DSN")
    if not dsn or not admin_dsn:
        raise SystemExit("Load the explicit development database environment first.")
    with psycopg.connect(admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT workspace_id,source_id,version_id,chunk_id,title,content,content_hash,metadata,"
            "embedding::text AS embedding,embedding_profile_id,dimensions FROM workbench.chunks "
            "WHERE workspace_id=%s ORDER BY chunk_id",
            ("development",),
        ).fetchall()
        server = connection.execute("SELECT current_setting('server_version') AS version").fetchone()
        extension = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        indexes = connection.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='workbench' ORDER BY indexname"
        ).fetchall()
        connection.execute("SET LOCAL enable_seqscan=off")
        plan = connection.execute(
            "EXPLAIN SELECT chunk_id FROM workbench.chunks WHERE workspace_id=%s "
            "AND search_vector @@ plainto_tsquery('simple',%s)",
            ("development", "publication"),
        ).fetchall()
    assert len(rows) == 8 and server is not None and extension is not None
    fingerprint = sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
        snapshot = runner.run(_application_snapshot(dsn))
    with httpx.Client(base_url="http://127.0.0.1:8011", timeout=5) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")
        capabilities = client.get("/api/v1/capabilities").json()
    assert live.status_code == 200 and ready.status_code == 503
    assert capabilities["profiles"] == [] and capabilities["dependencies"]["database"]["status"] == "ready"
    observation = {
        "row_count": len(rows),
        "corpus_sha256": fingerprint,
        "chunk_ids": [row["chunk_id"] for row in rows],
        "postgresql": server["version"],
        "pgvector": extension["extversion"],
        "application": snapshot,
        "api_capabilities": capabilities,
        "indexes": indexes,
        "diagnostic_explain_seqscan_disabled": plan,
        "ann_index_claim": "none",
    }
    report = {} if arguments.phase == "baseline" else json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    if arguments.phase != "baseline":
        assert report["baseline"]["corpus_sha256"] == fingerprint
        assert report["baseline"]["chunk_ids"] == observation["chunk_ids"]
        assert report["baseline"]["application"]["source_ids"] == snapshot["source_ids"]
    report[arguments.phase] = observation
    _EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    _EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": arguments.phase, "rows": len(rows), "corpus_sha256": fingerprint, "status": "passed"}))


if __name__ == "__main__":
    main()

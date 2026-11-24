"""Reuse lexical HTTP evidence and cross-check it against read-only persisted SQL snapshots."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from importlib import metadata
from pathlib import Path
from typing import Any

import psycopg

from apps.workbench.persistence.models import WorkspaceContext
from apps.workbench.postgres.postgres import PostgresPersistence
from scripts import workbench_lexical_smoke as lexical_smoke

_DIRECTORY = Path("tasks/evidence/eval-vertical-2026-11-22")
_HTTP_EVIDENCE = _DIRECTORY / "backend-http-durability.json"


def _environment_metadata(dsn: str) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        schema = connection.execute("SELECT version_num FROM workbench.alembic_version").fetchall()
        ledger = connection.execute(
            "SELECT revision, checksum, tool_version FROM workbench.schema_migrations"
        ).fetchall()
        extension = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        server = connection.execute("SHOW server_version").fetchone()
        role = connection.execute(
            "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
    assert schema == [("0001",)] and extension is not None and server is not None
    assert role == (False, False, False, False)
    containers = subprocess.check_output(
        ["docker", "ps", "--filter", "label=com.docker.compose.project=rag-workbench", "--format", "{{.ID}}"], text=True
    ).split()
    assert len(containers) == 1
    template = (
        '{"image_reference":{{json .Config.Image}},"image_id":{{json .Image}},'
        '"started_at":{{json .State.StartedAt}},"mount_names":{{json .Mounts}}}'
    )
    container = json.loads(
        subprocess.check_output(["docker", "inspect", containers[0], "--format", template], text=True)
    )
    container["mount_names"] = [item["Name"] for item in container["mount_names"] if item["Type"] == "volume"]
    container["repository_digests"] = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", container["image_id"], "--format", "{{json .RepoDigests}}"], text=True
        )
    )
    # Hatch may omit a process-injected Git config value while retaining its count; no config override is needed here.
    git_environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_CONFIG_")}
    return {
        "repo_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], env=git_environment, text=True).strip(),
        "python_version": sys.version.split()[0],
        "dependencies": {
            name: metadata.version(name)
            for name in ("haystack-ai", "psycopg", "psycopg-pool", "fastapi", "starlette", "httpx")
        },
        "schema_revisions": [row[0] for row in schema],
        "migration_ledger": [{"revision": row[0], "checksum": row[1], "tool_version": row[2]} for row in ledger],
        "pgvector_version": extension[0],
        "postgresql_version": server[0],
        "application_role_unprivileged": True,
        "container": container,
    }


async def _sql_parity(phase: str, *, dsn: str, observation: dict[str, Any], fixtures: dict[str, Any]) -> dict[str, Any]:
    context = WorkspaceContext(workspace_id="development")
    repository = PostgresPersistence(dsn)
    await repository.start()
    try:
        before = await repository.corpus_snapshot(context)
        assert before.corpus_revision == observation["documents"]["corpus_revision"]
        assert len(before.documents) == before.chunk_count == 8
        groups = (
            ("exact", fixtures["gated_exact_queries"], observation["evaluation"]["gated_exact"]),
            ("paraphrase", fixtures["diagnostic_paraphrases"], observation["evaluation"]["diagnostic_paraphrases"]),
        )
        comparisons = []
        for group, gold_cases, http_cases in groups:
            for index, (gold, http_case) in enumerate(zip(gold_cases, http_cases, strict=True), 1):
                snapshot = await repository.lexical_search_snapshot(context, query=gold["query"], top_k=5)
                http_response = http_case["response"]
                assert snapshot.corpus_revision == before.corpus_revision == http_response["corpus_revision"]
                sql_results = []
                for hit in snapshot.hits:
                    item = {
                        "chunk_id": hit.chunk.chunk_id,
                        "source_id": hit.chunk.source_id,
                        "source_version_id": hit.chunk.version_id,
                        "rank": hit.rank,
                        "score": hit.score,
                        "score_type": hit.score_type,
                        "title": hit.chunk.title,
                        "content_sha256": sha256(hit.chunk.content.encode("utf-8")).hexdigest(),
                    }
                    if hit.chunk.page is not None:
                        item["page"] = hit.chunk.page
                    sql_results.append(item)
                assert sql_results == http_response["results"]
                comparisons.append(
                    {
                        "query_id": f"{group}-{index:02}",
                        "query_sha256": sha256(gold["query"].encode("utf-8")).hexdigest(),
                        "expected_source_id": gold["expected_source_id"],
                        "request_id": http_response["request_id"],
                        "trace_id": http_response["trace_id"],
                        "run_id": http_response["run_id"],
                        "sql_http_equal": True,
                        "results": sql_results,
                    }
                )
        after = await repository.corpus_snapshot(context)
        assert before == after
    finally:
        await repository.close()
    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "phase": phase,
        "lane": "real_http_and_read_only_postgres_adapter",
        "http_artifact": str(_HTTP_EVIDENCE).replace("\\", "/"),
        "environment": await asyncio.to_thread(_environment_metadata, dsn),
        "corpus_revision": before.corpus_revision,
        "source_count": len(before.documents),
        "chunk_count": before.chunk_count,
        "content_bytes": before.content_bytes,
        "sources": [
            {"source_id": item.source_id, "active_version_id": item.active_version_id, "chunk_count": item.chunk_count}
            for item in before.documents
        ],
        "read_only_corpus_unchanged": True,
        "sql_parity_case_count": len(comparisons),
        "cases": comparisons,
    }


def main() -> None:
    """Run baseline/after-api/after-database/database-unavailable without restarting or mutating services."""
    phase = sys.argv[1] if len(sys.argv) == 2 else ""
    if phase not in ("baseline", "after-api", "after-database", "database-unavailable"):
        raise SystemExit("Expected baseline, after-api, after-database or database-unavailable.")
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise SystemExit("Load the existing application-only database environment first.")
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    # The historic collector predates configurable destinations. Keep its historical artifact and cursor untouched.
    lexical_smoke._EVIDENCE = _HTTP_EVIDENCE
    lexical_smoke._CURSOR = Path(tempfile.gettempdir()) / "workbench-eval-vertical-cursor-2026-11-22.txt"
    lexical_smoke.main()
    if phase == "database-unavailable":
        return
    observation = json.loads(_HTTP_EVIDENCE.read_text(encoding="utf-8"))[phase]
    fixtures = json.loads(Path("apps/workbench/retrieval/fixtures/lexical-evaluation.json").read_text(encoding="utf-8"))
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=factory) as runner:
        report = runner.run(_sql_parity(phase, dsn=dsn, observation=observation, fixtures=fixtures))
    path = _DIRECTORY / f"backend-sql-{phase}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "sql_http_equal": report["sql_parity_case_count"],
                "corpus_revision": report["corpus_revision"],
                "sources": report["source_count"],
                "status": "passed",
            }
        )
    )


if __name__ == "__main__":
    main()

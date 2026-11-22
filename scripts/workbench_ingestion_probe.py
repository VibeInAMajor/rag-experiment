"""Capture scoped, read-only ingestion durability identities without retaining passages or credentials."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.rows import dict_row

_DIRECTORY = Path("tasks/evidence/ingestion-2026-11-22")
_PHASES = ("before-migration", "after-migration", "after-upload", "after-api", "after-database")
_MAX_ROWS = 100_000


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sanitize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) > _MAX_ROWS:
        raise ValueError("Snapshot row bound exceeded.")
    result = []
    for original in rows:
        row = dict(original)
        for field in ("metadata", "stage_timings_jsonb"):
            if field in row:
                row[f"{field}_sha256"] = _hash(row.pop(field))
        for field in ("content", "title"):
            if field in row:
                row[f"{field}_sha256"] = hashlib.sha256(row.pop(field).encode("utf-8")).hexdigest()
        for name, value in row.items():
            if isinstance(value, datetime):
                row[name] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        result.append(row)
    return result


def _database_snapshot(dsn: str) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=5, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SELECT set_config('workbench.workspace_id','development',true)")
        connection.execute("SELECT set_config('statement_timeout','5000',true)")
        connection.execute("SELECT set_config('lock_timeout','1000',true)")
        role = connection.execute(
            "SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        if role is None or any(role.values()):
            raise ValueError("Use the unprivileged application connection.")
        schema = connection.execute("SELECT version_num FROM workbench.alembic_version").fetchall()
        ledger = connection.execute(
            "SELECT revision,checksum,tool_version FROM workbench.schema_migrations ORDER BY revision"
        ).fetchall()
        server = connection.execute("SHOW server_version").fetchone()
        vector = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
        sources = _sanitize_rows(
            connection.execute(
                "SELECT source_id,title,media_type,metadata,created_at,updated_at FROM workbench.sources "
                "WHERE workspace_id=%s ORDER BY source_id LIMIT %s",
                ("development", _MAX_ROWS + 1),
            ).fetchall()
        )
        versions = _sanitize_rows(
            connection.execute(
                "SELECT source_id,version_id,status,content_hash,metadata,created_at,updated_at "
                "FROM workbench.source_versions "
                "WHERE workspace_id=%s ORDER BY source_id,version_id LIMIT %s",
                ("development", _MAX_ROWS + 1),
            ).fetchall()
        )
        chunks = _sanitize_rows(
            connection.execute(
                "SELECT source_id,version_id,chunk_id,content_hash,content,metadata,"
                "octet_length(content) AS content_bytes,page,"
                "embedding IS NULL AS embedding_is_null,embedding_profile_id IS NULL AS embedding_profile_is_null,"
                "dimensions IS NULL AS dimensions_is_null FROM workbench.chunks WHERE workspace_id=%s "
                "ORDER BY source_id,version_id,chunk_id LIMIT %s",
                ("development", _MAX_ROWS + 1),
            ).fetchall()
        )
        jobs_present = connection.execute("SELECT to_regclass('workbench.ingestion_jobs') AS name").fetchone()
        jobs = []
        if jobs_present and jobs_present["name"] is not None:
            jobs = _sanitize_rows(
                connection.execute(
                    "SELECT job_id,reserved_source_id AS source_id,reserved_version_id,effective_version_id,operation,"
                    "status,stage,error_code,retryable,chunk_count,outcome,source_content_sha256,processing_profile_fingerprint,"
                    "corpus_revision,stage_timings_jsonb,created_at,updated_at,finished_at "
                    "FROM workbench.ingestion_jobs "
                    "WHERE workspace_id=%s ORDER BY job_id LIMIT %s",
                    ("development", _MAX_ROWS + 1),
                ).fetchall()
            )
    active = {(row["source_id"], row["version_id"]) for row in versions if row["status"] == "active"}
    active_chunks = [row for row in chunks if (row["source_id"], row["version_id"]) in active]
    return {
        "workspace_id": "development",
        "read_only_repeatable_read": True,
        "application_role_unprivileged": True,
        "schema": schema,
        "ledger": ledger,
        "postgresql": server,
        "pgvector": vector,
        "sources": sources,
        "versions": versions,
        "chunks": chunks,
        "jobs": jobs,
        "source_count": len(sources),
        "version_count": len(versions),
        "chunk_count": len(chunks),
        "job_count": len(jobs),
        "active_source_count": len(active),
        "active_chunk_count": len(active_chunks),
        "active_content_bytes": sum(row["content_bytes"] for row in active_chunks),
        "source_version_chunk_fingerprint": _hash([sources, versions, chunks]),
        "job_fingerprint": _hash(jobs),
        "all_chunk_vectors_null": all(
            row["embedding_is_null"] and row["embedding_profile_is_null"] and row["dimensions_is_null"]
            for row in chunks
        ),
        "ingestion_jobs_table_present": bool(jobs_present and jobs_present["name"] is not None),
    }


def _container() -> dict[str, Any]:
    identifiers = subprocess.check_output(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=rag-workbench",
            "--filter",
            "label=com.docker.compose.service=postgres",
            "--format",
            "{{.ID}}",
        ],
        text=True,
        timeout=10,
    ).split()
    if len(identifiers) != 1:
        raise ValueError("Exactly one application PostgreSQL container is required.")
    template = (
        '{"container_id":{{json .Id}},"image":{{json .Config.Image}},"image_id":{{json .Image}},'
        '"started_at":{{json .State.StartedAt}},"mounts":{{json .Mounts}}}'
    )
    result = json.loads(
        subprocess.check_output(["docker", "inspect", identifiers[0], "--format", template], text=True, timeout=10)
    )
    result["volumes"] = [row["Name"] for row in result.pop("mounts") if row["Type"] == "volume"]
    return result


def _api_metadata() -> dict[str, Any]:
    try:
        with httpx.Client(base_url="http://127.0.0.1:8011", timeout=5) as client:
            live, ready, discovery = [
                client.get(path) for path in ("/api/v1/health/live", "/api/v1/health/ready", "/api/v1/capabilities")
            ]
            body = discovery.json()
            return {
                "live_http": live.status_code,
                "ready_http": ready.status_code,
                "capabilities_http": discovery.status_code,
                "backend_revision": body.get("backend_revision"),
                "contract_revision": body.get("contract_revision"),
                "features": body.get("features"),
                "database": body.get("dependencies", {}).get("database"),
            }
    except (httpx.HTTPError, ValueError):
        return {"status": "unavailable", "server_request_id_invented": False}


def main() -> None:
    """Capture one operator-requested phase; this utility never migrates, publishes, seeds or restarts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=_PHASES)
    phase = parser.parse_args().phase
    dsn = os.environ.get("WORKBENCH_DB_DSN")
    if not dsn:
        raise SystemExit("Load the existing application-only environment first.")
    snapshot = _database_snapshot(dsn)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_CONFIG_")}
    report = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "phase": phase,
        "database": snapshot,
        "repo_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, env=environment, timeout=10
        ).strip(),
        "container": _container(),
        "api": _api_metadata(),
        "comparisons": {},
    }
    reference_phase = (
        "before-migration"
        if phase == "after-migration"
        else "after-upload"
        if phase in ("after-api", "after-database")
        else None
    )
    if reference_phase:
        reference = json.loads((_DIRECTORY / f"sql-{reference_phase}.json").read_text(encoding="utf-8"))
        comparisons = report["comparisons"]
        comparisons["source_version_chunk_tuples_unchanged"] = (
            snapshot["source_version_chunk_fingerprint"] == reference["database"]["source_version_chunk_fingerprint"]
        )
        comparisons["same_container_and_volume"] = all(
            report["container"][key] == reference["container"][key] for key in ("container_id", "volumes", "image_id")
        )
        if phase != "after-migration":
            comparisons["job_tuples_unchanged"] = (
                snapshot["job_fingerprint"] == reference["database"]["job_fingerprint"]
            )
            comparisons["schema_and_ledger_unchanged"] = (
                snapshot["schema"] == reference["database"]["schema"]
                and snapshot["ledger"] == reference["database"]["ledger"]
            )
    report["result"] = "PASS" if all(report["comparisons"].values()) else "FAIL"
    _DIRECTORY.mkdir(parents=True, exist_ok=True)
    (_DIRECTORY / f"sql-{phase}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "phase": phase,
                "source_count": snapshot["source_count"],
                "active_chunk_count": snapshot["active_chunk_count"],
                "job_count": snapshot["job_count"],
                "result": report["result"],
            }
        )
    )
    if report["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

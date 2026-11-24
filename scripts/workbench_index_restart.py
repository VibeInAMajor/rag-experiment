"""Verify generation persistence across real API and isolated PostgreSQL process restarts."""

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

import httpx
import psycopg

from apps.workbench.persistence.models import Chunk, Source, SourceVersion, Workspace, WorkspaceContext
from apps.workbench.postgres.db_migrations import bootstrap_role, migrate
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.retrieval.profiles import POSTGRES_FTS_PROFILE_ID, POSTGRES_FTS_PROFILE_REVISION

_IMAGE = "pgvector/pgvector:0.8.2-pg17-bookworm@sha256:feb68f4f15446397d8cac7f4fe48fe4586de83160d1fc48b46283312d1a33966"
_CONTEXT = WorkspaceContext(workspace_id="development", trace_id="index-restart-r1")


def _docker(*arguments: str, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, env=environment, timeout=90
    )
    return result.stdout.strip()


def _wait_database(dsn: str) -> None:
    deadline = monotonic() + 60
    while monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=2) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.Error:
            sleep(0.5)
    raise RuntimeError("The isolated PostgreSQL process did not become ready.")


@contextmanager
def _isolated_database() -> Iterator[tuple[str, str, str]]:
    name = f"rag-index-restart-{uuid4().hex}"
    database = f"rag_test_{uuid4().hex}"
    password = secrets.token_urlsafe(32)
    application_password = secrets.token_urlsafe(32)
    environment = {**os.environ, "POSTGRES_PASSWORD": password}
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        published_port = listener.getsockname()[1]
    _docker("image", "inspect", _IMAGE)
    try:
        _docker(
            "run",
            "--detach",
            "--name",
            name,
            "--env",
            "POSTGRES_PASSWORD",
            "--env",
            "POSTGRES_USER=workbench_admin",
            "--env",
            f"POSTGRES_DB={database}",
            "--publish",
            f"127.0.0.1:{published_port}:5432",
            _IMAGE,
            environment=environment,
        )
        port = _docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        administrator = f"postgresql://workbench_admin:{password}@127.0.0.1:{port}/{database}"
        application = f"postgresql://workbench_app:{application_password}@127.0.0.1:{port}/{database}"
        _wait_database(administrator)
        bootstrap_role(administrator, password=application_password)
        migrate(administrator)
        yield name, administrator, application
    finally:
        if not name.startswith("rag-index-restart-"):
            raise RuntimeError("Refusing to remove an unowned container.")
        _docker("rm", "--force", "--volumes", name)


@contextmanager
def _api(dsn: str) -> Iterator[httpx.Client]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        **os.environ,
        "WORKBENCH_DB_DSN": dsn,
        "WORKBENCH_API_PORT": str(port),
        "WORKBENCH_CORPUS_SNAPSHOT_MODE": "persisted",
        "HAYSTACK_TELEMETRY_ENABLED": "false",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "apps.workbench.api"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            deadline = monotonic() + 60
            while monotonic() < deadline:
                ready = False
                with suppress(httpx.HTTPError):
                    ready = client.get("/api/v1/health/live").status_code == 200
                if ready:
                    break
                if process.poll() is not None:
                    raise RuntimeError("The isolated API process exited before readiness.")
                sleep(0.25)
            else:
                raise RuntimeError("The isolated API process did not become ready.")
            yield client
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _search(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/api/v1/workspaces/development/search",
        json={
            "query": "restartverificationtoken",
            "top_k": 5,
            "profile_id": POSTGRES_FTS_PROFILE_ID,
            "expected_profile_revision": POSTGRES_FTS_PROFILE_REVISION,
        },
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "corpus_revision": payload["corpus_revision"],
        "trace_id": payload["trace_id"],
        "results": [
            {key: result[key] for key in ("source_id", "source_version_id", "chunk_id", "score", "score_type")}
            for result in payload["results"]
        ],
    }


async def _run(output: Path) -> None:
    with _isolated_database() as (container, administrator, application):
        repository = PostgresPersistence(application)
        await repository.start()
        try:
            await repository.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Restart test"))
            source = Source(workspace_id="development", source_id="restart-source", title="Synthetic restart test")
            version = SourceVersion(
                workspace_id="development",
                source_id=source.source_id,
                version_id="restart-version",
                content_hash="test",
            )
            chunk = Chunk(
                workspace_id="development",
                source_id=source.source_id,
                version_id=version.version_id,
                chunk_id="restart-chunk",
                title=source.title,
                content="restartverificationtoken",
                content_hash="test",
            )
            await repository.publish_source(_CONTEXT, source=source, version=version, chunks=[chunk])
            generation = await repository.current_index_generation(_CONTEXT)
        finally:
            await repository.close()
        with _api(application) as client:
            before = _search(client)
        with _api(application) as client:
            after_api = _search(client)
        _docker("restart", container)
        _wait_database(administrator)
        with _api(application) as client:
            after_database = _search(client)
        assert before["results"] == after_api["results"] == after_database["results"]
        assert before["corpus_revision"] == after_api["corpus_revision"] == after_database["corpus_revision"]
        assert before["corpus_revision"] == generation.corpus_revision
        report = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "image": _IMAGE,
            "scope": "UUID-owned isolated container and loopback API processes; no shared services restarted",
            "generation": generation.model_dump(mode="json"),
            "before": before,
            "after_api_restart": after_api,
            "after_database_restart": after_database,
            "result": "passed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_text, json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Verified actual API and isolated PostgreSQL restarts; evidence written.")


def main() -> None:
    """Run restart verification using the installed local image and an ephemeral container."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("tasks/evidence/index-2026-11-23/restart.json"))
    arguments = parser.parse_args()
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        runner.run(_run(arguments.output))


if __name__ == "__main__":
    main()

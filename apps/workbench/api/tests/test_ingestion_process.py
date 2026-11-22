"""Kill and restart an actual API subprocess using only the fixture's owned disposable database."""

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
import pytest

from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.persistence import Chunk, CorpusSnapshot, Source, SourceVersion, Workspace, WorkspaceContext
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_CONTEXT = WorkspaceContext(workspace_id="development")
_ROOT = Path(__file__).resolve().parents[4]


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _spawn(database: DisposableDatabase, marker: Path, port: int) -> subprocess.Popen[bytes]:
    environment = dict(os.environ)
    environment["WORKBENCH_DB_DSN"] = database.app_dsn
    environment["WORKBENCH_INGESTION_PROCESS_MARKER"] = str(marker)
    for key in list(environment):
        if key.startswith(("WORKBENCH_DB_ADMIN", "WORKBENCH_TEST_")):
            environment.pop(key)
    return subprocess.Popen(
        [sys.executable, "-m", "apps.workbench.api.tests._ingestion_process", "--port", str(port)],
        cwd=_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


async def _wait_ready(client: httpx.AsyncClient, process: subprocess.Popen[bytes]) -> None:
    async with asyncio.timeout(15):
        while True:
            if process.poll() is not None:
                pytest.fail("The isolated API process exited before readiness.")
            try:
                response = await client.get("/api/v1/health/ready")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)


async def _search(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/workspaces/development/search",
        json={
            "query": query,
            "top_k": 5,
            "profile_id": "postgres-fts-baseline",
            "expected_profile_revision": "postgres-fts-baseline-r1",
        },
    )
    assert response.status_code == 200
    return response.json()


async def _verify_recovery(
    client: httpx.AsyncClient,
    repository: PostgresPersistence,
    *,
    job_id: str,
    source: Source,
    version: SourceVersion,
    chunk: Chunk,
    baseline: CorpusSnapshot,
) -> tuple[dict[str, Any], int]:
    response = await client.get(f"/api/v1/workspaces/development/jobs/{job_id}")
    assert response.status_code == 200
    recovered = response.json()
    assert recovered["status"] == "failed" and recovered["stage"] == "parsing"
    assert recovered["error_code"] == "INTERRUPTED" and recovered["retryable"]
    assert recovered["source_version_id"] is None
    old = await _search(client, chunk.content)
    assert old["results"][0]["chunk_id"] == chunk.chunk_id
    assert (await _search(client, "aftercrashuniqueterm"))["results"] == []
    assert await repository.corpus_snapshot(_CONTEXT) == baseline
    replay = await client.post(
        "/api/v1/workspaces/development/documents",
        headers={"Idempotency-Key": "interrupted_process_test"},
        files={"file": ("replacement.txt", b"aftercrashuniqueterm", "text/plain")},
        data={"source_id": source.source_id, "expected_active_version_id": version.version_id},
    )
    assert replay.status_code == 409 and replay.json()["error"]["code"] == "INTERRUPTED"
    return recovered, replay.status_code


async def test_killed_api_recovers_durable_job_without_replaying_upload_bytes(
    disposable_database: DisposableDatabase, tmp_path: Path, record_testsuite_property: Callable[[str, Any], None]
) -> None:
    """A real process stop between checkpoint and publication leaves old search intact across a real restart."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    old_text = "beforecrashuniqueterm"
    try:
        await repository.create_workspace(
            _CONTEXT, Workspace(workspace_id="development", name="Disposable process test")
        )
        source = Source(workspace_id="development", source_id="durable-source", title="Existing source")
        version = SourceVersion(
            workspace_id="development",
            source_id=source.source_id,
            version_id="existing-v1",
            content_hash=hashlib.sha256(old_text.encode()).hexdigest(),
        )
        chunk = Chunk(
            workspace_id="development",
            source_id=source.source_id,
            version_id=version.version_id,
            chunk_id="existing-chunk",
            title=source.title,
            content=old_text,
            content_hash=version.content_hash,
        )
        await repository.publish_source(_CONTEXT, source=source, version=version, chunks=[chunk])
        baseline = await repository.corpus_snapshot(_CONTEXT)
        marker = tmp_path / "reserved-job.json"
        port = _unused_port()
        first = _spawn(disposable_database, marker, port)
        second: subprocess.Popen[bytes] | None = None
        pending: asyncio.Task[httpx.Response] | None = None
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=20) as client:
                await _wait_ready(client, first)
                pending = asyncio.create_task(
                    client.post(
                        "/api/v1/workspaces/development/documents",
                        headers={"Idempotency-Key": "interrupted_process_test"},
                        files={"file": ("replacement.txt", b"aftercrashuniqueterm", "text/plain")},
                        data={"source_id": source.source_id, "expected_active_version_id": version.version_id},
                    )
                )
                async with asyncio.timeout(10):
                    while not await asyncio.to_thread(marker.exists):
                        if pending.done():
                            pytest.fail("Upload ended before the test-only durable checkpoint.")
                        await asyncio.sleep(0.05)
                confirmed = json.loads(await asyncio.to_thread(marker.read_text, encoding="utf-8"))
                assert confirmed["status"] == confirmed["stage"] == "parsing"
                live_job = await repository.get_ingestion_job(_CONTEXT, job_id=confirmed["job_id"])
                assert live_job is not None and live_job.status == "parsing"
                first.kill()
                await asyncio.to_thread(first.wait, timeout=10)
                with pytest.raises(httpx.HTTPError):
                    await pending
                second = _spawn(disposable_database, marker, port)
                await _wait_ready(client, second)
                recovered, replay_http = await _verify_recovery(
                    client,
                    repository,
                    job_id=confirmed["job_id"],
                    source=source,
                    version=version,
                    chunk=chunk,
                    baseline=baseline,
                )
                record_testsuite_property(
                    "actual_api_process_crash_recovery",
                    json.dumps(
                        {
                            "killed_pid": first.pid,
                            "restarted_pid": second.pid,
                            "job_id": confirmed["job_id"],
                            "durable_checkpoint": "parsing",
                            "recovered_status": recovered["status"],
                            "error_code": recovered["error_code"],
                            "old_active_chunk_id": chunk.chunk_id,
                            "old_source_version_id": version.version_id,
                            "corpus_unchanged": True,
                            "same_key_replay_http": replay_http,
                            "new_term_hits": 0,
                            "database_scope": "fixture-owned-disposable",
                            "production_fault_hook": False,
                        }
                    ),
                )
        finally:
            for process in (first, second):
                if process is not None and process.poll() is None:
                    process.kill()
                    await asyncio.to_thread(process.wait, timeout=10)
            if pending is not None and not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError, httpx.HTTPError):
                    await pending
    finally:
        await repository.close()

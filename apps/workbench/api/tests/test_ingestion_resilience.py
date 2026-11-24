"""HTTP cancellation, deadlines and admission over actual durable ingestion."""

import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.workbench.api.application import create_app
from apps.workbench.api.tests.test_ingestion_routes import _CONTEXT, _DOCUMENTS, _error, _upload
from apps.workbench.api.tests.test_ingestion_routes import ingestion_app as ingestion_app
from apps.workbench.api.tests.test_ingestion_routes import ingestion_client as ingestion_client
from apps.workbench.api.tests.test_ingestion_routes import ingestion_repository as ingestion_repository
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.ingestion import ingestion as ingestion_module
from apps.workbench.persistence.models import DatabaseUnavailable
from apps.workbench.postgres.postgres import PostgresPersistence

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]


async def test_publication_failure_persists_failed_job_and_rolls_back_source(
    ingestion_client: httpx.AsyncClient, ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shared-writer failure cannot leave a successful source or a permanently publishing job."""
    before = await ingestion_repository.corpus_snapshot(_CONTEXT)
    original = PostgresPersistence._publish

    async def failed_publish(*args: Any, **kwargs: Any) -> None:
        await original(*args, **kwargs)
        raise DatabaseUnavailable("private-database-diagnostic")

    monkeypatch.setattr(PostgresPersistence, "_publish", failed_publish)
    error = _error(await _upload(ingestion_client), status=503, code="DEPENDENCY_UNAVAILABLE")
    assert "private-database-diagnostic" not in str(error)
    assert error["error"]["job_id"]
    job = (await ingestion_client.get(f"/api/v1/workspaces/development/jobs/{error['error']['job_id']}")).json()
    assert job["status"] == "failed" and job["stage"] == "publishing"
    assert [stage["stage"] for stage in job["stages"]] == ["parsing", "chunking", "publication"]
    assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before


async def test_timeout_is_durable_and_late_worker_cannot_publish(
    ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deadline commits failure while pure CPU work retains its slot and cannot later write."""
    release = threading.Event()
    finished = threading.Event()
    original = ingestion_module.parse_source

    def delayed_parse(*args: Any, **kwargs: Any) -> Any:
        try:
            release.wait(timeout=2)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(ingestion_module, "parse_source", delayed_parse)
    app = create_app(settings=ApiSettings(ingestion_timeout_seconds=0.3), persistence=ingestion_repository)
    before = await ingestion_repository.corpus_snapshot(_CONTEXT)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
        ):
            response = await _upload(client)
            error = _error(response, status=504, code="INGESTION_TIMEOUT")
            assert error["error"]["job_id"]
            job = (await client.get(f"/api/v1/workspaces/development/jobs/{error['error']['job_id']}")).json()
            assert job["status"] == "failed" and job["error_code"] == "INGESTION_TIMEOUT"
            release.set()
            assert await asyncio.to_thread(finished.wait, 1)
            assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before
    finally:
        release.set()


async def test_in_progress_replay_and_capacity_are_distinct(
    ingestion_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One owned key replays as in-progress, while a full upload lane returns admission failure."""
    release = threading.Event()
    entered = threading.Event()
    original = ingestion_module.parse_source

    def held_parse(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        release.wait(timeout=2)
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion_module, "parse_source", held_parse)
    key = uuid4().hex
    first = asyncio.create_task(_upload(ingestion_client, key=key))
    second: asyncio.Task[httpx.Response] | None = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        _error(await _upload(ingestion_client, key=key), status=409, code="INGESTION_IN_PROGRESS")
        entered.clear()
        second = asyncio.create_task(_upload(ingestion_client))
        assert await asyncio.to_thread(entered.wait, 1)
        busy = await _upload(ingestion_client)
        _error(busy, status=429, code="INGESTION_BUSY")
        assert busy.headers["Retry-After"] == "1"
    finally:
        release.set()
        await asyncio.gather(*[task for task in (first, second) if task is not None])


async def test_streamed_body_limit_and_deadline_need_no_content_length() -> None:
    """A chunked sender cannot bypass byte accounting or retain an admission slot indefinitely."""
    app = create_app(settings=ApiSettings(ingestion_timeout_seconds=0.1))

    async def oversized() -> AsyncIterator[bytes]:
        yield b"x" * 5_000_000
        yield b"y" * 5_000_000

    async def stalled() -> AsyncIterator[bytes]:
        yield b"--boundary\r\n"
        await asyncio.Event().wait()

    headers = {"Content-Type": "multipart/form-data; boundary=boundary", "Idempotency-Key": uuid4().hex}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        _error(
            await client.post(_DOCUMENTS, content=oversized(), headers=headers), status=413, code="PAYLOAD_TOO_LARGE"
        )
        _error(await client.post(_DOCUMENTS, content=stalled(), headers=headers), status=504, code="INGESTION_TIMEOUT")


async def test_slow_body_shares_processing_deadline_and_retains_job_id(
    ingestion_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transport time reduces processing time; the resulting timeout identifies its durable failed job."""
    release = threading.Event()
    original = ingestion_module.parse_source

    def held_parse(*args: Any, **kwargs: Any) -> Any:
        release.wait(timeout=2)
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion_module, "parse_source", held_parse)
    app = create_app(settings=ApiSettings(ingestion_timeout_seconds=0.5), persistence=ingestion_repository)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
        ):
            built = client.build_request(
                "POST", _DOCUMENTS, files={"file": ("slow.txt", b"slowbodyterm", "text/plain")}
            )
            body = await built.aread()

            async def slow_body() -> AsyncIterator[bytes]:
                yield body[:50]
                await asyncio.sleep(0.25)
                yield body[50:]

            response = await client.post(
                _DOCUMENTS,
                content=slow_body(),
                headers={"Content-Type": built.headers["Content-Type"], "Idempotency-Key": uuid4().hex},
            )
            failure = _error(response, status=504, code="INGESTION_TIMEOUT")
            job_id = failure["error"]["job_id"]
            job = (await client.get(f"/api/v1/workspaces/development/jobs/{job_id}")).json()
            assert job["status"] == "failed" and job["error_code"] == "INGESTION_TIMEOUT"
    finally:
        release.set()

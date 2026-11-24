"""Directly saved YAML reaches actual PostgreSQL ingestion only after the supported restart boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from apps.workbench.api.application import create_app
from apps.workbench.api.tests.test_configuration_editor import _ORIGIN, _URL
from apps.workbench.api.tests.test_configuration_editor import editor_settings as editor_settings
from apps.workbench.api.tests.test_ingestion_routes import _DOCUMENTS, _upload
from apps.workbench.api.tests.test_ingestion_routes import ingestion_repository as ingestion_repository
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.testing.database import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]


@asynccontextmanager
async def _client(database: DisposableDatabase, settings: ApiSettings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=settings, persistence=PostgresPersistence(database.app_dsn))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011", headers=_ORIGIN
        ) as client,
    ):
        yield client


@pytest.mark.usefixtures("ingestion_repository")
async def test_saved_policy_is_used_by_new_ingestion_after_restart(
    disposable_database: DisposableDatabase, editor_settings: ApiSettings
) -> None:
    """A live save keeps the old consumer intact; a fresh consumer uses the same saved file."""
    async with _client(disposable_database, editor_settings) as client:
        first = (await client.get(_URL)).json()
        old = await _upload(client, content=b"English before a configuration change.")
        source_id = old.json()["source_id"]
        original = (await client.get(f"{_DOCUMENTS}/{source_id}")).json()
        text = (
            "document_processing:\n  default_language: ru\n  recursive_splitter:\n"
            "    split_length: 80\n    split_overlap: 15\n"
        )
        result = await client.put(_URL, json={"yaml": text, "expected_revision": first["revision"]})
        assert result.status_code == 200 and result.json()["activation"] == "requires_restart"
        still_old = await _upload(client, content=b"The running service retains English.")
        chunks = (await client.get(f"{_DOCUMENTS}/{still_old.json()['source_id']}/chunks")).json()["items"]
        assert all(
            item["metadata"]["sentence_language"] == "en" and item["metadata"]["target_size"] == 500 for item in chunks
        )
    restarted = ApiSettings.from_env({"WORKBENCH_DOCUMENT_PROCESSING_CONFIG": editor_settings.configuration_file or ""})
    async with _client(disposable_database, restarted) as client:
        assert (await client.get(_URL)).json()["activation"] == "active"
        uploaded = await _upload(client, content=("Иванов проверил отчёт. Следующая глава сохранена. " * 50).encode())
        assert uploaded.status_code == 201
        chunks = (await client.get(f"{_DOCUMENTS}/{uploaded.json()['source_id']}/chunks")).json()["items"]
        assert len(chunks) > 1 and all(
            item["metadata"]["sentence_language"] == "ru" and item["metadata"]["target_size"] == 80 for item in chunks
        )
        previous = (await client.get(f"{_DOCUMENTS}/{source_id}")).json()
        assert previous["active_version_id"] == original["active_version_id"]
        assert previous["processing_profile_fingerprint"] == original["processing_profile_fingerprint"]

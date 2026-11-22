"""Configured processing over real ASGI routes and fixture-owned disposable PostgreSQL."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.workbench.api.application import create_app
from apps.workbench.api.chunking import ModelTokenAdmission
from apps.workbench.api.chunking_adapters import count_tokens
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.document_processing import DocumentProcessingSettings
from apps.workbench.api.model_token_counter import LocalQwenTokenCounter
from apps.workbench.api.persistence import Workspace, WorkspaceContext
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase
from apps.workbench.api.tests.test_ingestion_routes import _CONTEXT, _DOCUMENTS, _error, _upload
from apps.workbench.api.tests.test_ingestion_routes import ingestion_repository as ingestion_repository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="function"),
    pytest.mark.usefixtures("ingestion_repository"),
]


@asynccontextmanager
async def _client(
    database: DisposableDatabase, processing: DocumentProcessingSettings
) -> AsyncIterator[httpx.AsyncClient]:
    # Each application lifecycle owns its pool; policy changes reuse only the fixture's durable database.
    repository = PostgresPersistence(database.app_dsn)
    app = create_app(settings=ApiSettings(document_processing=processing), persistence=repository)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        yield client


def _settings(language: str = "en", **kwargs: Any) -> DocumentProcessingSettings:
    return DocumentProcessingSettings.model_validate({"default_language": language, **kwargs})


@pytest.fixture
def qwen_directory() -> Path:
    """Require explicit operator assets; ordinary test environments never assume a local model directory."""
    selected = os.environ.get("WORKBENCH_TEST_QWEN_TOKENIZER_DIR")
    if selected is None:
        pytest.skip("Explicit WORKBENCH_TEST_QWEN_TOKENIZER_DIR is required for native tokenizer qualification")
    return Path(selected)


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("en", "Dr. Smith arrived at 10 a.m. He read the report.\nThe next section follows. "),
        ("ru", "Проф. Иванов прочитал доклад. Следующая глава готова.\nЭто проверка границ предложений. "),
    ],
)
async def test_configured_language_and_splitter_reach_persisted_http_chunks(
    disposable_database: DisposableDatabase, language: str, text: str
) -> None:
    """Every reported setting belongs to actual parser/chunker output committed by the route."""
    settings = _settings(
        language,
        recursive_splitter={
            "split_length": 48,
            "split_overlap": 9,
            "separators": ["sentence", "\n\n", "\n", " "],
            "sentence_splitter_params": {"keep_white_spaces": False},
        },
    )
    content = "# Overview\r\n\r\n" + text * 50
    async with _client(disposable_database, settings) as client:
        features = (await client.get("/api/v1/capabilities")).json()["features"]
        assert features["upload"] is True
        response = await _upload(client, content=content.encode(), filename="configured.md", mime="text/markdown")
        assert response.status_code == 201, response.text
        uploaded = response.json()
        source_url = f"{_DOCUMENTS}/{uploaded['source_id']}"
        detail = (await client.get(source_url)).json()
        assert detail["default_language"] == language
        assert detail["language_policy"] == "configured_sentence_language"
        assert detail["document_processing"]["recursive_splitter"]["split_length"] == 48
        items = (await client.get(source_url + "/chunks", params={"limit": 100})).json()["items"]
        assert len(items) == uploaded["chunk_count"] > 1
        for item in items:
            metadata = item["metadata"]
            assert metadata["sentence_language"] == metadata["default_language"] == language
            assert metadata["target_size"] == 48 and metadata["requested_overlap"] == 9
            assert metadata["sentence_keep_white_spaces"] is False
            assert metadata["fallback_reasons"] == []
            assert metadata["separators"] == ["sentence", "\n\n", "\n", " "]
            assert count_tokens(item["content"]) == metadata["length_tiktoken"] <= 48
            span = metadata["source_span"]
            assert item["content"] == content[span["start"] : span["end"]]
            assert item["page"] is None


async def test_config_change_preserves_terminal_replay_and_requires_explicit_reingestion(
    disposable_database: DisposableDatabase,
) -> None:
    """Server policy changes affect new jobs without reinterpreting committed idempotency keys."""
    key = uuid4().hex
    content = ("An English sentence. Another documented sentence. " * 120).encode()
    async with _client(disposable_database, _settings()) as client:
        first_response = await _upload(client, content=content, key=key)
        assert first_response.status_code == 201
        first = first_response.json()
        old_detail = (await client.get(f"{_DOCUMENTS}/{first['source_id']}")).json()
    changed = _settings("ru", recursive_splitter={"split_length": 64, "split_overlap": 8})
    async with _client(disposable_database, changed) as client:
        replay_response = await _upload(client, content=content, key=key)
        assert replay_response.status_code == 200
        replay = replay_response.json()
        assert replay["replayed"] is True
        for field in ("job_id", "source_id", "source_version_id", "chunk_count", "corpus_revision"):
            assert replay[field] == first[field]
        detail = (await client.get(f"{_DOCUMENTS}/{first['source_id']}")).json()
        assert detail["default_language"] == "en"
        assert detail["processing_profile_fingerprint"] == old_detail["processing_profile_fingerprint"]
        response = await _upload(
            client,
            content=content,
            fields={"source_id": first["source_id"], "expected_active_version_id": first["source_version_id"]},
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["outcome"] == "updated" and updated["source_version_id"] != first["source_version_id"]
        detail = (await client.get(f"{_DOCUMENTS}/{first['source_id']}")).json()
        assert detail["default_language"] == "ru"
        assert detail["processing_profile_fingerprint"] != old_detail["processing_profile_fingerprint"]


async def test_configured_processing_does_not_enable_workspace_or_request_overrides(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """The configured language cannot be overridden by multipart input or cross-workspace routing."""
    foreign = WorkspaceContext(workspace_id="foreign")
    await ingestion_repository.create_workspace(foreign, Workspace(workspace_id="foreign", name="Foreign"))
    async with _client(disposable_database, _settings("ru")) as client:
        before = await ingestion_repository.corpus_snapshot(_CONTEXT)
        _error(await _upload(client, fields={"language": "en"}), status=400, code="INVALID_REQUEST")
        response = await client.post(
            "/api/v1/workspaces/foreign/documents",
            files={"file": ("foreign.txt", b"foreign text", "text/plain")},
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 404
        assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before
        assert (await ingestion_repository.corpus_snapshot(foreign)).documents == []


async def test_actual_qwen_guard_counts_same_configured_input_separately_from_tiktoken(
    disposable_database: DisposableDatabase, qwen_directory: Path
) -> None:
    """Native counts come from the approved tokenizer bytes, without model weights or inference."""
    counter = await asyncio.to_thread(LocalQwenTokenCounter, qwen_directory)
    settings = _settings(
        native_model_guard={
            "enabled": True,
            "local_asset_directory": str(qwen_directory),
            "max_tokens": 32768,
            "prefix": "Document: ",
            "suffix": "\n",
            "include_heading_path": True,
        }
    )
    content = "# Overview\n\nHello world.\n\n# Details\n\nПривет, мир! Український приклад."
    async with _client(disposable_database, settings) as client:
        assert (await client.get("/api/v1/capabilities")).json()["features"]["upload"] is True
        response = await _upload(client, filename="native.md", mime="text/markdown", content=content.encode())
        assert response.status_code == 201, response.text
        source_url = f"{_DOCUMENTS}/{response.json()['source_id']}"
        items = (await client.get(source_url + "/chunks")).json()["items"]
        admission = ModelTokenAdmission(
            counter_revision=counter.counter_revision,
            max_tokens=32768,
            prefix="Document: ",
            suffix="\n",
            include_heading_path=True,
        )
        differences = []
        for item in items:
            metadata = item["metadata"]
            formatted = admission.embedding_input(item["content"], heading_path=tuple(item["section_path"]))
            native_count = counter.count_tokens(formatted)
            encoding_count = count_tokens(formatted)
            assert metadata["model_counter_revision"] == counter.counter_revision
            assert metadata["length_model_token"] == native_count <= 32768
            assert metadata["length_tiktoken_model_input"] == encoding_count
            assert metadata["model_minus_tiktoken_model_input"] == native_count - encoding_count
            differences.append(native_count != encoding_count)
        assert any(differences)
        detail = (await client.get(source_url)).json()
        guard = detail["document_processing"]["native_model_guard"]
        assert guard["enabled"] is True and guard["counter_revision"] == counter.counter_revision
        safe = json.dumps(detail)
        assert str(qwen_directory) not in safe and "local_asset_directory" not in safe
        assert "Document: " not in safe and "prefix_sha256" in safe


async def test_actual_qwen_overflow_fails_durably_without_publication_or_implicit_retry(
    ingestion_repository: PostgresPersistence, disposable_database: DisposableDatabase, qwen_directory: Path
) -> None:
    """A one-token native ceiling rejects a real input and terminal replay remains rejected after policy changes."""
    settings = _settings(
        native_model_guard={"enabled": True, "local_asset_directory": str(qwen_directory), "max_tokens": 1}
    )
    key = uuid4().hex
    before = await ingestion_repository.corpus_snapshot(_CONTEXT)
    async with _client(disposable_database, settings) as client:
        failure = _error(
            await _upload(client, content=b"Hello world", key=key), status=413, code="MODEL_TOKEN_LIMIT_EXCEEDED"
        )
        assert failure["error"]["retryable"] is False
        job_id = failure["error"]["job_id"]
        job = (await client.get(f"/api/v1/workspaces/development/jobs/{job_id}")).json()
        assert job["status"] == "failed" and job["error_code"] == "MODEL_TOKEN_LIMIT_EXCEEDED"
        assert job["source_version_id"] is None
        _error(await client.get(f"{_DOCUMENTS}/{job['source_id']}"), status=404)
        assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before
    async with _client(disposable_database, _settings()) as client:
        replay = _error(
            await _upload(client, content=b"Hello world", key=key), status=413, code="MODEL_TOKEN_LIMIT_EXCEEDED"
        )
        assert replay["error"]["job_id"] == job_id
        assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before

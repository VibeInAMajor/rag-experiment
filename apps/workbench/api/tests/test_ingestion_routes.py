"""Real bounded HTTP uploads publish into the same PostgreSQL corpus used by Haystack search."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from jsonschema import Draft202012Validator

from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.db_migrations import migrate
from apps.workbench.api.db_seed import seed_development
from apps.workbench.api.persistence import Workspace, WorkspaceContext
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.tests.conftest import DisposableDatabase

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_DOCUMENTS = "/api/v1/workspaces/development/documents"
_CONTEXT = WorkspaceContext(workspace_id="development")


@pytest_asyncio.fixture(loop_scope="function")
async def ingestion_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Migrate and seed only this test's guarded disposable database."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        await seed_development(repository)
        yield repository
    finally:
        await repository.close()


@pytest_asyncio.fixture(loop_scope="function")
async def ingestion_app(ingestion_repository: PostgresPersistence) -> AsyncIterator[FastAPI]:
    """Compose actual application lifecycle around the persistent test corpus."""
    app = create_app(settings=ApiSettings(), persistence=ingestion_repository)
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture(loop_scope="function")
async def ingestion_client(ingestion_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Exercise the real ASGI transport policy and routes."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingestion_app), base_url="http://127.0.0.1:8011"
    ) as client:
        yield client


def _error(response: httpx.Response, *, status: int, code: str | None = None) -> dict[str, Any]:
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["trace_id"]
    assert payload["error"]["http_status"] == status
    if code:
        assert payload["error"]["code"] == code
    return payload


async def _upload(
    client: httpx.AsyncClient,
    *,
    content: bytes = b"durablealphaprobe",
    filename: str = "notes.txt",
    mime: str = "text/plain",
    key: str | None = None,
    fields: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        _DOCUMENTS,
        files={"file": (filename, content, mime)},
        data=fields,
        headers={"Idempotency-Key": key or uuid4().hex},
    )


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
    assert response.status_code == 200, response.text
    return response.json()


def _counts(database: DisposableDatabase) -> tuple[int, int, int, int]:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT (SELECT count(*) FROM workbench.sources), (SELECT count(*) FROM workbench.source_versions), "
            "(SELECT count(*) FROM workbench.chunks), (SELECT count(*) FROM workbench.ingestion_jobs)"
        ).fetchone()
    assert row is not None
    return tuple(row)


@pytest.mark.parametrize(
    ("filename", "mime", "content"),
    [
        ("plain.txt", "text/plain", "durablealphaprobe English русский український".encode()),
        (
            "headings.md",
            "text/markdown",
            b"# Heading\n\ndurablealphaprobe\n\n```txt\ncode preserved\n```\n\n|A|B|\n|-|-|\n|one|two|",
        ),
        ("bom.txt", "text/plain", b"\xef\xbb\xbfdurablealphaprobe"),
    ],
)
async def test_upload_details_chunks_jobs_and_existing_search_agree(
    ingestion_client: httpx.AsyncClient,
    ingestion_app: FastAPI,
    disposable_database: DisposableDatabase,
    filename: str,
    mime: str,
    content: bytes,
) -> None:
    """Committed HTTP identities and lexical hits must refer to the same stored chunks."""
    response = await _upload(ingestion_client, filename=filename, mime=mime, content=content)
    assert response.status_code == 201, response.text
    upload = response.json()
    assert upload["request_id"] == response.headers["x-request-id"]
    assert upload["status"] == "completed" and upload["outcome"] == "created"
    assert {stage["stage"] for stage in upload["stages"]} == {"parsing", "chunking", "publication"}
    assert all(stage["duration_ms"] >= 0 for stage in upload["stages"])
    definition = ingestion_app.openapi()["paths"]["/api/v1/workspaces/{workspace_id}/documents"]["post"]["responses"][
        "201"
    ]
    Draft202012Validator(
        {**definition["content"]["application/json"]["schema"], "components": ingestion_app.openapi()["components"]}
    ).validate(upload)
    detail = (await ingestion_client.get(f"{_DOCUMENTS}/{upload['source_id']}")).json()
    assert detail["active_version_id"] == upload["source_version_id"]
    assert detail["original_content_available"] is False
    assert detail["chunk_count"] == upload["chunk_count"]
    chunks_response = await ingestion_client.get(f"{_DOCUMENTS}/{upload['source_id']}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()
    assert chunks["source_version_id"] == upload["source_version_id"]
    assert len(chunks["items"]) == upload["chunk_count"]
    assert all(chunk["page"] is None for chunk in chunks["items"])
    indexed_text = "\n".join(chunk["content"] for chunk in chunks["items"])
    assert "durablealphaprobe" in indexed_text
    if filename.endswith(".md"):
        assert "code preserved" in indexed_text and "|one|two|" in indexed_text
        assert any(chunk["section_path"] for chunk in chunks["items"])
    job = (await ingestion_client.get(f"/api/v1/workspaces/development/jobs/{upload['job_id']}")).json()
    assert job["status"] == "completed"
    assert job["source_version_id"] == upload["source_version_id"]
    assert job["chunk_count"] == upload["chunk_count"]
    result = await _search(ingestion_client, "durablealphaprobe")
    assert result["corpus_revision"] == upload["corpus_revision"]
    assert result["results"][0]["source_id"] == upload["source_id"]
    assert result["results"][0]["source_version_id"] == upload["source_version_id"]
    assert result["results"][0]["score_type"] == "postgres_ts_rank_cd"
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT count(*) FROM workbench.chunks WHERE source_id=%s AND "
            "(embedding IS NOT NULL OR embedding_profile_id IS NOT NULL OR dimensions IS NOT NULL)",
            (upload["source_id"],),
        ).fetchone() == (0,)


async def test_replay_unchanged_and_guarded_replacement_keep_identity(
    ingestion_client: httpx.AsyncClient, disposable_database: DisposableDatabase
) -> None:
    """Retries preserve identity; a guarded replacement alone switches the active version."""
    key = uuid4().hex
    first = (await _upload(ingestion_client, key=key)).json()
    before = _counts(disposable_database)
    replay = await _upload(ingestion_client, key=key)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    for field in ("job_id", "source_id", "source_version_id", "chunk_count"):
        assert replay.json()[field] == first[field]
    assert _counts(disposable_database) == before
    _error(await _upload(ingestion_client, key=key, content=b"different"), status=409, code="IDEMPOTENCY_CONFLICT")
    fields = {"source_id": first["source_id"], "expected_active_version_id": first["source_version_id"]}
    unchanged = await _upload(ingestion_client, fields=fields)
    assert unchanged.status_code == 200
    assert unchanged.json()["outcome"] == "unchanged"
    assert unchanged.json()["source_version_id"] == first["source_version_id"]
    assert unchanged.json()["chunk_count"] == first["chunk_count"]
    assert _counts(disposable_database)[:3] == before[:3]
    update_key = uuid4().hex
    updated = await _upload(ingestion_client, key=update_key, fields=fields, content=b"replacementbetaprobe")
    assert updated.status_code == 200, updated.text
    active = updated.json()
    assert active["outcome"] == "updated" and active["source_id"] == first["source_id"]
    assert active["source_version_id"] != first["source_version_id"]
    before_replay = _counts(disposable_database)
    # Replaying the completed update must precede stale expected-version rejection.
    updated_replay = await _upload(ingestion_client, key=update_key, fields=fields, content=b"replacementbetaprobe")
    assert updated_replay.status_code == 200
    assert updated_replay.json()["job_id"] == active["job_id"]
    assert _counts(disposable_database) == before_replay
    _error(await _upload(ingestion_client, fields=fields, content=b"stalegamma"), status=409, code="VERSION_CONFLICT")
    assert (await _search(ingestion_client, "durablealphaprobe"))["results"] == []
    assert (await _search(ingestion_client, "replacementbetaprobe"))["results"][0]["source_version_id"] == active[
        "source_version_id"
    ]


@pytest.mark.parametrize(
    ("content", "filename", "mime", "status"),
    [
        (b"\xff", "invalid.txt", "text/plain", 400),
        (b"secret\0text", "nul.txt", "text/plain", 400),
        (b" \n\t", "empty.txt", "text/plain", 400),
        (b"", "zero.txt", "text/plain", 400),
        (b"%PDF-fake", "fake.txt", "text/plain", 415),
        (b"hello", "file.pdf", "application/pdf", 400),
        (b"hello", "file.md", "application/pdf", 415),
        (b"hello", "../escape.txt", "text/plain", 400),
        (b"hello", "C:\\escape.txt", "text/plain", 400),
        (b"x" * (1_048_576 + 1), "huge.txt", "text/plain", 413),
    ],
)
async def test_invalid_upload_never_changes_active_corpus(
    ingestion_client: httpx.AsyncClient,
    ingestion_repository: PostgresPersistence,
    content: bytes,
    filename: str,
    mime: str,
    status: int,
) -> None:
    """Invalid bytes and names cannot displace or extend the searchable corpus."""
    before = await ingestion_repository.corpus_snapshot(_CONTEXT)
    response = await _upload(ingestion_client, content=content, filename=filename, mime=mime)
    error = _error(response, status=status)
    assert await ingestion_repository.corpus_snapshot(_CONTEXT) == before
    if job_id := error["error"].get("job_id"):
        job = await ingestion_client.get(f"/api/v1/workspaces/development/jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "failed"


async def test_failed_update_preserves_old_active_and_failed_replay_is_terminal(
    ingestion_client: httpx.AsyncClient,
) -> None:
    """A durable failed request remains replayable while the previous good version stays active."""
    first = (await _upload(ingestion_client)).json()
    fields = {"source_id": first["source_id"], "expected_active_version_id": first["source_version_id"]}
    key = uuid4().hex
    error = _error(await _upload(ingestion_client, fields=fields, key=key, content=b"\xff"), status=400)
    assert error["error"]["job_id"]
    repeat = _error(await _upload(ingestion_client, fields=fields, key=key, content=b"\xff"), status=400)
    assert repeat["error"]["job_id"] == error["error"]["job_id"]
    assert (await _search(ingestion_client, "durablealphaprobe"))["results"][0]["source_version_id"] == first[
        "source_version_id"
    ]


async def test_duplicate_unknown_fields_and_malformed_multipart_fail_safely(
    ingestion_client: httpx.AsyncClient,
) -> None:
    """Multipart fields and terminal framing cannot be silently truncated."""
    cases: list[list[tuple[str, tuple[str | None, bytes | str] | tuple[str, bytes, str]]]] = [
        [("file", ("one.txt", b"one", "text/plain")), ("file", ("two.txt", b"two", "text/plain"))],
        [("file", ("one.txt", b"one", "text/plain")), ("unexpected", (None, "value"))],
        [("file", ("one.txt", b"one", "text/plain")), ("source_id", (None, "one")), ("source_id", (None, "one"))],
    ]
    for files in cases:
        _error(
            await ingestion_client.post(_DOCUMENTS, files=files, headers={"Idempotency-Key": uuid4().hex}), status=400
        )
    _error(
        await ingestion_client.post(
            _DOCUMENTS,
            content=b"--incomplete\r\n",
            headers={"Content-Type": "multipart/form-data; boundary=incomplete", "Idempotency-Key": uuid4().hex},
        ),
        status=400,
    )
    _error(await ingestion_client.post(_DOCUMENTS, files={"file": ("one.txt", b"one")}), status=400)


@pytest.mark.parametrize(
    "disposition",
    [
        'form-data; name="unexpected"; name="file"; filename="note.txt"',
        'form-data; name="file"; filename="bad.txt"; filename="good.txt"',
        'form-data; name="file"; filename="one.txt"; filename*=UTF-8\'\'two.txt',
        'form-data; name="file"; filename="unterminated.txt',
    ],
)
async def test_ambiguous_part_parameters_are_rejected_before_reservation(
    ingestion_client: httpx.AsyncClient, disposable_database: DisposableDatabase, disposition: str
) -> None:
    """Different MIME parsers cannot reinterpret a duplicated field name or filename."""
    before = _counts(disposable_database)
    body = ("--boundary\r\nContent-Disposition: " + disposition + "\r\n\r\ntext\r\n--boundary--\r\n").encode()
    _error(
        await ingestion_client.post(
            _DOCUMENTS,
            content=body,
            headers={"Content-Type": "multipart/form-data; boundary=boundary", "Idempotency-Key": uuid4().hex},
        ),
        status=400,
        code="INVALID_REQUEST",
    )
    assert _counts(disposable_database) == before


async def test_chunk_pagination_is_scoped_and_stale_after_publication(ingestion_client: httpx.AsyncClient) -> None:
    """Chunk positions are scoped to the source, workspace and unchanged corpus."""
    content = ("# Long\n\n" + "boundedpageterm " * 1600).encode()
    created = await _upload(ingestion_client, content=content, filename="long.md", mime="text/markdown")
    assert created.status_code == 201, created.text
    first = created.json()
    route = f"{_DOCUMENTS}/{first['source_id']}/chunks"
    page = (await ingestion_client.get(route, params={"limit": 1})).json()
    assert page["next_cursor"]
    second = await ingestion_client.get(route, params={"limit": 1, "cursor": page["next_cursor"]})
    assert second.status_code == 200
    assert second.json()["items"][0]["chunk_id"] != page["items"][0]["chunk_id"]
    _error(
        await ingestion_client.get(f"{_DOCUMENTS}/demo-backup/chunks", params={"cursor": page["next_cursor"]}),
        status=400,
        code="INVALID_CURSOR",
    )
    await _upload(ingestion_client, content=b"another source changes corpus")
    _error(await ingestion_client.get(route, params={"cursor": page["next_cursor"]}), status=400, code="INVALID_CURSOR")
    _error(await ingestion_client.get(route, params={"limit": 0}), status=400)


async def test_foreign_scope_and_safe_missing_reads(ingestion_client: httpx.AsyncClient) -> None:
    """Foreign and absent identities reveal neither data nor privileged context."""
    _error(
        await ingestion_client.post(
            "/api/v1/workspaces/foreign/documents",
            files={"file": ("one.txt", b"one")},
            headers={"Idempotency-Key": uuid4().hex},
        ),
        status=404,
        code="WORKSPACE_NOT_FOUND",
    )
    _error(await ingestion_client.get(f"{_DOCUMENTS}/missing"), status=404, code="DOCUMENT_NOT_FOUND")
    _error(await ingestion_client.get(f"{_DOCUMENTS}/missing/chunks"), status=404, code="DOCUMENT_NOT_FOUND")
    _error(await ingestion_client.get("/api/v1/workspaces/development/jobs/missing"), status=404, code="JOB_NOT_FOUND")


async def test_empty_authorized_workspace_can_discover_and_publish_first_upload(
    disposable_database: DisposableDatabase,
) -> None:
    """Write availability is certified independently of a nonempty executable search corpus."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        await repository.create_workspace(_CONTEXT, Workspace(workspace_id="development", name="Development"))
        app = create_app(settings=ApiSettings(), persistence=repository)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
        ):
            features = (await client.get("/api/v1/capabilities")).json()["features"]
            assert features["upload"] and features["document_details"] and features["jobs"]
            assert features["search"] is False
            response = await _upload(client)
            assert response.status_code == 201
            assert (await _search(client, "durablealphaprobe"))["results"][0]["source_id"] == response.json()[
                "source_id"
            ]
    finally:
        await repository.close()


async def test_cors_upload_and_search_body_policies_remain_separate(ingestion_client: httpx.AsyncClient) -> None:
    """Upload preflight preserves search JSON limits and exact loopback origins."""
    for method in ("GET", "POST"):
        response = await ingestion_client.options(
            _DOCUMENTS,
            headers={
                "Origin": "http://127.0.0.1:4173",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Content-Type, Idempotency-Key" if method == "POST" else "Accept",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"
    _error(
        await ingestion_client.options(
            _DOCUMENTS,
            headers={
                "Origin": "http://127.0.0.1:4173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        ),
        status=403,
    )
    _error(
        await ingestion_client.post(
            _DOCUMENTS,
            files={"file": ("one.txt", b"one")},
            headers={"Idempotency-Key": uuid4().hex, "Origin": "https://attacker.example"},
        ),
        status=403,
    )
    _error(
        await ingestion_client.post(
            "/api/v1/workspaces/development/search", content=b" " * 32769, headers={"Content-Type": "application/json"}
        ),
        status=413,
    )

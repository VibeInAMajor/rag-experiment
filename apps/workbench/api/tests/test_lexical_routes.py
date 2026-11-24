"""Real HTTP-to-Haystack-to-PostgreSQL retrieval over the persisted development corpus."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
import pytest_asyncio
from jsonschema import Draft202012Validator

from apps.workbench.api import application as application_module
from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.persistence.models import Chunk, Source, SourceVersion, Workspace, WorkspaceContext
from apps.workbench.postgres.db_migrations import migrate
from apps.workbench.postgres.db_seed import seed_development
from apps.workbench.postgres.postgres import PostgresPersistence
from apps.workbench.testing.database import DisposableDatabase
from haystack import Pipeline

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_SEARCH = "/api/v1/workspaces/development/search"
_DOCUMENTS = "/api/v1/workspaces/development/documents"
_PROFILE = "postgres-fts-baseline"
_REVISION = "postgres-fts-baseline-r1"
_CONTEXT = WorkspaceContext(workspace_id="development")


def _body(query: str = "PostgreSQL", **overrides: Any) -> dict[str, Any]:
    return {"query": query, "top_k": 5, "profile_id": _PROFILE, "expected_profile_revision": _REVISION, **overrides}


def _error(response: httpx.Response, status: int, code: str | None = None) -> dict[str, Any]:
    assert response.status_code == status, response.text
    payload = response.json()
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["trace_id"]
    assert payload["error"]["http_status"] == status
    if code:
        assert payload["error"]["code"] == code
    return payload


@pytest_asyncio.fixture(loop_scope="function")
async def corpus_repository(disposable_database: DisposableDatabase) -> AsyncIterator[PostgresPersistence]:
    """Explicitly seed the fixture-owned database once before composing the application."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    await repository.start()
    try:
        await seed_development(repository)
        yield repository
    finally:
        await repository.close()


@pytest_asyncio.fixture(loop_scope="function")
async def live_client(corpus_repository: PostgresPersistence) -> AsyncIterator[httpx.AsyncClient]:
    """Run real application lifespan and HTTP policy on the repository's event loop."""
    app = create_app(settings=ApiSettings(), persistence=corpus_repository)

    async def check_schema(response: httpx.Response) -> None:
        await response.aread()
        path = "/api/v1/workspaces"
        if response.request.url.path.endswith("/search"):
            path = "/api/v1/workspaces/{workspace_id}/search"
        elif response.request.url.path.endswith("/documents"):
            path = "/api/v1/workspaces/{workspace_id}/documents"
        specification = app.openapi()
        definition = specification["paths"][path][response.request.method.lower()]["responses"][
            str(response.status_code)
        ]
        Draft202012Validator(
            {**definition["content"]["application/json"]["schema"], "components": specification["components"]}
        ).validate(response.json())

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8011",
            event_hooks={"response": [check_schema]},
        ) as client,
    ):
        yield client


async def test_live_search_executes_real_haystack_and_matches_postgres_scores(
    live_client: httpx.AsyncClient, corpus_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The orchestration is an actual Pipeline invocation over the existing SQL adapter."""
    invocations: list[Pipeline] = []
    original = Pipeline.run_async

    async def execute(pipeline: Pipeline, *args: Any, **kwargs: Any) -> Any:
        invocations.append(pipeline)
        return await original(pipeline, *args, **kwargs)

    monkeypatch.setattr(Pipeline, "run_async", execute)
    response = await live_client.post(_SEARCH, json=_body("PostgreSQL"))
    assert response.status_code == 200, response.text
    payload = response.json()
    sql_hits = await corpus_repository.lexical_search(_CONTEXT, query="PostgreSQL", top_k=5)
    assert invocations
    assert [item["chunk_id"] for item in payload["results"]] == [hit.chunk.chunk_id for hit in sql_hits]
    for result, hit in zip(payload["results"], sql_hits, strict=True):
        assert result["score"] == pytest.approx(hit.score)
        assert result["score_type"] == "postgres_ts_rank_cd"
        assert result["content"] == hit.chunk.content
        assert result["source_version_id"] == hit.chunk.version_id
        assert result["rank"] == hit.rank
        if hit.chunk.page is None:
            assert "page" not in result
    assert payload["profile_id"] == _PROFILE
    assert payload["profile_revision"] == _REVISION
    assert payload["mode"] == "live"
    assert payload["status"] == "success"
    assert payload["duration_ms"] >= sum(stage["duration_ms"] for stage in payload["stages"])
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["trace_id"]
    assert payload["run_id"]


async def test_labeled_exact_queries_and_diagnostic_paraphrases(
    live_client: httpx.AsyncClient, record_testsuite_property: Callable[[str, Any], None]
) -> None:
    """At least nine of ten labeled lexical targets appear in the first five hits."""
    fixture = json.loads(
        (Path(__file__).parents[2] / "retrieval/fixtures/lexical-evaluation.json").read_text(encoding="utf-8")
    )
    matched = 0
    missed: list[str] = []
    revisions: set[str] = set()
    exact = fixture["gated_exact_queries"]
    assert len(exact) == 10
    for case in exact:
        response = await live_client.post(_SEARCH, json=_body(case["query"]))
        assert response.status_code == 200, response.text
        payload = response.json()
        revisions.add(payload["corpus_revision"])
        hit = case["expected_source_id"] in [hit["source_id"] for hit in payload["results"]]
        matched += hit
        if not hit:
            missed.append(case["query"])
    assert matched >= 9, missed
    assert len(revisions) == 1
    diagnostics: list[dict[str, Any]] = []
    for case in fixture["diagnostic_paraphrases"]:
        response = await live_client.post(_SEARCH, json=_body(case["query"]))
        assert response.status_code == 200
        assert isinstance(response.json()["results"], list)
        diagnostics.append(
            {
                **case,
                "expected_source_in_top5": case["expected_source_id"]
                in [hit["source_id"] for hit in response.json()["results"]],
            }
        )
    record_testsuite_property(
        "lexical_evaluation",
        json.dumps(
            {
                "matched_top5": matched,
                "query_count": 10,
                "missed": missed,
                "corpus_revision": next(iter(revisions)),
                "diagnostics": diagnostics,
            }
        ),
    )


async def test_queries_change_rankings_while_ids_and_corpus_revision_remain_stable(
    live_client: httpx.AsyncClient,
) -> None:
    """Query-dependent rankings share durable provenance rather than a fixture replay."""
    first = (await live_client.post(_SEARCH, json=_body("retention"))).json()
    second = (await live_client.post(_SEARCH, json=_body("cosine"))).json()
    repeated = (await live_client.post(_SEARCH, json=_body("retention"))).json()
    assert first["results"] != second["results"]
    assert first["results"] == repeated["results"]
    assert first["corpus_revision"] == second["corpus_revision"] == repeated["corpus_revision"]
    assert first["run_id"] != repeated["run_id"]


async def test_documents_are_real_stably_paginated_records(live_client: httpx.AsyncClient) -> None:
    """Pagination traverses one identified snapshot without duplicate or invented sources."""
    items: list[dict[str, Any]] = []
    revisions: set[str] = set()
    cursor = None
    while True:
        params = {"limit": "3"}
        if cursor:
            params["cursor"] = cursor
        response = await live_client.get(_DOCUMENTS, params=params)
        assert response.status_code == 200, response.text
        page = response.json()
        revisions.add(page["corpus_revision"])
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert len(items) <= 8
    assert len(items) == 8
    assert len({item["source_id"] for item in items}) == 8
    assert [item["source_id"] for item in items] == sorted(item["source_id"] for item in items)
    assert all(item["status"] == "ready" and item["active_version_id"] for item in items)
    assert len(revisions) == 1
    _error(await live_client.get(_DOCUMENTS, params={"cursor": "tampered"}), 400, "INVALID_CURSOR")
    workspaces = await live_client.get("/api/v1/workspaces", params={"limit": 1})
    assert workspaces.status_code == 200
    assert [item["workspace_id"] for item in workspaces.json()["items"]] == ["development"]
    assert workspaces.json()["next_cursor"] is None


async def test_required_fields_and_pagination_bounds_are_not_framework_422s(live_client: httpx.AsyncClient) -> None:
    """Explicit request completeness and cursor bounds share canonical typed client errors."""
    for field in ["query", "top_k", "profile_id", "expected_profile_revision"]:
        body = _body()
        del body[field]
        _error(await live_client.post(_SEARCH, json=body), 400, "INVALID_REQUEST")
    invalid_pages: list[dict[str, str | int]] = [{"limit": 0}, {"limit": 101}, {"limit": "true"}, {"cursor": "x" * 513}]
    for parameters in invalid_pages:
        _error(await live_client.get(_DOCUMENTS, params=parameters), 400)


@pytest.mark.parametrize("query", ["  документация\n", "ДОКУМЕНТАЦИЯ", "пошук", "RAG_MVP_2026"])
async def test_trimmed_case_and_non_english_search_use_postgres_simple_tokens(
    live_client: httpx.AsyncClient, query: str
) -> None:
    """Whitespace trimming and actual PostgreSQL token rules need no invented stemming."""
    response = await live_client.post(_SEARCH, json=_body(query))
    assert response.status_code == 200
    assert response.json()["results"][0]["source_id"] == "demo-identifiers"


async def test_no_matches_is_a_measured_success(live_client: httpx.AsyncClient) -> None:
    """Zero hits remain a real successful run with no fallback passages."""
    response = await live_client.post(_SEARCH, json=_body("uniquenonexistenttoken2026"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"] == []
    assert payload["status"] == "success"
    assert payload["duration_ms"] >= 0
    assert payload["run_id"]


async def test_publication_hides_superseded_chunks_and_expires_document_cursors(
    live_client: httpx.AsyncClient, corpus_repository: PostgresPersistence
) -> None:
    """Read endpoints follow one complete active version and identify changed corpus snapshots."""
    old_search = (await live_client.post(_SEARCH, json=_body("retention"))).json()
    original = await corpus_repository.get_chunk(_CONTEXT, old_search["results"][0]["chunk_id"])
    assert original is not None
    page = (await live_client.get(_DOCUMENTS, params={"limit": 2})).json()
    source = next(
        item for item in await corpus_repository.list_sources(_CONTEXT) if item.source_id == original.source_id
    )
    version = SourceVersion(
        workspace_id="development", source_id=source.source_id, version_id="replacement-v2", content_hash="replacement"
    )
    replacement = original.model_copy(
        update={"version_id": "replacement-v2", "chunk_id": "replacement-chunk", "content": "replacementuniqueterm"}
    )
    await corpus_repository.publish_source(_CONTEXT, source=source, version=version, chunks=[replacement])
    new_search = (await live_client.post(_SEARCH, json=_body("replacementuniqueterm"))).json()
    assert new_search["results"][0]["source_id"] == original.source_id
    assert new_search["results"][0]["source_version_id"] == "replacement-v2"
    assert new_search["corpus_revision"] != old_search["corpus_revision"]
    assert (await live_client.post(_SEARCH, json=_body("retention"))).json()["results"] == []
    documents = (await live_client.get(_DOCUMENTS)).json()["items"]
    assert (
        next(item for item in documents if item["source_id"] == original.source_id)["active_version_id"]
        == "replacement-v2"
    )
    _error(await live_client.get(_DOCUMENTS, params={"limit": 2, "cursor": page["next_cursor"]}), 400, "INVALID_CURSOR")


async def test_equal_sql_scores_use_chunk_identifier_before_top_k(
    live_client: httpx.AsyncClient, corpus_repository: PostgresPersistence
) -> None:
    """Ties are deterministic over candidates rather than incidental insertion order."""
    for identifier in ["tie-a", "tie_a", "tiea", "tie-A"]:
        source = Source(workspace_id="development", source_id=identifier, title="Tie source")
        version = SourceVersion(workspace_id="development", source_id=identifier, version_id="v1", content_hash="same")
        chunk = Chunk(
            workspace_id="development",
            source_id=identifier,
            version_id="v1",
            chunk_id=identifier,
            title="Tie source",
            content="tiesearchuniqueterm",
            content_hash="same",
        )
        await corpus_repository.publish_source(_CONTEXT, source=source, version=version, chunks=[chunk])
    response = await live_client.post(_SEARCH, json=_body("tiesearchuniqueterm", top_k=4))
    assert response.status_code == 200, response.text
    tied = response.json()["results"]
    one = (await live_client.post(_SEARCH, json=_body("tiesearchuniqueterm", top_k=1))).json()["results"]
    expected = ["tie-A", "tie-a", "tie_a", "tiea"]
    sql_hits = await corpus_repository.lexical_search(_CONTEXT, query="tiesearchuniqueterm", top_k=4)
    assert [hit["chunk_id"] for hit in tied] == expected
    assert [hit.chunk.chunk_id for hit in sql_hits] == expected
    assert len({hit["score"] for hit in tied}) == 1
    assert all(hit["score_type"] == "postgres_ts_rank_cd" for hit in tied)
    assert [hit["score"] for hit in tied] == pytest.approx([hit.score for hit in sql_hits])
    assert one == tied[:1]


@pytest.mark.parametrize(
    "overrides",
    [
        {"query": ""},
        {"query": " \t\n"},
        {"query": True},
        {"query": 123},
        {"query": "a" * 4097},
        {"top_k": True},
        {"top_k": 5.0},
        {"top_k": "5"},
        {"top_k": 0},
        {"top_k": 51},
        {"filters": {"workspace_id": "other-owner"}},
        {"sql": "DROP TABLE workbench.chunks"},
        {"graph": {}},
        {"__proto__": {"admin": True}},
    ],
)
async def test_search_rejects_malformed_or_executable_fields(
    live_client: httpx.AsyncClient, overrides: dict[str, Any]
) -> None:
    """The HTTP body is a strict search request, never a graph or SQL execution envelope."""
    _error(await live_client.post(_SEARCH, json=_body(**overrides)), 400, "INVALID_REQUEST")


@pytest.mark.parametrize(
    "overrides",
    [{"profile_id": "postgres-keyword-v1"}, {"profile_id": "bm25-v1"}, {"expected_profile_revision": "old-revision"}],
)
async def test_unapproved_profiles_and_revision_changes_require_rediscovery(
    live_client: httpx.AsyncClient, overrides: dict[str, Any]
) -> None:
    """Reserved DTO identifiers and stale revisions cannot silently select another executor."""
    _error(await live_client.post(_SEARCH, json=_body(**overrides)), 409, "PROFILE_NOT_AVAILABLE")


async def test_workspace_scope_cannot_be_selected_by_url_or_extra_filter(
    live_client: httpx.AsyncClient, corpus_repository: PostgresPersistence
) -> None:
    """Unknown and foreign workspaces have the same non-enumerating response."""
    foreign = WorkspaceContext(workspace_id="other-owner")
    await corpus_repository.create_workspace(foreign, Workspace(workspace_id="other-owner", name="Foreign owner"))
    source = Source(workspace_id="other-owner", source_id="private-source", title="Private")
    version = SourceVersion(
        workspace_id="other-owner", source_id="private-source", version_id="v1", content_hash="private"
    )
    chunk = Chunk(
        workspace_id="other-owner",
        source_id="private-source",
        version_id="v1",
        chunk_id="private-chunk",
        title="Private",
        content="foreigndocumentsecrettoken",
        content_hash="private",
    )
    await corpus_repository.publish_source(foreign, source=source, version=version, chunks=[chunk])
    for workspace in ["other-owner", "private-source", "does-not-exist"]:
        _error(
            await live_client.post(f"/api/v1/workspaces/{workspace}/search", json=_body()), 404, "WORKSPACE_NOT_FOUND"
        )
        _error(await live_client.get(f"/api/v1/workspaces/{workspace}/documents"), 404, "WORKSPACE_NOT_FOUND")
    _error(await live_client.get(_DOCUMENTS, params={"workspace_id": "other-owner"}), 400, "INVALID_REQUEST")
    assert (await live_client.post(_SEARCH, json=_body("foreigndocumentsecrettoken"))).json()["results"] == []


async def test_transport_and_json_boundaries_are_enforced(live_client: httpx.AsyncClient) -> None:
    """Body limits, media type and ambiguous JSON are rejected before retrieval."""
    _error(
        await live_client.post(_SEARCH, content="{}", headers={"Content-Type": "text/plain"}),
        415,
        "UNSUPPORTED_MEDIA_TYPE",
    )
    _error(
        await live_client.post(_SEARCH, content="{", headers={"Content-Type": "application/json"}), 400, "INVALID_JSON"
    )
    _error(
        await live_client.post(_SEARCH, content=b"\xff", headers={"Content-Type": "application/json"}),
        400,
        "INVALID_JSON",
    )
    _error(
        await live_client.post(
            _SEARCH, content=json.dumps(_body("\ud800")), headers={"Content-Type": "application/json"}
        ),
        400,
        "INVALID_REQUEST",
    )
    _error(
        await live_client.post(
            _SEARCH, content='{"query":"one","query":"two"}', headers={"Content-Type": "application/json"}
        ),
        400,
        "INVALID_JSON",
    )
    _error(
        await live_client.post(_SEARCH, content=b" " * 32769, headers={"Content-Type": "application/json"}),
        413,
        "PAYLOAD_TOO_LARGE",
    )


@pytest.mark.parametrize(
    "corruption",
    ["UPDATE workbench.alembic_version SET version_num='future'", "DROP INDEX workbench.chunks_search_vector"],
)
async def test_schema_or_index_failure_is_not_a_preview_fallback(
    live_client: httpx.AsyncClient,
    disposable_database: DisposableDatabase,
    corruption: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A storage contract failure is a truthful service error without fixture results."""
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(corruption)
    caplog.set_level(logging.INFO)
    private_query = "private-failed-query-sentinel"
    response = await live_client.post(_SEARCH, json=_body(private_query))
    _error(response, 503)
    assert "results" not in response.json()
    assert private_query not in caplog.text + response.text


async def test_search_operational_logs_do_not_capture_private_queries(
    live_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Actual HTTP, pipeline and SQL stages retain correlation without request contents."""
    caplog.set_level(logging.INFO)
    secret = "private-query-sentinel-2026"
    response = await live_client.post(_SEARCH, json=_body(secret), headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if record.name.startswith("workbench")]
    assert messages
    assert secret not in "\n".join(messages)


async def test_two_search_slots_are_released_only_after_cancellation_cleanup(
    live_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third search is busy while two execute; cancellation frees a usable owned slot."""
    from apps.workbench.retrieval.lexical import LexicalService

    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    original = LexicalService.search

    async def gated(service: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
        await release.wait()
        return await original(service, *args, **kwargs)

    monkeypatch.setattr(LexicalService, "search", gated)
    first = asyncio.create_task(live_client.post(_SEARCH, json=_body()))
    second = asyncio.create_task(live_client.post(_SEARCH, json=_body("cosine")))
    await asyncio.wait_for(entered.wait(), timeout=2)
    busy = await live_client.post(_SEARCH, json=_body())
    _error(busy, 429, "SEARCH_BUSY")
    assert busy.headers["retry-after"]
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert (await second).status_code == 200
    assert (await live_client.post(_SEARCH, json=_body())).status_code == 200


async def test_search_deadline_cancels_work_and_preserves_next_request(
    live_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeout produces a real failed run and waits for owned task cleanup before reuse."""
    from apps.workbench.retrieval.lexical import LexicalService

    original = LexicalService.search
    cancelled: list[bool] = []

    async def blocked(_service: Any, *_args: Any, **_kwargs: Any) -> Any:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(application_module, "_SEARCH_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(LexicalService, "search", blocked)
    failure = await live_client.post(_SEARCH, json=_body())
    payload = _error(failure, 504, "SEARCH_TIMEOUT")
    assert payload["error"]["run_id"]
    assert cancelled == [True]
    monkeypatch.setattr(LexicalService, "search", original)
    monkeypatch.setattr(application_module, "_SEARCH_TIMEOUT_SECONDS", 10.0)
    assert (await live_client.post(_SEARCH, json=_body())).status_code == 200


async def test_api_startup_does_not_seed_an_empty_database(disposable_database: DisposableDatabase) -> None:
    """HTTP composition never creates migrations, seed records or an in-memory fallback."""
    migrate(disposable_database.admin_dsn)
    repository = PostgresPersistence(disposable_database.app_dsn)
    app = create_app(settings=ApiSettings(), persistence=repository)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        assert (await client.get("/api/v1/health/live")).status_code == 200
        assert (await client.get("/api/v1/health/ready")).status_code == 503
        assert (await client.get("/api/v1/capabilities")).json()["profiles"] == []
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.workspaces").fetchone() == (0,)


async def test_late_completed_search_cannot_succeed_after_application_shutdown(
    corpus_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real result already read from SQL cannot become a false success after shutdown."""
    from apps.workbench.retrieval.lexical import LexicalService

    original = LexicalService.search
    entered = asyncio.Event()
    release = asyncio.Event()

    async def late(service: Any, *args: Any, **kwargs: Any) -> Any:
        result = await original(service, *args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(LexicalService, "search", late)
    app = create_app(settings=ApiSettings(), persistence=corpus_repository)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client:
        async with app.router.lifespan_context(app):
            pending = asyncio.create_task(client.post(_SEARCH, json=_body()))
            await asyncio.wait_for(entered.wait(), timeout=2)
        release.set()
        response = await pending
        _error(response, 503)
        assert "results" not in response.json()

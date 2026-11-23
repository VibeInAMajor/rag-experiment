"""Profile admission stays separate from retrieval and uses real workspace-scoped PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
import psycopg
import pytest
import pytest_asyncio
from psycopg import AsyncConnection

from apps.workbench.api.application import create_app
from apps.workbench.api.config import ApiSettings
from apps.workbench.api.lexical import LexicalService
from apps.workbench.api.persistence import (
    Chunk,
    CorpusNotReady,
    LexicalSearchSnapshot,
    Source,
    SourceVersion,
    WorkspaceContext,
)
from apps.workbench.api.postgres import PostgresPersistence
from apps.workbench.api.postgres_profiles import promote_profile, sync_registry, transition_profile
from apps.workbench.api.profile_registry import (
    ProfileDefinition,
    ProfileRegistry,
    ProfileRollout,
    default_profile_registry,
)
from apps.workbench.api.tests.conftest import DisposableDatabase
from apps.workbench.api.tests.test_lexical_routes import corpus_repository as corpus_repository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="function")]
_SEARCH = "/api/v1/workspaces/development/search"
_PROFILE = "postgres-fts-baseline"
_REVISION = "postgres-fts-baseline-r1"


@pytest_asyncio.fixture(loop_scope="function")
async def live_client(corpus_repository: PostgresPersistence) -> AsyncIterator[httpx.AsyncClient]:
    """Use real application lifespan without a route-specific schema hook from another suite."""
    app = create_app(settings=ApiSettings(), persistence=corpus_repository)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        yield client


@asynccontextmanager
async def _profile_client(
    repository: PostgresPersistence, registry: ProfileRegistry
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings=ApiSettings(), persistence=repository, registry=registry)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        yield client


def _definition(
    profile_id: str = "postgres-fts-limited", revision: str = "limited-r1", **changes: Any
) -> ProfileDefinition:
    baseline = default_profile_registry().profiles[0]
    return ProfileDefinition.model_validate(
        {
            **baseline.model_dump(),
            "profile_id": profile_id,
            "profile_revision": revision,
            "label": "Limited keyword search",
            **changes,
        }
    )


def _registry(*definitions: ProfileDefinition) -> ProfileRegistry:
    return ProfileRegistry(profiles=(*default_profile_registry().profiles, *definitions))


async def _transition(
    database: DisposableDatabase,
    definition: ProfileDefinition,
    state: Literal["draft", "qualified", "active", "retired"],
    *,
    expected: int | None = None,
) -> ProfileRollout:
    return await asyncio.to_thread(
        transition_profile,
        database.admin_dsn,
        workspace_id="development",
        profile_id=definition.profile_id,
        profile_revision=definition.profile_revision,
        state=state,
        expected_rollout_version=expected,
    )


async def _activate(database: DisposableDatabase, definition: ProfileDefinition) -> ProfileRollout:
    qualified = await _transition(database, definition, "qualified")
    return await _transition(database, definition, "active", expected=qualified.rollout_version)


async def _publish_extra(repository: PostgresPersistence) -> None:
    context = WorkspaceContext(workspace_id="development")
    source = Source(workspace_id="development", source_id="new-source", title="New source")
    version = SourceVersion(
        workspace_id="development", source_id=source.source_id, version_id="new-version", content_hash="new"
    )
    chunk = Chunk(
        workspace_id="development",
        source_id=source.source_id,
        version_id=version.version_id,
        chunk_id="new-chunk",
        title=source.title,
        content="Additional PostgreSQL passage",
        content_hash="new",
    )
    await repository.publish_source(context, source=source, version=version, chunks=[chunk])


def _body(**overrides: Any) -> dict[str, Any]:
    return {
        "query": "PostgreSQL",
        "top_k": 5,
        "profile_id": _PROFILE,
        "expected_profile_revision": _REVISION,
        **overrides,
    }


def _forbid_persistence(repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Pure profile preflight touched persistence")

    for name in ("get_profile_rollouts", "corpus_summary", "current_index_generation", "lexical_search_snapshot"):
        if hasattr(repository, name):
            monkeypatch.setattr(repository, name, forbidden)


@pytest.mark.parametrize(
    "change",
    [
        {"profile_id": "unregistered-profile"},
        {"profile_id": "dense-not-installed"},
        {"profile_id": "hybrid-rrf-not-installed"},
        {"profile_id": "bm25-v1"},
        {"expected_profile_revision": "unknown-revision"},
    ],
)
async def test_unknown_profile_or_configured_revision_refuses_before_any_persistence(
    live_client: httpx.AsyncClient,
    corpus_repository: PostgresPersistence,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, str],
) -> None:
    """Unregistered identities cannot acquire readiness through an expensive dependency probe."""
    _forbid_persistence(corpus_repository, monkeypatch)
    response = await live_client.post(_SEARCH, json=_body(**change))
    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "PROFILE_NOT_AVAILABLE"
    assert payload["error"]["http_status"] == 409
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["trace_id"] and "results" not in payload


@pytest.mark.parametrize("change", [{"top_k": 51}, {"top_k": 0}, {"candidate_k": 50}, {"graph": {}}])
async def test_request_bounds_and_executable_fields_fail_before_profile_lookup(
    live_client: httpx.AsyncClient,
    corpus_repository: PostgresPersistence,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
) -> None:
    """The four-field request never accepts candidate policy or executable graph input."""
    _forbid_persistence(corpus_repository, monkeypatch)
    response = await live_client.post(_SEARCH, json=_body(**change))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


async def test_foreign_workspace_fails_before_profile_or_corpus_lookup(
    live_client: httpx.AsyncClient, corpus_repository: PostgresPersistence, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured profile cannot authorize an otherwise unavailable workspace."""
    _forbid_persistence(corpus_repository, monkeypatch)
    response = await live_client.post("/api/v1/workspaces/foreign/search", json=_body())
    assert response.status_code == 404
    assert response.json()["error"]["http_status"] == 404


async def test_default_profile_preserves_lexical_descriptor_and_score_contract(live_client: httpx.AsyncClient) -> None:
    """The registry does not rename the approved baseline or fabricate semantic score types."""
    capabilities = (await live_client.get("/api/v1/capabilities")).json()
    assert len(capabilities["profiles"]) == 1
    profile = capabilities["profiles"][0]
    assert set(profile) == {
        "profile_id",
        "profile_revision",
        "kind",
        "workspace_ids",
        "corpus_id",
        "parameters",
        "limits",
        "score_type",
    }
    assert profile["profile_id"] == _PROFILE
    assert profile["profile_revision"] == _REVISION
    assert profile["kind"] == "lexical_search"
    assert profile["score_type"] == "postgres_ts_rank_cd"
    assert profile["parameters"]["top_k"]["maximum"] == 50
    response = await live_client.post(_SEARCH, json=_body())
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "contract_revision",
        "request_id",
        "trace_id",
        "mode",
        "workspace_id",
        "corpus_revision",
        "profile_id",
        "profile_revision",
        "run_id",
        "status",
        "duration_ms",
        "stages",
        "results",
    }
    assert payload["profile_id"] == _PROFILE and payload["profile_revision"] == _REVISION
    assert payload["corpus_revision"]
    assert payload["results"]
    assert all(result["score_type"] == "postgres_ts_rank_cd" for result in payload["results"])


async def test_profile_lifecycle_advertises_only_active_qualified_policy(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored draft/qualified/retired definitions never become executable capabilities."""
    definition = _definition(max_top_k=3, candidate_k=5)
    registry = _registry(definition)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    request = _body(profile_id=definition.profile_id, expected_profile_revision=definition.profile_revision, top_k=3)
    async with _profile_client(corpus_repository, registry) as client:
        original = corpus_repository.lexical_search_snapshot

        async def no_retrieval(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("An inactive policy reached retrieval")

        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", no_retrieval)
        for state in ("draft", "qualified", "retired"):
            await _transition(disposable_database, definition, state)
            response = await client.post(_SEARCH, json=request)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "PROFILE_NOT_AVAILABLE"
            capabilities = (await client.get("/api/v1/capabilities")).json()
            assert [item["profile_id"] for item in capabilities["profiles"]] == [_PROFILE]
        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", original)
        await _activate(disposable_database, definition)
        capabilities = (await client.get("/api/v1/capabilities")).json()
        approved = next(item for item in capabilities["profiles"] if item["profile_id"] == definition.profile_id)
        assert approved["parameters"]["top_k"]["maximum"] == 3
        response = await client.post(_SEARCH, json=request)
        assert response.status_code == 200
        assert response.json()["profile_id"] == definition.profile_id
        assert response.json()["profile_revision"] == definition.profile_revision


async def test_revision_swap_and_explicit_rollback_preserve_real_results(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A durable revision swap invalidates old requests and rollback restores the original policy identity."""
    baseline = default_profile_registry().profiles[0]
    replacement = _definition(profile_id=_PROFILE, revision="postgres-fts-baseline-r2", max_top_k=3, candidate_k=5)
    registry = _registry(replacement)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    async with _profile_client(corpus_repository, registry) as client:
        before = (await client.post(_SEARCH, json=_body(top_k=3))).json()
        assert before["results"]
        active = await _activate(disposable_database, replacement)
        assert active.profile_revision == replacement.profile_revision
        old = await client.post(_SEARCH, json=_body(top_k=3))
        assert old.status_code == 409
        current = await client.post(
            _SEARCH, json=_body(top_k=3, expected_profile_revision=replacement.profile_revision)
        )
        assert current.status_code == 200
        assert current.json()["profile_revision"] == replacement.profile_revision
        assert current.json()["results"] == before["results"]
        with monkeypatch.context() as policy_guard:
            _forbid_persistence(corpus_repository, policy_guard)
            oversized = await client.post(
                _SEARCH, json=_body(top_k=4, expected_profile_revision=replacement.profile_revision)
            )
            assert oversized.status_code == 400
        restored = await _activate(disposable_database, baseline)
        assert restored.rollout_version > active.rollout_version
        after = await client.post(_SEARCH, json=_body(top_k=3))
        assert after.status_code == 200
        assert after.json()["profile_revision"] == _REVISION
        assert after.json()["corpus_revision"] == before["corpus_revision"]
        assert after.json()["results"] == before["results"]
        stale = await client.post(_SEARCH, json=_body(top_k=3, expected_profile_revision=replacement.profile_revision))
        assert stale.status_code == 409


async def test_retirement_between_admission_and_sql_rejects_stale_fence(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retrieval transaction checks the exact rollout admitted by application policy."""
    definition = default_profile_registry().profiles[0]
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = corpus_repository.lexical_search_snapshot

    async def delayed(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        await asyncio.wait_for(proceed.wait(), timeout=10)
        return await original(*args, **kwargs)

    async with _profile_client(corpus_repository, default_profile_registry()) as client:
        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", delayed)
        search = asyncio.create_task(client.post(_SEARCH, json=_body()))
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            await _transition(disposable_database, definition, "retired")
        finally:
            proceed.set()
        response = await asyncio.wait_for(search, timeout=10)
        assert response.status_code == 409
        assert "results" not in response.json()


async def test_current_corpus_admission_is_rechecked_after_publication(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A previously qualified tighter corpus cap cannot silently execute after source generation growth."""
    definition = _definition(max_corpus_chunks=8)
    registry = _registry(definition)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    await _activate(disposable_database, definition)
    await _publish_extra(corpus_repository)
    async with _profile_client(corpus_repository, registry) as client:

        async def no_retrieval(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("A profile whose corpus admission failed reached retrieval")

        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", no_retrieval)
        response = await client.post(
            _SEARCH, json=_body(profile_id=definition.profile_id, expected_profile_revision=definition.profile_revision)
        )
        assert response.status_code == 503
        capabilities = (await client.get("/api/v1/capabilities")).json()
        assert [item["profile_id"] for item in capabilities["profiles"]] == [_PROFILE]


@pytest.mark.parametrize("dependency", ["embedding_coverage", "ann_index", "bm25_index", "capacity_policy"])
async def test_forged_active_state_cannot_qualify_missing_dependencies(
    corpus_repository: PostgresPersistence,
    disposable_database: DisposableDatabase,
    monkeypatch: pytest.MonkeyPatch,
    dependency: str,
) -> None:
    """Even an administrator-written active flag is insufficient without actual capability proof."""
    definition = _definition(capability_requirements=("schema", "source_generation", "lexical_index", dependency))
    registry = _registry(definition)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    with pytest.raises(CorpusNotReady):
        await _transition(disposable_database, definition, "qualified")
    draft = await _transition(disposable_database, definition, "draft")
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        connection.execute(
            "UPDATE workbench.retrieval_profile_rollouts SET state='active',rollout_version=rollout_version+1,"
            "qualified_generation_id=(SELECT generation_id FROM workbench.corpus_index_state "
            "WHERE workspace_id='development') WHERE workspace_id='development' AND profile_id=%s",
            (definition.profile_id,),
        )
    assert draft.state == "draft"
    async with _profile_client(corpus_repository, registry) as client:

        async def no_retrieval(*_args: Any, **_kwargs: Any) -> Any:
            pytest.fail("Unproven dependencies reached retrieval")

        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", no_retrieval)
        response = await client.post(
            _SEARCH, json=_body(profile_id=definition.profile_id, expected_profile_revision=definition.profile_revision)
        )
        assert response.status_code == 503
        capabilities = (await client.get("/api/v1/capabilities")).json()
        assert [item["profile_id"] for item in capabilities["profiles"]] == [_PROFILE]


async def test_source_growth_after_admission_is_rejected_before_candidate_sql(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same-snapshot policy check blocks corpus growth before any ranking query executes."""
    definition = _definition(max_corpus_chunks=8)
    registry = _registry(definition)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    await _activate(disposable_database, definition)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original_search = corpus_repository.lexical_search_snapshot
    original_execute = AsyncConnection.execute
    ranking_queries: list[bool] = []

    async def delayed(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        await asyncio.wait_for(proceed.wait(), timeout=10)
        return await original_search(*args, **kwargs)

    async def observe(connection: AsyncConnection[Any], query: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(query, str) and "ts_rank_cd(c.search_vector" in query:
            ranking_queries.append(True)
        return await original_execute(connection, query, *args, **kwargs)

    async with _profile_client(corpus_repository, registry) as client:
        monkeypatch.setattr(corpus_repository, "lexical_search_snapshot", delayed)
        monkeypatch.setattr(AsyncConnection, "execute", observe)
        pending = asyncio.create_task(
            client.post(
                _SEARCH,
                json=_body(profile_id=definition.profile_id, expected_profile_revision=definition.profile_revision),
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            await _publish_extra(corpus_repository)
        finally:
            proceed.set()
        response = await asyncio.wait_for(pending, timeout=10)
        assert response.status_code == 503
        assert ranking_queries == []
        assert "results" not in response.json()


async def test_atomic_promotion_failure_preserves_previous_rollout_and_audit(
    corpus_repository: PostgresPersistence, disposable_database: DisposableDatabase
) -> None:
    """A failed activation cannot leave a new qualified revision or partial audit history committed."""
    replacement = _definition(profile_id=_PROFILE, revision="postgres-fts-baseline-r2")
    registry = _registry(replacement)
    await asyncio.to_thread(sync_registry, disposable_database.admin_dsn, registry)
    context = WorkspaceContext(workspace_id="development")
    before = await corpus_repository.get_profile_rollouts(context)
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        audit_count = connection.execute("SELECT count(*) FROM workbench.profile_rollout_events").fetchone()
        connection.execute(
            "CREATE FUNCTION workbench.reject_profile_activation() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.profile_revision='postgres-fts-baseline-r2' AND NEW.state='active' THEN "
            "RAISE EXCEPTION 'intentional activation failure'; END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER reject_profile_activation BEFORE UPDATE ON workbench.retrieval_profile_rollouts "
            "FOR EACH ROW EXECUTE FUNCTION workbench.reject_profile_activation()"
        )
    with pytest.raises(psycopg.errors.RaiseException):
        await asyncio.to_thread(
            promote_profile,
            disposable_database.admin_dsn,
            workspace_id="development",
            profile_id=_PROFILE,
            profile_revision=replacement.profile_revision,
            expected_rollout_version=before[0].rollout_version,
        )
    assert await corpus_repository.get_profile_rollouts(context) == before
    with psycopg.connect(disposable_database.admin_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM workbench.profile_rollout_events").fetchone() == audit_count
    async with _profile_client(corpus_repository, registry) as client:
        response = await client.post(_SEARCH, json=_body())
        assert response.status_code == 200 and response.json()["profile_revision"] == _REVISION


@pytest.mark.parametrize(
    "altered",
    [
        {"profile_revision": "different-revision"},
        {"profile_id": "different-profile"},
        {"profile_id": None, "profile_revision": None, "policy_hash": None},
    ],
)
async def test_provider_result_cannot_be_attributed_to_another_or_missing_policy(
    live_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, altered: dict[str, Any]
) -> None:
    """Projection refuses missing or mismatched policy provenance instead of relabeling results."""
    original = LexicalService.search

    async def altered_result(service: LexicalService, *args: Any, **kwargs: Any) -> LexicalSearchSnapshot:
        result = await original(service, *args, **kwargs)
        return result.model_copy(update=altered)

    monkeypatch.setattr(LexicalService, "search", altered_result)
    response = await live_client.post(_SEARCH, json=_body())
    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "results" not in payload

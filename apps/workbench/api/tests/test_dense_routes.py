"""Fake-provider HTTP contract tests; these establish no model quality or performance claim."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import create_autospec

import httpx
import pytest
import pytest_asyncio

from apps.workbench.api.application import create_app
from apps.workbench.configuration.config import ApiSettings
from apps.workbench.embedding.embedding import (
    EmbeddingBatch,
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.embedding.embedding_jobs import EmbeddingCoverage
from apps.workbench.persistence.models import (
    Chunk,
    CorpusNotReady,
    CorpusSnapshot,
    DatabaseUnavailable,
    PersistenceReady,
    VectorHit,
    VectorSearchSnapshot,
)
from apps.workbench.retrieval.dense import DensePersistencePort, DenseService
from apps.workbench.retrieval.profile_registry import ProfileRegistry, ProfileRollout, default_profile_registry
from apps.workbench.retrieval.profiles import dense_profile_definition

pytestmark = pytest.mark.asyncio(loop_scope="function")
_SEARCH = "/api/v1/workspaces/development/search"


class _Counter:
    counter_revision = "dense-test-tokenizer"

    def count_tokens(self, text: str) -> int:
        return len(text.split())


_PROFILE = EmbeddingProfile(
    profile_id="dense-test-model",
    profile_revision="dense-test-model-r1",
    provider_adapter_id="tei-openai",
    model_id="fake-unit-model",
    model_revision="a" * 40,
    model_digest="b" * 64,
    tokenizer_digest="c" * 64,
    tokenizer_revision=_Counter.counter_revision,
    dimensions=32,
)
_DEFINITION = dense_profile_definition(_PROFILE, capacity_policy_id="test-capacity")
_ROLLOUT = ProfileRollout(
    workspace_id="development",
    profile_id=_DEFINITION.profile_id,
    profile_revision=_DEFINITION.profile_revision,
    state="active",
    policy_hash=_DEFINITION.policy_hash,
    rollout_version=1,
    qualified_generation_id=7,
)


class _Provider:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []
        self.error: EmbeddingErrorCode | None = None
        self.embed_error: EmbeddingErrorCode | None = None
        self.mutation: dict[str, Any] = {}
        self.block = False
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def warm_up_async(self) -> None:
        """Represent explicit fake provider readiness."""
        if self.error is not None:
            raise EmbeddingError(self.error)

    async def close_async(self) -> None:
        """The fake owns no external resources."""

    async def embed(self, request: EmbeddingRequest) -> EmbeddingBatch:
        """Return deterministic vectors solely to test the HTTP/provenance boundary."""
        self.requests.append(request)
        self.entered.set()
        if self.embed_error is not None:
            raise EmbeddingError(self.embed_error)
        if self.block:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        if self.error is not None:
            raise EmbeddingError(self.error)
        prepared = prepare_embedding_request(_PROFILE, request, _Counter())
        result = validate_embedding_batch(
            _PROFILE,
            request,
            prepared,
            vectors=((1.0,) + (0.0,) * 31,),
            usage_tokens=sum(item.token_count for item in prepared),
            usage_provenance="tokenizer_counted_proxy",
            duration_ms=0.0,
        )
        return result.model_copy(update=self.mutation)


def _repository() -> Any:
    repository = create_autospec(DensePersistencePort, instance=True)
    repository.readiness.return_value = PersistenceReady(
        schema_revision="0005", workspace_id="development", source_count=1, chunk_count=2
    )
    repository.ingestion_ready.return_value = False
    repository.get_profile_rollouts.return_value = (_ROLLOUT,)
    repository.corpus_summary.return_value = CorpusSnapshot(
        corpus_revision="generation-7", documents=[], chunk_count=2, content_bytes=20, index_generation_id=7
    )
    repository.embedding_coverage.return_value = EmbeddingCoverage(
        workspace_id="development",
        profile_id=_PROFILE.profile_id,
        profile_revision=_PROFILE.profile_revision,
        profile_fingerprint=_PROFILE.fingerprint,
        index_generation=7,
        eligible_active_chunks=2,
        ready_embeddings=2,
        stale_embeddings=0,
        coverage_fraction=1.0,
        ready=True,
    )
    repository.vector_search_snapshot.return_value = VectorSearchSnapshot(
        corpus_revision="generation-7",
        index_generation_id=7,
        embedding_profile_revision=_PROFILE.profile_revision,
        embedding_profile_fingerprint=_PROFILE.fingerprint,
        chunk_count=2,
        content_bytes=20,
        corpus_load_duration_ms=0.0,
        retrieval_duration_ms=0.0,
        hits=[
            VectorHit(
                chunk=Chunk(
                    workspace_id="development",
                    source_id="source",
                    version_id="version",
                    chunk_id=f"chunk-{rank}",
                    title="Evidence",
                    content="Persisted passage",
                    content_hash="test-content-hash",
                ),
                rank=rank,
                distance=distance,
            )
            for rank, distance in ((1, 0.1), (2, 0.5))
        ],
    )
    return repository


@pytest_asyncio.fixture(loop_scope="function")
async def dense_client() -> AsyncIterator[tuple[httpx.AsyncClient, Any, _Provider]]:
    """Exercise actual HTTP policy, Haystack orchestration and response projection."""
    repository, provider = _repository(), _Provider()
    registry = ProfileRegistry(profiles=(*default_profile_registry().profiles, _DEFINITION))
    service = DenseService(
        repository,
        embedding=provider,
        profile=_PROFILE,
        counter=_Counter(),
        registry=registry,
        readiness=provider.warm_up_async,
        capacity_policy_id="test-capacity",
    )
    app = create_app(settings=ApiSettings(), persistence=repository, registry=registry, dense=service)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        yield client, repository, provider


def _body(**changes: Any) -> dict[str, Any]:
    return dict(
        query="relevant passage",
        top_k=2,
        profile_id=_DEFINITION.profile_id,
        expected_profile_revision=_DEFINITION.profile_revision,
        **changes,
    )


async def test_dense_distances_provenance_and_exclusive_measured_stages(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider],
) -> None:
    """Lower distance is better; PostgreSQL IDs and server stage timestamps survive projection."""
    client, repository, provider = dense_client
    response = await client.post(_SEARCH, json=_body(), headers={"X-Trace-ID": "dense-safe-trace"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["score"] for item in payload["results"]] == [0.1, 0.5]
    assert all(item["score_type"] == "cosine_distance" for item in payload["results"])
    assert payload["results"][0]["source_version_id"] == "version"
    assert "page" not in payload["results"][0]
    assert payload["index_generation"] == 7
    assert payload["model_digest"] == _PROFILE.model_digest
    assert payload["trace_id"] == provider.requests[0].trace_id
    assert payload["request_id"] == response.headers["x-request-id"]
    assert [stage["stage"] for stage in payload["stages"]] == ["query_embedding", "vector_search", "projection"]
    assert all(stage["started_at"] <= stage["finished_at"] for stage in payload["stages"])
    assert sum(stage["duration_ms"] for stage in payload["stages"]) <= payload["duration_ms"]
    assert provider.requests[0].task_kind == "query"
    repository.vector_search_snapshot.assert_awaited_once()


@pytest.mark.parametrize(
    "mutation",
    [
        {"vectors": ((1.0,),)},
        {"model_digest": "0" * 64},
        {"input_hashes": ("0" * 64,)},
        {"vectors": ((float("nan"),) * 32,)},
    ],
)
async def test_invalid_provider_output_never_reaches_sql(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider], mutation: dict[str, Any]
) -> None:
    """Wrong dimensions, identity, input policy and nonfinite vectors are unavailable."""
    client, repository, provider = dense_client
    provider.mutation = mutation
    response = await client.post(_SEARCH, json=_body())
    assert response.status_code == 503, response.text
    repository.vector_search_snapshot.assert_not_awaited()


@pytest.mark.parametrize(
    "code,status",
    [
        (EmbeddingErrorCode.RATE_LIMITED, 429),
        (EmbeddingErrorCode.MODEL_UNAVAILABLE, 503),
        (EmbeddingErrorCode.TIMEOUT, 504),
    ],
)
async def test_model_failures_are_explicit_without_preview(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider], code: EmbeddingErrorCode, status: int
) -> None:
    """Provider failures never return empty success or synthetic data."""
    client, repository, provider = dense_client
    provider.error = code
    response = await client.post(_SEARCH, json=_body())
    assert response.status_code == status
    assert response.json()["error"]["code"] == code.value
    assert "results" not in response.json()
    repository.vector_search_snapshot.assert_not_awaited()
    capability = await client.get("/api/v1/capabilities")
    assert not any(item["kind"] == "dense_search" for item in capability.json()["profiles"])


@pytest.mark.parametrize(
    "code,status",
    [
        (EmbeddingErrorCode.RATE_LIMITED, 429),
        (EmbeddingErrorCode.MODEL_UNAVAILABLE, 503),
        (EmbeddingErrorCode.TIMEOUT, 504),
    ],
)
async def test_provider_refusal_during_query_preserves_error_and_trace(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider], code: EmbeddingErrorCode, status: int
) -> None:
    """A readiness success cannot mask a subsequent transport or admission refusal."""
    client, repository, provider = dense_client
    provider.embed_error = code
    response = await client.post(_SEARCH, json=_body())
    payload = response.json()
    assert response.status_code == status
    assert payload["error"]["code"] == code.value
    assert payload["trace_id"] == provider.requests[0].trace_id
    assert payload["error"]["run_id"]
    repository.vector_search_snapshot.assert_not_awaited()


@pytest.mark.parametrize("error", [CorpusNotReady("changed generation"), DatabaseUnavailable("private details")])
async def test_sql_drift_and_dependency_failures_are_safe(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider], error: Exception
) -> None:
    """The final SQL fence refuses publication/DB failures after actual query embedding."""
    client, repository, provider = dense_client
    repository.vector_search_snapshot.side_effect = error
    response = await client.post(_SEARCH, json=_body())
    assert response.status_code == 503
    assert provider.requests
    assert str(error) not in response.text


async def test_partial_coverage_and_revision_denial_precede_model(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider],
) -> None:
    """No partial generation or browser-selected model/vector is executable."""
    client, repository, provider = dense_client
    repository.embedding_coverage.return_value = repository.embedding_coverage.return_value.model_copy(
        update={"ready": False}
    )
    assert (await client.post(_SEARCH, json=_body())).status_code == 503
    bad_revision = _body()
    bad_revision["expected_profile_revision"] = "wrong"
    assert (await client.post(_SEARCH, json=bad_revision)).status_code == 409
    assert (await client.post(_SEARCH, json={**_body(), "embedding": [1.0]})).status_code == 400
    assert (await client.post(_SEARCH.replace("development", "denied"), json=_body())).status_code == 404
    assert not provider.requests
    repository.vector_search_snapshot.assert_not_awaited()


async def test_cancellation_releases_model_before_next_search(
    dense_client: tuple[httpx.AsyncClient, Any, _Provider],
) -> None:
    """Cancellation propagates through Haystack to the model without late result projection."""
    client, repository, provider = dense_client
    provider.block = True
    request = asyncio.create_task(client.post(_SEARCH, json=_body()))
    await asyncio.wait_for(provider.entered.wait(), timeout=3)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    await asyncio.wait_for(provider.cancelled.wait(), timeout=3)
    repository.vector_search_snapshot.assert_not_awaited()
    provider.block = False
    assert (await client.post(_SEARCH, json=_body())).status_code == 200


async def test_approved_dense_revision_dispatches_by_composition() -> None:
    """An operator-approved exact policy uses dense execution independently of its label identity."""
    definition = _DEFINITION.model_copy(update={"profile_id": "alternate-exact", "profile_revision": "alternate-r1"})
    registry = ProfileRegistry(profiles=(definition,))
    repository, provider = _repository(), _Provider()
    repository.get_profile_rollouts.return_value = (
        _ROLLOUT.model_copy(
            update={
                "profile_id": definition.profile_id,
                "profile_revision": definition.profile_revision,
                "policy_hash": definition.policy_hash,
            }
        ),
    )
    service = DenseService(
        repository,
        embedding=provider,
        profile=_PROFILE,
        counter=_Counter(),
        registry=registry,
        readiness=provider.warm_up_async,
        capacity_policy_id="test-capacity",
    )
    app = create_app(settings=ApiSettings(), persistence=repository, registry=registry, dense=service)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8011") as client,
    ):
        response = await client.post(
            _SEARCH,
            json={
                **_body(),
                "profile_id": definition.profile_id,
                "expected_profile_revision": definition.profile_revision,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["profile_id"] == definition.profile_id
    assert all(hit["score_type"] == "cosine_distance" for hit in response.json()["results"])
    assert len(provider.requests) == 1

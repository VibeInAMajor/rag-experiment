"""Approved exact dense retrieval through the shared embedding owner and PostgreSQL."""

import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol

from pydantic import Field

from apps.workbench.chunking.chunking import ExactModelCounter
from apps.workbench.contracts.schemas import ExecutionProfile, StageTiming
from apps.workbench.embedding.embedding import (
    EmbeddingError,
    EmbeddingErrorCode,
    EmbeddingItem,
    EmbeddingPort,
    EmbeddingProfile,
    EmbeddingRequest,
    prepare_embedding_request,
    validate_embedding_batch,
)
from apps.workbench.embedding.embedding_jobs import EmbeddingPersistencePort
from apps.workbench.persistence.models import (
    CorpusNotReady,
    CorpusSnapshot,
    DatabaseUnavailable,
    PersistenceError,
    PersistencePort,
    VectorSearchSnapshot,
    WorkspaceContext,
)
from apps.workbench.retrieval.profile_registry import ProfileDefinition, ProfileRegistry, ProfileRollout
from apps.workbench.retrieval.profiles import (
    active_profile_rollout,
    execution_profile,
    resolve_profile,
    validate_dense_policy,
    validate_search_policy,
)
from apps.workbench.retrieval.services import ReadinessSnapshot
from haystack import Pipeline, component
from haystack.core.errors import PipelineRuntimeError
from haystack.tracing import disable_tracing


class DensePersistencePort(PersistencePort, EmbeddingPersistencePort, Protocol):
    """The existing persistence adapter implements both retrieval and embedding coverage."""


class QueryEmbedding(CorpusSnapshot):
    """A validated internal query vector pinned to a complete corpus generation."""

    vector: tuple[float, ...] = Field(repr=False)
    timing: StageTiming


class DenseSearchResult(VectorSearchSnapshot):
    """Server-only measured execution metadata accompanying a certified SQL snapshot."""

    profile_id: str
    profile_revision: str
    policy_hash: str
    embedding_profile: EmbeddingProfile = Field(repr=False)
    stages: list[StageTiming]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@component
class QueryEmbedder:
    """Use the same instruction, native tokenizer and shared admission as document embedding."""

    def __init__(self, embedding: EmbeddingPort, *, profile: EmbeddingProfile, counter: ExactModelCounter) -> None:
        self._embedding = embedding
        self._profile = profile
        self._counter = counter

    @component.output_types(query_embedding=QueryEmbedding)
    def run(
        self,
        context: WorkspaceContext,  # noqa: ARG002
        query: str,  # noqa: ARG002
        corpus: CorpusSnapshot,  # noqa: ARG002
    ) -> dict[str, QueryEmbedding]:
        """Require the async pipeline for local provider I/O."""
        raise RuntimeError("Use Pipeline.run_async() for query embedding.")

    @component.output_types(query_embedding=QueryEmbedding)
    async def run_async(
        self, context: WorkspaceContext, query: str, corpus: CorpusSnapshot
    ) -> dict[str, QueryEmbedding]:
        """Validate identity, transformed input and finite normalized dimensions before SQL."""
        started, started_at = monotonic(), _now()
        request = EmbeddingRequest(
            profile_id=self._profile.profile_id,
            profile_revision=self._profile.profile_revision,
            task_kind="query",
            items=(EmbeddingItem(item_id="query", text=query, input_hash=hashlib.sha256(query.encode()).hexdigest()),),
            deadline=started + self._profile.timeout_seconds,
            workspace_id=context.workspace_id,
            trace_id=context.trace_id or "dense-query",
        )
        prepared = prepare_embedding_request(self._profile, request, self._counter)
        output = await self._embedding.embed(request)
        checked = validate_embedding_batch(
            self._profile,
            request,
            prepared,
            vectors=output.vectors,
            usage_tokens=output.usage_tokens,
            usage_provenance=output.usage_provenance,
            duration_ms=output.duration_ms,
        )
        # Provider-neutral ports are untrusted too: validate the full identity and exact transformed input.
        if output != checked:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_RESPONSE)
        timing = StageTiming(
            stage="query_embedding",
            duration_ms=(monotonic() - started) * 1000,
            started_at=started_at,
            finished_at=_now(),
        )
        return {"query_embedding": QueryEmbedding(**corpus.model_dump(), vector=checked.vectors[0], timing=timing)}


@component
class PostgresDenseRetriever:
    """Execute exact cosine against the same fenced durable PostgreSQL embedding generation."""

    def __init__(
        self,
        repository: DensePersistencePort,
        *,
        profile: EmbeddingProfile,
        definition: ProfileDefinition,
        rollout: ProfileRollout,
    ) -> None:
        self._repository, self._profile = repository, profile
        self._definition, self._rollout = definition, rollout

    @component.output_types(snapshot=DenseSearchResult)
    def run(
        self,
        context: WorkspaceContext,  # noqa: ARG002
        query_embedding: QueryEmbedding,  # noqa: ARG002
        *,
        top_k: int = 10,  # noqa: ARG002
    ) -> dict[str, DenseSearchResult]:
        """Require async execution to propagate SQL cancellation."""
        raise RuntimeError("Use Pipeline.run_async() for dense retrieval.")

    @component.output_types(snapshot=DenseSearchResult)
    async def run_async(
        self, context: WorkspaceContext, query_embedding: QueryEmbedding, *, top_k: int = 10
    ) -> dict[str, DenseSearchResult]:
        """Fence source/profile changes that occurred while the model was computing."""
        if query_embedding.index_generation_id is None:
            raise CorpusNotReady("Dense retrieval requires a persisted generation.")
        started, started_at = monotonic(), _now()
        snapshot = await self._repository.vector_search_snapshot(
            context,
            embedding=list(query_embedding.vector),
            embedding_profile=self._profile,
            expected_index_generation=query_embedding.index_generation_id,
            profile_fence=self._rollout,
            profile_definition=self._definition,
            top_k=top_k,
        )
        if (
            snapshot.embedding_profile_fingerprint != self._profile.fingerprint
            or snapshot.embedding_profile_revision != self._profile.profile_revision
            or snapshot.index_generation_id != query_embedding.index_generation_id
            or snapshot.corpus_revision != query_embedding.corpus_revision
        ):
            raise CorpusNotReady("Dense snapshot provenance changed.")
        return {
            "snapshot": DenseSearchResult(
                **snapshot.model_dump(),
                profile_id=self._definition.profile_id,
                profile_revision=self._definition.profile_revision,
                policy_hash=self._definition.policy_hash,
                embedding_profile=self._profile,
                stages=[
                    query_embedding.timing,
                    StageTiming(
                        stage="vector_search",
                        duration_ms=(monotonic() - started) * 1000,
                        started_at=started_at,
                        finished_at=_now(),
                    ),
                ],
            )
        }


class DenseService:
    """Qualify immutable dense policies before any query inference or candidate SQL."""

    def __init__(
        self,
        repository: DensePersistencePort,
        *,
        embedding: EmbeddingPort,
        profile: EmbeddingProfile,
        counter: ExactModelCounter,
        registry: ProfileRegistry,
        capacity_policy_id: str,
        readiness: Callable[[], Awaitable[None]],
    ) -> None:
        disable_tracing()
        self._repository, self._embedding = repository, embedding
        self._profile, self._counter, self._registry = profile, counter, registry
        self._capacity_policy_id = capacity_policy_id
        self._readiness = readiness

    async def _qualify(
        self, context: WorkspaceContext, definition: ProfileDefinition
    ) -> tuple[CorpusSnapshot, ProfileRollout]:
        validate_dense_policy(definition, self._profile, workspace_id=context.workspace_id)
        if definition.capacity_policy_id != self._capacity_policy_id:
            raise CorpusNotReady("The dense profile does not match the composed capacity policy.")
        rollout = active_profile_rollout(
            definition, await self._repository.get_profile_rollouts(context), workspace_id=context.workspace_id
        )
        corpus = await self._repository.corpus_summary(context)
        coverage = await self._repository.embedding_coverage(context, self._profile)
        if (
            not coverage.ready
            or coverage.coverage_fraction != 1.0
            or coverage.index_generation != corpus.index_generation_id
            or rollout.qualified_generation_id != corpus.index_generation_id
            or coverage.profile_fingerprint != self._profile.fingerprint
            or coverage.eligible_active_chunks != corpus.chunk_count
            or not 1 <= corpus.chunk_count <= definition.max_corpus_chunks
            or not 1 <= corpus.content_bytes <= definition.max_corpus_bytes
        ):
            raise CorpusNotReady("The complete semantic generation is not ready.")
        await self._readiness()
        return corpus, rollout

    async def snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        """Advertise dense only while the model, rollout and full current generation qualify."""
        profiles: list[ExecutionProfile] = []
        for definition in self._registry.profiles:
            if definition.composition != "exact_dense" or context.workspace_id not in definition.workspace_ids:
                continue
            try:
                corpus, _rollout = await self._qualify(context, definition)
            except (PersistenceError, EmbeddingError):
                continue
            profiles.append(
                execution_profile(
                    definition,
                    workspace_id=context.workspace_id,
                    corpus_id=corpus.corpus_id,
                    index_generation=corpus.index_generation_id,
                )
            )
        return ReadinessSnapshot(profiles=profiles)

    async def search(
        self, context: WorkspaceContext, *, query: str, top_k: int, profile_id: str, expected_profile_revision: str
    ) -> DenseSearchResult:
        """Run a fixed two-component Haystack pipeline under the existing HTTP deadline."""
        definition = resolve_profile(
            self._registry,
            profile_id=profile_id,
            profile_revision=expected_profile_revision,
            workspace_id=context.workspace_id,
        )
        validate_search_policy(definition, query=query, top_k=top_k)
        corpus, rollout = await self._qualify(context, definition)
        pipeline = Pipeline()
        pipeline.add_component(
            "query_embedder", QueryEmbedder(self._embedding, profile=self._profile, counter=self._counter)
        )
        pipeline.add_component(
            "retriever",
            PostgresDenseRetriever(self._repository, profile=self._profile, definition=definition, rollout=rollout),
        )
        pipeline.connect("query_embedder.query_embedding", "retriever.query_embedding")
        try:
            output = await pipeline.run_async(
                data={
                    "query_embedder": {"context": context, "query": query.strip(), "corpus": corpus},
                    "retriever": {"context": context, "top_k": top_k},
                },
                concurrency_limit=1,
            )
        except PipelineRuntimeError as error:
            if isinstance(error.__cause__, (PersistenceError, EmbeddingError)):
                raise error.__cause__ from None
            raise DatabaseUnavailable("The dense pipeline is unavailable.") from None
        result = output.get("retriever", {}).get("snapshot")
        if not isinstance(result, DenseSearchResult):
            raise DatabaseUnavailable("The dense pipeline returned invalid provenance.")
        return result

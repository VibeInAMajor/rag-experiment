"""Allowlisted, genuinely asynchronous Haystack retrieval over the existing corpus."""

from apps.workbench.api.persistence import (
    CorpusSnapshot,
    DatabaseUnavailable,
    LexicalSearchSnapshot,
    PersistenceError,
    PersistencePort,
    ProfileNotAvailable,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.api.profile_registry import (
    ProfileDefinition,
    ProfileRegistry,
    ProfileRollout,
    default_profile_registry,
)
from apps.workbench.api.profiles import (
    active_profile_rollout,
    execution_profile,
    qualify_profile,
    require_profile_dependencies,
    resolve_profile,
    validate_search_policy,
)
from apps.workbench.api.services import ReadinessSnapshot
from haystack import Pipeline, component
from haystack.core.errors import PipelineRuntimeError
from haystack.tracing import disable_tracing


class UnsupportedProfile(ProfileNotAvailable):
    """The requested immutable execution profile is not approved."""


@component
class PostgresLexicalRetriever:
    """Execute the existing asynchronous persistence port without another store."""

    def __init__(
        self,
        repository: PersistencePort,
        *,
        profile_fence: ProfileRollout | None = None,
        definition: ProfileDefinition | None = None,
    ) -> None:
        self._repository = repository
        self._profile_fence = profile_fence
        self._definition = definition

    @component.output_types(snapshot=LexicalSearchSnapshot)
    def run(
        self,
        context: WorkspaceContext,  # noqa: ARG002
        query: str,  # noqa: ARG002
        *,
        top_k: int = 10,  # noqa: ARG002
    ) -> dict[str, LexicalSearchSnapshot]:
        """Require async execution; Haystack requires matching sync/async socket names."""
        raise RuntimeError("Use Pipeline.run_async() for this asynchronous persistence component.")

    @component.output_types(snapshot=LexicalSearchSnapshot)
    async def run_async(
        self, context: WorkspaceContext, query: str, *, top_k: int = 10
    ) -> dict[str, LexicalSearchSnapshot]:
        """Await the real PostgreSQL query and propagate cancellation to its transaction."""
        snapshot = await self._repository.lexical_search_snapshot(
            context, query=query, top_k=top_k, profile_fence=self._profile_fence, profile_definition=self._definition
        )
        return {"snapshot": snapshot}


def _build_pipeline(
    repository: PersistencePort,
    *,
    profile_fence: ProfileRollout | None = None,
    definition: ProfileDefinition | None = None,
) -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component(
        "retriever", PostgresLexicalRetriever(repository, profile_fence=profile_fence, definition=definition)
    )
    return pipeline


_COMPOSITIONS = {"postgres_fts": _build_pipeline}


class LexicalService:
    """Bind approved immutable profiles to a static table of reviewed compositions."""

    def __init__(self, repository: PersistencePort, *, registry: ProfileRegistry | None = None) -> None:
        disable_tracing()
        self._repository = repository
        self._registry = default_profile_registry() if registry is None else registry

    async def snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        """Qualify schema, index and a bounded complete corpus without executing a search."""
        try:
            rollouts = await self._repository.get_profile_rollouts(context)
            candidates = [
                definition
                for definition in self._registry.profiles
                if definition.composition in _COMPOSITIONS
                and context.workspace_id in definition.workspace_ids
                and any(
                    (item.profile_id, item.profile_revision, item.state)
                    == (definition.profile_id, definition.profile_revision, "active")
                    for item in rollouts
                )
            ]
            if not candidates:
                return ReadinessSnapshot()
            corpus = await self._repository.corpus_summary(context)
            approved = []
            for definition in candidates:
                try:
                    active_profile_rollout(definition, rollouts, workspace_id=context.workspace_id)
                    qualify_profile(definition, corpus)
                    _COMPOSITIONS[definition.composition](self._repository)
                except PersistenceError:
                    continue
                approved.append(
                    execution_profile(definition, workspace_id=context.workspace_id, corpus_id=corpus.corpus_id)
                )
        except PersistenceError:
            return ReadinessSnapshot()
        return ReadinessSnapshot(profiles=approved)

    async def documents(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Read actual source/version metadata and its consistent corpus revision."""
        return await self._repository.corpus_snapshot(context)

    async def workspaces(self, context: WorkspaceContext) -> list[Workspace]:
        """List workspaces already selected by server authorization policy."""
        return await self._repository.list_workspaces(context)

    async def search(
        self, context: WorkspaceContext, *, query: str, top_k: int, profile_id: str, expected_profile_revision: str
    ) -> LexicalSearchSnapshot:
        """Execute only the reviewed profile using the public async pipeline API."""
        definition = resolve_profile(
            self._registry,
            profile_id=profile_id,
            profile_revision=expected_profile_revision,
            workspace_id=context.workspace_id,
        )
        validate_search_policy(definition, query=query, top_k=top_k)
        rollout = active_profile_rollout(
            definition, await self._repository.get_profile_rollouts(context), workspace_id=context.workspace_id
        )
        # Unsupported dependencies must fail before corpus qualification or candidate SQL.
        require_profile_dependencies(definition)
        qualify_profile(definition, await self._repository.corpus_summary(context))
        try:
            output = await _COMPOSITIONS[definition.composition](
                self._repository, profile_fence=rollout, definition=definition
            ).run_async(
                data={"retriever": {"context": context, "query": query.strip(), "top_k": top_k}}, concurrency_limit=1
            )
        except PipelineRuntimeError as error:
            if isinstance(error.__cause__, PersistenceError):
                raise error.__cause__ from None
            raise DatabaseUnavailable("The retrieval pipeline is unavailable.") from None
        result = output.get("retriever", {}).get("snapshot")
        if not isinstance(result, LexicalSearchSnapshot):
            raise DatabaseUnavailable("The retrieval pipeline returned an invalid result.")
        qualify_profile(
            definition,
            CorpusSnapshot(
                corpus_revision=result.corpus_revision,
                documents=[],
                chunk_count=result.chunk_count,
                content_bytes=result.content_bytes,
            ),
        )
        return result.model_copy(
            update={
                "profile_id": definition.profile_id,
                "profile_revision": definition.profile_revision,
                "policy_hash": definition.policy_hash,
            }
        )

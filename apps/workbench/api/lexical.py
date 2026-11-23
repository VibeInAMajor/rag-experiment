"""Allowlisted, genuinely asynchronous Haystack retrieval over the existing corpus."""

from apps.workbench.api.contracts import ExecutionProfile
from apps.workbench.api.persistence import (
    CorpusNotReady,
    CorpusSnapshot,
    DatabaseUnavailable,
    LexicalSearchSnapshot,
    PersistenceError,
    PersistencePort,
    Workspace,
    WorkspaceContext,
)
from apps.workbench.api.profiles import POSTGRES_FTS_PROFILE_ID as PROFILE_ID
from apps.workbench.api.profiles import POSTGRES_FTS_PROFILE_REVISION as PROFILE_REVISION
from apps.workbench.api.services import ReadinessSnapshot
from haystack import Pipeline, component
from haystack.core.errors import PipelineRuntimeError
from haystack.tracing import disable_tracing


class UnsupportedProfile(PersistenceError):
    """The requested immutable execution profile is not approved."""


@component
class PostgresLexicalRetriever:
    """Execute the existing asynchronous persistence port without another store."""

    def __init__(self, repository: PersistencePort) -> None:
        self._repository = repository

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
        snapshot = await self._repository.lexical_search_snapshot(context, query=query, top_k=top_k)
        return {"snapshot": snapshot}


def _qualify(corpus: CorpusSnapshot | LexicalSearchSnapshot) -> None:
    if not 1 <= corpus.chunk_count <= 10000 or not 1 <= corpus.content_bytes <= 52428800:
        raise CorpusNotReady("The complete authorized corpus is not ready for this profile.")


def _build_pipeline(repository: PersistencePort) -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component("retriever", PostgresLexicalRetriever(repository))
    return pipeline


class LexicalService:
    """Compose one fixed profile; authorization and response metadata stay outside SDKs."""

    def __init__(self, repository: PersistencePort) -> None:
        disable_tracing()
        self._repository = repository

    async def snapshot(self, context: WorkspaceContext) -> ReadinessSnapshot:
        """Qualify schema, index and a bounded complete corpus without executing a search."""
        try:
            _build_pipeline(self._repository)
            corpus = await self._repository.corpus_summary(context)
            _qualify(corpus)
        except PersistenceError:
            return ReadinessSnapshot()
        return ReadinessSnapshot(
            profiles=[
                ExecutionProfile(
                    profile_id=PROFILE_ID,
                    profile_revision=PROFILE_REVISION,
                    workspace_ids=[context.workspace_id],
                    corpus_id=corpus.corpus_id,
                    score_type="postgres_ts_rank_cd",
                )
            ]
        )

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
        if profile_id != PROFILE_ID or expected_profile_revision != PROFILE_REVISION:
            raise UnsupportedProfile("The requested execution profile is not available.")
        if (
            type(query) is not str
            or not 1 <= len(query.strip()) <= 4096
            or type(top_k) is not int
            or not 1 <= top_k <= 50
        ):
            raise ValueError("Invalid lexical search parameters.")
        try:
            output = await _build_pipeline(self._repository).run_async(
                data={"retriever": {"context": context, "query": query.strip(), "top_k": top_k}}, concurrency_limit=1
            )
        except PipelineRuntimeError as error:
            if isinstance(error.__cause__, PersistenceError):
                raise error.__cause__ from None
            raise DatabaseUnavailable("The retrieval pipeline is unavailable.") from None
        result = output.get("retriever", {}).get("snapshot")
        if not isinstance(result, LexicalSearchSnapshot):
            raise DatabaseUnavailable("The retrieval pipeline returned an invalid result.")
        _qualify(result)
        return result

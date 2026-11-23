"""Validate and project a certified lexical snapshot without inventing timing or provenance."""

from time import monotonic

from apps.workbench.api.contracts import Meta, SearchResponse, SearchResult, StageTiming
from apps.workbench.api.persistence import DatabaseUnavailable, LexicalSearchSnapshot, WorkspaceContext
from apps.workbench.api.profile_registry import ProfileDefinition
from apps.workbench.api.profiles import POSTGRES_FTS_PROFILE_ID, POSTGRES_FTS_PROFILE_REVISION


def project_search(
    snapshot: LexicalSearchSnapshot,
    *,
    context: WorkspaceContext,
    top_k: int,
    meta: Meta,
    run_id: str,
    started: float,
    expected_profile: ProfileDefinition | None = None,
) -> SearchResponse:
    """Project exact passages and measured exclusive stages from an authorized snapshot."""
    projection_started = monotonic()
    if expected_profile is not None and (snapshot.profile_id, snapshot.profile_revision, snapshot.policy_hash) != (
        expected_profile.profile_id,
        expected_profile.profile_revision,
        expected_profile.policy_hash,
    ):
        raise DatabaseUnavailable("The execution result has incompatible profile provenance.")
    if len(snapshot.hits) > top_k or len({hit.chunk.chunk_id for hit in snapshot.hits}) != len(snapshot.hits):
        raise ValueError("Invalid result projection")
    results = []
    previous: tuple[float, str] | None = None
    for index, hit in enumerate(snapshot.hits, 1):
        order = (-hit.score, hit.chunk.chunk_id)
        if (
            hit.chunk.workspace_id != context.workspace_id
            or hit.rank != index
            or previous is not None
            and order < previous
        ):
            raise ValueError("Invalid result provenance or ordering")
        previous = order
        results.append(
            SearchResult(
                chunk_id=hit.chunk.chunk_id,
                source_id=hit.chunk.source_id,
                source_version_id=hit.chunk.version_id,
                title=hit.chunk.title,
                page=hit.chunk.page,
                content=hit.chunk.content,
                rank=hit.rank,
                score=hit.score,
            )
        )
    stages = [
        StageTiming(stage="corpus_load", duration_ms=snapshot.corpus_load_duration_ms),
        StageTiming(stage="retrieval", duration_ms=snapshot.retrieval_duration_ms),
        StageTiming(stage="projection", duration_ms=(monotonic() - projection_started) * 1000),
    ]
    duration_ms = (monotonic() - started) * 1000
    if sum(stage.duration_ms for stage in stages) > duration_ms:
        raise ValueError("Invalid measured timing")
    if (snapshot.profile_id is None) != (snapshot.profile_revision is None):
        raise ValueError("Incomplete profile provenance")
    return SearchResponse(
        **meta.model_dump(),
        profile_id=snapshot.profile_id or POSTGRES_FTS_PROFILE_ID,
        profile_revision=snapshot.profile_revision or POSTGRES_FTS_PROFILE_REVISION,
        workspace_id=context.workspace_id,
        corpus_revision=snapshot.corpus_revision,
        run_id=run_id,
        duration_ms=duration_ms,
        stages=stages,
        results=results,
    )

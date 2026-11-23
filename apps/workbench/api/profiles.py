"""Application policy for immutable definitions and their approved workspace rollouts."""

from typing import Final

from apps.workbench.api.contracts import (
    ExecutionProfile,
    ProfileLimits,
    ProfileParameters,
    QueryParameter,
    TopKParameter,
)
from apps.workbench.api.persistence import (
    CorpusNotReady,
    CorpusSnapshot,
    IndexGeneration,
    InvalidSearchParameters,
    ProfileNotAvailable,
)
from apps.workbench.api.profile_registry import ProfileDefinition, ProfileRegistry, ProfileRollout
from apps.workbench.api.profile_registry import ProfileNotAvailable as RegistryProfileNotAvailable

POSTGRES_FTS_PROFILE_ID: Final = "postgres-fts-baseline"
POSTGRES_FTS_PROFILE_REVISION: Final = "postgres-fts-baseline-r1"
_AVAILABLE_REQUIREMENTS = frozenset({"schema", "source_generation", "lexical_index"})


def resolve_profile(
    registry: ProfileRegistry, *, profile_id: str, profile_revision: str, workspace_id: str
) -> ProfileDefinition:
    """Reject identities outside the trusted catalog before any dependency work."""
    try:
        return registry.resolve(profile_id, expected_profile_revision=profile_revision, workspace_id=workspace_id)
    except RegistryProfileNotAvailable:
        raise ProfileNotAvailable("The requested execution profile is not available.") from None


def validate_search_policy(definition: ProfileDefinition, *, query: str, top_k: int) -> None:
    """Apply the selected policy inside the transport's fixed safety envelope."""
    if (
        type(query) is not str
        or not 1 <= len(query.strip()) <= definition.max_query_characters
        or "\0" in query
        or any(0xD800 <= ord(character) <= 0xDFFF for character in query)
        or type(top_k) is not int
        or not 1 <= top_k <= definition.max_top_k
        or top_k > definition.candidate_k
    ):
        raise InvalidSearchParameters("The request exceeds the approved search policy.")


def active_profile_rollout(
    definition: ProfileDefinition, rollouts: tuple[ProfileRollout, ...], *, workspace_id: str
) -> ProfileRollout:
    """Pin the current approved revision without trusting a client-supplied lifecycle flag."""
    rollout = next((item for item in rollouts if item.profile_id == definition.profile_id), None)
    if (
        rollout is None
        or rollout.workspace_id != workspace_id
        or rollout.state != "active"
        or rollout.profile_revision != definition.profile_revision
    ):
        raise ProfileNotAvailable("The requested execution profile is not active.")
    if rollout.policy_hash != definition.policy_hash:
        raise CorpusNotReady("The configured policy differs from its durable approved revision.")
    return rollout


def require_profile_dependencies(definition: ProfileDefinition) -> None:
    """Refuse dependencies without an implemented qualification path before corpus work."""
    if (
        definition.composition != "postgres_fts"
        or not set(definition.capability_requirements).issubset(_AVAILABLE_REQUIREMENTS)
        or any(
            value is not None
            for value in (
                definition.parser_profile_revision,
                definition.chunk_profile_revision,
                definition.processing_policy_hash,
            )
        )
    ):
        # The current lexical manifest cannot attest semantic or per-processor corpus coverage.
        raise CorpusNotReady("The profile requires unavailable qualification evidence.")


def qualify_profile(definition: ProfileDefinition, generation: IndexGeneration | CorpusSnapshot) -> None:
    """Qualify only implemented compositions against actual checked corpus metadata."""
    require_profile_dependencies(definition)
    if isinstance(generation, IndexGeneration):
        count, size = generation.active_chunk_count, generation.content_bytes
        if generation.lexical_index_revision != POSTGRES_FTS_PROFILE_REVISION:
            raise CorpusNotReady("The physical lexical index revision is incompatible.")
    else:
        count, size = generation.chunk_count, generation.content_bytes
    if not 1 <= count <= definition.max_corpus_chunks or not 1 <= size <= definition.max_corpus_bytes:
        raise CorpusNotReady("The complete authorized corpus is not ready for this profile.")


def execution_profile(definition: ProfileDefinition, *, workspace_id: str, corpus_id: str) -> ExecutionProfile:
    """Project existing discovery fields with truthful algorithm semantics and approved bounds."""
    return ExecutionProfile(
        profile_id=definition.profile_id,
        profile_revision=definition.profile_revision,
        workspace_ids=[workspace_id],
        corpus_id=corpus_id,
        score_type="postgres_ts_rank_cd",
        parameters=ProfileParameters(
            query=QueryParameter(max_length=definition.max_query_characters),
            top_k=TopKParameter(default=min(10, definition.max_top_k), maximum=definition.max_top_k),
        ),
        limits=ProfileLimits(
            timeout_ms=definition.timeout_ms,
            max_concurrent_searches=definition.max_concurrent,
            max_corpus_chunks=definition.max_corpus_chunks,
            max_corpus_bytes=definition.max_corpus_bytes,
        ),
    )

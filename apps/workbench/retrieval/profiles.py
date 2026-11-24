"""Application policy for immutable definitions and their approved workspace rollouts."""

from typing import Final

from apps.workbench.contracts.schemas import (
    ExecutionProfile,
    ProfileLimits,
    ProfileParameters,
    QueryParameter,
    TopKParameter,
)
from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.persistence.models import (
    CorpusNotReady,
    CorpusSnapshot,
    IndexGeneration,
    InvalidSearchParameters,
    ProfileNotAvailable,
)
from apps.workbench.retrieval.profile_registry import ProfileDefinition, ProfileRegistry, ProfileRollout
from apps.workbench.retrieval.profile_registry import ProfileNotAvailable as RegistryProfileNotAvailable

POSTGRES_FTS_PROFILE_ID: Final = "postgres-fts-baseline"
POSTGRES_FTS_PROFILE_REVISION: Final = "postgres-fts-baseline-r1"
_AVAILABLE_REQUIREMENTS = frozenset({"schema", "source_generation", "lexical_index"})


def validate_dense_policy(
    definition: ProfileDefinition, profile: EmbeddingProfile, *, workspace_id: str, top_k: int = 1
) -> None:
    """Bind the fixed exact composition to the immutable indexed model and input policy."""
    if (
        definition.composition != "exact_dense"
        or workspace_id not in definition.workspace_ids
        or (definition.model_profile_id, definition.model_profile_revision, definition.dimensions)
        != (profile.profile_id, profile.profile_revision, profile.dimensions)
        or definition.index_dimensions != profile.dimensions
        or definition.vector_representation != "vector"
        or definition.normalization != "l2"
        or any(
            value is not None
            for value in (
                definition.parser_profile_revision,
                definition.chunk_profile_revision,
                definition.processing_policy_hash,
            )
        )
        or not set(definition.capability_requirements).issubset(
            {"schema", "source_generation", "embedding_model", "embedding_coverage", "capacity_policy"}
        )
    ):
        raise CorpusNotReady("The exact dense policy does not match its qualified embedding dependencies.")
    if type(top_k) is not int or not 1 <= top_k <= min(definition.max_top_k, definition.candidate_k):
        raise InvalidSearchParameters("The request exceeds the approved dense search policy.")


def dense_profile_definition(profile: EmbeddingProfile, *, capacity_policy_id: str) -> ProfileDefinition:
    """Build the sole reviewed exact-dense policy from an operator-qualified local model."""
    return ProfileDefinition(
        profile_id="postgres-dense-exact",
        profile_revision="postgres-dense-exact-r1",
        label="PostgreSQL exact dense search",
        kind="dense",
        composition="exact_dense",
        workspace_ids=("development",),
        model_profile_id=profile.profile_id,
        model_profile_revision=profile.profile_revision,
        dimensions=profile.dimensions,
        index_dimensions=profile.dimensions,
        vector_representation="vector",
        normalization="l2",
        capacity_policy_id=capacity_policy_id,
        score_type="cosine_distance",
        score_direction="lower_is_better",
        capability_requirements=(
            "schema",
            "source_generation",
            "embedding_model",
            "embedding_coverage",
            "capacity_policy",
        ),
    )


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


def execution_profile(
    definition: ProfileDefinition, *, workspace_id: str, corpus_id: str, index_generation: int | None = None
) -> ExecutionProfile:
    """Project existing discovery fields with truthful algorithm semantics and approved bounds."""
    if definition.score_type not in {"cosine_distance", "postgres_ts_rank_cd", "bm25_raw"}:
        raise CorpusNotReady("The output score semantics are not implemented.")
    return ExecutionProfile(
        profile_id=definition.profile_id,
        profile_revision=definition.profile_revision,
        workspace_ids=[workspace_id],
        corpus_id=corpus_id,
        kind="dense_search" if definition.composition == "exact_dense" else "lexical_search",
        score_type="cosine_distance" if definition.composition == "exact_dense" else "postgres_ts_rank_cd",
        score_direction="lower_is_better" if definition.composition == "exact_dense" else None,
        embedding_profile_revision=definition.model_profile_revision,
        index_generation=index_generation,
        min_coverage=1 if definition.composition == "exact_dense" else None,
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

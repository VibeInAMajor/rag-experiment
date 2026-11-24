"""Durable embedding work, tenant-local reuse and generation coverage contracts."""

import math
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.workbench.contracts.schemas import Identifier
from apps.workbench.embedding.embedding import EmbeddingProfile
from apps.workbench.persistence.models import PersistenceError, WorkspaceContext

EmbeddingCacheKey = tuple[str, str]
EmbeddingVector = tuple[float, ...]
EmbeddingCache = dict[EmbeddingCacheKey, EmbeddingVector]


class EmbeddingOwnershipLost(PersistenceError):
    """An expired or superseded lease cannot attach a late provider result."""


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class EmbeddingJob(_Record):
    workspace_id: Identifier
    job_id: Identifier
    source_id: Identifier
    version_id: Identifier
    profile_id: Identifier
    profile_revision: Identifier
    profile_fingerprint: str
    status: Literal["queued", "running", "retryable_failed", "completed", "stale", "poisoned"]
    attempts: int
    cursor: str | None = None
    owner_token: str | None = Field(default=None, repr=False)
    lease_expires_at: datetime | None = None
    error_code: str | None = None


class EmbeddingCandidate(_Record):
    workspace_id: Identifier
    source_id: Identifier
    version_id: Identifier
    chunk_id: Identifier
    content: str = Field(repr=False)
    content_hash: str
    metadata: dict[str, Any] = Field(repr=False)
    version_metadata: dict[str, Any] = Field(repr=False)


class EmbeddingWrite(_Record):
    source_id: Identifier
    version_id: Identifier
    chunk_id: Identifier
    expected_content_hash: str = Field(min_length=1, max_length=128)
    processing_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    vector: EmbeddingVector = Field(min_length=32, max_length=2560, repr=False)

    @model_validator(mode="after")
    def _normalized_vector(self) -> "EmbeddingWrite":
        if any(not math.isfinite(value) for value in self.vector) or abs(math.hypot(*self.vector) - 1.0) > 0.001:
            raise ValueError("Embedding vectors require finite normalized values")
        return self


class EmbeddingCoverage(_Record):
    workspace_id: Identifier
    profile_id: Identifier
    profile_revision: Identifier
    profile_fingerprint: str
    index_generation: int | None = None
    eligible_active_chunks: int
    ready_embeddings: int
    stale_embeddings: int
    coverage_fraction: float
    ready: bool
    checkpoint: str | None = None


class PersistedEmbeddingHit(_Record):
    workspace_id: Identifier
    source_id: Identifier
    version_id: Identifier
    chunk_id: Identifier
    content: str = Field(repr=False)
    content_hash: str
    source_content_hash: str
    input_hash: str
    profile_fingerprint: str
    index_generation: int
    distance: float


class EmbeddingPersistencePort(Protocol):
    async def register_embedding_profile(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, enabled: bool = True
    ) -> None:
        """Register immutable profile identity without enabling a search API."""
        ...

    async def enqueue_embedding_backfill(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, limit: int = 1000
    ) -> int:
        """Enqueue a bounded set of active source versions idempotently."""
        ...

    async def lease_embedding_job(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, lease_seconds: int = 120
    ) -> EmbeddingJob | None:
        """Claim recoverable work without retaining a transaction during inference."""
        ...

    async def renew_embedding_job(
        self, context: WorkspaceContext, job: EmbeddingJob, *, lease_seconds: int = 120
    ) -> EmbeddingJob:
        """Renew only an unexpired lease held by this worker."""
        ...

    async def embedding_job_chunks(
        self, context: WorkspaceContext, job: EmbeddingJob, *, limit: int = 8
    ) -> tuple[EmbeddingCandidate, ...]:
        """Read a bounded stable chunk-ID page from the active leased source version."""
        ...

    async def lookup_embedding_cache(
        self, context: WorkspaceContext, profile: EmbeddingProfile, *, keys: tuple[EmbeddingCacheKey, ...]
    ) -> EmbeddingCache:
        """Reuse only identical model/input/processing keys in the same workspace."""
        ...

    async def commit_embedding_batch(
        self,
        context: WorkspaceContext,
        job: EmbeddingJob,
        profile: EmbeddingProfile,
        *,
        records: tuple[EmbeddingWrite, ...],
        cursor: str | None,
        complete: bool = False,
    ) -> EmbeddingJob:
        """Fence active source and lease, persist a batch and publish complete coverage atomically."""
        ...

    async def fail_embedding_job(
        self,
        context: WorkspaceContext,
        job: EmbeddingJob,
        *,
        error_code: str,
        retryable: bool,
        retry_after_seconds: int,
    ) -> EmbeddingJob:
        """Retain a safe failure category and bounded retry/poison state."""
        ...

    async def get_embedding_job(self, context: WorkspaceContext, job_id: str) -> EmbeddingJob | None:
        """Inspect one workspace-scoped job."""
        ...

    async def retry_embedding_job(self, context: WorkspaceContext, job_id: str) -> EmbeddingJob:
        """Explicitly recover a quarantined active job without regenerating committed progress."""
        ...

    async def embedding_coverage(self, context: WorkspaceContext, profile: EmbeddingProfile) -> EmbeddingCoverage:
        """Read actual current coverage and its matching immutable ready generation."""
        ...

    async def preview_embedding_backfill(
        self, context: WorkspaceContext, profile: EmbeddingProfile
    ) -> EmbeddingCoverage:
        """Inspect eligibility without registering or enabling any profile."""
        ...

    async def exact_embedding_search(
        self, context: WorkspaceContext, profile: EmbeddingProfile, query_vector: EmbeddingVector, *, limit: int = 10
    ) -> tuple[PersistedEmbeddingHit, ...]:
        """Search only a fully covered current generation within one consistent read snapshot."""
        ...

"""Application-owned records and workspace-scoped persistence boundary."""

from contextlib import AbstractAsyncContextManager
from math import isfinite
from pathlib import PurePosixPath
from typing import Literal, Protocol

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from apps.workbench.api.contracts import ContractModel, Identifier


class PersistenceError(Exception):
    """A safe persistence failure, without database or payload diagnostics."""


class DatabaseUnavailable(PersistenceError):
    """The database operation could not complete."""


class SchemaIncompatible(PersistenceError):
    """The installed schema or required extension is incompatible."""


class WorkspaceNotFound(PersistenceError):
    """The workspace is absent or outside the authorized scope."""


class InvalidEmbedding(PersistenceError):
    """An embedding does not match its registered profile."""


class SeedConflict(PersistenceError):
    """Existing data does not match the explicit development seed."""


class RecordConflict(PersistenceError):
    """A write conflicts with immutable identities or reference constraints."""


class CorpusNotReady(PersistenceError):
    """The complete authorized corpus cannot qualify for this execution profile."""


class DocumentNotFound(PersistenceError):
    """A source is absent from the authorized workspace."""


class IdempotencyConflict(PersistenceError):
    """A reserved key belongs to a different immutable request."""


class VersionConflict(PersistenceError):
    """The expected active source version is stale."""


class IngestionOwnershipLost(PersistenceError):
    """An ingestion checkpoint no longer belongs to the caller."""


class CorpusLimitExceeded(PersistenceError):
    """A publication would exceed the existing lexical corpus bounds."""


class IngestionInProgress(PersistenceError):
    """Another live request owns this durable idempotency reservation."""

    def __init__(self, job_id: str | None = None) -> None:
        self.job_id = job_id
        super().__init__("Ingestion is already in progress.")


class WorkspaceContext(ContractModel):
    """Server-resolved scope; never deserialize this from an HTTP body/filter."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    workspace_id: Identifier
    trace_id: Identifier | None = None


def resolve_development_workspace(requested_id: str = "development") -> WorkspaceContext:
    """Resolve the single local-development scope; this is not production auth."""
    if requested_id != "development":
        raise WorkspaceNotFound("Workspace is not available.")
    return WorkspaceContext(workspace_id="development")


class Workspace(ContractModel):
    workspace_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Source(ContractModel):
    workspace_id: Identifier
    source_id: Identifier
    title: str = Field(min_length=1, max_length=500)
    media_type: str = Field(default="text/plain", min_length=1, max_length=128)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SourceVersion(ContractModel):
    workspace_id: Identifier
    source_id: Identifier
    version_id: Identifier
    content_hash: str = Field(min_length=1, max_length=128)
    status: Literal["staged", "active", "superseded", "error"] = "staged"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class LocalOriginalRegistration(ContractModel):
    """Version-bound relative location recorded by a trusted local operator."""

    relative_path: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("relative_path")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not path.parts
            or path.as_posix() != value
            or any(part in {".", ".."} for part in path.parts)
            or any(character in value for character in ("\\", ":"))
            or any(
                ord(character) < 32 or ord(character) == 127 or 0xD800 <= ord(character) <= 0xDFFF
                for character in value
            )
        ):
            raise ValueError("Original location must be a normalized relative path")
        return value


class LocalOriginalRecord(ContractModel):
    """Scoped original-registration lookup without exposing locations over HTTP."""

    source_id: Identifier
    version_id: Identifier
    is_demo: bool
    registration: LocalOriginalRegistration | None = None


class Chunk(ContractModel):
    workspace_id: Identifier
    source_id: Identifier
    version_id: Identifier
    chunk_id: Identifier
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=32768)
    content_hash: str = Field(min_length=1, max_length=128)
    page: int | None = Field(default=None, ge=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_profile_id: Identifier | None = None
    dimensions: int | None = Field(default=None, ge=1, le=16000)

    @field_validator("embedding")
    @classmethod
    def _finite_embedding(cls, embedding: list[float] | None) -> list[float] | None:
        if embedding is not None and (not embedding or not all(isfinite(value) for value in embedding)):
            raise ValueError("Embedding values must be finite and nonempty")
        return embedding

    @model_validator(mode="after")
    def _embedding_profile(self) -> "Chunk":
        if self.embedding is None:
            if self.embedding_profile_id is not None or self.dimensions is not None:
                raise ValueError("An unset embedding cannot have a profile or dimensions")
        elif self.embedding_profile_id is None or self.dimensions != len(self.embedding):
            raise ValueError("Embedding dimensions and profile must be explicit and consistent")
        return self


class LexicalHit(ContractModel):
    chunk: Chunk
    rank: int = Field(ge=1)
    score: float = Field(allow_inf_nan=False, ge=0)
    score_type: Literal["postgres_ts_rank_cd"] = "postgres_ts_rank_cd"


class VectorHit(ContractModel):
    chunk: Chunk
    rank: int = Field(ge=1)
    distance: float = Field(allow_inf_nan=False, ge=0, le=2)
    score_type: Literal["cosine_distance"] = "cosine_distance"


class PersistenceReady(ContractModel):
    schema_revision: str
    workspace_id: Identifier
    source_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)


class DocumentRecord(ContractModel):
    source_id: Identifier
    title: str
    media_type: str
    status: Literal["ready", "processing", "error"]
    active_version_id: Identifier | None
    chunk_count: int = Field(ge=0)
    updated_at: str
    error_code: str | None = None


class CorpusSnapshot(ContractModel):
    corpus_id: Identifier = "development-corpus-v1"
    corpus_revision: Identifier
    documents: list[DocumentRecord]
    chunk_count: int = Field(ge=0)
    content_bytes: int = Field(ge=0)


class IndexGeneration(ContractModel):
    """One committed lexical generation; it does not qualify any semantic index."""

    workspace_id: Identifier
    corpus_id: Identifier
    generation_id: int = Field(ge=0)
    corpus_revision: Identifier
    committed_at: str
    active_source_count: int = Field(ge=0)
    active_chunk_count: int = Field(ge=0)
    content_bytes: int = Field(ge=0)
    active_source_manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    lexical_index_revision: Identifier
    status: Literal["ready"]
    previous_generation: int | None = Field(default=None, ge=0)
    event_id: Identifier


class LexicalSearchSnapshot(ContractModel):
    corpus_revision: Identifier
    hits: list[LexicalHit]
    chunk_count: int = Field(ge=0)
    content_bytes: int = Field(ge=0)
    corpus_load_duration_ms: float = Field(ge=0, allow_inf_nan=False)
    retrieval_duration_ms: float = Field(ge=0, allow_inf_nan=False)


class IngestionTiming(ContractModel):
    """An actually measured ingestion stage, without content diagnostics."""

    stage: Literal["parsing", "chunking", "publication"]
    duration_ms: float = Field(ge=0, allow_inf_nan=False)


class IngestionJob(ContractModel):
    """Durable last-confirmed state; reserved identifiers do not imply published records."""

    workspace_id: Identifier
    job_id: Identifier
    source_id: Identifier
    reserved_version_id: Identifier
    operation: Literal["create", "update"]
    expected_active_version_id: Identifier | None = None
    effective_version_id: Identifier | None = None
    status: Literal["pending", "parsing", "chunking", "publishing", "completed", "failed"]
    stage: Literal["pending", "parsing", "chunking", "publishing", "completed"]
    error_code: str | None = None
    retryable: bool = False
    source_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    processing_profile_fingerprint: str | None = None
    chunk_count: int | None = Field(default=None, ge=0, le=10000)
    outcome: Literal["created", "updated", "unchanged"] | None = None
    corpus_revision: Identifier | None = None
    stages: list[IngestionTiming] = Field(default_factory=list)
    created_at: str
    updated_at: str
    finished_at: str | None = None


class UploadReservation(ContractModel):
    """A newly owned request or immutable terminal replay, held by a context manager."""

    job: IngestionJob
    newly_reserved: bool
    owner_token: Identifier | None = None


class SourceDetail(ContractModel):
    """Active source metadata; this is not an original-file download."""

    source: Source
    version: SourceVersion | None
    chunk_count: int = Field(ge=0, le=10000)
    corpus_revision: Identifier
    updated_at: str


class ActiveChunkPage(ContractModel):
    """A bounded active-version keyset page from one identified corpus snapshot."""

    source_id: Identifier
    source_version_id: Identifier
    corpus_revision: Identifier
    items: list[Chunk]
    next_after: Identifier | None = None


class PersistencePort(Protocol):
    async def current_index_generation(
        self, context: WorkspaceContext, *, expected_generation_id: int | None = None
    ) -> IndexGeneration:
        """Read the committed scoped generation; historical reads are not supported."""
        ...

    async def ingestion_ready(self, context: WorkspaceContext) -> bool:
        """Qualify the separately migrated durable-ingestion schema."""
        ...

    async def recover_ingestions(self, context: WorkspaceContext) -> int:
        """Fail abandoned reservations only after proving no live advisory-lock owner exists."""
        ...

    def reserve_ingestion(
        self,
        context: WorkspaceContext,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        source_content_sha256: str,
        source_id: str | None = None,
        expected_active_version_id: str | None = None,
    ) -> AbstractAsyncContextManager[UploadReservation]:
        """Hold exclusive crash-released ownership while reserving stable request/source/version identities."""
        ...

    async def transition_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        stage: Literal["parsing", "chunking", "publishing"],
    ) -> IngestionJob:
        """Commit one ordered stage checkpoint for the matching durable owner."""
        ...

    async def complete_ingestion_with_publication(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        source: Source,
        version: SourceVersion,
        chunks: list[Chunk],
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        """Atomically publish a guarded source version and its completed job, or record unchanged content."""
        ...

    async def fail_ingestion(
        self,
        context: WorkspaceContext,
        *,
        job_id: str,
        owner_token: str,
        error_code: str,
        retryable: bool,
        stages: list[IngestionTiming],
    ) -> IngestionJob:
        """Commit a safe terminal failure without altering any active source version."""
        ...

    async def get_ingestion_job(self, context: WorkspaceContext, *, job_id: str) -> IngestionJob | None:
        """Read scoped durable state without exposing the idempotency key or ownership token."""
        ...

    async def get_source_detail(self, context: WorkspaceContext, *, source_id: str) -> SourceDetail | None:
        """Read one source and its actual active-version processing metadata."""
        ...

    async def list_active_chunks(
        self,
        context: WorkspaceContext,
        *,
        source_id: str,
        limit: int = 50,
        after_chunk_id: str | None = None,
        expected_corpus_revision: str | None = None,
    ) -> ActiveChunkPage | None:
        """Read a bounded stable keyset page; stale corpus revisions raise RecordConflict."""
        ...

    async def start(self) -> None:
        """Open a bounded database pool without modifying its schema."""
        ...

    async def close(self) -> None:
        """Release connections and background pool workers."""
        ...

    async def readiness(self, context: WorkspaceContext) -> PersistenceReady:
        """Certify schema, extension and committed active rows in the authorized scope."""
        ...

    async def create_workspace(self, context: WorkspaceContext, workspace: Workspace) -> None:
        """Create exactly the server-resolved workspace."""
        ...

    async def list_workspaces(self, context: WorkspaceContext) -> list[Workspace]:
        """List only the workspace visible to this context."""
        ...

    async def list_sources(self, context: WorkspaceContext) -> list[Source]:
        """List bounded source metadata within the authorized workspace."""
        ...

    async def get_chunk(self, context: WorkspaceContext, chunk_id: str) -> Chunk | None:
        """Read an active chunk without revealing foreign-workspace identities."""
        ...

    async def get_local_original(
        self, context: WorkspaceContext, *, source_id: str, version_id: str
    ) -> LocalOriginalRecord | None:
        """Read the registered original for an active version in this scope."""
        ...

    async def register_local_original(
        self, context: WorkspaceContext, *, source_id: str, version_id: str, relative_path: str, sha256: str
    ) -> None:
        """Register an existing non-demo active version; identical retries are harmless."""
        ...

    async def publish_source(
        self, context: WorkspaceContext, *, source: Source, version: SourceVersion, chunks: list[Chunk]
    ) -> None:
        """Publish a complete source version atomically."""
        ...

    async def lexical_search(self, context: WorkspaceContext, *, query: str, top_k: int = 10) -> list[LexicalHit]:
        """Search persisted active chunks using native PostgreSQL ranking."""
        ...

    async def corpus_snapshot(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Read bounded authoritative source metadata and its committed corpus revision."""
        ...

    async def corpus_summary(self, context: WorkspaceContext) -> CorpusSnapshot:
        """Read qualification metadata without enumerating source or chunk records."""
        ...

    async def lexical_search_snapshot(
        self, context: WorkspaceContext, *, query: str, top_k: int = 10
    ) -> LexicalSearchSnapshot:
        """Read fingerprint and ranked hits from one repeatable-read SQL snapshot."""
        ...

    async def vector_search(
        self, context: WorkspaceContext, *, embedding: list[float], profile_id: str, top_k: int = 10
    ) -> list[VectorHit]:
        """Search compatible persisted vectors using exact cosine distance."""
        ...

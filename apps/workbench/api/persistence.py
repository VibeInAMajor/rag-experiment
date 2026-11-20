"""Application-owned records and workspace-scoped persistence boundary."""

from math import isfinite
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


class PersistencePort(Protocol):
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

    async def publish_source(
        self, context: WorkspaceContext, *, source: Source, version: SourceVersion, chunks: list[Chunk]
    ) -> None:
        """Publish a complete source version atomically."""
        ...

    async def lexical_search(self, context: WorkspaceContext, *, query: str, top_k: int = 10) -> list[LexicalHit]:
        """Search persisted active chunks using native PostgreSQL ranking."""
        ...

    async def vector_search(
        self, context: WorkspaceContext, *, embedding: list[float], profile_id: str, top_k: int = 10
    ) -> list[VectorHit]:
        """Search compatible persisted vectors using exact cosine distance."""
        ...

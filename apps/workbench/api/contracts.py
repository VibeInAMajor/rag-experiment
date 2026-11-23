"""Versioned HTTP discovery contracts independent of provider implementations."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$")]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Meta(ContractModel):
    contract_revision: Literal["rag-api-v1.0"] = "rag-api-v1.0"
    request_id: Identifier
    trace_id: Identifier


class ErrorField(ContractModel):
    field: str
    code: str


class ApiError(ContractModel):
    code: str
    message: str
    retryable: bool
    http_status: int
    run_id: Identifier | None = None
    job_id: Identifier | None = None
    fields: list[ErrorField] | None = None


class ErrorResponse(Meta):
    error: ApiError


class QueryParameter(ContractModel):
    type: Literal["string"] = "string"
    min_length: Literal[1] = 1
    max_length: int = Field(default=4096, ge=1, le=4096)


class TopKParameter(ContractModel):
    type: Literal["integer"] = "integer"
    default: int = Field(default=10, ge=1, le=50)
    minimum: Literal[1] = 1
    maximum: int = Field(default=50, ge=1, le=50)

    @model_validator(mode="after")
    def _default_within_bounds(self) -> "TopKParameter":
        if self.default > self.maximum:
            raise ValueError("The default top-k must fit the approved maximum")
        return self


class ProfileParameters(ContractModel):
    query: QueryParameter = Field(default_factory=QueryParameter)
    top_k: TopKParameter = Field(default_factory=TopKParameter)


class ProfileLimits(ContractModel):
    max_request_bytes: int = Field(default=32768, ge=1, le=32768)
    timeout_ms: int = Field(default=10000, ge=1, le=10000)
    max_concurrent_searches: int = Field(default=2, ge=1, le=2)
    max_corpus_chunks: int = Field(default=10000, ge=1, le=10000)
    max_corpus_bytes: int = Field(default=52428800, ge=1, le=52428800)


class ExecutionProfile(ContractModel):
    profile_id: Identifier = "bm25-v1"
    profile_revision: Identifier
    kind: Literal["lexical_search"] = "lexical_search"
    workspace_ids: list[Identifier] = Field(min_length=1, max_length=1)
    corpus_id: Identifier
    parameters: ProfileParameters = Field(default_factory=ProfileParameters)
    limits: ProfileLimits = Field(default_factory=ProfileLimits)
    score_type: Literal["bm25_raw", "postgres_ts_rank_cd"] = "bm25_raw"

    @model_validator(mode="after")
    def _profile_score(self) -> "ExecutionProfile":
        expected = "bm25_raw" if self.profile_id == "bm25-v1" else "postgres_ts_rank_cd"
        if self.score_type != expected:
            raise ValueError("Execution profile and score semantics must match")
        return self


class ServiceState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class LiveResponse(Meta):
    status: Literal["alive"] = "alive"
    backend_revision: Identifier


class ReadyResponse(Meta):
    status: Literal["ready"] = "ready"
    backend_revision: Identifier
    ready_profile_ids: list[Identifier]


class Features(ContractModel):
    documents: bool = False
    search: bool = False
    upload: bool = False
    document_details: bool = False
    jobs: bool = False


class DatabaseDependencyStatus(ContractModel):
    status: Literal["unconfigured", "ready", "unavailable", "incompatible", "empty"]
    schema_revision: str | None = None
    workspace_id: Identifier | None = None
    source_count: int | None = Field(default=None, ge=1)
    chunk_count: int | None = Field(default=None, ge=1)


class Dependencies(ContractModel):
    database: DatabaseDependencyStatus = Field(default_factory=lambda: DatabaseDependencyStatus(status="unconfigured"))


class PdfIngestionCapabilities(ContractModel):
    """Text-layer availability is independent from original evidence, OCR and visual semantics."""

    available: bool = False
    text_layer: bool = False
    page_provenance: bool = False
    table_rows: bool = False
    original_evidence: Literal[False] = False
    ocr: Literal[False] = False
    visual_understanding: Literal[False] = False
    visual_detection_coverage: Literal["unverified"] = "unverified"
    max_bytes: Literal[8_388_608] = 8_388_608
    max_pages: Literal[32] = 32


class CapabilitiesResponse(Meta):
    backend_revision: Identifier
    deployment_mode: Literal["single_workspace_dev"] = "single_workspace_dev"
    service_state: ServiceState
    profiles: list[ExecutionProfile]
    features: Features = Field(default_factory=Features)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    pdf_ingestion: PdfIngestionCapabilities = Field(default_factory=PdfIngestionCapabilities)


class SearchRequest(ContractModel):
    query: str
    top_k: int = Field(ge=1, le=50)
    profile_id: Identifier
    expected_profile_revision: Identifier

    @field_validator("query")
    @classmethod
    def _query(cls, value: str) -> str:
        trimmed = value.strip()
        if "\0" in trimmed or not 1 <= len(trimmed) <= 4096:
            raise ValueError("Query must contain 1 to 4096 characters")
        if any(0xD800 <= ord(character) <= 0xDFFF for character in trimmed):
            raise ValueError("Query must contain valid Unicode characters")
        return trimmed


class StageTiming(ContractModel):
    stage: Literal["corpus_load", "retrieval", "projection"]
    status: Literal["success", "skipped"] = "success"
    duration_ms: float = Field(ge=0, allow_inf_nan=False)


class SearchResult(ContractModel):
    chunk_id: Identifier
    source_id: Identifier
    source_version_id: Identifier
    title: str
    page: int | None = Field(default=None, ge=1)
    content: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, allow_inf_nan=False)
    score_type: Literal["postgres_ts_rank_cd"] = "postgres_ts_rank_cd"


class SearchResponse(Meta):
    mode: Literal["live"] = "live"
    workspace_id: Identifier
    corpus_revision: Identifier
    profile_id: Identifier = "postgres-fts-baseline"
    profile_revision: Identifier = "postgres-fts-baseline-r1"
    run_id: Identifier
    status: Literal["success"] = "success"
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    stages: list[StageTiming]
    results: list[SearchResult]


class WorkspaceItem(ContractModel):
    workspace_id: Identifier
    name: str
    status: Literal["ready", "unavailable"]


class WorkspacePage(Meta):
    items: list[WorkspaceItem]
    next_cursor: str | None


class DocumentItem(ContractModel):
    source_id: Identifier
    title: str
    media_type: str
    status: Literal["ready", "processing", "error"]
    active_version_id: Identifier | None
    chunk_count: int = Field(ge=0)
    updated_at: str
    error_code: str | None = None


class DocumentPage(Meta):
    workspace_id: Identifier
    corpus_revision: Identifier
    items: list[DocumentItem]
    next_cursor: str | None


class IngestionStageTiming(ContractModel):
    stage: Literal["parsing", "chunking", "publication"]
    duration_ms: float = Field(ge=0, allow_inf_nan=False)


class IngestionResponse(Meta):
    workspace_id: Identifier
    source_id: Identifier
    source_version_id: Identifier
    job_id: Identifier
    outcome: Literal["created", "updated", "unchanged"]
    status: Literal["completed"] = "completed"
    chunk_count: int = Field(ge=1)
    corpus_revision: Identifier
    stages: list[IngestionStageTiming]
    replayed: bool = False


class IngestionJobResponse(Meta):
    workspace_id: Identifier
    job_id: Identifier
    source_id: Identifier
    source_version_id: Identifier | None
    reserved_version_id: Identifier
    status: Literal["pending", "parsing", "chunking", "publishing", "completed", "failed"]
    stage: Literal["pending", "parsing", "chunking", "publishing", "completed", "failed"]
    retryable: bool
    error_code: str | None
    chunk_count: int | None = Field(ge=0)
    outcome: Literal["created", "updated", "unchanged"] | None
    created_at: str
    updated_at: str
    finished_at: str | None
    stages: list[IngestionStageTiming]


class DocumentDetail(Meta):
    workspace_id: Identifier
    corpus_revision: Identifier
    source_id: Identifier
    title: str
    media_type: str
    status: Literal["ready", "processing", "error"]
    active_version_id: Identifier | None
    chunk_count: int = Field(ge=0)
    updated_at: str
    processing_profile: dict[str, JsonValue] | None = None
    processing_profile_fingerprint: str | None = None
    ingestion_policy_revision: str | None = None
    language_policy: (
        Literal["unqualified_source_locale", "configured_sentence_language", "configured_structural_boundaries"] | None
    ) = None
    default_language: Literal["en", "ru"] | None = None
    document_processing: dict[str, JsonValue] | None = None
    source_content_sha256: str | None = None
    source_bytes: int | None = Field(default=None, ge=0)
    parsed_element_count: int | None = Field(default=None, ge=0)
    parser: dict[str, JsonValue] | None = None
    warnings: list[str] = Field(default_factory=list)
    original_content_available: Literal[False] = False


class ActiveChunkItem(ContractModel):
    chunk_id: Identifier
    order: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=32768)
    content_hash: str
    page: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ActiveChunkPageResponse(Meta):
    workspace_id: Identifier
    source_id: Identifier
    source_version_id: Identifier
    corpus_revision: Identifier
    items: list[ActiveChunkItem]
    next_cursor: str | None


class LocalSourceFileResponse(Meta):
    name: str | None = Field(max_length=255)
    can_reveal: bool
    reason: (
        Literal["not_registered", "demo_source", "root_unconfigured", "file_unavailable", "host_unavailable"] | None
    ) = None


class RevealSourceRequest(ContractModel):
    """Native selection accepts source identity in the route, never a browser path."""


class RevealSourceResponse(Meta):
    status: Literal["revealed"] = "revealed"


class ConfigurationYamlRequest(ContractModel):
    yaml: str = Field(min_length=1)


class ConfigurationSaveRequest(ConfigurationYamlRequest):
    expected_revision: str = Field(pattern=r"^config-(?:[0-9a-f]{64}|missing)$")


class ConfigurationIssueResponse(ContractModel):
    message: str
    path: str | None = None
    line: int | None = None
    column: int | None = None


class ConfigurationValidationResponse(Meta):
    valid: bool
    errors: list[ConfigurationIssueResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfigurationDocumentResponse(Meta):
    scope: Literal["application"] = "application"
    yaml: str
    revision: str
    exists: bool
    activation: Literal["active", "requires_restart"]
    max_bytes: Literal[65536] = 65536
    effective_default_language: Literal["en", "ru"]
    deployment_overrides: list[Literal["default_language"]] = Field(default_factory=list)


class ConfigurationSaveResponse(ConfigurationDocumentResponse):
    status: Literal["saved"] = "saved"

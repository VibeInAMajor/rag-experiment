"""Versioned HTTP discovery contracts independent of provider implementations."""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

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
    kind: Literal["lexical_search", "dense_search"] = "lexical_search"
    workspace_ids: list[Identifier] = Field(min_length=1, max_length=1)
    corpus_id: Identifier
    parameters: ProfileParameters = Field(default_factory=ProfileParameters)
    limits: ProfileLimits = Field(default_factory=ProfileLimits)
    score_type: Literal["bm25_raw", "postgres_ts_rank_cd", "cosine_distance"] = "bm25_raw"
    score_direction: Literal["lower_is_better"] | None = None
    embedding_profile_revision: Identifier | None = None
    index_generation: int | None = Field(default=None, ge=0)
    min_coverage: Literal[1] | None = None

    @model_validator(mode="after")
    def _profile_score(self) -> "ExecutionProfile":
        if self.kind == "dense_search":
            if self.score_type != "cosine_distance" or any(
                value is None
                for value in (
                    self.score_direction,
                    self.embedding_profile_revision,
                    self.index_generation,
                    self.min_coverage,
                )
            ):
                raise ValueError("Dense profiles require complete distance and generation semantics")
            return self
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
    upload_folders: bool = False
    document_details: bool = False
    jobs: bool = False
    agent_operations: Literal[True] | None = None


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


def _opaque_agent_id(value: str) -> str:
    if value.lower().startswith(("sk-", "bearer", "token_", "apikey", "api-key", "password", "secret")):
        raise ValueError("Use an opaque operations identifier")
    return value


def _utc_timestamp(value: str) -> str:
    datetime.fromisoformat(value)
    return value


def _public_price_source(value: str) -> str:
    source = urlsplit(value)
    hostname = source.hostname
    if (
        source.scheme != "https"
        or hostname is None
        or "." not in hostname
        or source.netloc != hostname
        or source.query
        or source.fragment
    ):
        raise ValueError("A price source must be a public HTTPS document URL")
    return value


AgentScope = Literal["local-operator"]
AgentKey = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"), AfterValidator(_opaque_agent_id)
]
AgentRevision = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}$"), AfterValidator(_opaque_agent_id)
]
AgentRunId = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"), AfterValidator(_opaque_agent_id)
]
AgentCount = Annotated[int, Field(ge=0, le=2**53 - 1)]
AgentSequence = Annotated[int, Field(ge=1, le=100_000)]
AgentMoney = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,18})?$")]
AgentTimestamp = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)$"),
    AfterValidator(_utc_timestamp),
]
AgentPriceSource = Annotated[
    str, StringConstraints(max_length=512, pattern=r"^https://[a-zA-Z0-9./_-]+$"), AfterValidator(_public_price_source)
]
AgentRunStatus = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted", "blocked"]
AgentStage = Literal["queued", "admission", "provider", "output_validation", "evidence_validation", "finalizing"]
AgentEventKind = Literal[
    "run_queued",
    "run_started",
    "stage_changed",
    "call_pending",
    "call_completed",
    "case_completed",
    "checkpoint_reused",
    "run_finished",
]
AgentReason = Literal[
    "INVALID_INPUT",
    "UNKNOWN_AGENT",
    "UNKNOWN_PROFILE",
    "UNSUPPORTED_CAPABILITY",
    "EGRESS_DISABLED",
    "MISSING_CREDENTIALS",
    "TIMEOUT",
    "RATE_LIMITED",
    "PROVIDER_FAILURE",
    "REFUSAL",
    "INCOMPLETE_OUTPUT",
    "INVALID_OUTPUT",
    "BUDGET_EXCEEDED",
    "CANCELLED",
    "RESPONSE_TOO_LARGE",
    "PRIVACY_POLICY",
    "CONFIGURATION_ERROR",
    "INTERRUPTED",
    "CHECKPOINT_REUSED",
    "JOURNAL_UNAVAILABLE",
    "MODEL_MISMATCH",
]


class AgentQualification(ContractModel):
    state: Literal["qualified", "unqualified", "blocked", "stale"]
    revision: AgentKey | None = None
    verified_at: AgentTimestamp | None = None
    reason: (
        Literal[
            "historical_pass",
            "joint_pass",
            "offline_only",
            "capacity_unverified",
            "tariff_unverified",
            "stale_evidence",
        ]
        | None
    ) = None


class AgentTariff(ContractModel):
    version: AgentKey
    provider: AgentKey
    model: AgentKey
    service_tier: AgentKey
    currency: Literal["USD"] = "USD"
    unit: Literal["per_million_tokens"] = "per_million_tokens"
    ordinary_input: AgentMoney | None = None
    cached_read: AgentMoney | None = None
    cached_write: AgentMoney | None = None
    output: AgentMoney | None = None
    source_url: AgentPriceSource | None = None
    effective_at: AgentTimestamp | None = None
    verified_at: AgentTimestamp | None = None
    cache_ttl_seconds: AgentCount | None = None
    status: Literal["verified", "stale", "unknown"]


class AgentProfileDefinition(ContractModel):
    profile_id: AgentKey
    provider: AgentKey
    model: AgentKey
    modes: list[AgentKey] = Field(min_length=1, max_length=24)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    max_estimated_input_tokens: AgentCount = Field(gt=0)
    max_output_tokens: AgentCount = Field(gt=0)
    max_request_bytes: AgentCount | None = None
    max_response_bytes: AgentCount | None = None
    timeout_seconds: AgentCount | None = None
    reserve_usd: AgentMoney | None = None
    cache_mode: AgentKey
    cache_ttl_seconds: AgentCount | None = None
    qualification: AgentQualification
    tariff: AgentTariff | None = None

    @model_validator(mode="after")
    def _tariff_identity(self) -> "AgentProfileDefinition":
        if self.tariff is not None and (self.tariff.provider, self.tariff.model) != (self.provider, self.model):
            raise ValueError("A profile tariff must match the configured provider and model")
        return self


class AgentDefinition(ContractModel):
    agent_id: Identifier
    display_name: Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9 ._-]{0,79}$")]
    runtime_revision: AgentKey
    modes: list[AgentKey] = Field(min_length=1, max_length=24)
    default_profile_id: AgentKey
    profiles: Sequence[AgentProfileDefinition] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def _references(self) -> "AgentDefinition":
        ids = {profile.profile_id for profile in self.profiles}
        if self.default_profile_id not in ids or len(ids) != len(self.profiles):
            raise ValueError("Agent profiles must have distinct IDs and a registered default")
        if any(not set(profile.modes).issubset(self.modes) for profile in self.profiles):
            raise ValueError("Agent profiles must use registered modes")
        return self


class AgentSelection(ContractModel):
    profile_id: AgentKey
    revision: Identifier


class AgentProfileItem(AgentProfileDefinition):
    selectable: bool


class AgentItem(AgentDefinition):
    profiles: list[AgentProfileItem] = Field(min_length=1, max_length=24)
    selection: AgentSelection


class AgentCatalogResponse(Meta):
    scope: AgentScope
    agents: list[AgentItem]
    history_available: bool


class AgentSelectionRequest(ContractModel):
    profile_id: AgentKey
    expected_revision: Identifier


class AgentSelectionResponse(Meta):
    scope: AgentScope
    agent_id: Identifier
    selection: AgentSelection


class AgentUsage(ContractModel):
    input_tokens: AgentCount | None = None
    ordinary_input_tokens: AgentCount | None = None
    cached_read_tokens: AgentCount | None = None
    cached_write_tokens: AgentCount | None = None
    output_tokens: AgentCount | None = None
    reasoning_tokens: AgentCount | None = None
    total_tokens: AgentCount | None = None


class AgentCall(ContractModel):
    call_id: AgentKey
    case_id: AgentKey
    mode: AgentKey | None = None
    actual_model: AgentKey | None = None
    provider_request_id: AgentKey | None = None
    requests: Literal[0, 1] | None = None
    elapsed_ms: AgentCount | None = None
    usage: AgentUsage | None = None
    estimated_cost_usd: AgentMoney | None = None
    reserve_usd: AgentMoney | None = None

    @field_validator("requests", mode="before")
    @classmethod
    def _integer_request_count(cls, value: object) -> object:
        if value is not None and type(value) is not int:
            raise ValueError("Physical requests must be an integer")
        return value


class AgentRunIdentity(ContractModel):
    agent_id: Identifier
    mode: AgentKey
    origin: Literal["evaluation", "calibration"]
    profile_id: AgentKey
    model: AgentKey
    provider: AgentKey
    runtime_revision: AgentKey
    prompt_revision: AgentRevision | None
    schema_revision: AgentRevision | None
    cache_mode: AgentKey
    tariff: AgentTariff | None = None
    selection_revision: Identifier | None = None
    planned_cases: AgentCount | None = None
    budget_usd: AgentMoney | None = None


class AgentEvent(ContractModel):
    schema_version: Literal[1]
    scope: AgentScope
    run_id: AgentRunId
    sequence: AgentSequence
    timestamp: AgentTimestamp
    kind: AgentEventKind
    stage: AgentStage | None = None
    status: AgentRunStatus | None = None
    reason: AgentReason | None = None
    case_id: AgentKey | None = None
    run: AgentRunIdentity | None = None
    call: AgentCall | None = None

    @model_validator(mode="after")
    def _event_payload(self) -> "AgentEvent":
        if (self.kind == "run_queued") != (self.run is not None):
            raise ValueError("A queued run requires its frozen identity")
        if (self.kind in {"call_pending", "call_completed"}) != (self.call is not None):
            raise ValueError("Call events require a call record")
        if self.kind in {"run_finished", "call_completed"} and self.status not in {
            "completed",
            "failed",
            "cancelled",
            "interrupted",
            "blocked",
        }:
            raise ValueError("A terminal event requires a terminal status")
        if (
            self.kind == "call_pending"
            and self.call is not None
            and any(value is not None for value in (self.call.requests, self.call.usage, self.call.estimated_cost_usd))
        ):
            raise ValueError("A pending call cannot report terminal usage")
        return self


class AgentCoverage(ContractModel):
    known_calls: AgentCount
    total_calls: AgentCount


class AgentRunItem(AgentRunIdentity):
    run_id: AgentRunId
    status: AgentRunStatus
    stage: AgentStage
    queued_at: AgentTimestamp
    started_at: AgentTimestamp | None
    finished_at: AgentTimestamp | None
    last_sequence: AgentSequence
    completed_cases: AgentCount
    failed_cases: AgentCount
    blocked_cases: AgentCount
    reused_cases: AgentCount
    physical_requests: AgentCount
    pending_calls: AgentCount
    cache_observed_requests: AgentCount
    cache_hit_requests: AgentCount
    cache_hit_percent: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    cache_read_percent: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    actual_models: list[AgentKey]
    usage: AgentUsage
    usage_coverage: AgentCoverage
    estimated_cost_usd: AgentMoney | None
    cost_coverage: AgentCoverage
    pending_reserve_usd: AgentMoney | None


class AgentRunPage(Meta):
    scope: AgentScope
    runs: list[AgentRunItem]
    next_cursor: str | None


class AgentRunDetail(Meta):
    scope: AgentScope
    run: AgentRunItem
    events: list[AgentEvent]
    next_cursor: str
    has_more: bool


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
    stage: Literal["corpus_load", "retrieval", "query_embedding", "vector_search", "projection"]
    status: Literal["success", "skipped"] = "success"
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    started_at: str | None = None
    finished_at: str | None = None


class SearchResult(ContractModel):
    chunk_id: Identifier
    source_id: Identifier
    source_version_id: Identifier
    title: str
    page: int | None = Field(default=None, ge=1)
    content: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0, allow_inf_nan=False)
    score_type: Literal["postgres_ts_rank_cd", "cosine_distance"] = "postgres_ts_rank_cd"


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
    embedding_profile_revision: Identifier | None = None
    index_generation: int | None = Field(default=None, ge=0)
    model_revision: str | None = None
    model_digest: str | None = None
    tokenizer_digest: str | None = None
    input_format_revision: str | None = None


class WorkspaceItem(ContractModel):
    workspace_id: Identifier
    name: str
    status: Literal["ready", "unavailable"]


class WorkspacePage(Meta):
    items: list[WorkspaceItem]
    next_cursor: str | None


class UploadLocation(ContractModel):
    """Display-only location in one folder selection, never a server filesystem path."""

    group_id: Identifier
    path: str = Field(min_length=1, max_length=2048)
    folder_totals: list[int] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_tree(self) -> "UploadLocation":
        parts = self.path.split("/")
        if (
            len(parts) != len(self.folder_totals) + 1
            or any(part in {"", ".", ".."} for part in parts)
            or any(character in self.path for character in ("\\", ":"))
            or any(
                ord(character) < 32 or ord(character) == 127 or 0xD800 <= ord(character) <= 0xDFFF
                for character in self.path
            )
            or any(total < 1 or total > 1000000 for total in self.folder_totals)
            or self.folder_totals != sorted(self.folder_totals, reverse=True)
        ):
            raise ValueError("Invalid upload folder location.")
        return self


class FolderState(ContractModel):
    """Recursive status of documents actually present in one corpus snapshot."""

    file_count: int = Field(ge=1)
    ready_count: int = Field(ge=0)
    status: Literal["ready", "processing", "error"]


class DocumentItem(ContractModel):
    source_id: Identifier
    title: str
    media_type: str
    status: Literal["ready", "processing", "error"]
    active_version_id: Identifier | None
    chunk_count: int = Field(ge=0)
    updated_at: str
    error_code: str | None = None
    upload_location: UploadLocation | None = None
    folder_states: list[FolderState] | None = None


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
    upload_location: UploadLocation | None = None
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

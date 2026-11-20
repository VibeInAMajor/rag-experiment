"""Versioned HTTP discovery contracts independent of provider implementations."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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
    fields: list[ErrorField] | None = None


class ErrorResponse(Meta):
    error: ApiError


class QueryParameter(ContractModel):
    type: Literal["string"] = "string"
    min_length: Literal[1] = 1
    max_length: Literal[4096] = 4096


class TopKParameter(ContractModel):
    type: Literal["integer"] = "integer"
    default: Literal[10] = 10
    minimum: Literal[1] = 1
    maximum: Literal[50] = 50


class ProfileParameters(ContractModel):
    query: QueryParameter = Field(default_factory=QueryParameter)
    top_k: TopKParameter = Field(default_factory=TopKParameter)


class ProfileLimits(ContractModel):
    max_request_bytes: Literal[32768] = 32768
    timeout_ms: Literal[10000] = 10000
    max_concurrent_searches: Literal[2] = 2
    max_corpus_chunks: Literal[10000] = 10000
    max_corpus_bytes: Literal[52428800] = 52428800


class ExecutionProfile(ContractModel):
    profile_id: Literal["bm25-v1", "postgres-keyword-v1"] = "bm25-v1"
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


class DatabaseDependencyStatus(ContractModel):
    status: Literal["unconfigured", "ready", "unavailable", "incompatible", "empty"]
    schema_revision: str | None = None
    workspace_id: Identifier | None = None
    source_count: int | None = Field(default=None, ge=1)
    chunk_count: int | None = Field(default=None, ge=1)


class Dependencies(ContractModel):
    database: DatabaseDependencyStatus = Field(default_factory=lambda: DatabaseDependencyStatus(status="unconfigured"))


class CapabilitiesResponse(Meta):
    backend_revision: Identifier
    deployment_mode: Literal["single_workspace_dev"] = "single_workspace_dev"
    service_state: ServiceState
    profiles: list[ExecutionProfile]
    features: Features = Field(default_factory=Features)
    dependencies: Dependencies = Field(default_factory=Dependencies)

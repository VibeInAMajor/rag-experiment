export const contractRevision = "rag-api-v1.0";

export type ApiMeta = {
  contract_revision: typeof contractRevision;
  request_id: string;
  trace_id: string;
};

export type ApiFailure = ApiMeta & {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    http_status: number;
    run_id?: string | null;
    job_id?: string | null;
    fields?: Array<{ field: string; code: string }> | null;
  };
};

export type LiveResponse = ApiMeta & {
  status: "alive";
  backend_revision: string;
};

export type ReadyResponse = ApiMeta & {
  status: "ready";
  backend_revision: string;
  ready_profile_ids: string[];
};

type BackendProfileBase = {
  profile_id: string;
  profile_revision: string;
  workspace_ids: string[];
  corpus_id: string;
  parameters: {
    query: { type: "string"; min_length: 1; max_length: number };
    top_k: { type: "integer"; default: number; minimum: 1; maximum: number };
  };
  limits: {
    max_request_bytes: number;
    timeout_ms: number;
    max_concurrent_searches: number;
    max_corpus_chunks: number;
    max_corpus_bytes: number;
  };
};

export type BackendProfile = BackendProfileBase &
  (
    | { kind: "lexical_search"; score_type: "postgres_ts_rank_cd" | "bm25_raw" }
    | {
        kind: "dense_search";
        score_type: "cosine_distance";
        score_direction: "lower_is_better";
        embedding_profile_revision: string;
        index_generation: number;
        min_coverage: 1;
      }
  );

export type BackendCapabilities = ApiMeta & {
  backend_revision: string;
  deployment_mode: "single_workspace_dev";
  service_state: "starting" | "running" | "stopping" | "stopped";
  profiles: BackendProfile[];
  features: {
    documents: boolean;
    search: boolean;
    upload: boolean;
    upload_folders?: boolean;
    document_details: boolean;
    jobs: boolean;
    agent_operations?: boolean;
  };
  pdf_ingestion: PdfIngestionCapabilities;
  dependencies: {
    database: {
      status:
        "unconfigured" | "ready" | "unavailable" | "incompatible" | "empty";
      schema_revision?: string | null;
      workspace_id?: string | null;
      source_count?: number | null;
      chunk_count?: number | null;
    };
  };
};

export type AgentSelection = { profile_id: string; revision: string };
export type AgentMoney = string | null;
export type AgentTariff = {
  version: string;
  provider: string;
  model: string;
  service_tier: string;
  currency: "USD";
  unit: "per_million_tokens";
  ordinary_input: AgentMoney;
  cached_read: AgentMoney;
  cached_write: AgentMoney;
  output: AgentMoney;
  source_url: string | null;
  effective_at: string | null;
  verified_at: string | null;
  cache_ttl_seconds: number | null;
  status: "verified" | "stale" | "unknown";
};
export type AgentProfile = {
  profile_id: string;
  provider: string;
  model: string;
  modes: string[];
  reasoning_effort: string | null;
  max_estimated_input_tokens: number;
  max_output_tokens: number;
  max_request_bytes: number | null;
  max_response_bytes: number | null;
  timeout_seconds: number | null;
  reserve_usd: AgentMoney;
  cache_mode: string;
  cache_ttl_seconds: number | null;
  qualification: {
    state: "qualified" | "unqualified" | "blocked" | "stale";
    revision: string | null;
    verified_at: string | null;
    reason: string | null;
  };
  tariff: AgentTariff | null;
  selectable: boolean;
};
export type AgentOperationsAgent = {
  agent_id: string;
  display_name: string;
  runtime_revision: string;
  modes: string[];
  default_profile_id: string;
  selection: AgentSelection;
  profiles: AgentProfile[];
};
export type AgentCatalog = ApiMeta & {
  scope: "local-operator";
  history_available: boolean;
  agents: AgentOperationsAgent[];
};
export type AgentSelectionResult = ApiMeta & {
  scope: "local-operator";
  agent_id: string;
  selection: AgentSelection;
};

export const agentRunStatuses = [
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
  "interrupted",
  "blocked",
] as const;
export type AgentRunStatus = (typeof agentRunStatuses)[number];
export type AgentUsage = {
  input_tokens: number | null;
  ordinary_input_tokens: number | null;
  cached_read_tokens: number | null;
  cached_write_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  total_tokens: number | null;
};
type AgentCoverage = { known_calls: number; total_calls: number };
export type AgentRun = {
  run_id: string;
  agent_id: string;
  mode: string;
  origin: "evaluation" | "calibration";
  profile_id: string;
  model: string;
  provider: string;
  runtime_revision: string;
  prompt_revision: string | null;
  schema_revision: string | null;
  cache_mode: string;
  tariff: AgentTariff | null;
  planned_cases: number | null;
  budget_usd: AgentMoney;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: AgentRunStatus;
  stage: string | null;
  last_sequence: number;
  completed_cases: number;
  reused_cases: number;
  failed_cases: number;
  blocked_cases: number;
  actual_models: string[];
  selection_revision: string | null;
  physical_requests: number;
  pending_calls: number;
  cache_observed_requests: number;
  cache_hit_requests: number;
  cache_hit_percent: number | null;
  cache_read_percent: number | null;
  usage: AgentUsage | null;
  usage_coverage: AgentCoverage;
  estimated_cost_usd: AgentMoney;
  cost_coverage: AgentCoverage;
  pending_reserve_usd: AgentMoney;
};
export type AgentEvent = {
  run_id: string;
  sequence: number;
  timestamp: string;
  kind:
    | "run_queued"
    | "run_started"
    | "stage_changed"
    | "call_pending"
    | "call_completed"
    | "case_completed"
    | "checkpoint_reused"
    | "run_finished";
  stage: string | null;
  status: AgentRunStatus | null;
  reason: string | null;
  case_id: string | null;
  call: {
    call_id: string;
    case_id: string;
    mode: string | null;
    actual_model: string | null;
    provider_request_id: string | null;
    requests: number | null;
    elapsed_ms: number | null;
    usage: AgentUsage | null;
    estimated_cost_usd: AgentMoney;
    reserve_usd: AgentMoney;
  } | null;
};
export type AgentRunPage = ApiMeta & {
  scope: "local-operator";
  runs: AgentRun[];
  next_cursor: string | null;
};
export type AgentRunDetail = ApiMeta & {
  scope: "local-operator";
  run: AgentRun;
  events: AgentEvent[];
  next_cursor: string | null;
  has_more: boolean;
};

export type WorkspaceItem = {
  workspace_id: string;
  name: string;
  status: "ready" | "unavailable";
};

export type WorkspacePage = ApiMeta & {
  items: WorkspaceItem[];
  next_cursor: string | null;
};

export type SearchRequest = {
  query: string;
  top_k: number;
  profile_id: string;
  expected_profile_revision: string;
};

export type SearchResult = {
  chunk_id: string;
  source_id: string;
  source_version_id: string;
  title: string;
  page?: number | null;
  content: string;
  rank: number;
  score: number;
  score_type: "postgres_ts_rank_cd" | "cosine_distance";
};

export type SearchResponse = ApiMeta & {
  mode: "live";
  workspace_id: string;
  corpus_revision: string;
  profile_id: string;
  profile_revision: string;
  run_id: string;
  status: "success";
  duration_ms: number;
  embedding_profile_revision?: string;
  index_generation?: number;
  model_revision?: string;
  model_digest?: string;
  tokenizer_digest?: string;
  input_format_revision?: string;
  stages: Array<{
    stage:
      | "corpus_load"
      | "retrieval"
      | "query_embedding"
      | "vector_search"
      | "projection";
    status: "success" | "skipped";
    duration_ms: number;
    started_at?: string;
    finished_at?: string;
  }>;
  results: SearchResult[];
};

export type UploadLocation = {
  group_id: string;
  path: string;
  folder_totals: number[];
};

export type DocumentItem = {
  source_id: string;
  title: string;
  media_type: string;
  status: "ready" | "processing" | "error";
  active_version_id: string | null;
  chunk_count: number;
  updated_at: string;
  error_code?: string | null;
  upload_location?: UploadLocation | null;
  folder_states?:
    | {
        file_count: number;
        ready_count: number;
        status: "ready" | "processing" | "error";
      }[]
    | null;
};

export type DocumentPage = ApiMeta & {
  workspace_id: string;
  corpus_revision: string;
  items: DocumentItem[];
  next_cursor: string | null;
};

export type PdfIngestionCapabilities = {
  available: boolean;
  text_layer: boolean;
  page_provenance: boolean;
  table_rows: boolean;
  original_evidence: false;
  ocr: false;
  visual_understanding: false;
  visual_detection_coverage: "unverified";
  max_bytes: 8388608;
  max_pages: 32;
};

export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type DocumentDetail = ApiMeta &
  Omit<DocumentItem, "error_code"> & {
    workspace_id: string;
    corpus_revision: string;
    processing_profile?: Record<string, JsonValue> | null;
    processing_profile_fingerprint?: string | null;
    ingestion_policy_revision?: string | null;
    language_policy?:
      | "unqualified_source_locale"
      | "configured_sentence_language"
      | "configured_structural_boundaries"
      | null;
    default_language?: "en" | "ru" | null;
    document_processing?: Record<string, JsonValue> | null;
    source_content_sha256?: string | null;
    source_bytes?: number | null;
    parsed_element_count?: number | null;
    parser?: Record<string, JsonValue> | null;
    warnings: string[];
    original_content_available: false;
  };

export type ActiveChunkItem = {
  chunk_id: string;
  order: number;
  content: string;
  content_hash: string;
  page?: number | null;
  section_path: string[];
  metadata: Record<string, JsonValue>;
};

export type ActiveChunkPageResponse = ApiMeta & {
  workspace_id: string;
  source_id: string;
  source_version_id: string;
  corpus_revision: string;
  items: ActiveChunkItem[];
  next_cursor: string | null;
};

export type IngestionStageTiming = {
  stage: "parsing" | "chunking" | "publication";
  duration_ms: number;
};

export type IngestionResponse = ApiMeta & {
  workspace_id: string;
  source_id: string;
  source_version_id: string;
  job_id: string;
  outcome: "created" | "updated" | "unchanged";
  status: "completed";
  chunk_count: number;
  corpus_revision: string;
  stages: IngestionStageTiming[];
  replayed: boolean;
};

export type IngestionJobResponse = ApiMeta & {
  workspace_id: string;
  job_id: string;
  source_id: string;
  source_version_id: string | null;
  reserved_version_id: string;
  status:
    "pending" | "parsing" | "chunking" | "publishing" | "completed" | "failed";
  stage:
    "pending" | "parsing" | "chunking" | "publishing" | "completed" | "failed";
  retryable: boolean;
  error_code: string | null;
  chunk_count: number | null;
  outcome: "created" | "updated" | "unchanged" | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  stages: IngestionStageTiming[];
};

export type LocalSourceFile = ApiMeta & {
  name: string | null;
  can_reveal: boolean;
  reason?:
    | "not_registered"
    | "demo_source"
    | "root_unconfigured"
    | "file_unavailable"
    | "host_unavailable"
    | null;
};

export type SourceRevealResponse = ApiMeta & {
  status: "revealed";
};

export type ConfigurationDocument = ApiMeta & {
  scope: "application";
  yaml: string;
  revision: string;
  exists: boolean;
  activation: "active" | "requires_restart";
  max_bytes: 65536;
  effective_default_language: "en" | "ru";
  deployment_overrides: "default_language"[];
};

export type ConfigurationIssue = {
  message: string;
  path: string | null;
  line: number | null;
  column: number | null;
};

export type ConfigurationValidation = ApiMeta & {
  valid: boolean;
  errors: ConfigurationIssue[];
  warnings: string[];
};

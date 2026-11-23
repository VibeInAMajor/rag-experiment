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

export type BackendProfile = {
  profile_id: string;
  profile_revision: string;
  kind: "lexical_search";
  workspace_ids: string[];
  corpus_id: string;
  score_type: "postgres_ts_rank_cd" | "bm25_raw";
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

export type BackendCapabilities = ApiMeta & {
  backend_revision: string;
  deployment_mode: "single_workspace_dev";
  service_state: "starting" | "running" | "stopping" | "stopped";
  profiles: BackendProfile[];
  features: {
    documents: boolean;
    search: boolean;
    upload: boolean;
    document_details: boolean;
    jobs: boolean;
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
  score_type: "postgres_ts_rank_cd";
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
  stages: Array<{
    stage: "corpus_load" | "retrieval" | "projection";
    status: "success" | "skipped";
    duration_ms: number;
  }>;
  results: SearchResult[];
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

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
  profile_id: "bm25-v1" | "postgres-keyword-v1" | "postgres-fts-baseline";
  profile_revision: string;
  kind: "lexical_search";
  workspace_ids: string[];
  corpus_id: string;
  score_type: "postgres_ts_rank_cd" | "bm25_raw";
  parameters: {
    query: { type: "string"; min_length: 1; max_length: 4096 };
    top_k: { type: "integer"; default: 10; minimum: 1; maximum: 50 };
  };
  limits: {
    max_request_bytes: 32768;
    timeout_ms: 10000;
    max_concurrent_searches: 2;
    max_corpus_chunks: 10000;
    max_corpus_bytes: 52428800;
  };
};

export type BackendCapabilities = ApiMeta & {
  backend_revision: string;
  deployment_mode: "single_workspace_dev";
  service_state: "starting" | "running" | "stopping" | "stopped";
  profiles: BackendProfile[];
  features: { documents: boolean; search: boolean };
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
  profile_id: "postgres-fts-baseline";
  profile_revision: "postgres-fts-baseline-r1";
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

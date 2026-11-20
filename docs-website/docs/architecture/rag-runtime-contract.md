---
title: RAG runtime and API v1 contract
description: Canonical decisions and integration boundaries for the local RAG Workbench.
---

# RAG runtime and API v1 contract

**Created:** 2026-11-20  
**Updated:** 2026-11-21
**Decision status:** Accepted implementation contract; discovery bootstrap implemented, retrieval API remains planned.  
**Contract revision:** `rag-api-v1.0`

This is the single source of truth for RAG runtime and Workbench integration. It supersedes runtime choices in the [dated architecture reference](../tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md). The [Workbench README](../../../apps/workbench/web/README.md) describes what can run today. The PostgreSQL foundation decision dated 2026-11-21 supersedes the earlier in-memory BM25 first-slice proposal: the next HTTP retrieval slice must rank persisted rows directly in PostgreSQL and use its truthful native FTS score type. No HTTP retrieval, real embedding or ANN result is implied by the storage foundation.

## Current bootstrap

The independent [Workbench API](../../../apps/workbench/api/README.md) implements the three health/discovery routes in section 4. From the repository root, run `hatch run workbench-api:serve`; the default listener is `127.0.0.1:8011`. Its dependencies live in a detached Hatch environment and do not change the Haystack library dependencies. Stop it with Ctrl+C.

Liveness is 200, overall readiness remains 503 `NOT_READY`, and capabilities return `profiles: []`, `features: {documents: false, search: false}`. Configuring `WORKBENCH_DB_DSN` composes the PostgreSQL persistence adapter; `dependencies.database` reports `unconfigured`, `ready`, `empty`, `incompatible` or `unavailable`. A ready database is necessary storage evidence, not an executable HTTP search profile. There is no workspace/document/search route or readiness-enabling flag yet. The existing validator on port 8010 and standalone preview UI remain independent. Follow the [PostgreSQL runbook](postgresql-foundation.md) for explicit migrations, seed and operations.

The [published OpenAPI schema](../../../apps/workbench/api/openapi.json) describes implemented routes and response models. Capabilities add `service_state` (`starting`, `running`, `stopping`, `stopped`), `features` (`documents`, `search` booleans), and a typed `dependencies.database` status with certified revision/counts when ready. These describe actual availability; constructor mappings are never executable profiles. Configuration, operational logging and startup details are in the API runbook.

## 1. Evidence and resolved contradictions

Paths below are relative to the repository root; links identify the actual owners.

| Evidence inspected | Observation | Resolution |
| --- | --- | --- |
| [Historical architecture](../tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md) | Original v1.1 selected OpenSearch and Ollama embeddings | Historical decisions retained there; PostgreSQL + pgvector and TEI below supersede them |
| [Workbench catalog](../../../apps/workbench/web/src/domain/catalog.ts) | Contains the Haystack class labels `OpenAITextEmbedder`, `OpenAIDocumentEmbedder`, `InMemoryBM25Retriever` and `PgvectorEmbeddingRetriever` | These describe current editor metadata, not selected providers. Embeddings are planned through local TEI/Qwen; its endpoint is not yet bound in the constructor validator |
| [Graph implementation](../../../apps/workbench/web/src/domain/graph.ts) and [tests](../../../apps/workbench/web/src/domain/graph.test.ts) | Workbench `schemaVersion: 1`; safe JSON import/export; incomplete drafts and cycles can be saved | Keep this editor format unchanged; it is not Haystack YAML or an executable API |
| [Preview implementation](../../../apps/workbench/web/src/domain/preview.ts) | Results, scores, node progression and timings come from fixtures | Preserve explicit preview provenance; never substitute it after a live error |
| [Validator README](../../../apps/workbench/validator/README.md), [registry](../../../apps/workbench/validator/registry.py), [validation orchestration](../../../apps/workbench/validator/validator.py) | Real construction/connect/input checks, but no execution, warm-up or durable binding | Retain the existing validation-only contract; validation success is not live readiness |
| [BM25 retriever](../../../haystack/components/retrievers/in_memory/bm25_retriever.py) and [in-memory store](../../../haystack/document_stores/in_memory/document_store.py) | Genuine BM25 implementation exists in the framework | It is not used as a Live corpus or silently substituted for PostgreSQL FTS; any later BM25 profile needs a separate qualified decision |
| [Persistence port](../../../apps/workbench/api/persistence.py), [PostgreSQL adapter](../../../apps/workbench/api/postgres.py) and [migrations](../../../apps/workbench/api/db_migrations.py) | Durable scoped records, forced RLS, native FTS and exact synthetic-vector storage are implemented | Only storage primitives are ready; HTTP retrieval and real embedding qualification remain separate |
| [Splitter](../../../haystack/components/preprocessors/document_splitter.py) | Token splitting defaults to tiktoken `o200k_base` | Current token splitting is not evidence of Qwen-compatible token counts |

Both the constructor validator and independent API bootstrap exist. The PostgreSQL registry/persistence adapter is implemented; search, ingestion and workspace data HTTP routes are still absent. The implemented `/api/v1/health/*` and `/api/v1/capabilities` routes are separate from `/api/pipelines/validate`; the workspace/search HTTP interface below remains planned.

## 2. Canonical runtime decisions

| Concern | Selected direction | Qualification still required |
| --- | --- | --- |
| Durable search data | PostgreSQL 17.10 + pgvector 0.8.2 in a digest-pinned Docker image; app-owned SQL adapter | Container/restart, migration, FTS and synthetic-vector evidence is in the foundation task; no throughput or ANN claim |
| Metadata/version registry | PostgreSQL relational workspace/source/version/chunk records, composite FKs and forced RLS | Job/cache extensions and production authorization remain future work |
| First lexical backend | PostgreSQL `simple` configuration, stored `tsvector`, GIN and `ts_rank_cd`; planned profile `postgres-keyword-v1`, score `postgres_ts_rank_cd` | Storage primitive tested; implement and qualify the HTTP retrieval slice before advertising it |
| Genuine BM25 | Deferred; `bm25-v1` remains reserved for actual BM25 semantics | No Live in-memory corpus/fallback; any PostgreSQL BM25 extension needs a separate deployment/licensing decision |
| Embedding transport | Existing local TEI service; deployment target `http://127.0.0.1:8081` | Recheck health, server schema, runtime revision and served model before integration; this task performs no inference |
| Embedding model | Qwen3-Embedding-4B, full **2560** dimensions, normalized vectors and cosine search | Pin model/tokenizer revisions and prove actual output shape, finite values and normalization with a logged probe |
| Embedding API | Prefer TEI's OpenAI-compatible `/v1/embeddings`, isolated behind an adapter | Verify served model identifier, instruction handling, usage and error payloads. Native TEI transport may replace it behind the same port after equivalent tests |
| Dense representation | Nullable dimensionless `vector`, registry-enforced profile dimensions, exact cosine storage primitive; no ANN index | Synthetic 3/2560 tests prove storage only. Actual model dimension and any halfvec/ANN design need later qualification; never truncate vectors |
| Generation | Deferred until retrieval MVP; agreed later local model `qwen3.8:27b` | No chat, generator, Ollama dependency or generation endpoint in the first slice |

“Separate registry” means separate authoritative relational responsibilities, not a second database engine. PostgreSQL owns chunk text/provenance and all durable application data. The selected adapter uses those same chunk rows for FTS and vectors; there is no second document table or Live in-memory fallback. Do not reuse another application's PostgreSQL database, credentials or tables.

The first slice uses the explicitly seeded development corpus in PostgreSQL. A future live search must query those stored passages with native FTS; a seed corpus is not permission to return precomputed answers. Seed is explicit, idempotent and refuses non-demo or modified content. A missing database or failed corpus load fails dependency readiness/search; it never triggers fixture fallback.

### Tokenization and embedding profile identity

There are two different tokenizer responsibilities:

- **Native lexical search:** PostgreSQL `simple` configuration, with PostgreSQL parsing/lowercasing and no language-specific stemming promise. Identifier and Cyrillic token tests are recorded in the foundation suite. This is distinct from the framework BM25 tokenizer and from model tokens.
- **Embeddings:** use the tokenizer files from the pinned Qwen model revision for chunk size and admission estimates, including instructions and special tokens. The current generic splitter configuration does not establish parity. Qualify the counting path against the served runtime before enabling embeddings; silent truncation is prohibited.

Proposed query instruction, to verify against the actual service configuration:

```text
Instruct: Given a web search query, retrieve relevant passages that answer the query
Query: {query}
```

Document input has no query instruction. Apply the query instruction exactly once. The profile fingerprint includes model and tokenizer revision, pooling, normalization, precision/representation, dimension, input transformation and instructions. Batch/request token limits remain unqualified until inspected and probed; no throughput or TPM value is approved here. A profile change requires a new compatible index/cache generation and reindexing, not reuse based on text hash alone.

The [model card](https://huggingface.co/Qwen/Qwen3-Embedding-4B) documents the model's full dimension and instruction-aware usage; [TEI's supported models](https://huggingface.co/docs/text-embeddings-inference/supported_models) lists Qwen3. These are upstream compatibility evidence, not a local runtime test. [pgvector documentation](https://github.com/pgvector/pgvector) distinguishes ANN indexing limits for `vector` and `halfvec`; the proposed half-precision representation still needs application qualification.

## 3. First executable profile and graph boundary

The next eligible HTTP slice is `postgres-keyword-v1`: one query, native PostgreSQL full-text ranking, and result projection over authorized persisted active chunks. Its score type is `postgres_ts_rank_cd`; raw values are not probabilities or BM25. Defaults remain `top_k = 10`, range 1–50, with query/HTTP bounds below. It has no embedding, RRF, generation or ingestion stage. The current API advertises no profiles until that HTTP slice is implemented and tested.

The storage foundation uses an application-owned persistence port and a PostgreSQL adapter behind it. `pgvector-haystack==8.2.1` was exercised with repository Haystack 3.5.0 on a disposable database. Its standard keyword and synthetic-vector operations work, but its flat document table and implicit table/index initialization do not satisfy migration-owned composite workspace/source/version FKs, forced RLS and transactional publication. Reusing it would require a second corpus or invasive overriding. The narrow SQL adapter therefore owns the single authoritative table layout. Evidence and exact commands are in the PostgreSQL runbook.

All reads and writes carry a server-resolved workspace context. Publication stages a full replacement and atomically changes the active version. Queries constrain workspace, active version and, for vectors, compatible embedding profile; user filters cannot overwrite those conditions. Pool, connection, statement and lock limits are bounded. No client graph JSON, Python class path, SQL, YAML, model identifier, provider URL or credential is executable input.

`bm25-v1` remains a distinct reserved profile name for genuine BM25. The prior in-memory BM25-first proposal is superseded by the PostgreSQL foundation decision; neither `ts_rank_cd` nor the current UI BM25 node may be presented as that algorithm. The pending retrieval task must be reconciled before implementation: persisted corpus, native lexical name/score, canonical request/error fields and no memory-only seed.

### Workbench eligibility

The frontend remains a standalone preview. Its existing indexing and hybrid templates, including the BM25-labeled node, are not Live execution bindings. A subsequent UI integration task must introduce a truthful native-keyword node/profile mapping and a strict exact-shape eligibility check; unsupported graphs return `UNSUPPORTED_GRAPH_PROFILE` rather than dropping branches or silently replacing algorithms.

Query/result nodes remain API projections rather than invented Haystack pass-through components. Constructor validation is separate from profile eligibility and data readiness. Reuse the existing catalog/domain structures, `importPipeline`, `portableGraph` and structural checks; preserve graph `schemaVersion: 1`. The selected node parameters must map explicitly to the advertised backend profile. Scope/collection labels and UI Settings do not grant database access.

## 4. API v1 types and protocol

Only the three health/discovery endpoints are implemented by the bootstrap; workspace/document/search endpoints remain future work. JSON uses UTF-8 and snake_case. Unknown request fields are rejected. Identifiers are opaque server-issued ASCII strings matching `[A-Za-z0-9_-]{1,128}`; examples are illustrative. Times are RFC 3339 UTC, durations are finite nonnegative milliseconds. Counts/ranks/limits are integers, booleans cannot stand in for numbers. Responses include `contract_revision: "rag-api-v1.0"`, `request_id`, and `trace_id`. Every response also returns `X-Request-ID`; the server generates IDs and does not trust arbitrary caller IDs for logging. Use W3C trace context only after validating it under the deployment's trace policy.

The service binds to loopback for the first development slice. All data endpoints require the server's development identity or later authenticated principal. Workspace listing grants no access by itself. Authorization precedes resource lookup, search and pagination. Health responses reveal no DSNs, filesystem paths, credentials or provider exceptions.

```typescript
type Meta = {
  contract_revision: "rag-api-v1.0";
  request_id: string;
  trace_id: string;
};
type StageTiming = {
  stage: "corpus_load" | "retrieval" | "projection";
  status: "success" | "error" | "skipped";
  duration_ms: number;
};
type ErrorBody = Meta & {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    http_status: number;
    run_id?: string;
    fields?: { field: string; code: string }[];
  };
};
```

### Health

| Endpoint | Success body, in addition to Meta | Failure |
| --- | --- | --- |
| `GET /api/v1/health/live` | `{status: "alive", backend_revision: string}` | 503 `SERVICE_UNAVAILABLE` during shutdown; it does not check dependencies |
| `GET /api/v1/health/ready` | `{status: "ready", backend_revision: string, ready_profile_ids: string[]}` | 503 `NOT_READY` if no profile can execute against its complete authorized corpus |

Readiness checks configured PostgreSQL access, registry/schema compatibility and committed active corpus rows for the configured development workspace. TEI is not a readiness dependency for native lexical search. Check state without running inference on every request. A failed unrelated future adapter cannot disable a healthy approved lexical profile. Liveness remains independent of data/provider failures.

### Capabilities

`GET /api/v1/capabilities` returns Meta plus:

```typescript
type Capabilities = {
  backend_revision: string;
  deployment_mode: "single_workspace_dev"; // first slice only
  profiles: {
    profile_id: string;
    profile_revision: string;
    kind: "lexical_search";
    workspace_ids: string[];
    corpus_id: string;
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
    score_type: "bm25_raw" | "postgres_ts_rank_cd";
  }[];
};
```

List only executable, qualified profiles available to the caller at response time. The current API returns `profiles: []`; it may list `postgres-keyword-v1` only after the HTTP implementation and qualification gates pass. `bm25-v1` is reserved for genuine BM25, never a native FTS alias. `backend_revision` identifies deployed application/configuration revision; `profile_revision` identifies immutable execution semantics. Neither is the validator's `workbench-components-v1`. UI must reject an unknown contract revision, refresh changed capabilities and disable Live for profiles absent from them. Availability can change after discovery; the server checks again at execution. Provider substitution preserves the public request shape, but semantic/ranking changes need a new profile revision and qualification.

### Workspaces and documents

`GET /api/v1/workspaces?limit=50&cursor=...` returns Meta plus:

```typescript
type WorkspacePage = {
  items: { workspace_id: string; name: string; status: "ready" | "unavailable" }[];
  next_cursor: string | null;
};
```

`GET /api/v1/workspaces/{workspace_id}/documents?limit=50&cursor=...` returns Meta plus:

```typescript
type DocumentPage = {
  workspace_id: string;
  corpus_revision: string;
  items: {
    source_id: string;
    title: string;
    media_type: string;
    status: "ready" | "processing" | "error";
    active_version_id: string | null;
    chunk_count: number;
    updated_at: string;
    error_code?: string;
  }[];
  next_cursor: string | null;
};
```

Both list endpoints allow integer `limit` 1–100 (default 50) and an optional opaque cursor up to 512 characters. Stable ordering is by server ID; cursor is bound to authorized scope and list snapshot. Invalid/expired cursors return 400 `INVALID_CURSOR`; clients restart listing. Empty pages are successful with `items: []`, `next_cursor: null`. Document status `error` contains a safe code, not raw parsing errors; an old active version may remain usable while processing a replacement. No raw filesystem paths or file-download URLs are exposed by this contract.

### Search

`POST /api/v1/workspaces/{workspace_id}/search`, `Content-Type: application/json`:

```json
{"query":"How are updates published?","top_k":10,"profile_id":"postgres-keyword-v1","expected_profile_revision":"postgres-keyword-v1-r1"}
```

All four fields are required. `query` is trimmed for execution, then must contain 1–4096 Unicode code points; count before any provider instruction. `top_k` is an integer 1–50. `profile_id` selects an executable backend-approved profile, never a model name. `expected_profile_revision` must equal the revision last discovered in capabilities; a mismatch returns 409 `PROFILE_NOT_AVAILABLE` before execution, requiring refresh. It does not pin the corpus: each run returns the actual certified `corpus_revision`. Total request body is at most 32 KiB, including JSON encoding. No filters, graph or provider overrides are accepted in v1. Headers/transport limits and concurrency quotas are enforced server-side before expensive work.

HTTP 200 returns Meta plus:

```typescript
type SearchResponse = {
  mode: "live";
  workspace_id: string;
  corpus_revision: string;
  profile_id: string;
  profile_revision: string;
  run_id: string;
  status: "success";
  duration_ms: number;
  stages: StageTiming[];
  results: {
    chunk_id: string;
    source_id: string;
    source_version_id: string;
    title: string;
    page?: number;
    content: string;
    rank: number;
    score: number;
    score_type: "bm25_raw" | "postgres_ts_rank_cd";
  }[];
};
```

`results` has 0–`top_k` items, unique `chunk_id`, ordered by descending raw score; ties are broken by `chunk_id` over the complete bounded candidate set before truncation. Rank is contiguous and one-based. Scores must be finite; raw lexical values are not percentages, probabilities or comparable across profiles/corpora. Do not clamp or normalize them in the UI. Missing page provenance omits `page`; a present page is a positive one-based integer. Content is the stored passage, rendered as text with unsafe HTML escaped. A successful zero-hit query has `results: []`, not an error. No response contains generated answers.

All hits must come from the same certified corpus revision and authorized active versions. Projection verifies source/version access again before returning content. The first slice returns full stored chunk content up to a corpus-admission ceiling of 32,768 Unicode code points per chunk; larger chunks fail corpus qualification rather than get silently shortened. Search never returns unauthorized hits followed by client-side filtering.

### Stable error semantics

Every non-2xx response uses ErrorBody; its `http_status` equals the HTTP status. Messages are safe fixed summaries, `fields` identifies invalid request fields without echoing their values. No fake successful/partial results accompany errors.

| HTTP | Code | Retryable | Meaning |
| --- | --- | --- | --- |
| 400 | `INVALID_JSON`, `INVALID_REQUEST`, `INVALID_CURSOR` | false | Bad encoding/shape, extra fields, invalid limits or cursor |
| 401 | `UNAUTHENTICATED` | false | Caller identity required; authenticate before retry |
| 403 | `FORBIDDEN` | false | Authenticated caller cannot use the requested operation |
| 404 | `WORKSPACE_NOT_FOUND` | false | Workspace absent or not visible; same outward behavior prevents enumeration |
| 409 | `PROFILE_NOT_AVAILABLE` | false | Unknown/unapproved profile or revision changed; refresh capabilities before resubmitting |
| 413 | `PAYLOAD_TOO_LARGE` | false | Request body exceeds the advertised byte limit |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | false | Search requires JSON |
| 429 | `SEARCH_BUSY` | true | Two admitted searches already active; include bounded `Retry-After` seconds |
| 503 | `NOT_READY`, `DEPENDENCY_UNAVAILABLE`, `SERVICE_UNAVAILABLE` | true | No certified corpus, database failure or service shutdown |
| 504 | `SEARCH_TIMEOUT` | true | Ten-second admitted-operation deadline elapsed |
| 500 | `INTERNAL_ERROR` | false | Sanitized unexpected failure; correlate by trace ID |

Missing/malformed fields return 400 rather than framework-specific validation payloads. Methods outside the endpoint contract return 405 `METHOD_NOT_ALLOWED`. Unexpected routing errors return 404 `ENDPOINT_NOT_FOUND`. Retryable is advice, not permission for unbounded retries. Search is read-only; a retry creates a new run ID. No idempotency guarantee, streaming, asynchronous jobs or partial-success mode is defined in v1. Cancellation/deadline must stop admission and propagate to owned work; blocking calls must be bounded so a timed-out request does not release a concurrency slot while work continues unaccounted.

## 5. Run, provenance and timing meanings

- **Preview:** existing deterministic browser fixtures, separate in-memory `PreviewRun` data. Fixture node outputs/timings/scores do not acquire live provenance by passing validation.
- **Live:** an authorized API call actually runs the approved retrieval profile over the identified persisted corpus. A development seed corpus still requires a real PostgreSQL query. Provider or storage failures remain errors, with no preview fallback.
- **Run ID:** new server-generated opaque ID per admitted search, including failed executions. Shape/auth failures before admission have no run ID. Return it on execution errors where allocated. It does not imply a persisted run-history route; future storage/retention is a separate task.
- **Trace ID:** server-owned correlation identity across API, stages and adapters; present even on rejected requests. It differs from a run ID and never embeds query text or secrets. A trace ID does not promise that an external tracing collector is deployed.
- **Source identity:** `source_id` is stable server registry identity within a workspace, independent of display title/path. Rename changes metadata, not identity. `source_version_id` identifies a specific immutable parsed content version; `chunk_id` identifies an occurrence within that version. Clients cannot mint authoritative IDs or permissions by editing graphs/Settings.
- **Embedding cache:** eventual workspace-scoped key over exact transformed input plus the full embedding fingerprint. It is distinct from chunk occurrence identity; no cross-workspace reuse in the initial implementation.
- **Duration:** monotonic server time from admitted search start through result projection or failure, excluding network transit and pre-admission rejection. Health/list calls are not runs. Stage durations are measured exclusive sequential intervals; stages are corpus load (including authorization/snapshot acquisition), retrieval and projection. Their sum is at most total duration, with overhead explaining the remainder. A ready cached snapshot can have a short corpus-load stage. Unexecuted stages are `skipped` with duration zero; no invented node durations are inferred from totals.

Future dense scores must use an explicitly versioned `score_type` (for example, cosine similarity, not an ambiguous distance). RRF scores are fusion scores over ranks, not sums of BM25/cosine values. Neither score type is enabled by this first-slice union; extend and qualify the contract when those profiles are introduced.

## 6. Ownership, security and observability

Application-owned orchestration depends on neutral search/profile and corpus repository contracts; provider adapters depend inward on those contracts. SDK imports, TEI URLs, model names, SQL handles and Haystack class labels stay in adapter/configuration code. Use existing Haystack component and pipeline APIs behind that boundary; do not build a second graph interpreter. Add interfaces only for the actual corpus-store and search-adapter substitution/test seams.

Server identity and authorization select the workspace, allowed profiles, source versions and corpus. UI Settings, collection labels and client filters grant no authority. SQL queries are scoped and parameterized; enforce both workspace and active-version constraints. A BM25 store loaded with all tenants followed by user-editable filters is prohibited. Multi-workspace production readiness requires authorization and negative isolation tests against at least three workspaces, including revocation and stale snapshots. The initial single-workspace loopback development identity is **not production multi-tenant security**; a remote deployment requires its own authentication, TLS, origin/CSRF policy and per-principal limits.

Log only request/trace/run IDs, authorized opaque workspace ID where policy permits, profile/backend/corpus revisions, stage status/duration, result counts and stable error codes. Redact query text, chunk contents, file names/paths, authorization headers, DSNs, keys and raw exceptions by default; no graph payload logging. Exception detail belongs only in separately access-controlled diagnostics after redaction. Return user-safe errors without stack traces.

Deployment owner defines retention and deletion before enabling persistent logs/traces or run storage: purpose, access control, TTL, backups and source deletion handling must be documented in the implementation/deployment task. First local development default is process-local diagnostics with no payload capture or automatic external trace export; persistent retention has no implicit unlimited default. IDs are correlation data, not permission tokens. Do not reuse another application's Langfuse instance without an explicit integration decision.

## 7. Qualification gates and deferred decisions

| Gate | Required evidence in the implementing task |
| --- | --- |
| API schemas | Machine-readable schema derived from this contract; validate requests, responses, example payloads and errors; unknown fields/types rejected; capabilities and route tests |
| Native lexical HTTP slice | Logged real API run over known stored passages, expected ranking/source IDs and postgres_ts_rank_cd scores, zero hits, no fixture fallback, bounded corpus and timeout/concurrency tests |
| UI integration | Exact three-node matcher, unsupported graph rejection, capabilities changes, live/preview distinction, stale/cancelled responses; retain existing graph round-trip/security tests |
| PostgreSQL registry | Pinned Docker images, migrations, backup/recovery, active-version publication, workspace isolation and permissions tests |
| TEI compatibility | Record health/info/schema and pinned model/tokenizer fingerprint, then approved logged inference probes for dimension/normalization, query prefix once, tokenizer parity, no truncation, failure/usage handling |
| pgvector representation | Confirm adapter/extension compatibility for 2560 dimensions, cosine HNSW using qualified representation, round-trip precision and recall evaluation; retain open status until proven |
| Scaling and hybrid | Corpus/memory/rebuild limits, genuine durable BM25 decision, dense/BM25/RRF baselines, shared endpoint admission and measured completed throughput; reranker only after comparison |

The original architecture reconciliation ran no database, model, benchmark or API execution. Subsequent bootstrap and PostgreSQL tasks record their own HTTP/schema, storage, synthetic-vector and restart evidence. These checks do not qualify real embeddings, ANN or HTTP retrieval. No provider or integration version is certified solely by upstream docs or by constructor validation. Python commands must use Hatch from the repository root and actual implementation paths; do not copy a generic `src tests` command. Existing validator checks are described in its README and prove only that boundary.

The historical Delta Detector/TPM references are design inputs; source-code reuse requires license/permission review and a pinned source revision. Preserve source/version/chunk semantics, staged publication, cache compatibility, recovery, query-priority admission and honest throughput measurement. Do not copy the external runtime or its benchmark numbers as local evidence.

## 8. Compatibility and changes

Workbench export remains `schemaVersion: 1`, including nodes, parameters, connections, coordinates and viewport. No runtime data migration or frontend design change occurs here. The validation route/revision is unchanged. API v1 health/discovery is implemented by the isolated bootstrap; workspace/document/search routes and execution remain separate tasks. The additive discovery fields do not change the `rag-api-v1.0` request or score semantics.

Change this decision before dependent code/tasks when semantics change. Additive responses require clients to tolerate unknown response fields; request fields remain strict. Breaking request/response or score semantics require a new contract/API version or explicitly negotiated profile revision. Rollback is reverting these documentation edits; once dependent implementations exist, reconcile their contracts and migration obligations first.

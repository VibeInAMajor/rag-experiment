# TASK-RAG-DENSE-001 — Implement qualified live dense retrieval over versioned real Qwen embeddings

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation specification only, no runtime tests executed  
**Priority:** P0  
**Dependencies:** EMBED-001, EMBED-002, INDEX-001, PROFILE-001; completed RAG-001/DB-001  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md

## A. Title

Implement qualified live dense retrieval over versioned real Qwen embeddings

## B. Context / Problem

The PostgreSQL vector_search method already exists but no public Haystack dense execution profile performs real query embedding or returns cosine distance from a qualified model. ANN should not be a prerequisite for correctness: begin with exact pgvector search, measure it, then introduce ANN separately. A real semantic result is only valid when the embedding model, indexing generation, query input policy, workspace and source active-version all match.

## C. Current Repository State

**Actual code inspected:** [postgres.py](../apps/workbench/api/postgres.py) contains vector_search() that uses exact cosine distance on existing nullable chunk.embedding; lexical_search_snapshot() executes PostgreSQL plainto_tsquery('simple') + ts_rank_cd with active source versions. [lexical.py](../apps/workbench/api/lexical.py) contains a fixed allowlisted Haystack Pipeline with PostgresLexicalRetriever. [profiles.py](../apps/workbench/api/profiles.py) exposes only postgres-fts-baseline-r1. [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py) and [projection.py](../apps/workbench/api/projection.py) enforce the current four-field search request and truthful metadata. [0001 migration](../apps/workbench/api/migrations/0001_initial.up.sql) created GIN/tsvector and pgvector storage but no HNSW/IVFFlat ANN index. [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) specifies future local TEI/Qwen 2560, not an existing real dense API.
[WorkspaceContext](../apps/workbench/api/persistence.py) is development-only. Existing SearchResult score_type is currently postgres_ts_rank_cd; new dense output must remain truthful raw cosine distance/similarity, not simulate BM25 relevance. The current UI uses Preview and approved Live lexical graph.

## D. Goal

A verified semantic query generates a real local embedding via EmbeddingPort, executes Haystack dense retrieval against active PostgreSQL rows, returns actual cosine distances and generation/profile provenance; missing/incomplete model or corpus returns explicit unavailable, never Preview fallback.

## E. Scope

New approved dense Haystack component/profile, typed QueryEmbedding stage, exact cosine retrieval bounded top_k, registered model generation, timing/trace/rank response schema, profile-capability handshake, UI-specific approved graph and tests. Queries must use the same text transform/tokenizer/model version used to index documents.

## F. Non-Goals

No BM25 switch, ANN acceleration, RRF, vectors from demo fixtures, cloud provider fallback, arbitrary component instantiation, model generation or unverified "confidence" percentages.

## G. Architecture / Boundaries

FastAPI approved dense profile -> embedding application port -> local TEI adapter (only if qualified) -> Haystack Pipeline -> PersistencePort.vector_search() -> pgvector exact. Backend performs workspace/profile/generation checks; browser cannot select a model by arbitrary string. Keep response source/version/asset identifiers from PostgreSQL.

## H. Contracts / Interfaces / Data Model

SearchRequest remains four fields and expected_profile_revision. Add profile kind dense_search, embedding_profile_revision, index_generation, min_coverage and output score semantics. Separate "cosine_distance" (smaller is better) from normalized similarity; any inverted display score has explicit score_type "cosine_similarity" with formula and contract revision. Response stages query_embedding, vector_search, projection with server timestamps. Reject missing embedding model, vector dimension mismatch, stale source generation, partial coverage or malformed query with safe 4xx/5xx; 200 empty only on genuinely zero matches.

## I. Repository Files / Components Impacted

CREATE apps/workbench/api/dense.py (or shared retrieval composition), tests/test_dense_routes.py and real model-gated tests/test_dense_model_smoke.py; MODIFY profiles.py, services.py, application.py, contracts.py, projection.py, optional client src/api and approved graph matcher in apps/workbench/web/src/domain/. REUSE postgres.py vector_search(), persistence.py, embeddings port and current v1 error boundary. NEVER mutate 0001/0002 or create a second store.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Reinspect exact vector_search filter and embedding-profile checks. Write API DTO contract tests for distance direction, model/generation, optional page and source_version_id. Preserve lexical response unchanged.
2. J2 — Add allowlisted Haystack QueryEmbedder + PostgresDenseRetriever composition. Validate EmbeddingPort output before database query; no query vectors accepted directly from browser, no model inference inside SQL adapter.
3. J3 — Enforce generation readiness from EMBED-002/INDEX-001: eligible active chunks have qualified embeddings; reject stale/partial profile before search, and never mix model revisions in one result list.
4. J4 — Extend API capabilities and fixed profile dispatch; add strict typed frontend Live Dense template behind capability. Existing default keyword Live and Preview remain identical; unsupported graph makes zero HTTP calls.
5. J5 — Compare 10+ exact lexical and 30+ semantic/paraphrase questions with labelled evidence and persisted source IDs; benchmark exact top-k and timings. Measure query GPU p50/p95 separately from SQL and UI render time.
6. J6 — Test 400 invalid, 404 workspace, 409 profile revision mismatch, 503 model/DB, 504 timeout, cancellation, source swap during query, wrong-dimension vectors and trace correlation. No fabricated per-node timings.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

Unit/query transformer tests, fake provider and real gated local TEI smoke; PostgreSQL exact cosine oracle for 100+ vector rows, inactive version exclusion, mixed RU/UK/EN paraphrases, finite normalized embeddings, model down, version drift, profiles unset, concurrency, cancellation, UI session provenance and all existing lexical/validation/Preview regressions. Record true distances and latency.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

## M. Acceptance Criteria

- [ ] Real query embedding is produced by the selected qualified local model and input policy
- [ ] Dense result includes exact stored chunk_id, source_version_id, rank, raw cosine distance, model/index generation and server trace
- [ ] No partial/retired semantic generation can appear as Live executable
- [ ] Exact pgvector retrieval agrees with independent SQL distance oracle for labeled cases
- [ ] Two distinct semantic queries produce real query-dependent hits
- [ ] Offline provider never causes synthetic vector or Preview fallback
- [ ] Profile/distance semantics and UI display are truthful
- [ ] At least 30 labelled semantic queries and measured latency breakdown recorded

## N. Documentation / Migration / Compatibility / Rollback

Enable dense capability only after qualified generation complete. On model failure disable dense while lexical remains online; keep vectors for future repair. No reindex/data deletion on frontend rollback, and ANN activation separately gated.

## O. Mandatory Completion Checklist

- [ ] Source, dependency and existing tests re-inspected; blueprint updated if runtime diverged.
- [ ] Reuse current persistence, tokenizer, API and Haystack components; no duplicate storage.
- [ ] New profile semantics, failures and capability gates match exact contracts.
- [ ] Workspace, source version and index generation constraints enforced.
- [ ] Quality, performance, adversarial and restart tests actually executed.
- [ ] No misleading BM25/vector/ANN/hybrid score or capability claims.
- [ ] Migration/rollout/rollback non-destructive and operator documented.
- [ ] Real runtime evidence, commands, benchmark inputs and safe trace IDs linked.
- [ ] Changes and compatibility issues reviewed against dependent tasks.
- [ ] Mark COMPLETE only with proof of every applicable acceptance check.

**Documentation convention:** no feature is marked qualified merely because a test is described; amend A–O before any material scope expansion.

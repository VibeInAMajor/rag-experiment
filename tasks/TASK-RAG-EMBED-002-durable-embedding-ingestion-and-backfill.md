# TASK-RAG-EMBED-002 — Durable generation-aware embedding ingestion, resumable backfill and initial delta reuse

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — detailed implementation blueprint; no code changes or runtime tests in this task publication  
**Priority:** P0  
**Dependencies:** EMBED-001, INDEX-001; completed RAG-002/DB-001, coordinate PROFILE-001  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target location:** tasks/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md

## A. Title

Durable generation-aware embedding ingestion, resumable backfill and initial delta reuse

## B. Context / Problem

Today sources publish successfully as lexical chunks with embedding=None. On adding real vector processing, a document may be searchable lexically before semantic indexing is ready. Embedding failures must not corrupt source publication, claim dense readiness or force reupload of unchanged content. We need a resumable, idempotent, workspace-scoped embedding job path and active generation. Profile/model/chunk text changes must invalidate only relevant vectors.

## C. Current Repository State

**Source inspection (2026-11-23):** [SQL migration 0001](../apps/workbench/api/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../apps/workbench/api/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../apps/workbench/api/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../apps/workbench/api/contracts.py), [API route owner](../apps/workbench/api/application.py), [Haystack lexical profile](../apps/workbench/api/lexical.py) and [runtime decision](../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
[postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) complete_ingestion_with_publication explicitly requires all chunks to have null embedding (lexical ingestion); DO NOT remove that guard blindly. [persistence.py](../apps/workbench/api/persistence.py) validates profile_id/dimensions. [postgres.py](../apps/workbench/api/postgres.py) _validate_embedding verifies registered dimensions, vector_search exact cosine; no job table for embedding backfill. [embedding_profiles](../apps/workbench/api/migrations/0001_initial.up.sql) only has synthetic-test-v1 initially, not a qualified real Qwen profile.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

## D. Goal

After a lexical source is published, a durable embedding job can process every eligible **active** chunk of a chosen model profile, persist exact finite vectors with idempotent keys and generation metadata, survive restart and expose honest coverage. Partial or stale vectors are never mixed into a qualified Live dense profile. A source update invalidates/reembeds changed chunks while reusing only explicitly safe compatible content/profile embeddings.

## E. Scope

Add additive schema for semantic model profiles, embedding jobs and generation/coverage (coordinate INDEX-001/PROFILE-001), bounded embedding worker initially in-process or reusable durable queue, batch/admission retries, deterministic idempotency, backfill CLI, source-update scheduling and cancellation, transactional readiness and exact-vector validation.

## F. Non-Goals

No ANN tuning (ANN-001), no direct new browser upload path, no automatic vector search exposure before DENSE-001, no global shared cache across tenants, no remote providers without approval, no blind in-place model-upgrade of all old vectors.

## G. Architecture / Boundaries

Existing source ingest remains lexical-first. New embedding queue receives immutable chunk IDs/version hashes, requests EmbeddingPort adapter, stores typed EmbeddingGeneration rows bound to active source snapshot; a semantic index generation becomes ready only when required coverage passes and model identity matches. SQL writes use server workspace scope/RLS and existing connection lifecycle. Avoid holding a write transaction over GPU inference.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

EmbeddingJob{workspace,job_id,source_version_id,model_profile_revision,input_fingerprint,status queued/running/retryable_failed/completed/stale,attempts,cursor,started_at,finished_at}; EmbeddingRecord{chunk_id,source_version,model_profile,model_digest,input_hash,dim,vector_storage_ref,created_at}; EmbeddingCoverage{workspace,index_generation,profile,eligible_active_chunks,ready_embeddings,stale_embeddings,coverage_fraction,ready_boolean,checkpoint}. Content hashes include actual model input heading/instruction, parser/chunk profile revision, normalization and model digest. Do not mutate old vectors when the profile revision changes; separate generation namespace or table/pointer may be necessary.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

## I. Repository Files / Components Impacted

MODIFY [persistence.py](../apps/workbench/api/persistence.py), [postgres.py](../apps/workbench/api/postgres.py), [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) only through reviewed port; CREATE embedding_ingestion.py, embedding_jobs.py, tests/test_embedding_ingestion.py, next additive migration(s) after INDEX-001 schema; extend profiles.py, application.py capabilities and ops docs. MUST NOT alter lexical chunking and publication atomicity or original evidence links, applied 0001/0002 or static seed.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

## J. Implementation Requirements — ordered blueprint

1. J1 — Inventory publication write ownership and dimension rules; design job+coverage schema with workspace FKs, RLS and idempotent unique (chunk/version/model_profile/input_hash). Model how a source replacement supersedes its old vector candidates and how a model revision creates a new semantic generation.
2. J2 — Add a bounded CLI to backfill active sources in batches without rescanning entire corpus on every query; enqueue jobs idempotently via source-version and index-generation identity. Do not keep a DB transaction open during embedding requests; reserve/lease work with expiry and cancellation.
3. J3 — Use the qualified EmbeddingPort to embed verified model input, validate exact dimensions/finite/normalization and persist vector under the selected immutable profile. Chunk source/version/hash must be rechecked in the same transaction that writes vectors to reject stale work.
4. J4 — Record coverage and readiness from durable checkpoints, not a boolean UI flag; make profile unavailable until complete/approved coverage. Retries bounded with exponential backoff; poison inputs quarantined with safe codes and operator recovery.
5. J5 — Test source unchanged, one-chunk edit, model revision, tokenization change, duplicate job, crash between inference/write, network timeout and partial backfill. Reuse only compatible same-tenant cached vectors; prove fingerprint correctness.
6. J6 — Run 10k–100k synthetic/real-fake benchmark; verify no silent vector loss across API/DB restart. Publish non-destructive reindex and rollback runbook with dry-run manifest.

All implementation methods use descriptive domain names (not task identifiers); all new behavior is fail-closed and traceable. No acceptance box is checked merely because a file was created.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

Real qualified model optional GPU integration and fake provider deterministic tests; 100+ chunks, mixed languages, source update, quota/429, network outage, stale job/lease, wrong dimension, missing asset, RLS tenant denial, source version swap, crash recovery, latency/throughput and PostgreSQL migration/rollback. Acceptance requires 100% coverage on a known small supported corpus; larger backfill completeness reported with counts.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

## M. Acceptance Criteria

- [ ] Lexical ingest remains available while embedding worker is offline; no half-ready dense advertised
- [ ] Every ready vector has exact source/version/chunk/profile digest and finite verified dimension
- [ ] Small corpus eligible active chunks reach 100% coverage with stable generation and real vector lookup
- [ ] Stop/restart resumes job without duplicates or stale writes
- [ ] Same-key retry and unchanged compatible text do not regenerate vectors unnecessarily
- [ ] Changing source text/model/profile invalidates stale embeddings correctly
- [ ] Cross-workspace cache reuse forbidden unless separately security-reviewed
- [ ] Database migrations and existing lexical/Evidence regression pass

## N. Documentation / Migration / Compatibility / Rollback

New schema additive and staged; semantic generation pointer only activated after coverage gate. Disable embedding worker on errors while preserving lexical search and stored vectors for later safe recovery. Do not mutate applied 0001/0002, delete original source assets or silently expose old vectors with a new model identity.

Update [API README](../apps/workbench/api/README.md), architecture and this task with exact evidence and compatibility details before marking ready.

## O. Mandatory Completion Checklist

- [ ] Section C revalidated against actual repository and completed tasks; gaps identified with source evidence.
- [ ] Existing ports/services reused without duplicate SQL, tokenizer, registry or provider coupling.
- [ ] Contracts, state machine and failure/retry/rollback conditions tested.
- [ ] Tenant isolation, secret hygiene, input bounds and negative scenarios verified.
- [ ] Real performance/quality baseline and release gate metrics recorded where applicable.
- [ ] Unit, contract, integration, security and applicable browser tests actually executed.
- [ ] API/capabilities/documentation reflect only working qualified features.
- [ ] Non-destructive rollback and data preservation proven.
- [ ] Actual modified paths, commit, revision and sanitized evidence linked.
- [ ] Status changed to COMPLETE only with all measurable criteria supported.

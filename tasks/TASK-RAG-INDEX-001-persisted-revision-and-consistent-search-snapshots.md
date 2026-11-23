# TASK-RAG-INDEX-001 — Persisted corpus/index revisions and constant-cost retrieval snapshot qualification

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — detailed implementation blueprint; no code changes or runtime tests in this task publication  
**Priority:** P0  
**Dependencies:** Completed DB-001, RAG-001, RAG-002; coordinate PROFILE-001 before changing public API  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target location:** tasks/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md

## A. Title

Persisted corpus/index revisions and constant-cost retrieval snapshot qualification

## B. Context / Problem

Currently _corpus_snapshot() reads all active source/version/chunk records and hashes a serialized corpus fingerprint on every lexical search. This is defensible for an eight-source baseline but not for millions of chunks; it scales roughly with corpus metadata and repeats work for each query. Revisions must be persisted **at publication**, and every query must pin an immutable index generation. Distinguish source-content revision from lexical index generation and semantic embedding-profile generation. Do not solve this by caching an eventually stale digest in the browser.

## C. Current Repository State

**Source inspection (2026-11-23):** [SQL migration 0001](../apps/workbench/api/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../apps/workbench/api/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../apps/workbench/api/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../apps/workbench/api/contracts.py), [API route owner](../apps/workbench/api/application.py), [Haystack lexical profile](../apps/workbench/api/lexical.py) and [runtime decision](../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
Specific code in [postgres.py](../apps/workbench/api/postgres.py): _corpus_snapshot() queries counts, all document rows, all active chunk hashes, then SHA256 serializes the set; lexical_search_snapshot() invokes it inside a REPEATABLE READ transaction for every query. The same method is called after publication by complete_ingestion_with_publication() in [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py). Readiness checks GIN availability. A per-workspace durable manifest/counter and a constant-cost search snapshot have not been implemented.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

## D. Goal

After initial one-time backfill, every successful source publication atomically advances the workspace corpus generation exactly once. Search reads a versioned committed snapshot without enumerating all active chunks; query evidence includes generation/profile, and API/DB restart preserves it. Verified no-change upload does not advance the generation. Time spent establishing a snapshot is bounded independently from corpus size.

## E. Scope

New additive SQL/Alembic revision with workspace-scoped corpus_index_state and immutable index_generation/event ledger (names adapt existing conventions); stable generation IDs and per-profile readiness/coverage; transactional update in PostgresPersistence._publish and job path; versioned API snapshot metadata; migration/backfill, concurrency, rollback and 100k+ chunk benchmark. Distinguish lexical ready from embedding partially ready.

## F. Non-Goals

No complete rewrite of SQL lexical ranking, no cache-only revision, no BM25, no GPU, no arbitrary event bus, no second corpus store, no unreviewed deletion/retention policy.

## G. Architecture / Boundaries

Postgres is the authoritative generation owner, [PersistencePort](../apps/workbench/api/persistence.py) exposes read-current-generation and publish-generation operations, Haystack search composes the pinned profile and server propagates its generation in SearchResponse. Do not put revision writes in UI or Haystack SDK. A strict REPEATABLE READ read spans the manifest and hits; all update transitions are in one source-publication transaction.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

IndexGeneration fields: workspace_id, corpus_id, generation_id (monotonic sequence or UUID with consistent ordering), committed_at, active_source_count, active_chunk_count, content_bytes, active_source_manifest_hash, lexical_index_revision, readiness/status, previous_generation?, build/commit event ID. A separate EmbeddingIndexGeneration must include embedding_profile_id/revision, model/tokenizer/normalization, source_generation, covered_chunk_count and vector index state; lexical-only versions are valid. SnapshotRequest selects current allowed generation or an explicitly supported pinned historical generation. SearchResponse.corpus_revision remains compatible (map to new committed generation) while optional index_revision fields are additive under contract review; never send unqualified revisions as ready.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

## I. Repository Files / Components Impacted

MODIFY [postgres.py](../apps/workbench/api/postgres.py) _corpus_snapshot/lexical_search_snapshot/_publish, [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py), [persistence.py](../apps/workbench/api/persistence.py), [db_migrations.py](../apps/workbench/api/db_migrations.py), [projection.py](../apps/workbench/api/projection.py), [contracts.py](../apps/workbench/api/contracts.py), [lexical.py](../apps/workbench/api/lexical.py); CREATE next sequential immutable SQL/Alembic migration and tests/test_index_generations.py; update [postgres-lexical-search.md](../docs-website/docs/architecture/postgres-lexical-search.md) and runtime contract. MUST NOT edit applied 0001/0002, SQL scoring or demo fixtures.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

### I.1. Concrete implementation ownership — source reinspection 2026-11-23

| Existing file (direct link) | Symbol, contract and test reuse |
| --- | --- |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | _corpus_snapshot enumerates and hashes active documents/chunks; lexical_search_snapshot reads it for each request |
| [`apps/workbench/api/postgres_ingestion.py`](../apps/workbench/api/postgres_ingestion.py) | complete_ingestion_with_publication calls _publish and commits job and revision |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | CorpusSnapshot/LexicalSearchSnapshot/WorkspaceContext boundaries |
| [`apps/workbench/api/db_migrations.py`](../apps/workbench/api/db_migrations.py) | explicit checksum migration tooling |
| [`apps/workbench/api/tests/test_ingestion_persistence.py`](../apps/workbench/api/tests/test_ingestion_persistence.py) | transaction and version regression |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../apps/workbench/api/tests/test_lexical_routes.py) | HTTP/SQL rank and corpus provenance |

**Related project, pinned audit sources (architecture/test patterns only):** [`docs/63-progressive-repository-indexing-architecture.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/63-progressive-repository-indexing-architecture.md); [`tests/pipeline/test_semantic_restore_delta_lifecycle.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_semantic_restore_delta_lifecycle.py). Donor uses a different physical Qdrant/SQLite index; no code copying without [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) review.

## J. Implementation Requirements — ordered blueprint

1. J1 — Trace all reads and writes of corpus_revision in SQL, API, tests and UI. Record baseline EXPLAIN/timings at 8, 10k and >=100k **disposable synthetic** chunks, separating fingerprint time from ranking time. Identify every existing _corpus_snapshot caller, including readiness and post-publication; do not leave an O(N) path hidden there.
2. J2 — Design one manifest/generation migration with enforced workspace FKs, RLS, monotonic generation constraints and checksum-backed migration. Populate revision once from existing active rows; compare old digest and new snapshot before switching. Preserve actual source/version IDs; no historical SQL rewrite.
3. J3 — In the existing source update transaction, update manifest counts and generation using a serialized workspace-scoped lock; source version activation, terminal ingestion job and generation commit must agree. Unchanged idempotent replay must not increment; aborted/failed writes must not expose a newer manifest.
4. J4 — Replace query-time enumeration with one manifest read and ranking on the same committed snapshot; prove constant metadata query count under corpus growth. Preserve existing corpus_revision field contract or introduce explicitly negotiated revision; never mask stale generation with a locally cached value.
5. J5 — Verify race conditions: concurrent writes/queries, source replacement while search runs, same-key retries, corpus rollback, unavailability and schema mismatch. Compare stable generation before/after API and DB restarts. Provide non-destructive rollback and backfill runbook.
6. J6 — Release behind a tested capability/readiness gate; track manifest drift counters and an offline reconciliation job that checks real counts and repairs only with operator authorization. Record benchmark, SQL plans and trace IDs.

All implementation methods use descriptive domain names (not task identifiers); all new behavior is fail-closed and traceable. No acceptance box is checked merely because a file was created.

### J7–J13. Executable, file-specific implementation sequence

**J7.** Measure SQL plans from `_corpus_snapshot`/`lexical_search_snapshot` on 8/10k/100k synthetic chunks, recording rows read, CPU and p50/p95 independent from actual FTS ranking.

**J8.** Add additive per-workspace manifest/index_generation with RLS, counts, model/source/profile boundaries and monotonic state; migrate once from populated 0002 without modifying old files.

**J9.** Within existing `_publish` transaction update new active source version, committed job and manifest generation exactly once; unchanged retries/failures do not advance.

**J10.** Replace full all-chunk SHA per query with a constant metadata read under REPEATABLE READ, while returning original rank/source/version/score unchanged.

**J11.** Reconciliation offline command checks manifest vs true counts, never force-ready or re-hash every corpus on each HTTP request.

**J12.** Concurrency, unknown generation, DB restart and stale UI cursor tests; compare old 10 exact/3 paraphrase FTS profile quality.

**Cross-task evidence boundary:** [Index/Profile/Dense/ANN/Hybrid roadmap](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md); [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) is the single owner of actual 0.92/0.95 model admission, and does not turn missing model measurements into success.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

SQL migration from populated 0002; same-key replay, one generation per changed source, no generation on failure/unchanged, concurrent source updates, cross-workspace RLS, corrupted manifest 503, read transaction consistency, API contract, 100k synthetic performance and restart. Compare p50/p95 snapshot SQL duration and number of rows read versus old baseline; old lexical gold and API/frontend tests stay green.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

### L.1. Specialized test matrix / release gate

- [ ] Execute primary owner-specific tests named in I.1 and new focused unit and disposable PostgreSQL integration tests for this stage; attach actual commands/output.
- [ ] Prove 400/404/409/429/503/504 failure/cancellation, source-version drift, tenant RLS, safe trace IDs and absence of fixture fallback.
- [ ] Compare real source/result identities with independently checked PostgreSQL response and report quality/latency sample counts; no synthetic numerical performance claims.
- [ ] Re-run workbench-api Hatch check/test/types and (if browser touched) npm typecheck/test/build, Preview/validation/Live browser regression.

## M. Acceptance Criteria

- [ ] No O(N) active-chunk hash scan in successful lexical retrieval; manifest lookup count is O(1) for same profile
- [ ] Changed publication increments generation exactly once within existing terminal job transaction
- [ ] Unchanged/idempotent/failing publication leaves generation unchanged
- [ ] 100k-chunk synthetic benchmark records p50/p95 snapshot time and row counts before/after; threshold chosen from measured baseline
- [ ] No cross-workspace/cross-generation mixing, source version citation and original score unaffected
- [ ] Database/API restart yields same active generation without reseed
- [ ] Migration preserves 0001/0002 history and all existing records
- [ ] No false readyness for partially embedded semantic generation

## N. Documentation / Migration / Compatibility / Rollback

Introduce additive revision; rebuild manifest offline only on explicit operator command. Roll out read comparison before cutover, then switch qualified profile. If inconsistency is found, disable new query fast path, fall back to verified old query behavior behind explicit rollout flag (not silent), preserve every version and volume; audit backfill. Future ANN/dense profiles attach their generation to this catalog.

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

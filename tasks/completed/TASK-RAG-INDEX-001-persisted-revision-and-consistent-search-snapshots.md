# TASK-RAG-INDEX-001 — Persisted corpus/index revisions and constant-cost retrieval snapshot qualification

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** COMPLETE — persisted lexical generations implemented; scoped checks, real PostgreSQL, 100k metadata and isolated restart gates passed
**Priority:** P0  
**Dependencies:** Completed DB-001, RAG-001, RAG-002; coordinate PROFILE-001 before changing public API  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target location:** tasks/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md

## A. Title

Persisted corpus/index revisions and constant-cost retrieval snapshot qualification

## B. Context / Problem

Currently _corpus_snapshot() reads all active source/version/chunk records and hashes a serialized corpus fingerprint on every lexical search. This is defensible for an eight-source baseline but not for millions of chunks; it scales roughly with corpus metadata and repeats work for each query. Revisions must be persisted **at publication**, and every query must pin an immutable index generation. Distinguish source-content revision from lexical index generation and semantic embedding-profile generation. Do not solve this by caching an eventually stale digest in the browser.

## C. Current Repository State

**Pre-implementation source baseline (2026-11-23):** [SQL migration 0001](../../apps/workbench/postgres/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../../apps/workbench/postgres/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../../apps/workbench/postgres/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../../apps/workbench/postgres/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../../apps/workbench/contracts/schemas.py), [API route owner](../../apps/workbench/api/application.py), [Haystack lexical profile](../../apps/workbench/retrieval/lexical.py) and [runtime decision](../../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
Specific code in [postgres.py](../../apps/workbench/postgres/postgres.py): _corpus_snapshot() queries counts, all document rows, all active chunk hashes, then SHA256 serializes the set; lexical_search_snapshot() invokes it inside a REPEATABLE READ transaction for every query. The same method is called after publication by complete_ingestion_with_publication() in [postgres_ingestion.py](../../apps/workbench/postgres/postgres_ingestion.py). Readiness checks GIN availability. A per-workspace durable manifest/counter and a constant-cost search snapshot have not been implemented.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

### Implementation reinspection — 2026-11-23

The existing source-publication path already serializes writers with a workspace row lock; reuse it for manifest advancement. Both standalone publication and terminal ingestion publication use the same `_publish` owner. Unchanged ingestion takes a separate path and must retain its existing generation. Local-original registration updates active version metadata, previously included in the computed fingerprint, and must continue to invalidate the corpus revision and cursors when the registration changes.

`corpus_snapshot()` also supplies document listing, source details and pagination. Separate document materialization from the manifest-only readiness/search/job path; constant snapshot qualification does not promise constant-cost document listing or FTS ranking. Keep the approved lexical profile's 10,000-chunk / 50 MiB bounds; a 100k synthetic snapshot benchmark is scalability evidence for the manifest, not permission to advertise a larger Live corpus. Real embeddings, ANN and authenticated production multi-tenancy remain separately gated.

The root `AGENTS.md` references `docs/PROJECT_MAP.md` and `docs/ENGINEERING.md`, which are absent in this checkout. Their actual navigation/conventions documents were found and read at [docs-website/PROJECT_MAP.md](../../docs-website/PROJECT_MAP.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md), alongside the canonical runtime contract, application README, PostgreSQL runbook and actual owner modules above. No donor code is copied.

The implementation now adds [migration 0003](../../apps/workbench/postgres/migrations/0003_index_generations.up.sql), [generation persistence/reconciliation](../../apps/workbench/postgres/postgres_indexes.py), `PersistencePort.current_index_generation()` and `corpus_summary()`. The old enumerating fingerprint is retained only under explicit trusted `WORKBENCH_CORPUS_SNAPSHOT_MODE=legacy`; default `persisted` requires `0003` and never silently downgrades. Changed publication and local registration use the existing workspace lock and commit one generation with active-version changes. Readiness/search/job/detail/chunk qualification uses the manifest; document listing remains explicit materialization. Catalog guards require enabled protection/RLS, latest-generation state and equality with immutable history. Offline reconciliation checks actual rows and requires explicit `--repair` to commit a repair generation.

## D. Goal

After initial one-time backfill, every successful source publication atomically advances the workspace corpus generation exactly once. Search reads a versioned committed snapshot without enumerating all active chunks; query evidence includes generation/profile, and API/DB restart preserves it. Verified no-change upload does not advance the generation. Time spent establishing a snapshot is bounded independently from corpus size.

## E. Scope

New additive SQL/Alembic revision with workspace-scoped corpus_index_state and immutable index_generation/event ledger (names adapt existing conventions); stable generation IDs and per-profile readiness/coverage; transactional update in PostgresPersistence._publish and job path; versioned API snapshot metadata; migration/backfill, concurrency, rollback and 100k+ chunk benchmark. Distinguish lexical ready from embedding partially ready.

## F. Non-Goals

No complete rewrite of SQL lexical ranking, no cache-only revision, no BM25, no GPU, no arbitrary event bus, no second corpus store, no unreviewed deletion/retention policy.

## G. Architecture / Boundaries

Postgres is the authoritative generation owner, [PersistencePort](../../apps/workbench/persistence/models.py) exposes read-current-generation and publish-generation operations, Haystack search composes the pinned profile and server propagates its generation in SearchResponse. Do not put revision writes in UI or Haystack SDK. A strict REPEATABLE READ read spans the manifest and hits; all update transitions are in one source-publication transaction.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](../TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

IndexGeneration fields: workspace_id, corpus_id, generation_id (monotonic sequence or UUID with consistent ordering), committed_at, active_source_count, active_chunk_count, content_bytes, active_source_manifest_hash, lexical_index_revision, readiness/status, previous_generation?, build/commit event ID. A separate EmbeddingIndexGeneration must include embedding_profile_id/revision, model/tokenizer/normalization, source_generation, covered_chunk_count and vector index state; lexical-only versions are valid. SnapshotRequest selects current allowed generation or an explicitly supported pinned historical generation. SearchResponse.corpus_revision remains compatible (map to new committed generation) while optional index_revision fields are additive under contract review; never send unqualified revisions as ready.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

**Implemented compatibility decision:** no public fields are added. The existing opaque `corpus_revision` carries the persisted generation identity, and the existing capabilities `corpus_id` carries the actual workspace manifest identity. API revision, lexical profile/revision, source/version IDs and raw score semantics remain unchanged; no frontend/OpenAPI schema extension is necessary. Internal expected-generation reads reject stale/unknown generations; historical selection is unsupported. Generations are explicitly lexical-only: no semantic ready flag, partial embedding approval or model measurement is invented. Semantic generation attachment remains with EMBED/PROFILE/DENSE rather than expanding this task.

## I. Repository Files / Components Impacted

MODIFY [postgres.py](../../apps/workbench/postgres/postgres.py) _corpus_snapshot/lexical_search_snapshot/_publish, [postgres_ingestion.py](../../apps/workbench/postgres/postgres_ingestion.py), [models.py](../../apps/workbench/persistence/models.py), [db_migrations.py](../../apps/workbench/postgres/db_migrations.py), [projection.py](../../apps/workbench/api/projection.py), [schemas.py](../../apps/workbench/contracts/schemas.py), [lexical.py](../../apps/workbench/retrieval/lexical.py); CREATE next sequential immutable SQL/Alembic migration and tests/test_index_generations.py; update [postgres-lexical-search.md](../../docs-website/docs/architecture/postgres-lexical-search.md) and runtime contract. MUST NOT edit applied 0001/0002, SQL scoring or demo fixtures.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

**Final implementation surfaces:** create `postgres_indexes.py`, `0003_index_generations.up.sql` / `.down.sql` and its Alembic revision, focused generation/reconciliation tests, benchmark/restart scripts and the operator guide. Existing `postgres.py`, `postgres_ingestion.py`, `persistence.py`, `db_migrations.py` and `lexical.py` integrate generation ownership. `config.py`, `application.py`, `database_dependency.py` and `source_registration.py` propagate the trusted snapshot mode and actual corpus identity. Corresponding configuration/HTTP/ingestion test adapters are updated. Public `contracts.py`, `projection.py`, OpenAPI and frontend code need no changes because public shapes/scoring are preserved. Canonical docs, API README, project map/sidebar, release note, task and narrowly allowlisted evidence files complete the change.

### I.1. Concrete implementation ownership — source reinspection 2026-11-23

| Existing file (direct link) | Symbol, contract and test reuse |
| --- | --- |
| [`apps/workbench/postgres/postgres.py`](../../apps/workbench/postgres/postgres.py) | _corpus_snapshot enumerates and hashes active documents/chunks; lexical_search_snapshot reads it for each request |
| [`apps/workbench/postgres/postgres_ingestion.py`](../../apps/workbench/postgres/postgres_ingestion.py) | complete_ingestion_with_publication calls _publish and commits job and revision |
| [`apps/workbench/persistence/models.py`](../../apps/workbench/persistence/models.py) | CorpusSnapshot/LexicalSearchSnapshot/WorkspaceContext boundaries |
| [`apps/workbench/postgres/db_migrations.py`](../../apps/workbench/postgres/db_migrations.py) | explicit checksum migration tooling |
| [`apps/workbench/postgres/tests/test_ingestion_persistence.py`](../../apps/workbench/postgres/tests/test_ingestion_persistence.py) | transaction and version regression |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../../apps/workbench/api/tests/test_lexical_routes.py) | HTTP/SQL rank and corpus provenance |

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

**Cross-task evidence boundary:** [Index/Profile/Dense/ANN/Hybrid roadmap](../RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md); [TPM-001](../TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) is the single owner of actual 0.92/0.95 model admission, and does not turn missing model measurements into success.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

SQL migration from populated 0002; same-key replay, one generation per changed source, no generation on failure/unchanged, concurrent source updates, cross-workspace RLS, corrupted manifest 503, read transaction consistency, API contract, 100k synthetic performance and restart. Compare p50/p95 snapshot SQL duration and number of rows read versus old baseline; old lexical gold and API/frontend tests stay green.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

### L.1. Specialized test matrix / release gate

- [x] Execute primary owner-specific tests named in I.1 and new focused unit and disposable PostgreSQL integration tests for this stage; attach actual commands/output.
- [x] Prove 400/404/409/429/503/504 failure/cancellation, source-version drift, tenant RLS, safe trace IDs and absence of fixture fallback.
- [x] Compare real source/result identities with independently checked PostgreSQL response and report quality/latency sample counts; synthetic corpora are explicitly labeled and timings are measured, not fabricated.
- [x] Re-run workbench-api Hatch check/test/types; browser code is unchanged, so npm/browser checks are not applicable.

## M. Acceptance Criteria

- [x] No O(N) active-chunk hash scan in default persisted lexical retrieval; one manifest row/constant metadata query shape. Explicit legacy rollback deliberately retains enumeration.
- [x] Changed publication increments generation exactly once within existing terminal job transaction
- [x] Unchanged/idempotent/failing publication leaves generation unchanged
- [x] 100k-chunk synthetic benchmark records p50/p95 snapshot time and row counts before/after; the measured local metadata gate is ratified in section P
- [x] No cross-workspace/cross-generation mixing, source version citation and original score unaffected
- [x] Database/API restart yields same active generation without reseed
- [x] Migration preserves 0001/0002 history and all existing records
- [x] Lexical-only generation status cannot claim readiness for a partially embedded semantic generation

## N. Documentation / Migration / Compatibility / Rollback

Introduce additive revision; rebuild manifest offline only on explicit operator command. Roll out read comparison before cutover, then switch qualified profile. If inconsistency is found, disable new query fast path, fall back to verified old query behavior behind explicit rollout flag (not silent), preserve every version and volume; audit backfill. Future ANN/dense profiles attach their generation to this catalog.

Update [API README](../../apps/workbench/api/README.md), architecture and this task with exact evidence and compatibility details before marking ready.

## O. Mandatory Completion Checklist

- [x] Section C revalidated against actual repository and completed tasks; gaps identified with source evidence.
- [x] Existing ports/services reused without duplicate SQL, tokenizer, registry or provider coupling.
- [x] Contracts, state machine and failure/retry/rollback conditions tested.
- [x] Tenant isolation, secret hygiene, input bounds and negative scenarios verified.
- [x] Real performance/quality baseline and release gate metrics recorded where applicable.
- [x] Unit, contract, integration and security checks actually executed; browser checks are not applicable to unchanged frontend code.
- [x] API/capabilities/documentation reflect only working qualified features.
- [x] Non-destructive rollback and data preservation proven.
- [x] Actual modified paths, base commit, revision and sanitized evidence linked; working-tree changes remain uncommitted.
- [x] Status changed to COMPLETE only with all applicable measurable criteria supported.

## P. Implementation and qualification record — 2026-11-23

The working tree is based on commit `44866bb7e7dc01993bbaefefdec1ab1985951cc7`; no commit or production deployment is implied. This record supersedes the earlier inspected snapshot for implemented behavior. The [operator guide](../../docs-website/docs/architecture/persisted-index-generations.md) gives the exact migration, reconciliation and explicit legacy rollback commands.

### Existing ownership reused and intentional changes

The existing PostgreSQL corpus, `_publish` workspace lock, terminal ingestion transaction, RLS context, checksum migrator, async pool, Haystack lexical component and response projection remain authoritative. `0001`/`0002`, vector storage, ranking SQL and demo content are preserved. New generation persistence lives in `postgres_indexes.py` and additive `0003`; no second corpus, embedding registry or search engine is introduced.

Default persisted mode now requires `0003`. Older schemas require explicit trusted legacy mode; no automatic enumeration fallback exists. The public API/profile revisions and DTO shape remain unchanged. `corpus_revision` is explicitly opaque and durable; capabilities `corpus_id` is the actual manifest corpus identity. Local registration invalidates the persisted revision, while exact retry preserves it. Document listing and per-source publication work are not claimed constant time. Lexical-only generation status cannot qualify semantic readiness.

### Executed focused checks

With `WORKBENCH_TEST_ADMIN_DSN` / `WORKBENCH_TEST_APP_DSN` loaded from the existing administrator/application environment, the following commands create only fixture-owned disposable databases:

```powershell
hatch run workbench-api:python -m pytest -q apps/workbench/postgres/tests/test_index_generations.py
hatch run workbench-api:python -m pytest -q apps/workbench/postgres/tests/test_index_reconciliation.py
```

The generation suite passed **13 tests** and the reconciliation suite passed **9 tests**. They cover one advancement per changed publication; unchanged/idempotent/failure preservation; concurrency and a query/publication MVCC barrier; RLS/read-only manifest privileges; populated `0002` backfill; stale/malformed generation reads; staged-only changes; local drift; schema/protection drift; immutable history; check-only versus repair-once/no-op behavior; explicit legacy reads with generation-aware writes; and dirty-manifest HTTP 503/readiness/capability refusal with safe correlation envelopes. A controlled unmanaged other-source writer was observed waiting on a database lock, then left the manifest dirty rather than having its mutation hidden by another publication. Source/result/score identities remain actual PostgreSQL records.

### Reproduction and measurement boundary

```powershell
hatch run workbench-api:python -m scripts.workbench_index_benchmark
hatch run workbench-api:python -m scripts.workbench_index_restart
```

The benchmark uses 30 measured samples at each of 8, 10,000 and 100,000 synthetic chunks and records exact SQL, migration checksums, guarded-query fingerprint, counts/bytes equality and `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plans. Its legacy comparator reconstructs the historical count/chunk-hash scans and Python fingerprint with a simplified document projection and omits the old 10k admission cap; it is not a byte-for-byte replay of the entire old HTTP path. The full guarded `current_index_generation()` timing includes application role/schema/index/ledger checks and round trips; an isolated manifest SELECT or SQL-plan execution time is not presented as that runtime latency.

The local metadata gate is one manifest row and constant query shape, with 100k guarded-runtime p95 no greater than twice the measured 8-chunk guarded-runtime p95. This gate qualifies bounded metadata establishment on this machine only. It does not change the 10k / 50 MiB Live admission policy, qualify FTS ranking throughput or assert production latency.

The final [benchmark JSON](../evidence/index-2026-11-23/benchmark.json) measured guarded runtime p50/p95 of **9.4963/15.4113 ms** at 8 chunks, **9.2706/14.6148 ms** at 10k, and **9.0743/15.1887 ms** at 100k. The reconstructed legacy scan measured **716.6820/776.1418 ms** at 100k and returned 100,002 metadata rows, versus one manifest row. The local gate passed: `15.1887 <= 2 × 15.4113 = 30.8226 ms` (ratio `0.9856`). The guarded SQL's 100k plan executed in 0.144 ms; that server-only time is not substituted for the full guarded runtime. The [evidence report](../evidence/index-2026-11-23/report.md) contains all sizes and comparator limitations.

The restart harness uses a UUID-owned container of the pinned PostgreSQL 17.10 / pgvector 0.8.2 image and actual loopback API processes. It publishes one synthetic source, restarts the API and then the isolated database, and verifies the same persisted generation, source/version/chunk identities and raw `postgres_ts_rank_cd` score. Shared services, main application data and existing volumes are not restarted or reseeded.

The final [restart JSON](../evidence/index-2026-11-23/restart.json) passed: generation 1, corpus revision and `restart-source` / `restart-version` / `restart-chunk` remained stable, with score `0.10000000149011612` before restart and after each restart. The harness cleaned up its ephemeral processes/container. [Focused INDEX JUnit](../evidence/index-2026-11-23/index-tests.xml) records 13 passing cases; the final whole-suite JUnit additionally includes the nine reconciliation cases.

### Risks and bugs addressed

Per-search all-chunk hashing and hidden all-corpus qualification in readiness/job/detail paths are removed from persisted mode. Revision invalidation for local-original registration is preserved. Review also caught stale state pointing to an older valid ledger generation, repair while protection triggers were disabled, and a concurrent unmanaged write being accidentally hidden; latest-tip/catalog guards and serialized dirty-marking address those cases. CLI administrator configuration uses the existing `WORKBENCH_DB_ADMIN_DSN` name.

Administrators can bypass ordinary mutation protection through disabled triggers, `TRUNCATE` or restore. Keep the API stopped and reconcile before resuming it. Collect `corpus_manifest_unavailable` events to count qualification failures; no persistent metrics service, automated repair, semantic model coverage or production authentication is claimed. Browser code is unchanged, so browser/frontend checks are not applicable to this backend task.

### Final regression and documentation checks

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test --tb=short --junitxml=tasks/evidence/index-2026-11-23/full-tests.xml
```

[Final JUnit](../evidence/index-2026-11-23/full-tests.xml): **930 passed, 16 skipped, zero failures/errors**, 237.53 seconds. All PostgreSQL/INDEX/reconciliation tests executed. The 16 skips require explicitly configured real Qwen tokenizer assets through `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; that setting was absent. They do not mask skipped database tests or qualify actual embeddings. The `lexical_evaluation` JUnit property records **10/10 exact targets in top five**, with all **three known paraphrase diagnostics still missing** their expected source; native FTS semantics are preserved. Existing HTTP fault, SQL identity/score parity, cancellation and source-version tests passed in this run.

[Quality output](../evidence/index-2026-11-23/quality-checks.txt): Ruff check/format passed for 95 files; mypy found no issues in 95 source files. Relative-link checks passed across touched guides, API README and project map; the sidebar page exists exactly once and `node --check docs-website/sidebars.js` passed. Strict UTF-8, final-newline/consistent-line-ending checks, `git diff --check`, and `hatch run workbench-api:python scripts/release_note_backticks.py --check releasenotes/notes/workbench-persisted-index-generations-5a874add4eb89b72.yaml` passed. Docusaurus full build was not run because `docs-website/node_modules` is absent; no dependencies were downloaded. No separate Markdown formatter is configured there. Frontend/browser and Haystack core suites were not run because those implementations were unchanged.

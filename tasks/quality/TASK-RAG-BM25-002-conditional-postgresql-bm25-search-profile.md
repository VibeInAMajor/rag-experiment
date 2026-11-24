# TASK-RAG-BM25-002 — Conditional BM25 PostgreSQL extension and truthful Live search profile

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** BLOCKED — GO decision and approval required  
**Priority:** P2 BLOCKED until BM25-001 Go + approved license and deployment  
**Dependencies:** [BM25-001](TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md) GO and explicit license/runtime approval, completed PROFILE-001/INDEX-001; existing local RLS; SCALE-001 mandatory only for later enterprise release.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-BM25-002-conditional-postgresql-bm25-search-profile.md

## A. Title

Conditional BM25 PostgreSQL extension and truthful Live search profile

## B. Context / Problem

If a benchmark justifies BM25, implement it as a **second, specifically named** PostgreSQL lexical profile rather than silently switching existing FTS or reusing in-memory Haystack BM25. The extension may require a custom PostgreSQL image, schema DDL and license approval. This task is intentionally blocked until conditions are met; completing its document is not approval to install code.

## C. Current Repository State

[PostgresPersistence](../../apps/workbench/postgres/postgres.py) now owns lexical_search_snapshot and real vector_search_snapshot over migration 0005's immutable embedding_vectors and chunk_embeddings, not nullable legacy chunks.embedding. [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py) executes qualified exact Dense; [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py) already defines rrf/bm25 but they are not executable merely by schema. [profiles.py](../../apps/workbench/retrieval/profiles.py), [retrieval routing](../../apps/workbench/retrieval/services.py), [projection](../../apps/workbench/api/projection.py) and [API contracts](../../apps/workbench/contracts/schemas.py) own qualification and score provenance. [actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md) records 102 real vectors, 52 queries and independently checked exact SQL; no independent quality holdout, BM25 or Hybrid runtime claim. Current local corpus cap 10k/50 MiB remains. No approved extension deployment; BM25-001 GO and license required, keep FTS unchanged.

## D. Goal

A separately qualified PostgreSQL BM25 adapter retrieves real, workspace-scoped active source chunks with truthful bm25_raw scores and preserves existing FTS baseline unchanged. Rollback to FTS does not require data loss or a second document store.

## E. Scope

Pin approved database extension and image/migration, add indexed BM25 SQL adapter behind application port, qualified profile/capabilities, source identity and filter handling, query analyzer/versioning, UI approved graph and robust quality/restart tests.

## F. Non-Goals

No implementation before explicit Go, no in-memory corpus, no replacing existing 0001 GIN index, no unlicensed deployment, no raw FTS cosine score mixing, no query-derived SQL strings or model requests.

## G. Architecture / Boundaries

Approved BM25 plugin extension runs in existing Postgres deployment in an operator-reviewed image. Application offers a separate BM25 retrieval adapter under PersistencePort, profiles registry chooses BM25 only for an allowed ID/version, and existing RLS/active-version policies remain authoritative. Hybrid may select this arm after retraining/evaluation, not by renaming lexical profile.

## H. Contracts / Interfaces / Data Model

BM25Profile includes algorithm=BM25, extension+analyzer revision, bm25_raw score direction, index generation, workspace, active source-version constraint, top-k and full-text analyzer options. No backwards-compatible change that alters postgres-fts-baseline. New profile request uses explicit expected_profile_revision and error code if extension unavailable; return source_version_id, chunk_id and score_type bm25_raw.

## I. Repository Files / Components Impacted

CREATE app-owned bm25.py adapter/test suite and next additive extension-specific migration/image packaging only after decision; MODIFY profiles.py, application.py dispatch, contracts.py, PostgreSQL ops docs, web approved template in narrow scope. MUST NOT edit historical migration 0001/0002, existing lexical.py score fields, original source assets, default UI Preview node behavior.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/postgres/migrations/0001_initial.up.sql`](../../apps/workbench/postgres/migrations/0001_initial.up.sql) | keep native GIN index |
| [`apps/workbench/postgres/db_migrations.py`](../../apps/workbench/postgres/db_migrations.py) | additive change approval |
| [`apps/workbench/postgres/postgres.py`](../../apps/workbench/postgres/postgres.py) | persistent workspace + active version SQL source |
| [`apps/workbench/retrieval/profiles.py`](../../apps/workbench/retrieval/profiles.py) | current FTS-only profile constants |
| [`apps/workbench/api/application.py`](../../apps/workbench/api/application.py) | fixed allowlist dispatch and safe errors |
| [`apps/workbench/contracts/schemas.py`](../../apps/workbench/contracts/schemas.py) | profile and score schema |
| [`apps/workbench/web/src/domain/approvedExecution.ts`](../../apps/workbench/web/src/domain/approvedExecution.ts) | supported Live graph matcher |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../../apps/workbench/api/tests/test_lexical_routes.py) | baseline scores/provenance |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/22-implementation-step-05-sparse-and-symbol-retrieval.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/22-implementation-step-05-sparse-and-symbol-retrieval.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

**Quality-track boundary:** [implementation order](IMPLEMENTATION_ORDER.md). Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion. Use DATASET-001 reviewed tuning data and common evidence facets, equal final context token budget, predeclared paired metrics and explicit no-go. The independent final holdout is reserved for QUALITY-002; prior synthetic query counts remain minimum regression tests, not final quality qualification. No production activation based on benchmark alone.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Verify BM25-001 signed Go document and license/OS/release approval, inspect current DB image and query/exact index results. Refuse work if unapproved.
2. J2 — Pin extension binary/image digest and schema/upgrade plan; test install on disposable production-like PostgreSQL 17 and fail readiness when extension version absent/incompatible.
3. J3 — Build BM25 index over existing source/chunk rows without a duplicate corpus; enforce RLS, active source filter and source/metadata join in one SQL query. Validate score semantics and stable ties.
4. J4 — Expose bm25-v1 as a **new** capability with its own profile generation and exact query analyzer version; retain old FTS path/score. Add frontend search template only after backend qualifies.
5. J5 — Run BM25-001 evaluation dataset as regression, workspace skew and update benchmark. Confirm score labels are truthful, 100% target citation identity and no missing active-version exclusion.
6. J6 — Canary controlled profile selection; verify fallback by explicit operator/profile action and rollback index extension without touching source rows or existing GIN.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Require BM25-001 real GO/NO-GO with accepted extension license and deployment version; refuse to install if decision incomplete.

**J8.** Define separate bm25-v1 profile, score_type bm25_raw and analyzer/embedding-independent rank semantics; do not reinterpret current postgres-fts-baseline.

**J9.** Install approved extension in a new digest-pinned Postgres 17 image and additive explicit schema/DDL, record upgrade/backup and extension permissions.

**J10.** Add one BM25 query adapter in the existing PostgresPersistence/PersistencePort layer with active version and tenant RLS; do not create secondary BM25 document-store ownership.

**J11.** Gate capabilities on actual extension,index state and workspace/source generation; profile 409 stale, 503 unavailable. Preserve FTS stable when extension off.

**J12.** Add approved Live BM25 keyword graph only when backend built; old Preview BM25 node label does not grant execution.

**J13.** Run BM25-001 benchmark as regression, verify raw score parity with SQL, tenant skew and failover, and document rollback to existing FTS index.

**Cross-cutting constraints:** BM25 is a measured GO/NO-GO; the production path must not relabel ts_rank_cd as bm25_raw.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

Extension startup/upgrade/uninstall, safe non-default profile, 100+ paired quality queries, 1% workspace skew, source replacement, idempotent retry, 429/503/504, security and backup restore. Use disposable DB and record actual performance. Re-run FTS gold/capability tests and browser negative/Preview regressions.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

### L.1. Task-specific reproducible test vectors

- [ ] Legacy FTS rank/score unchanged before/after BM25 deployment, 100+ gold queries and index correctness.
- [ ] Index invalid/missing extension/DDL denied, 404 foreign workspace, source superseded and stale profile errors.
- [ ] Rollback removes new profile and optionally index only, retains FTS corpus and old source versions.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

## M. Acceptance Criteria

- [ ] BM25-001 Go and license approval documented before any extension install
- [ ] Real BM25 extension pinned/healthy and correct score_type bm25_raw
- [ ] Native FTS profile remains byte-compatible and available
- [ ] All BM25 queries enforce tenant RLS and active-version filtering
- [ ] No duplicate persistent corpus/in-memory Live path introduced
- [ ] Benchmark gates meet previously ratified quality/latency goals
- [ ] Unknown/absent BM25 extension fails closed without renamed FTS
- [ ] Rollback removes BM25 profile/index only and preserves data

## N. Documentation / Migration / Compatibility / Rollback

BLOCKED by default; opt-in rollout with profile canary. On incompatibility disable BM25 capability, direct operators explicitly back to FTS, and remove only new index/extension if safe and after backup verification. No data or source version loss; preserve licensing and version records.

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

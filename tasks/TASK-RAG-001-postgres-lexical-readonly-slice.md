# TASK-RAG-001-postgres-lexical-readonly-slice

**Created:** 2026-11-20  
**Updated:** 2026-11-21
**Status:** COMPLETE
**Priority:** P0 · integration  
**Dependencies:** TASK-API-001, TASK-DB-001  
**Repository snapshot reviewed:** `5e7086364f62d4f15b7370e55767a8f84ed4dc14`

**Working-tree base inspected:** `7f19f4560012a47b812dfabe8f4b1fc53aa384e9` plus this task's scoped changes.

## A. Title

Expose real, PostgreSQL-backed Haystack keyword retrieval over the persistent development corpus

## B. Context / Problem

The Workbench currently returns fixed demo passages independently of the query. The target PostgreSQL + pgvector store must be operational **before** the first live search; otherwise a temporary `InMemoryDocumentStore` will introduce a parallel, disposable data path that later has to be replaced.

Use the persistent development corpus created by `TASK-DB-001`. PostgreSQL's native `ts_rank_cd` is **not BM25**; the first live lexical result must be labeled with its actual search algorithm and score type. A genuine BM25 extension, if needed, is separately scoped after measuring the initial baseline.

## C. Current Repository State

- `apps/workbench/web/src/domain/preview.ts` exposes four fixed results and mock timings; `search_executed: false` is part of the preview.
- The repository contains Haystack pipelines under `haystack/core/pipeline/` and `DocumentWriter`, along with in-memory retrievers. `InMemoryBM25Retriever` enforces an `InMemoryDocumentStore` instance and cannot be wired to pgvector.
- The external `pgvector-haystack` integration supplies `PgvectorDocumentStore` and `PgvectorKeywordRetriever`; its compatibility, filtering, versions and handling of server-owned workspace constraints must be validated in `TASK-DB-001` before direct use. The keyword retriever uses PostgreSQL `ts_rank_cd`, not BM25.
- Rechecked starting state: `TASK-DB-001` is complete. A dedicated PostgreSQL 17.10 + pgvector 0.8.2 container, Alembic `0001`, scoped SQL persistence port and eight explicitly seeded passages exist. API readiness remains 503 because no HTTP retrieval profile is implemented yet; database dependency status is ready.
- `pgvector-haystack` 8.2.1 has already been tested with repository Haystack 3.5.0. Its standard operations work, but its flat table/implicit DDL cannot satisfy the migration-owned composite workspace/source/version schema without duplicate storage or invasive overriding. Reuse the existing SQL adapter through a narrow Haystack component.
- The canonical contract had reserved `postgres-keyword-v1` in schemas but no executor used it. Following the user's clarification in this task, the executable profile will use `postgres-fts-baseline` from this specification. The old reserved identifier is not an execution alias.

## D. Goal

Return real, query-dependent, workspace-scoped ranked passages **from PostgreSQL** via a versioned FastAPI endpoint using Haystack pipeline orchestration/reusable adapters, with measured latency, stable source/chunk identity, and controlled empty/error states. Data survives process/container restarts.

## E. Scope

1. Use **only** the existing persisted corpus/active versions and database connection path supplied by `TASK-DB-001`; do not re-seed the corpus on every API start.
2. Assemble an allowlisted Haystack lexical pipeline using `PgvectorKeywordRetriever` and `PgvectorDocumentStore` when the verified integration enforces required workspace/version restrictions. Otherwise create a minimal app-owned Haystack `@component` backed by the **same PostgreSQL data model**, documenting why the off-the-shelf retriever cannot be used safely. Do not implement a second document store.
3. Expose `GET /api/v1/workspaces/{workspace_id}/documents` from PostgreSQL source/version/chunk records, and `POST /api/v1/workspaces/{workspace_id}/search` with validated non-empty query, bounded top-k and approved profile.
4. Report authoritative rank, `score_type="postgres_ts_rank_cd"`, `run_id`, `trace_id`, `duration_ms`, source ID/chunk ID, active version ID, title, nullable page and exact returned passage content.
5. Advertise the `postgres-fts-baseline` capability only when database schema, seed/index state and live retrieval are ready. Preserve truthful 503 and the canonical 400/409 failure paths.

Contract reconciliation: preserve the canonical `rag-api-v1.0` envelope and error semantics: malformed requests use 400, unsupported profile/revision uses 409, and unavailable storage uses 503. References to 422 in the original attachment are superseded by this existing contract. Profile `postgres-fts-baseline` is selected per the user's explicit clarification; its immutable initial revision is `postgres-fts-baseline-r1`.

## F. Non-Goals

No embeddings inference, vector semantic search, RRF, answer generation, document upload, full workspace RBAC, production ingestion workers, or arbitrary user-submitted graph execution. No ephemeral in-memory Live corpus. No false BM25 labels, mocked search scores, arbitrary per-node timings, or use of an additional search engine/extension without a separate architectural decision.

## G. Architecture / Boundaries

Affected: Retrieval/RAG, Application/orchestration, HTTP contract, PostgreSQL persistence adapter, Security/workspace resolution, Observability/evidence. Service orchestration is responsible for supported profiles and authorization; the persisted dataset is owned by `TASK-DB-001`'s storage layer. Reuse Haystack `Pipeline` and a compatible retriever adapter rather than duplicating retrieval/scoring. Provider SDKs stay outside core application policy.

```text
Live Workbench -> typed API -> FastAPI -> allowlisted lexical profile
                                            -> Haystack Pipeline
                                            -> PostgreSQL keyword retrieval adapter
                                            -> PostgreSQL + pgvector persistent storage
```

## H. Contracts / Interfaces / Data Model

`POST /api/v1/workspaces/{workspace_id}/search` requires `query` (trimmed, 1–4096 code points), strict integer `top_k` (1–50), `profile_id: "postgres-fts-baseline"` and `expected_profile_revision: "postgres-fts-baseline-r1"` from capability discovery. Preserve canonical Meta, `mode: "live"`, workspace/corpus/profile revisions, `run_id`, measured `duration_ms`, actual measured stages and `results[]`. Result provenance uses canonical `source_version_id` (the database `version_id`), plus `chunk_id`, `source_id`, title, optional positive page, exact content, contiguous rank, finite raw score and `score_type: "postgres_ts_rank_cd"`. An absent page is omitted per the existing contract. No version field alias or model/provider override is accepted.

Documents/workspace list responses follow the canonical versioned metadata and pagination schemas. Empty lists/no search hits succeed with empty arrays. Requests reject extra fields, caller filters, SQL, graph JSON and duplicate/ambiguous JSON keys. Errors use 400 for invalid request/cursor, 404 for missing or foreign development workspace, 409 for unsupported profile/revision, 413/415 for body/media violations, 429 for two occupied search slots, 503 for database/schema failures and 504 for the ten-second admitted deadline. No preview or in-memory fallback is permitted.

## I. Repository Files / Components Impacted

Expected `apps/workbench/api/` query route/service, retrieved-document response schemas, Haystack lexical profile composition, mapping and app tests. Minimal read extensions to the existing persistence port/SQL adapter are authorized for coherent document metadata, active-version corpus fingerprints, index qualification and same-snapshot ranked results; no migration, table or seed change is planned. Add repository Haystack as an application runtime dependency, using the existing source package rather than another corpus/store. Update capabilities, schema, canonical status, backend/Workbench runbooks and evaluation/restart scripts/evidence. Do not alter `haystack/` core sources, existing `src/domain/preview.ts`, UI sample fixtures, or unrelated frontend graph validation.

## J. Implementation Requirements

MUST query persisted PostgreSQL records, not an `InMemoryDocumentStore` or TypeScript fixture list. MUST reuse the verified pgvector Haystack keyword integration where compatible with tenant scoping; a custom adapter is justified only by documented incompatibility and must still execute PostgreSQL queries. MUST scope reads by server-resolved workspace and active source version, not caller-replaceable metadata filters. MUST use a deterministic tiebreaker for same scores (e.g. `chunk_id`). MUST reject unsupported/altered executable profiles before retrieval; no arbitrary component deserialization. MUST expose measured request duration and one truthful search span only unless more spans were actually captured. MUST return 503 on database/schema failures, without falling back to preview or ephemeral storage. MUST NOT call native FTS “BM25”.

## K. Security / Governance / Observability

Initial API is restricted to a single explicit, server-resolved development workspace; do not claim production multi-tenant isolation. A second test workspace must not be readable by guessing source/chunk IDs or passing custom filters. Use parameterized DB statements and bounded query/top-k; do not expose connection details or model provider credentials. Log trace IDs, authorized workspace, selected profile, SQL-stage timing, result counts and error classes only. Redact raw document text/query unless a sanitized fixture test explicitly requires capture.

## L. Testing / Evaluation / Runtime Verification

Use Hatch for focused `ruff`/`pytest -q` application checks, a running PostgreSQL + pgvector container and actual API HTTP smoke. Tests cover: two distinct queries with distinct rank lists; 10 labeled exact-term/identifier lexical queries plus non-gated paraphrase diagnostics; deterministic top-k and tie order; no matches; normalized and non-English input; stable IDs; persisted active versions; unknown/foreign workspace; unsupported profile; SQL/connection failure; migration mismatch; schema deletion refused; no runtime seeding; restart of API and DB preserving corpus and rankings. Compare actual SQL ranking with Haystack adapter responses, inspect trace IDs and run durations. Neither mock UI results nor fake embedding vectors count as lexical-quality evidence.

## M. Acceptance Criteria

- [x] Live queries retrieve 5–10 previously seeded passages **from PostgreSQL**, and documents API lists the same persisted source records.
- [x] `postgres-fts-baseline` executes at least ten labeled **exact-term/identifier** lexical queries with at least 9/10 expected sources in top five; record exceptions and the corpus version.
- [x] Two different queries produce different actual rank lists; result score type is `postgres_ts_rank_cd` (not BM25 and not a probability).
- [x] Every result has valid workspace-scoped `source_id`, `source_version_id`, `chunk_id`, rank, title, optional page and actual server-measured duration.
- [x] After API/DB restart, IDs, corpus and results remain durable; backend DB unavailable produces 503, not in-memory fallback.
- [x] Negative workspace/profile/input tests pass; audit traces do not include credentials or raw private content.
- [x] Backend tests/lint, database smoke and HTTP evidence are attached before marking complete.

## N. Documentation / Migration / Compatibility / Rollback

Reuse the database migration/seed lifecycle from `TASK-DB-001`; this task does not rebuild tables or create a parallel corpus. Update API/Workbench documentation to call the first supported profile **PostgreSQL full-text lexical search**, not BM25. If the existing UI palette retains a BM25 node for Preview, it must not be represented as an executable Live node for this profile. Future BM25/pg_search, dense/hybrid and reranking require separate capabilities and tests. Rollback disables the lexical Live profile and endpoint but **retains the PostgreSQL volume and indexed records**.

## O. Mandatory Completion Checklist

- [x] PostgreSQL-backed Haystack lexical pipeline and store adapter verified.
- [x] No in-memory Live fallback, misleading BM25 score or duplicate storage path.
- [x] Persistent restart, provenance, workspace negatives, canonical 400/409/503 and no-match paths verified.
- [x] Query ranking, timings, tracing and selected database language configuration documented.
- [x] Capabilities and UI contracts match operational behavior; tests/smoke pass.
- [x] Only mark COMPLETE after actual runtime evidence is recorded.

### Completion evidence — 2026-11-21

Implemented files and ownership:
- `apps/workbench/api/lexical.py`: allowlisted real Haystack component and a fresh one-component `Pipeline.run_async()` per search; it delegates to the existing PostgreSQL persistence adapter. Its synchronous `run()` explicitly refuses execution because the owned async pool is event-loop bound.
- `persistence.py`, `postgres.py`: minimal read extensions for authoritative document metadata, valid GIN qualification, bounded corpus fingerprints and native ranked hits from one read-only REPEATABLE READ SQL snapshot. No schema, migration, seed or parallel document store was introduced.
- `application.py`, `boundary.py`, `contracts.py`, `services.py`, `profiles.py`, `projection.py`: six typed routes, immutable task-selected profile/revision, signed scoped pagination, strict UTF-8/JSON/body boundaries, actual measured projection/stages, safe failures, two-search admission and cancellation/deadline accounting.
- `__init__.py`, `__main__.py`, `config.py`: local runtime revision, telemetry/content tracing disabled before SDK imports, normal interactive shutdown without a traceback, and unchanged loopback-only listener policy. No model client or inference is initialized.
- Root `pyproject.toml`: existing API environment now installs this repository's Haystack source. Application mypy checks follow imported code silently so unrelated optional framework stub errors do not change the scope; all owned API files remain checked. Framework source is unchanged.
- `tests/test_lexical_routes.py`, existing HTTP/composition test helpers and `fixtures/lexical-evaluation.json`: real SQL/pipeline parity, ten labeled exact/identifier queries, non-gated paraphrases and transport/lifecycle regression tests. Existing development seed data remains unchanged.
- `scripts/workbench_lexical_smoke.py`: repeatable actual-network quality/outage/restart probes. It stores passage hashes and authoritative metadata rather than passage bodies or credentials.
- API/UI READMEs, canonical contract, lexical guide, foundation status, project map/engineering router and sidebar; release note `workbench-postgres-lexical-search-07b456b5787c2b27.yaml`.

Reuse and intentional contract reconciliation:
- Reused the verified PostgreSQL pool, schema `0001`, source/version/chunk records, forced RLS, server development resolver, native FTS and existing API envelopes. The earlier `pgvector-haystack` compatibility evidence justifies the small app-owned Haystack component instead of a second flat integration table.
- Per the user's clarification, the executable name is `postgres-fts-baseline`, initial revision `postgres-fts-baseline-r1`. Earlier `postgres-keyword-v1` had no executable binding and is rejected with 409, not treated as an alias. `bm25-v1` remains non-executable here.
- Preserved canonical required `expected_profile_revision`, `source_version_id`, omitted unknown page and 400/409 error semantics. The attachment's three-field example, `version_id` response alias and 422 wording were reconciled before completion. No frontend graph or Preview behavior changed.

Actual verification:

| Command / gate | Result |
| --- | --- |
| `hatch --version` | Hatch 1.18.2 |
| API environment source check | Haystack 3.5.0 resolves to the repository's `haystack/__init__.py` |
| `hatch run workbench-api:check` | All checks passed; 29 Python files formatted |
| `hatch run workbench-api:types` | No issues in 29 owned source files |
| Full focused API suite with explicit disposable PostgreSQL test DSNs and `--junitxml=tasks/evidence/postgres-lexical-tests-2026-11-21.xml` | **144 passed**, **0 skipped**, 21.55 seconds; **57 real PostgreSQL integration cases**, **87 unit/contract cases** |
| Published `openapi.json` | Exactly matches the implemented application; response/error schemas validated and obsolete automatic 422 entries removed |
| Ten gated exact-term/identifier queries | **10/10 expected sources in top five**, missed cases `[]`; fixture `development-corpus-v1`, actual corpus revision recorded in each report |
| Three non-gated paraphrases | **0/3 expected sources**; reported explicitly as a lexical limitation |
| Actual network baseline, `after-api`, `after-database` probes | Eight documents and identical corpus revision, ranked identities/scores and passage hashes in all phases; no runtime seed |
| Actual database stopped while API remains running | Liveness 200; readiness, search and documents 503; profiles empty; failed search has a run ID and no fixture/ephemeral fallback |
| Documentation / safety checks | MDX/GFM compilation for 12 Markdown files, 82 local links and six typed/JSON examples passed; four maintained guides/READMEs passed Prettier; release-note YAML and Git whitespace checks passed. Runtime credential scan of 5,257 tracked/unignored text files found no generated secret value. |
| Raw ASGI client disconnect regression | Confirmed transport disconnect cancels/awaits owned SQL cleanup, preserves slot accounting, returns no HTTP payload or traceback and records operational 499; unrelated external cancellation still propagates |

Evidence:
- [JUnit with evaluation properties and test cases](evidence/postgres-lexical-tests-2026-11-21.xml).
- [Actual HTTP, quality, outage and restart responses](evidence/postgres-lexical-http-2026-11-21.json). Real network corpus revision: `corpus-b30ac0b84585409663a73375da38f9e1b74d5ca288c6b2139c69c6975c1b21ac`; stable ranked-result/content-hash fingerprint: `4d61e3ebcf3313e910b7c0b3e3e78ebc1d3df41598de0570fbddf4e89407068b`. Temporary test databases have their own metadata timestamps and recorded revisions; their identical seed content is not falsely asserted to share the main database's full metadata fingerprint.
- [Lexical operations and limits](../docs-website/docs/architecture/postgres-lexical-search.md).

The real HTTP probe was executed through `hatch run workbench-api:python -m scripts.workbench_lexical_smoke` with phases `baseline`, `after-api`, `database-unavailable`, `after-database`. The API was restarted independently; the dedicated PostgreSQL service was stopped/restarted without removing the named volume. The ten query cases, no-hit case and negative profile/workspace/input cases were rerun over the same persisted records after restarts.

Independent source review and fault tests corrected stale success after shutdown, missing mandatory PostgreSQL qualification for injected executors, capability/dependency races, default FastAPI 422 schema drift, database-collation tie ordering and normal-disconnect tracebacks before completion. Mixed-case and punctuation identifiers are ordered with explicit SQL `COLLATE "C"`, matching projection checks rather than inheriting the database language collation. No broad exception details, request text, source bodies, DSNs or credentials are emitted by operational logging. Cursors expire on API restart or corpus/scope/list change; there is no wall-clock TTL claim.

Not run: full upstream Haystack suite, frontend runtime/browser checks and full Docusaurus build. No framework or UI runtime source changed; no database migration, new seed, TEI/GPU inference, semantic/vector HTTP search, RRF, generation or production authorization was performed. Existing database foundation evidence remains valid and unchanged. This is a local development lexical slice, not production tenant RBAC or a semantic-quality benchmark. The UI on port 4173 still runs Preview; live frontend binding remains a separate task. Rollback disables this API/profile while retaining PostgreSQL rows and volume.
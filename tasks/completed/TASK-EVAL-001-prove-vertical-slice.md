# TASK-EVAL-001 — Prove the UI → Haystack → PostgreSQL lexical vertical slice

**Created:** 2026-11-20\
**Updated:** 2026-11-22\
**Status:** COMPLETE — local browser/Haystack/PostgreSQL lexical acceptance verified on 2026-11-22\
**Priority:** P0 · evidence gate for Live\
**Dependencies:** TASK-RAG-001, TASK-DB-001, TASK-UI-001, TASK-UI-002\
**Repository state inspected:** implementation base `deb9fb63dde97f68db6dd856d1fc2a13a2af2255` plus preserved working-tree changes; original blueprint snapshot `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`\
**Deliverable location:** `tasks/TASK-EVAL-001-prove-vertical-slice.md`\
**Previous task:** [TASK-UI-002](TASK-UI-002-execute-live-lexical-pipeline.md)\
**Next task:** [TASK-RAG-002](TASK-RAG-002-ingest-text-and-markdown.md)

## A. Title

Provide a repeatable, evidence-backed acceptance gate proving that the new Live UI searches **real persisted PostgreSQL chunks** through the existing FastAPI/Haystack pipeline and that the rendered outcomes match the authoritative HTTP and SQL results.

## B. Context / Problem

An end-to-end acceptance test must prove more than a green UI state. The backend has already shipped a qualified development lexical API and its **own** integration evidence; this task is not to write a second fake corpus or reproduce the existing PostgreSQL tests. Its missing proof is the new **browser-to-service** edge, UI-visible source/score parity, resilience to an outage, and reproducible diagnostics through the entire path.

The distinction between data and interpretation is essential: `postgres-fts-baseline` ranks persisted PostgreSQL `tsvector` using `ts_rank_cd`, not BM25. Its raw values are not probabilities, vector similarity, answer quality or a guarantee of semantic paraphrase recall. The current corpus is a bounded **eight-document synthetic development corpus**, not a production sample. Run the exact-term tests as an acceptance gate and preserve the three paraphrase misses as diagnostic baseline evidence.

## C. Current Repository State

### Actual evidence to **reuse**

| File/source (repository-relative hyperlink) | Current evidence | Consequence for this task |
| --- | --- | --- |
| [Lexical evaluation fixture](../apps/workbench/api/fixtures/lexical-evaluation.json) | `gated_exact_queries` contains **10** query → `expected_source_id` pairs; `diagnostic_paraphrases` contains **3** additional cases. | Treat as the canonical gold set; do not invent another ten-question dataset. |
| [Explicit development seed](../apps/workbench/api/fixtures/development-corpus.json) and [seed logic](../apps/workbench/api/db_seed.py) | Eight deterministic non-sensitive source records; seed is **explicit** and refuses a mutated/non-demo corpus. | Seed once on a clean development volume; do not reset or reseed after content changes. |
| [Backend lexical integration tests](../apps/workbench/api/tests/test_lexical_routes.py) | Actual `Pipeline.run_async`, PostgreSQL score parity, 10 gated exact cases, paraphrase diagnostics, zero hits, pagination, authorization, outages and cancellations. | Keep passing; reuse existing assertions, not copy-paste them into new test files. |
| [Recorded lexical HTTP evidence](../tasks/evidence/postgres-lexical-http-2026-11-21.json) | Captures ready profile, 8 persisted items, real run IDs, raw scores, SQL/result fingerprints and API/DB restart checks. | Establish backend baseline; newly generated UI evidence must add browser observations. |
| [PostgreSQL-focused test evidence](../tasks/evidence/postgres-lexical-tests-2026-11-21.xml), [database restart evidence](../tasks/evidence/postgresql-restart-2026-11-21.json) | Earlier scoped tests and persistence recovery evidence. | Cite historic baseline separately from the new test run. |
| [FastAPI contracts](../apps/workbench/api/contracts.py), [routes](../apps/workbench/api/application.py), [projection](../apps/workbench/api/projection.py) | `SearchResponse` returns `run_id`, `request_id`, `trace_id`, `corpus_revision`, timings and actual ranked chunks. | Compare browser-visible fields to live response exactly. |
| [SQL persistence](../apps/workbench/api/postgres.py) | `lexical_search_snapshot()` evaluates `ts_rank_cd`, active versions, RLS and a consistent source fingerprint in one read-only snapshot. | Optionally cross-check SQL for sampled cases, no independent query engine. |
| [UI `App.tsx`](../apps/workbench/web/src/App.tsx), [approved graph matcher](../apps/workbench/web/src/domain/approvedExecution.ts), [Live request lifecycle](../apps/workbench/web/src/domain/liveSearch.ts), [hook](../apps/workbench/web/src/hooks/useLiveSearch.ts) | UI-002 already routes explicit Live mode through the exact three-node keyword graph and four-field API request; Preview has a separate fixture path. Request generations reject stale context and Stop reports local interruption. | Verify the existing real browser edge; do not implement a second Live executor. |
| [Live result presentation](../apps/workbench/web/src/components/LiveRunDetails.tsx), [Results panel](../apps/workbench/web/src/components/ResultsPanel.tsx), [run history](../apps/workbench/web/src/views/RunsView.tsx) | Live cards already expose ordered source/version/chunk/rank/raw-score attributes, exact response JSON, actual server stages and correlation/profile/corpus details; `page == null` renders unavailable. | Reuse existing selectors/presentation for UI ↔ response parity, with fixes only for observed defects. |
| [Preview fixtures](../apps/workbench/web/src/domain/preview.ts), [Preview browser smoke](../apps/workbench/web/scripts/browser-smoke.js) | Hard-coded retrieval hits/durations and existing browser regressions. | Preview remains independent; no Preview hit may count toward Live metrics. |
| [Validation client](../apps/workbench/web/src/domain/validation.ts), [validation smoke](../apps/workbench/web/scripts/validation-smoke.js) | Constructor validation on port 8010, unrelated to executable readiness on port 8011. | Preserve and test this third, separate meaning of “valid.” |
| [Vite proxy](../apps/workbench/web/vite.config.ts) | Both dev and preview already proxy `/api/v1` → 8011 independently of `/api/pipelines/validate` → 8010. | Verify browser requests actually reach FastAPI; no proxy implementation is missing. |
| [Existing Live smoke](../apps/workbench/web/scripts/live-search-smoke.js) | Real `retention`/`GIN`/empty search capture and parity checks, followed by separately injected fault paths, already exist. | Add the canonical 10+3 acceptance matrix and restart evidence; do not recast the older smoke as the new full evaluation. |
| [Canonical API contract](../docs-website/docs/architecture/rag-runtime-contract.md), [lexical guide](../docs-website/docs/architecture/postgres-lexical-search.md), [database runbook](../docs-website/docs/architecture/postgresql-foundation.md) | Current authoritative runtime, errors, and start/restart commands. | Specifications and reports MUST follow these contracts, not the dated superseded storage proposal. |

**Reinspection on 2026-11-22:** UI-001/UI-002 are actual implemented prerequisites, verified in the sources above. The three cited 2026-11-21 backend/restart artifacts exist and remain historical evidence. The canonical fixture still contains ten gated exact and three diagnostic records, and the seed fixture contains eight synthetic sources; current database counts must be observed rather than inferred from file presence. The new 10+3 browser evaluation/report remains unexecuted at task creation. Existing CHUNK/parser/AGENTS dirty work is preserved and does not become evaluation evidence by association.

**Error-correlation warning:** the previous draft expected 422 for invalid input. Current FastAPI normalizes request failures to **400**. Unknown workspace currently returns **404** (not an inferred 403). `409` is the stale/unapproved profile path, `429` capacity, `503` dependency/unready, and `504` deadline. The E2E matrix must test real status and nested `error.code` rather than guess.

## D. Goal

Produce one reproducible acceptance package that demonstrates, with directly inspectable evidence:

1. A browser in **Live** mode selects the approved server profile and workspace, submits the four-field request and renders the **actual** returned result list.
2. Result source/version/chunk IDs, rank, raw score and score type are identical to the actual HTTP response, with no simulated result or fake stage duration.
3. The same ten backend-gold lexical questions can be exercised from the browser, with per-case Recall@5 and reciprocal-rank calculation; zero results and three diagnostic paraphrases remain visible.
4. Changing the query changes the persisted result identity when expected; the `corpus_revision` is unchanged by read-only queries and remains stable over an API/DB restart on the **same** volume.
5. Offline, unready, bad profile and invalid-body failures cannot display a false Live completion or Preview content.
6. Every failure can be correlated with a captured request/trace/run ID and a safe error code, without exporting secrets or private document text.

## E. Scope

- New browser-level Live smoke/evaluation script; test harness may call documented endpoints and collect network evidence but must not fabricate API responses in the **real-service** lane.
- Explicit operator runbook for the existing PostgreSQL, API, validator (optional for Live) and Vite processes.
- Reuse of `gated_exact_queries`/`diagnostic_paraphrases`, plus the existing service tests as mandatory baseline checks.
- New frontend unit tests only for missing quantitative helpers, selectors or visible presentation parity, not duplicate business logic.
- Two distinct evidence lanes: **real service** (live database/API/browser) and **mock fault injection** (deterministic UI failure paths).
- Report metric definitions, per-question results, traceability, versions, sample counts, latency distributions, known lexical limitations and all failures.
- A short, durable Markdown acceptance report under `docs-website/docs/tasks/`; runtime evidence can be attached under `tasks/evidence/` using the established evidence patterns when executing the task.

## F. Non-Goals

- No new embedding model, TEI qualification, cosine index, genuine BM25 extension, RRF, rerank, answer generation, LLM quality or GPU throughput claims.
- No unauthorized multi-tenant administration, remote CI environment provisioning, production latency SLO or artificial passing score targets.
- Do not replace the existing labeled corpus, modify `ts_rank_cd` behavior to make a test green, auto-migrate/reseed databases on application start or generate screenshots showing mock data as Live proof.
- No new server-side persistent run-history API: current `run_id` is a search correlation identifier; browser history is session-local.

## G. Architecture / Boundaries

```text
[Playwright real-browser acceptance]
       |  observes user input, mode, request, displayed fields
       v
[React Workbench — UI-001 / UI-002]
       |  POST /api/v1/workspaces/development/search
       v
[Vite same-origin /api/v1 proxy]
       v
[FastAPI RequestBoundary + v1 contracts]
       v
[LexicalService -> Haystack Pipeline.run_async]
       v
[PersistencePort -> PostgreSQL/FORCE RLS -> active chunks]
       |
       +--> response IDs, actual score_type, timings, corpus_revision
       +--> evidence collector (sanitized; never fixture Preview)

Separate: [preview fixture smoke] and [constructor validator smoke]
```

- **Application/core**: ranking and authorization remain on the server. The test reads; it does not own a competing ranking policy.
- **Port/contract**: use the published `rag-api-v1.0` schema, exact profile/revision and observed HTTP statuses.
- **Observability**: correlate browser network response and UI fields, not console prints of sensitive content.
- **Infrastructure**: use only the existing PostgreSQL + pgvector stack and detached Hatch API environment; do not modify Haystack internals.
- **Security**: explicit development workspace only; RLS and scope checks are still enforced server-side.

## H. Contracts / Interfaces / Data Model

### H1. Immutable existing request and response identity

Use the actual POST endpoint:

```http
POST /api/v1/workspaces/development/search
Content-Type: application/json

{
  "query": "retention",
  "top_k": 5,
  "profile_id": "postgres-fts-baseline",
  "expected_profile_revision": "postgres-fts-baseline-r1"
}
```

The response envelope provides `contract_revision = "rag-api-v1.0"`, `mode = "live"`, `status = "success"`, server `run_id`, `request_id`, `trace_id`, `workspace_id`, `corpus_revision`, `profile_id`, `profile_revision`, `duration_ms`, `stages[]` and `results[]`. Each result has `chunk_id`, `source_id`, `source_version_id`, `rank`, `title`, `content`, raw `score`, `score_type = "postgres_ts_rank_cd"` and optional/null `page`. Missing/null page metadata renders unavailable, never zero or an invented citation.

Frontend must NOT replace the raw score with a normalization, percentage or a rounded value in exported JSON. UI can use formatting for visual display if raw value remains available.

### H2. Metric definitions

Let `Q_exact` be the ten **already versioned** exact/identifier questions and `Q_para` the three diagnostic paraphrases from [lexical-evaluation.json](../apps/workbench/api/fixtures/lexical-evaluation.json). Each question labels **one expected source ID**, so metrics measure relevant source presence, not chunk-level relevance judgments:

- `hit@5(q) = 1` if the expected `source_id` appears in returned ranks 1..5, otherwise `0`.
- `Recall@5` for this **single-relevant-source** dataset is `sum(hit@5) / |Q|`. Name the report `expected-source-hit-rate@5` alongside Recall@5 to avoid implying an exhaustively judged corpus.
- `reciprocal_rank(q) = 1/r` where `r` is the first rank of expected source (1..5 in the cut-off evaluation), else `0`.
- `MRR@5 = sum(reciprocal_rank(q)) / |Q|` with the denominator including misses, errors and timeouts.
- `zero_hit_rate = number of successful 200 responses containing [] / number of successful 200 search responses` in the named query group. Report that denominator and failed attempts separately; a transport/HTTP error is not a successful empty result.
- Latency percentiles use **nearest rank**: sort the identified real samples ascending, then `p(q) = x[ceil(q * n) - 1]` for `q=0.50`/`0.95`. No interpolation, warmup sample deletion or zero imputation. Report `n`, startup/warm status, server `duration_ms` and independent browser request elapsed time separately; never pool these series or include mock faults in real-service latency. An absent observation is `NOT TESTED`/missing, never zero.
- Do not compute precision/nDCG without complete per-query relevance labels; do not treat all unjudged chunks as definitely irrelevant.

**Acceptance policy:** all 10 exact cases must be executed and reported; at least 9 of 10 must have expected source within top five for this development gate. Existing backend evidence previously records 10/10, so any reduction is a regression to investigate. **All three** paraphrases must be reported regardless of results and are not a release gate for a lexical-only profile. The test must fail on missing/errored cases, not remove them from the denominator.

### H3. Evaluation evidence (internal test artifacts, not an HTTP API)

The contract below is the original compact shape. The implemented package stores a phase report for `baseline`, `after-api` and `after-database`, an aggregate `acceptance-summary.json`, a `source-build-manifest.json`, and an independent `evidence-audit.json`. Per-phase `summary.exact`/`summary.paraphrase` retain all labeled denominators; the combined latency series has 14 successful UI queries including one explicit no-match. Environment/build fields live in the manifest/SQL artifacts instead of being duplicated into each case. This is no public API/schema change.

```text
EvaluationReport
  captured_at_utc: timestamp
  repo_revision: string
  ui_build_reference: string
  backend_revision: string
  contract_revision: "rag-api-v1.0"
  profile_id: string
  profile_revision: string
  corpus_revision: string
  database_schema_revision: string
  corpus_id: string
  run_mode: "real_browser_api_postgres"
  exact_cases: Case[]
  paraphrase_cases: Case[]
  error_cases: ErrorCase[]
  summary:
    tested_exact, passing_exact, source_hit_rate_at_5, mrr_at_5
    tested_paraphrase, passing_paraphrase
    server_latency_ms: {sample_count,p50,p95,max}
    browser_elapsed_ms: {sample_count,p50,p95,max}
  regressions: string[]
  limitations: string[]

Case:
  query_id, query_label_or_hash, expected_source_id
  returned_source_ids, returned_chunk_ids, ranks, score_type
  server_run_id, request_id, trace_id
  corpus_revision, duration_ms, browser_elapsed_ms
  hit_at_5, reciprocal_rank, outcome

ErrorCase:
  scenario, status, error_code, request_id, trace_id
  live_fixture_fallback_observed: false
```

Keep query **text** out of distributable evidence if later non-synthetic data is used; the synthetic gold labels may remain in the versioned fixture. Never store credentials, DSNs, raw original uploads, vector values or unrelated response bodies. Runtime evidence files other than Markdown are test outputs, not new human-facing documents.

### H4. Actual error contract

Errors have the nested Pydantic shape:

```json
{
  "contract_revision": "rag-api-v1.0",
  "request_id": "<server-generated>",
  "trace_id": "<server-generated>",
  "error": {
    "code": "PROFILE_NOT_AVAILABLE",
    "message": "<safe-text>",
    "retryable": false,
    "http_status": 409,
    "run_id": "<optional>"
  }
}
```

Test **400** malformed/invalid request, **404** unauthorized workspace, **409** revision/profile mismatch, **429** search admission, **503** dependency or unreadiness, **504** deadline, and proxy/network unavailable. A server may provide an `X-Request-ID` header; assert it matches JSON `request_id` on received HTTP responses. A local fetch/network rejection has **no server `request_id`** and must not invent one.

## I. Repository Files / Components Impacted

| Path | Expected action | Why |
| --- | --- | --- |
| [`apps/workbench/api/fixtures/lexical-evaluation.json`](../apps/workbench/api/fixtures/lexical-evaluation.json) | **Read/reuse**, generally no changes | Source of ten + three gold queries. |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../apps/workbench/api/tests/test_lexical_routes.py) | **Run/reuse** | Baseline HTTP-to-SQL and failure-path suite. |
| [`tasks/evidence/postgres-lexical-http-2026-11-21.json`](../tasks/evidence/postgres-lexical-http-2026-11-21.json) | **Read/reuse, do not overwrite** | Historical backend evidence. |
| [`apps/workbench/web/scripts/browser-smoke.js`](../apps/workbench/web/scripts/browser-smoke.js) | **Keep passing** | Preview-only browser baseline. |
| [`apps/workbench/web/scripts/validation-smoke.js`](../apps/workbench/web/scripts/validation-smoke.js) | **Keep passing** | Independent constructor validator. |
| `apps/workbench/web/scripts/live-evaluation-smoke.js` | **Create** | Real API-browser E2E trace and result parity checks. |
| `apps/workbench/web/scripts/live-resilience-smoke.js` | **Create** | Supervised real outage/reconnect observations and separately labeled stale-response/inert-text tests. |
| `scripts/workbench_evaluation_probe.py` | **Create** | Reuse existing lexical HTTP collection and read-only `PostgresPersistence` SQL parity without a second ranking engine. |
| `scripts/run_workbench_live_evaluation.ps1`, `scripts/run_workbench_recovery_evaluation.ps1` | **Create** | Canonical fixture injection, sanitized artifact retention and guarded same-process/volume recovery supervision. |
| Optional `src/domain/evaluation.test.ts` | **Not needed** | Metrics remain test-harness code and are independently recomputed in the artifact audit; no additional application ranking/evaluation module. |
| [`apps/workbench/web/src/App.tsx`](../apps/workbench/web/src/App.tsx), [`components/ResultsPanel.tsx`](../apps/workbench/web/src/components/ResultsPanel.tsx), [`views/RunsView.tsx`](../apps/workbench/web/src/views/RunsView.tsx) | **Read; small fixes only if evidence finds a defect** | Capture actual UI result fields. |
| [`apps/workbench/api/contracts.py`](../apps/workbench/api/contracts.py), [`application.py`](../apps/workbench/api/application.py), [`postgres.py`](../apps/workbench/api/postgres.py) | **Read, must not change merely to green the eval** | Server response and SQL authority. |
| `docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md` | **Create** | Current-date Markdown acceptance report with actual commands, two evidence lanes, metrics and limitations. |
| `tasks/evidence/eval-vertical-2026-11-22/` | **Generate when tests execute** | New sanitized API/SQL/browser/restart/check artifacts; preserve all historical evidence. |
| `apps/workbench/web/README.md`, `docs-website/PROJECT_MAP.md`, `docs-website/sidebars.js` | **Scoped update** | Document the new evaluation run and report navigation; correct proven discovery-only wording without rewriting existing behavior. |

**Source rule:** if a source path or endpoint changes after this reviewed commit, update Section C/H/I **before** expanding the task scope. Do not modify `haystack/`, database migration `0001`, or the baseline fixture to hide an E2E failure.

## J. Implementation Requirements — executable blueprint

### J1. Establish a non-destructive environment baseline

1. Confirm `hatch --version`, Docker, Node 22.12+ and that the API and browser tools are available.
2. Start the application-owned container through [Compose](../apps/workbench/postgres/compose.yaml) using the [PostgreSQL operations guide](../docs-website/docs/architecture/postgresql-foundation.md); do not use `down -v`.
3. For an **empty and explicitly disposable** local database, use the runbook to create environment, bootstrap role, apply migration and explicit seed. For a populated volume, **inspect first** and do not re-run `db-seed` after user-supplied sources were published.
4. Load app-only environment (`use-dev-env.ps1`), start `hatch run workbench-api:serve` and record non-secret schema/backend revision. Do not copy the environment file into evidence.
5. Verify `/api/v1/health/ready`=200 and `/api/v1/capabilities` advertises `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`, workspace `development`, matching database state.
6. Start Vite using the UI-001 proxy. Select explicit Live. Validator on 8010 may be started separately for its regression test; it is **not required** to falsely enable Live readiness.

**Gate:** all probes return authoritative data; no automatic seed, migration or fixture fallback occurred.

### J2. Reuse the existing gold questions and executable profile

1. Parse existing [lexical-evaluation.json](../apps/workbench/api/fixtures/lexical-evaluation.json) and validate 10 exact and 3 diagnostic records have nonempty unique queries and expected IDs.
2. Take `profile_id` and `profile_revision` from live capabilities—not a stale hard-coded browser setting—and `top_k=5` within advertised bounds.
3. In the browser, select the task's approved `keyword` graph and run a **fresh** Live request per query. Do not issue raw test-only API requests and count them as UI execution.
4. Capture the outbound request shape and inbound HTTP response with Playwright in the real-service lane. Assert **exact four request body keys**, live response envelope, score type and workspace.
5. Verify `results[].source_id` matching by first five ranks. Record every case, including zero hits or HTTP failures. Record MRR using **first** relevant source rank.
6. Cross-check selected real hit metadata through existing [PostgresPersistence](../apps/workbench/api/postgres.py) or by running existing [test_lexical_routes.py](../apps/workbench/api/tests/test_lexical_routes.py); do not run tests as a privileged SQL bypass against production data.

**Gate:** ten exact cases and three diagnostics attempted; all records counted, none borrowed from Preview.

### J3. Assert browser/network/SQL presentation parity

1. For every successful response, collect ordered `(chunk_id,source_id,source_version_id,rank,score,score_type)` tuples from HTTP.
2. Inspect rendered Results panel and JSON tab; compare identity and ordering exactly. Numeric display rounding is acceptable only when raw JSON still matches `score` exactly; never replace with percentages.
3. Ensure `page` **absent** is shown as unavailable, not `0`; server `duration_ms` and stage timings are displayed as server metrics. If a browser network measurement is shown, label it separately.
4. Assert server `run_id`, `trace_id`, `request_id`, `profile_revision`, `corpus_revision` remain accessible in Live run details; a Preview `liveRunId` variable is not server evidence.
5. Run two discriminating corpus terms, e.g. `retention` and `GIN`; assert their successful result lists include different authoritative `source_id` values. Query strings alone changing is insufficient proof.
6. Assert the run list distinguishes **Preview** versus **Live** and does not claim persisted server-side historical runs.

**Gate:** no mismatch for selected or complete captured cases; otherwise fail with precise field and source/HTTP IDs.

### J4. Test negative boundaries in both real and mocked lanes

1. Real service: POST an unavailable/mismatched profile revision, nonexistent workspace, invalid request body and a query designed for zero hits. Verify actual 409/404/400/200-empty outcomes and UI displays no simulated fallback. Use API tests for rare concurrency and genuine timeout behavior.
2. Browser fault-injection: intercept only targeted `/api/v1/...` calls to return well-formed safe **429, 503, 504** envelopes, malformed 200, or a network failure. Clearly label this evidence `mock_fault_injection`; it does not prove the backend genuinely failed.
3. Stop the API: ensure **Live** displays a transport error and `Preview` remains user-selectable only by explicit action; no auto-switch.
4. Race tests: change mode, workspace or graph while an older Live request is pending; reject stale UI commits even if a mock transport ignores abort.
5. Stop/cancel: verify the browser marks local abort honestly, and a server run is not declared cancelled without an authoritative server record. Backend cancels/disconnects and releases SQL resources per existing tests.
6. Verify separate `Validate` retains its real constructor-only semantics even if Live search works.

**Gate:** each negative case produces a distinct and safe observable outcome; false Live success count = 0.

### J5. Verify persistence and stable read-only behavior over restart

1. Snapshot source/chunk IDs and `corpus_revision` from a real search. Do not publish new documents during this restart comparison.
2. Restart API, re-query and compare source/chunk/version identities and `corpus_revision`; server request/run/trace IDs should change and must **not** be expected to stay equal.
3. Restart PostgreSQL **without deleting/recreating its named volume**. Check readiness recovers, then compare identities and corpus revision again.
4. If the backend invalidates pagination cursors on restart, that is expected; restart list pagination from first page. Do not turn an expired cursor into content loss.
5. Record DB schema revision, Docker image revision, API version, UI commit, command invocations and any recovery issue. Preserve existing prior evidence rather than overwriting it.

**Gate:** persisted identity/content remains unchanged, no seed rerun or temporary in-memory substitute.

### J6. Calculate metrics, review limitations and publish reports

1. Compute per-case hits and reciprocal ranks using the existing labeled fixture; use a pure TypeScript/Python test helper only if needed, but no duplicate ranking code.
2. Aggregate exact and paraphrase groups **separately**. Report sample counts and all failures in the denominator; calculate p50 and p95 with documented order-statistic/interpolation convention and `n`.
3. Write [Markdown report path from I] documenting method, commands, actual test outcomes and screenshots/network evidence IDs. Separate **observed** results from anticipated design thresholds.
4. Run existing backend integration, frontend `typecheck`/`format:check`/`test`/`build`, Preview smoke and validation smoke. Record exact executed commands and failures.
5. Review privacy: redact secrets, DSNs, original user content, raw request bodies in logs; use only non-sensitive synthetic gold for public evidence.
6. Leave status PROPOSED/BLOCKED if the browser path does not exist or any mandatory gate fails. No “complete” from source inspection alone.

**Gate:** report is reproducible by another engineer without modifying database data or accepting unmeasured quality claims.

## K. Security / Governance / Observability

- Backend ownership, workspace and RLS checks stay server-side. A 404 on foreign workspace is expected; the frontend selector is **not** authorization.
- Synthetic corpus only for shareable reports. Uploads and future customer text must never be exported by the evaluation harness by default.
- Use server-provided `request_id`/`trace_id`/`run_id` for troubleshooting. Do not log raw queries, retrieval text, DSN, credentials, vectors or server stack traces.
- Explicitly distinguish `network_unavailable` from `DEPENDENCY_UNAVAILABLE`, and `VALIDATION_UNAVAILABLE` from Live execution errors.
- `Not ready` must not mean `healthy because PostgreSQL answered ping`; only the qualified execution profile advertises readiness.
- Prompt-injection test: a snippet containing apparent instructions or HTML is displayed as plain text, never executed, hidden, or used to alter the test.
- Evidence retention must be defined before using real customer data; the initial synthetic-only run has no production retention policy claim.

## L. Testing / Evaluation / Runtime Verification

### L1. Baseline commands (repository-root PowerShell)

```powershell
hatch --version
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
# Run in a separate process/terminal; do not claim this was run in documentation-only work.
```

For backend regression use the task-specific Hatch environment and targeted tests from [API README](../apps/workbench/api/README.md) and [lexical guide](../docs-website/docs/architecture/postgres-lexical-search.md); record actual output. For the frontend:

```powershell
cd apps/workbench/web
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
npm run dev
```

The implemented browser scenario uses the runner-configured `apps/workbench/web/scripts/live-evaluation-smoke.js` described in the [Workbench README](../apps/workbench/web/README.md). `scripts/run_workbench_live_evaluation.ps1` loads the canonical fixture and injects its phase configuration; `scripts/run_workbench_recovery_evaluation.ps1` supervises real recovery and repeats the checks. The captured success path uses actual network responses, not hard-coded search results.

### L2. Minimum test matrix

| Case | Trigger | Expected observation | Where |
| --- | --- | --- | --- |
| Exact lexical gold | All 10 existing `gated_exact_queries` | >=9/10 expected source in rank <=5; actual scores and trace IDs | Real browser + API |
| Known lexical limitations | All 3 `diagnostic_paraphrases` | Every attempt reported; miss allowed; no semantics inferred | Real browser + API |
| Query discrimination | `retention` vs `GIN` | Different source IDs, same corpus revision | Real browser + API |
| No matches | Unmatched safe term | HTTP 200, `results: []`, UI success/empty | Real browser + API |
| Raw ranking parity | Selected hit + SQL parity from existing tests | `postgres_ts_rank_cd` raw score; no BM25/probability label | API + UI |
| Missing page | Seed hit with no page metadata | Omit page; UI shows unavailable | Real browser |
| Invalid request/profile | Invalid body + unapproved revision | HTTP 400/409 and nested safe errors | Real API + UI |
| Unauthorized workspace | Unknown workspace ID | HTTP 404; no foreign results | Real API + UI |
| Busy/deadline | Exceed backend admission or injected failure | Backend tests validate 429/504; browser UI reflects mocked envelopes | API tests + mock UI |
| Offline/backend failure | Stop backend while Live selected | No fake completion, recover only after reconnect | Real browser |
| Stale result | Request A pending then query/mode/workspace changed | Never overwrite active Live view with A | Browser fault injection |
| Persisted restart | API then DB restart, same volume | Result identity/revision preserved | Real API + DB + browser |
| Preview regression | Original six-node template and error scenario | Exactly existing demo behavior, labeled Preview | Preview browser smoke |
| Validator regression | Existing constructor contract | Validator status still independent of Live | Validator smoke |

### L3. Mandatory report fields

Report environment (OS/tools, API version, relevant commit, PostgreSQL/pgvector revisions), list of executed commands, raw **synthetic** test case IDs and expected/actual source IDs, exact profile/corpus revisions, status codes, per-stage and total durations, metric formulas/sample counts, p50/p95, browser/SQL parity, recovery proof and failures. A **missing observation** is `NOT TESTED`, never zero milliseconds or success.

## M. Acceptance Criteria

- [x] Backend retrieval regression remains green: 38 tests passed, zero skips; historical evidence remains separately referenced.
- [x] All 10 exact and 3 diagnostic cases have real browser attempts in all three phases, with captured server IDs: 39 canonical attempts total.
- [x] Exact hit@5=10/10 and MRR@5=1.0 in every phase; diagnostic hit@5=0/3 and MRR@5=0.0, with every miss retained.
- [x] UI/HTTP/SQL source/version/chunk/rank/raw-score/content-hash parity holds for 39 canonical cases; three extra empty cases have browser/HTTP parity. Actual server stages and request/trace/run IDs remain visible.
- [x] `retention` and `GIN` return different persisted source IDs while reads preserve the corpus/registry fingerprint.
- [x] Real API/database outages and nine mock error shapes, local Stop and strengthened late-response cases produce zero fixture fallback/false Live completion.
- [x] API process replacement and PostgreSQL stop/start preserve the same volume, source/version/chunk identities, content, migration ledger/image and corpus revision; no reseed/migration.
- [x] Existing Preview and constructor-validator browser regressions pass independently.
- [x] Sanitized local machine artifacts and the [dated report](../docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) record exact methods, versions, commands, counts, limitations and retained automation incidents.
- [x] Haystack implementation, migration `0001`, canonical gold fixture and main corpus are unchanged by evaluation; prior dirty work is preserved.

## N. Documentation / Migration / Compatibility / Rollback

- Produce `docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md` as a durable repository-local acceptance artifact, linking [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and [lexical API guide](../docs-website/docs/architecture/postgres-lexical-search.md). New evidence lives under `tasks/evidence/eval-vertical-2026-11-22/`; historical artifacts remain untouched. Update the task with actual PASS/FAIL/NOT TESTED per gate.
- No schema migration in this evaluation task. Existing `development` seed must not be overwritten. Metrics must pin corpus/profile revisions to permit future comparisons.
- When a gate fails, leave Live unavailable to general users or roll back only frontend Live exposure; preserve PostgreSQL data, API implementation and Preview/validator paths. Correct the defect and rerun the failed **and** regression cases.
- Later semantic/hybrid tasks may add metrics under separate profile IDs, but the existing lexical baseline remains valid for regression comparisons.

## O. Mandatory Completion Checklist

- [x] Existing UI-002 Live path was executed through the local browser, actual API and persisted PostgreSQL.
- [x] The canonical 10+3 fixture was loaded by the runner; all labeled attempts and misses counted separately from explicit no-match/error probes.
- [x] Actual statuses/profile/corpus revisions, unique server IDs and raw `postgres_ts_rank_cd` semantics verified.
- [x] 39 canonical browser/HTTP/SQL comparisons passed; three additional empty browser/HTTP responses passed, with no Preview substitution.
- [x] API/database recovery retained the same data/volume without migration, seed or destructive reset.
- [x] Real outages, real request-mutation errors, mock failures, local Stop, active/history stale-response guards and independent validator all covered.
- [x] Metrics use all-attempt denominators, top-five cutoff, explicit n and nearest-rank p50/p95; coarse observed zero-ms readings remain distinct from missing data.
- [x] Backend 38 and frontend 259 tests, frontend type/format/build, probe static checks and independent browser smokes actually passed.
- [x] Independent artifact audit confirms no configured credentials or full passage bodies, current source/build hashes and preserved historical evidence; machine artifacts stay local under the existing ignore policy.
- [x] The [report](../docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md), generated [summary](evidence/eval-vertical-2026-11-22/acceptance-summary.json), [audit](evidence/eval-vertical-2026-11-22/evidence-audit.json) and raw phase artifacts substantiate completion.

### Completion evidence and boundaries

Final execution uses the existing local Windows services, not a remote deployment. Baseline, after-API and after-database browser reports each contain 14 successful queries: 10 exact, 3 diagnostic, 1 explicit no-match. SQL parity separately queries the 13 canonical cases per phase. Real invalid body/workspace/profile responses are 400/404/409; stopping API produces proxy 502 without invented server IDs, and stopping PostgreSQL produces real correlated 503/Not ready. Recovery artifacts preserve all prior source/version/chunk identity on `rag-workbench_postgres_data`.

Two test-proof weaknesses were repaired without application changes: late responses are now checked in Runs history as well as the active panel, and the runner preserves sanitized FAIL artifacts. A deliberate runner failure verifies that behavior; it is not a product gate failure. Empty hosted CLI output and an initial cleanup selector mistake are retained as automation incidents, with successful complete reruns/restoration. The final browser is restored to unmocked Live `retention`/`demo-backup`, outside metric samples.

The implementation is a working-tree change on inspected base `deb9fb63dde97f68db6dd856d1fc2a13a2af2255`; no new commit/deployment is invented. This completes the synthetic local lexical acceptance gate only. It does not qualify semantic recall, production latency/security, ingestion, embeddings, generation or remote operation. Existing ignored artifact retention and all prior parser/chunker/AGENTS work remain unchanged.

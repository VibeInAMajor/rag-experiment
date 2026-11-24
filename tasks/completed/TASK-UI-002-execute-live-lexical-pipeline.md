# TASK-UI-002 — Execute the approved PostgreSQL lexical profile from the Workbench

**Created:** 2026-11-20  
**Updated:** 2026-11-24  
**Status:** COMPLETE — implemented and verified on 2026-11-21  
**Priority:** P0  
**Dependencies:** TASK-RAG-001 (COMPLETE), [TASK-UI-001](TASK-UI-001-typed-api-and-execution-mode.md) (COMPLETE; acceptance evidence reviewed); coordinate with completed TASK-VAL-001  
**Repository state inspected:** `1d082e043a7d7c8f89d7623cac321d7b83218f23` (UI-001 completed; original blueprint inspected `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`)  
**Deliverable location:** `tasks/TASK-UI-002-execute-live-lexical-pipeline.md`  
**Follow-up acceptance:** TASK-EVAL-001 (separate planned evaluation task; document not checked in)

## A. Title

Wire the Run action to the already implemented **allowlisted** `postgres-fts-baseline` search API; preserve the existing Preview graph and show server-authoritative ranks, sources, versions, correlation and measured timings.

## B. Context / Problem

The default graph is **Hybrid retrieval** (`query -> bm25 + text-embedder -> vector -> joiner -> results`). The actual executable backend supports **only one** profile: PostgreSQL `simple` full-text search using `ts_rank_cd`, `profile_id="postgres-fts-baseline"` and `profile_revision="postgres-fts-baseline-r1"`.

Calling the backend through the current `bm25` node would misrepresent algorithm and score semantics. Sending imported React Flow graph JSON to the server would bypass its allowlisted fixed Haystack pipeline. Presenting client-calculated node timelines would fabricate evidence. We need a small, **strictly matched editor representation** of the backend's lexical query, not an interpreter for all graph components.

The user must get a clear result for three independent concepts: (1) Preview passes its fixture DAG checks; (2) the constructor validator may say `unsupported` for conceptual UI nodes; (3) an **approved Live graph** is executable when the execution API advertises a compatible profile. Constructor validation does not supersede execution-profile authorization.

## C. Current Repository State

Implementation start rechecked the clean UI-001-complete commit above. The transport already provided runtime-validated discovery and the shell had Preview/Live controls; it did not yet expose POST search. The inventory below describes the pre-execution owners. Completion evidence and final owners are recorded in P.

### Actual code and contracts reviewed

| Owner                                                                                                                                           | Current source and precise finding                                                                                                                                                        | Consequence                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| [backend `lexical.py`](../../apps/workbench/retrieval/lexical.py)                                                                                        | `_build_pipeline()` creates a fresh single-component Haystack `Pipeline`; `PostgresLexicalRetriever.run_async()` calls `PersistencePort.lexical_search_snapshot()`.                       | Do not build an interpreter of arbitrary React nodes in the client/server.                                                                         |
| [backend `application.py`](../../apps/workbench/api/application.py)                                                                                | `_Routes._search()` enforces profile and revision, admission capacity, timeout and authorized workspace.                                                                                  | Reuse the existing route and error codes.                                                                                                          |
| [backend `profiles.py`](../../apps/workbench/retrieval/profiles.py)                                                                                      | `postgres-fts-baseline` / `postgres-fts-baseline-r1`.                                                                                                                                     | Select from capabilities, do not assume hard-coded version forever.                                                                                |
| [backend `contracts.py`](../../apps/workbench/contracts/schemas.py)                                                                                    | `SearchRequest` has **four required keys** `query`, `top_k`, `profile_id`, `expected_profile_revision`. `SearchResult` uses `source_version_id`, not `version_id`; `page` may be omitted. | Earlier task draft omitted `expected_profile_revision` and used the wrong version field; both must be corrected.                                   |
| [backend `projection.py`](../../apps/workbench/api/projection.py)                                                                                  | Actual server `run_id`, `request_id`, `trace_id`, `corpus_revision`, `duration_ms`, three `stages` and ranked `results`.                                                                  | Display real measured values only.                                                                                                                 |
| [backend `postgres.py`](../../apps/workbench/postgres/postgres.py)                                                                                      | Native `plainto_tsquery('simple', ...)`, `ts_rank_cd`, active source version and RLS checks, stable tie-break by `chunk_id`; no BM25.                                                     | Do not show scores as percentage/confidence or issue fake BM25 labels.                                                                             |
| [backend `tests/test_lexical_routes.py`](../../apps/workbench/api/tests/test_lexical_routes.py)                                                    | HTTP-to-Haystack-to-PostgreSQL integration; 10 lexical gold queries, 3 paraphrase diagnostics, real scores, 409/404/503/429/504/cancel tests.                                             | Use existing known-good responses to validate client/visual parity; do not reimplement quality baseline.                                           |
| [web `App.tsx`](../../apps/workbench/web/src/App.tsx)                                                                                              | `onRun` is Preview-only after UI-001; Live Run is disabled. Discovery/mode/workspace controls already exist; runs remain Preview models.                                                  | Introduce explicit Live execution path and run provenance; avoid attaching a stale response to a new graph.                                        |
| [web `domain/types.ts`](../../apps/workbench/web/src/domain/types.ts)                                                                              | `NodeKind` lacks a truthful keyword-search kind; `TemplateId` has `blank/indexing/retrieval`; `PreviewRun` includes synthetic per-node outputs.                                           | Add only an editor kind/template and separate Live DTO/view model.                                                                                 |
| [web `domain/catalog.ts`](../../apps/workbench/web/src/domain/catalog.ts)                                                                          | Existing `bm25` is labeled `InMemoryBM25Retriever`; result node has `limit`, query node has `query`.                                                                                      | Retain BM25 for Preview; new keyword node must be truthful and source-neutral in naming.                                                           |
| [web `domain/graph.ts`](../../apps/workbench/web/src/domain/graph.ts)                                                                              | `createPipeline`, `checkDraftConnection`, `checkPreviewGraph`, `portableGraph`, `importPipeline`/`exportPipeline` (`schemaVersion: 1`). Imported graphs support incomplete drafts.        | Extend existing serialization/allowlist and tests without deserialization of executable code.                                                      |
| [web `domain/preview.ts`](../../apps/workbench/web/src/domain/preview.ts)                                                                          | `completePreviewNode()` uses a **total** `Record<NodeKind, ...>` of fake outcomes.                                                                                                        | Adding a new node kind requires an explicit, safe Preview-unsupported branch (or typing adjustment); never manufacture a keyword Live result here. |
| [web `components/NodeIcon.tsx`](../../apps/workbench/web/src/components/NodeIcon.tsx)                                                              | Icon lookup keyed by `NodeKind`.                                                                                                                                                          | Add corresponding icon entry when extending the union.                                                                                             |
| [web `PipelineEditor.tsx`](../../apps/workbench/web/src/components/PipelineEditor.tsx)                                                             | Buttons use `onRun/onStop`, `busy`, `runningNodeId`; node colors driven by `run?.nodes`.                                                                                                  | Reuse toolbar/results shell, but do not fake node status for Live.                                                                                 |
| [web `ResultsPanel.tsx`](../../apps/workbench/web/src/components/ResultsPanel.tsx)                                                                 | Assumes `PreviewRun`, renders scores with `.toFixed(3)` and page as always present; tabs Output/Nodes/Errors.                                                                             | Introduce typed Live-specific rendering and real stage timings.                                                                                    |
| [web `RunsView.tsx`](../../apps/workbench/web/src/views/RunsView.tsx) and [`PipelinesView.tsx`](../../apps/workbench/web/src/views/PipelinesView.tsx) | Both consume `PreviewRun[]`, show history in browser session, not server persistence.                                                                                                     | Preserve session history, label provenance per row; do not claim durable server run history.                                                       |
| [web `SettingsView.tsx`](../../apps/workbench/web/src/views/SettingsView.tsx)                                                                      | Preview `resultLimit` and editor `defaultTemplate`.                                                                                                                                       | New template must appear; clear which limit is applied in Live.                                                                                    |
| [constructor validator registry](../../apps/workbench/validator/registry.py)                                                                       | `query` and `results` are explicitly **UI-only** / unsupported. The new keyword node is not registered.                                                                                   | Do not require validator `status=valid` to execute this separately approved profile. Do not pretend validation succeeded.                          |

References: [canonical contract](../../docs-website/docs/architecture/rag-runtime-contract.md), [lexical service guide](../../docs-website/docs/architecture/postgres-lexical-search.md), [Workbench README](../../apps/workbench/web/README.md), [existing Preview smoke](../../apps/workbench/web/scripts/browser-smoke.js), [validation smoke](../../apps/workbench/web/scripts/validation-smoke.js).

**Observed vs predicted:** HTTP retrieval is implemented and backend evidence exists; a React Live request **does not yet exist** in the inspected source. Thus UI/API parity is an acceptance test to run, not a claimed result. Current published API normalizes invalid JSON/validation to **400**, not the earlier draft's assumed 422. It returns **409** for stale/unsupported profile, **404** for foreign workspace, **429** capacity busy, **503** unavailable dependency and **504** deadline. These exact codes are important for the UI.

## D. Goal

A user explicitly chooses Live mode, opens a dedicated **Keyword search** graph, edits the query and top-K, clicks Run, and sees exactly the real ranked PostgreSQL passages returned by `POST /api/v1/workspaces/{workspace_id}/search`—with `run_id`, request/trace IDs, source/version/chunk provenance, actual score type, measured duration and a meaningful no-results state. Preview remains the existing six-node fixture demonstration.

A user who opens a Hybrid/indexing/invalid graph while in Live must see an explicit **unsupported graph** message and make **zero** search requests. Backend errors must never become fixture results.

## E. Scope

1. Add one non-provider-coupled editor kind `keyword-search` and template `keyword` consisting of exactly `query -> keyword-search -> results`; truthfully label the concrete backend algorithm using the **server-discovered** profile metadata, not by renaming `bm25`.
2. Build a **pure, strict graph-to-search-profile matcher** that rejects any graph outside this reviewed subset. It produces **only** `{query, top_k, profile_id, expected_profile_revision}`; no React Flow JSON travels to the execution API.
3. Use the shared transport from UI-001 and its capability/workspace data. Implement a single cancellable, generation-guarded Live request lifecycle.
4. Introduce a Live run view model and a discriminated Preview/Live representation; adapt existing ResultsPanel, RunsView, PipelinesView and editor toolbar rather than duplicating pages.
5. Render server-provided stages/IDs/scores/provenance; correctly handle absent page, no hits, offline, busy, stale profile and local cancellation.
6. Add targeted Vitest contract/graph/renderer tests, an actual PostgreSQL-backed browser Live smoke and regression coverage for Preview/validator/JSON imports.

## F. Non-Goals

No arbitrary graph compiler, no user-controlled Haystack class instantiation, no Qwen embeddings or model generation, no true BM25, no index writes/uploads, no server-side persisted run list, no streaming/websocket endpoint, no database or API schema changes. Do not copy the backend retrieval algorithm into TypeScript. No fabricated per-node duration/status: the server currently returns stage timings, not per-canvas-node outputs.

## G. Architecture / Boundaries

```text
Workbench graph (editable; schemaVersion=1)
     |
     +-- Preview -> checkPreviewGraph -> usePreview -> demo fixtures
     |
     +-- Live -> matchApprovedKeywordGraph(graph, capability)
                 -> (query, bounded topK, authorized workspace, profile revision)
                 -> shared apiClient.search(...)
                 -> FastAPI allowlist/profile check
                 -> Haystack PostgresLexicalRetriever.run_async()
                 -> PostgresPersistence.lexical_search_snapshot()
                 -> PostgreSQL RLS + FTS
                 -> SearchResponse
                 -> projectLiveRun() -> existing Results/Runs views

Separate: Validate -> /api/pipelines/validate (construction only)
```

- [x] Frontend domain: strict profile mapper and source-tagged run model.
- [x] Application orchestration: Live execution hook and mode dispatcher.
- [x] Port/contract: existing API client and fixed server request/response.
- [ ] Provider adapter: none added.
- [ ] Database: unchanged, must remain target PostgreSQL + pgvector.
- [x] Retrieval: reuse existing backend Haystack runtime, not build another.
- [ ] Agent runtime: N/A — no agents.
- [x] Security: fail-closed allowlist and authorized workspace, safe cancellation.
- [x] Observability: actual IDs, stages and error codes.
- [ ] Infrastructure: only test/smoke wiring if needed.
- [x] Documentation and compatibility.

The execution **profile** is backend policy; the graph is a user-facing representation. Match a known editor structure, but do not let the browser's matcher become an authorization control. The backend must continue to validate `profile_id` and `expected_profile_revision` on every request.

## H. Contracts / Interfaces / Data Model

### Authoritative request / response — **existing** backend contract

```json
{
  "query": "retention",
  "top_k": 5,
  "profile_id": "postgres-fts-baseline",
  "expected_profile_revision": "postgres-fts-baseline-r1"
}
```

Destination: `POST /api/v1/workspaces/development/search`, `Content-Type: application/json`. `development` here is an **example of a server-returned** workspace ID, not a client authority default.

Successful 200 includes these **actual** fields (illustrative IDs, not a simulated backend result):

```json
{
  "contract_revision": "rag-api-v1.0",
  "request_id": "server-request-id",
  "trace_id": "server-trace-id",
  "mode": "live",
  "workspace_id": "development",
  "corpus_revision": "corpus-revision-from-database",
  "profile_id": "postgres-fts-baseline",
  "profile_revision": "postgres-fts-baseline-r1",
  "run_id": "server-run-id",
  "status": "success",
  "duration_ms": 17.4,
  "stages": [
    { "stage": "corpus_load", "status": "success", "duration_ms": 9.2 },
    { "stage": "retrieval", "status": "success", "duration_ms": 6.1 },
    { "stage": "projection", "status": "success", "duration_ms": 0.3 }
  ],
  "results": [
    {
      "chunk_id": "server-chunk-id",
      "source_id": "server-source-id",
      "source_version_id": "server-version-id",
      "title": "Example document",
      "rank": 1,
      "score": 0.10000000149011612,
      "score_type": "postgres_ts_rank_cd",
      "content": "Actual content comes from the server only."
    }
  ]
}
```

`page` is optional and often **absent** for the persisted seed; its absence must display as `Page unavailable`, **not** `Page 0`, `undefined` or an invented page. `score` is a nonnegative finite raw rank; not 0–1 probability. `stages` are measured server operations, **not** visual node timings. The total `duration_ms` includes orchestration and need not equal the sum of stages.

### Domain model design (names are recommendations, do not create duplicate types)

```ts
type LiveSearchResult = {
  chunkId: string;
  sourceId: string;
  sourceVersionId: string;
  rank: number;
  title: string;
  content: string;
  page: number | null;
  score: number;
  scoreType: "postgres_ts_rank_cd";
};
type LiveRun = {
  source: "live";
  serverRunId?: string; // absent for failures before server creates a run
  requestId?: string;
  traceId?: string;
  profileId: string;
  profileRevision: string;
  corpusRevision?: string;
  workspaceId: string;
  pipelineId: string;
  pipelineName: string;
  graphSnapshot: Graph;
  startedAt: string;
  status: "Running" | "Completed" | "Failed" | "InterruptedLocally";
  durationMs?: number; // only server-measured on success
  stages: Array<{ stage: string; status: string; durationMs: number }>;
  results: LiveSearchResult[];
  error?: { code: string; message: string; httpStatus?: number };
};
type RunEntry =
  { source: "preview"; run: PreviewRun } | { source: "live"; run: LiveRun };
```

Keep this data model adapted from the actual API types. Do **not** populate `LiveRun.stages` from `PreviewRun.nodes` or fabricate successful node execution. If the HTTP response has `run_id`, use it, not a browser UUID as the server run ID. An optional separate local list ID may be needed for an interrupted request that never received a server ID.

### Strict executable-graph predicate

Approved exactly:

```text
query.query (textarea) --query--> keyword-search.query
keyword-search.documents --> results.documents
```

Recommended new `NodeKind = "keyword-search"` with `topK: number`, and `TemplateId = "keyword"`. Keep existing `query` + `results` kinds and ports and use existing `createNode()`/`connect()` helpers. Require all of the following:

- Exactly three **distinct** nodes and two **exactly matching** directed edges, with no extra/duplicate nodes/edges; allow arbitrary stable node UUIDs, labels, positions and viewport.
- Nodes are of kinds `query`, `keyword-search`, `results` exactly once; existing BM25/vector/joiner/indexing graphs are **not** executable Live.
- Strict permitted parameter keys: `query.{query}`, `keyword-search.{topK}`, `results.{limit}`. Reject missing, extra, non-integer and out-of-range values. `query` after trimming is 1–4096 Unicode code points, no NUL or unpaired surrogates.
- `topK` and `limit` are positive integers within the **discovered** profile max (`1..50` today), with no silent clamping.
- Define effective backend `top_k = min(keywordSearch.topK, results.limit)`; this reflects both candidate and visible-result constraints, and must be shown as “Requesting up to N results” rather than implying an unreturned remainder was ranked.
- Require discovery profile `kind="lexical_search"`, `score_type="postgres_ts_rank_cd"`, authorized workspace, ready state and immutable `profile_revision`. Unknown score/profile means refusal, not adapter substitution.
- The graph builder must be a **pure function** with a typed validation result (supported with request parameters or unsupported with actionable issues). Do not use text labels or node positions as authority.
- `onValidate` still invokes the separate Haystack constructor validator and may return `unsupported` because `query`/`results` are conceptual and the new kind is not in its registry. **Never change that result to `valid` or gate Live on it.** Show “Supported Live profile; constructor validation is separate” when appropriate.

### HTTP failure and operation state matrix

| Actual condition                                                                | HTTP / transport                            | UI state and message                                                               |
| ------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| Successful hits                                                                 | 200                                         | `Completed`, real source/version/chunk IDs, ordered raw scores.                    |
| No hits                                                                         | 200, `results=[]`                           | `Completed`, “No matches for this query”, not a failure or demo records.           |
| Empty/invalid query or extra request fields                                     | 400 `INVALID_REQUEST`                       | Invalid request, actionable input feedback, no fallback.                           |
| Unknown/expired profile revision                                                | 409 `PROFILE_NOT_AVAILABLE`                 | Mark current capability stale, prompt Refresh; do not retry with assumed revision. |
| Foreign workspace                                                               | 404 `WORKSPACE_NOT_FOUND`                   | Clear unauthorized selection and require rediscovery.                              |
| Database down / schema incompatible                                             | 503 `DEPENDENCY_UNAVAILABLE` / `NOT_READY`  | Explicit backend dependency unavailable.                                           |
| Capacity exhausted                                                              | 429 `SEARCH_BUSY`, `Retry-After` may be `1` | Render busy/retryable; do not silently queue new requests.                         |
| Server deadline                                                                 | 504 `SEARCH_TIMEOUT`                        | Failed with server error code/run ID if provided.                                  |
| Client user Stop                                                                | `AbortController.abort()`                   | `InterruptedLocally` only; **do not claim server cancellation confirmed**.         |
| Timeout / proxy 502 / HTML                                                      | Transport failure                           | Failed safely, no dummy results.                                                   |
| Malformed 200 JSON, wrong `run_id`, wrong workspace/profile or wrong score type | Contract violation                          | Failed safely, no partial success; debug with safe correlation.                    |

## I. Repository Files / Components Impacted

| File / directory                                                                                                                                   | Planned change                                                                                                                                            | Existing behavior to protect                                           |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| [`src/domain/types.ts`](../../apps/workbench/web/src/domain/types.ts)                                                                                 | Add `keyword-search`, template `keyword`; Live run-view types or a small adjacent `run.ts`.                                                               | Keep PreviewRun and existing graph types/imports compatible.           |
| [`src/domain/catalog.ts`](../../apps/workbench/web/src/domain/catalog.ts)                                                                             | Add truthful keyword node and its input/output port catalog; do not bind a provider SDK through the display name.                                         | Keep `bm25` label and ports unchanged.                                 |
| [`src/domain/graph.ts`](../../apps/workbench/web/src/domain/graph.ts)                                                                                 | Extend `createPipeline`, `importPipeline` template allowlist; reuse `portableGraph`, `checkDraftConnection`, `topologicalNodeIds`; call a strict matcher. | `schemaVersion: 1`, safe JSON import, bounded graph, drafts preserved. |
| `src/domain/approvedExecution.ts` (new)                                                                                                            | Pure exact graph/profile matcher and request projector.                                                                                                   | No HTTP, SQL, Python or fixture execution.                             |
| [`src/domain/preview.ts`](../../apps/workbench/web/src/domain/preview.ts)                                                                             | **Only necessary type/safety change** so new kind is explicitly preview-unsupported; do not add synthetic node timing or result.                          | Existing four fake results, old Preview scenarios untouched.           |
| [`src/components/NodeIcon.tsx`](../../apps/workbench/web/src/components/NodeIcon.tsx)                                                                 | Add icon for new kind.                                                                                                                                    | No visual redesign.                                                    |
| [`src/components/PipelineEditor.tsx`](../../apps/workbench/web/src/components/PipelineEditor.tsx)                                                     | Mode-aware Run/Stop/disabled state and explicit Live support diagnostics.                                                                                 | Existing toolbar, graph editing, `Validate`, keyboard actions.         |
| [`src/components/ResultsPanel.tsx`](../../apps/workbench/web/src/components/ResultsPanel.tsx)                                                         | Run union, labeled Live stages, raw rank, optional page and metadata.                                                                                     | Preview Output/Nodes/Errors remain functional.                         |
| [`src/views/RunsView.tsx`](../../apps/workbench/web/src/views/RunsView.tsx), [`PipelinesView.tsx`](../../apps/workbench/web/src/views/PipelinesView.tsx) | Show mixed session run sources and statuses, preserve selection by pipeline ID.                                                                           | No assertion of backend-stored run history.                            |
| [`src/views/SettingsView.tsx`](../../apps/workbench/web/src/views/SettingsView.tsx)                                                                   | New template option and Live numeric-limit meaning.                                                                                                       | Preview scenario still works in Preview.                               |
| [`src/App.tsx`](../../apps/workbench/web/src/App.tsx)                                                                                                 | Split Live/Preview run state and dispatch, account for mode, pipeline, workspace and request-generation changes.                                          | Local app navigation, `notify()`, import/export, existing validator.   |
| `src/hooks/useLiveSearch.ts` (new)                                                                                                                 | Server request lifecycle, cancellation, per-run immutable snapshots and status.                                                                           | No duplicate fetch logic; uses UI-001 API client.                      |
| `src/domain/approvedExecution.test.ts`, `src/hooks/useLiveSearch.test.ts`, `src/api/*.test.ts`                                                     | Contract/graph/status/cancellation tests.                                                                                                                 | Keep all existing Vitest tests.                                        |
| `scripts/live-search-smoke.js` (new) and [`README.md`](../../apps/workbench/web/README.md)                                                            | Real PostgreSQL-backed browser proof and operator instructions.                                                                                           | Keep existing Preview and validation smoke scripts.                    |

**MUST NOT change:** `haystack/`, `apps/workbench/retrieval/lexical.py`, `apps/workbench/postgres/postgres.py`, SQL migrations, preview result fixtures, validator response semantics, API profile identity or `schemaVersion: 1`. If another backend contract becomes necessary, STOP and revise the task first.

## J. Implementation Requirements — ordered coding blueprint

### J1. Stabilize the client-facing contract and source ID semantics

1. Verify TASK-UI-001's typed client has a `search(workspaceId, body, {signal})` method that uses the canonical request shape and safely decodes 200/error responses. Do not call `fetch()` from the graph editor, ResultsPanel or hook.
2. Cross-check `apps/workbench/contracts/schemas.py`: `source_version_id` (not `version_id`), `run_id`, `profile_revision`, optional `page` and server `stages`. Record the exact HTTP errors before writing UI conditions.
3. Read `apps/workbench/retrieval/fixtures/lexical-evaluation.json` and select two distinct exact queries (`retention`, `GIN`) for integration tests; avoid assertions on fictitious corpus text or UI Preview IDs.

**Gate:** the client can distinguish a complete SearchResponse from an ErrorResponse and malformed 200.

### J2. Add an explicit keyword editor template without changing old graphs

1. Extend `NodeKind`, `TemplateId`, node catalog and icon. Use meaningful names (`keywordSearch`, `approvedProfile`)—never milestone-coded variable or method names.
2. Build `createPipeline("keyword")` with `createNode("query")`, `createNode("keyword-search")`, `createNode("results")`, and two exact connections. Initial keyword `topK=10`, results `limit=5`, query defaults to an exact seeded term such as `retention` (documented as development example, **not** an expected answer).
3. Add `keyword` to PipelinesView template menu and Settings default template selector. Keep initial two pipelines and initial active six-node Hybrid graph unchanged so existing smoke remains valid.
4. Extend `importPipeline()` template allowlist while retaining its safe JSON key allowlists and node/edge limits. Test export/import round-trip for new template and old saved graph fixtures.
5. Explicitly mark new node unsupported by local **Preview**; update `checkPreviewGraph()` to return a meaningful `GraphIssue` before `completePreviewNode()` can be used. Adjust `Record<NodeKind,...>` typing in `preview.ts` minimally and make unsupported cases throw rather than fabricate data. Preview tests must still cover old fixtures.

**Gate:** new graph is portable in schema v1, but clicking Preview Run on it cannot produce fake keyword results.

### J3. Implement a pure approved-graph matcher

1. Add `matchApprovedKeywordGraph(graph, executionProfile)` as a pure domain module; require the exact topology and no extra operations. Reuse existing graph/type/catalog helpers; do **not** serialize the graph and post it to the backend.
2. Check types/ranges/allowed parameter keys exactly, query text (Unicode and NUL), capability kind/score limits, and workspace membership.
3. Return either `supported:{query,topK}` plus a sanitized diagnostic profile description or `unsupported:{issues:[...]}` with node/edge IDs where meaningful. Never “repair” mismatched graphs silently.
4. Write matrix tests: extra node, two `query` nodes, parallel edge, wrong handle, reversed edge, cycle, missing node, malformed parameter, empty/too-long query, unsupported profile, unexpected score type, revision mismatch, and non-default node labels/positions that **must still work**.

**Gate:** invalid/unsupported graphs produce **zero** HTTP search calls.

### J4. Create one cancellable Live execution hook

1. `useLiveSearch` receives `apiClient`, approved profile and authorized workspace; do not read `settings.workspaceName` as scope.
2. Guard against double submit, mode switch, pipeline change, graph edit, workspace change, component unmount and stale discovery revision. Abort only the obsolete client request; discard late completions by monotonic generation ID and immutable submitted graph snapshot.
3. Insert a Live run with temporary client-local identity while request is pending; upon successful server response, attach **server** `run_id`, `request_id`, `trace_id`, `corpus_revision`, `profile_revision`, `duration_ms`, raw results and stages. Use accurate source tag `"live"`.
4. On `ApiFailure`, mark `Failed` with code/status/correlation; on user Stop, mark `InterruptedLocally` and do not claim backend cancel acknowledgment. Never retain Preview results in a failed Live run.
5. Cap session run history with a documented limit (e.g. 100 entries) to prevent unbounded browser memory; this must not imply backend retention.
6. Decide how a completed response after a graph edit is handled: it may remain in the immutable history for its original graph, but **must not update the currently active editor**. Test both modes.

**Gate:** stale responses cannot paint results for the wrong mode/workspace/graph.

### J5. Reuse existing presentation with discriminated results

1. In `App.tsx`, keep Preview `usePreview` separate and call Live hook only when explicitly selected. `busy` and `onStop` must refer to **the current mode's** operation, not to Preview's ambiguously named `liveRunId`.
2. Extend `PipelineEditor` props minimally, preferably with one `execution` presentation object instead of many overlapping booleans. Disable Run for unsupported profile/graph and show specific reason; do not disable normal editing/import/export.
3. `ResultsPanel`: Preview continues showing synthetic nodes; Live shows stages (`corpus_load`, `retrieval`, `projection`), real total duration and result provenance. A 200 no-results response is a successful Live run.
4. Render scores as **raw PostgreSQL ts_rank_cd**; allow enough significant digits for inspection and provide the untouched numeric value in JSON view. Do not format as `96% relevance`. Validate before calling numeric formatters.
5. Display missing pages as `—`/`Not provided`, not `P. 0` or `NaN`. Include readable `source_id`, `source_version_id`, `chunk_id`, `rank`, `profile_revision`, `corpus_revision`, request and trace IDs in details/JSON.
6. Keep `RunsView`/`PipelinesView` mixed session history discriminated with source labels. A Live run is not a server historical record and is lost on refresh; document this.
7. The constructor-Validate button remains independent. Because `query`/`results` are conceptual, it may legitimately report `unsupported`, while the approved keyword profile can execute. Convey both facts without asserting validation passed.

**Gate:** UI-visible ordered IDs/scores and stage durations match the captured HTTP payload exactly (allow formatting only), including zero-hit/nullable-page cases.

### J6. Runtime safety, tests and rollout

1. Start PostgreSQL using existing `apps/workbench/postgres/compose.yaml`, migrate/seed **only if not already done**, and run `hatch run workbench-api:serve` after loading local app DB environment. Do not reset or re-seed a modified workspace.
2. Start Vite with the UI-001 proxy and optionally the independent validator. Create/select `keyword` template, select **Live**, execute `retention` and `GIN`.
3. Use Playwright network interception **only to capture real responses** in the integration smoke; separately use mocked negative-path response tests. Assert two different queries produce different source identities.
4. Exercise source unavailable (503), backend terminated/502, invalid query (400), unsupported profile (409), unauthorized workspace (404), admission busy (429), deadline (504), malformed 200 and local Stop.
5. Run existing Preview smoke and validator smoke unchanged; verify old Hybrid initial graph and its four demo hits are still confined to Preview.
6. Update user documentation, record output/trace IDs in a sanitized evidence artifact and enforce a pre-merge review of any source/API contract mismatch.

**Gate:** all acceptance criteria M and completion checklist O, with real evidence, must pass.

## K. Security / Governance / Observability

- **No arbitrary code:** graph is user-authored and may be imported; never send raw graph/YAML/Python/SQL to the server. Only submit the four allowlisted SearchRequest fields.
- **Server authority:** backend verifies selected profile/revision, resolves workspace (`development` for current dev) and enforces PostgreSQL RLS/active version. Frontend matching is UX defense, not auth.
- **Error handling:** use nested sanitized `ApiFailure`, not a server stack trace; 404 and 409 trigger capability/workspace rediscovery, not insecure fallback.
- **Timing:** `duration_ms` and `stages[*].duration_ms` belong to the server; a browser client round-trip may be separately labeled `network_elapsed_ms`, never substituted.
- **Data protection:** excerpts may contain user documents in later stages; render as plain text and avoid localStorage, analytics and console logs of raw query/results/content.
- **Traceability:** preserve server `request_id`, `trace_id`, `run_id` and `corpus_revision`. Do not claim a persistent tracing backend when one is not present.
- **Retention:** session-only run history with explicit bound, cleared on refresh. Workspace transitions remove stale selected results and pending scope.
- **Prompt-injection boundary:** retrieved chunks are data displayed as text, never executed or interpreted as UI commands or HTML.

## L. Testing / Evaluation / Runtime Verification

### Commands

```powershell
cd apps/workbench/web
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
```

With local PostgreSQL/pgvector and API running, execute the existing browser smoke plus `scripts/live-search-smoke.js`; the exact Playwright invocation follows the Workbench README (the script filename is a proposed new file, not presently present).

### Test cases (minimum, with explicit boundaries)

| Test level             | Test cases                                                                                                                                                        | Evidence                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Pure graph matcher     | Exactly approved 3-node topology succeeds; extra/duplicate/wrong-order/unknown-node/parameter/scope fails; labels/positions ignored; top-K/limit policy explicit. | `approvedExecution.test.ts` checks and no search calls for invalid graph. |
| Import/Export          | New graph v1 round-trip; old JSON unchanged; malicious keys/oversized graphs still rejected.                                                                      | Existing + new `graph.test.ts`.                                           |
| Preview regression     | Six-node default Hybrid, sample scores/timings, error scenario, Undo/Redo, editor.                                                                                | `browser-smoke.js` and Vitest.                                            |
| Constructor validation | Existing `validation.test.ts` and separate service still report `unsupported` for UI-only nodes.                                                                  | `validation-smoke.js` and status screenshot.                              |
| Live HTTP contract     | Query `retention`/`GIN`, score `postgres_ts_rank_cd`, server run/trace/corpus metadata, source/version/chunk identity, no page.                                   | Captured real HTTP 200 payload and UI assertions.                         |
| Live errors            | 400, 404, 409, 429, 503, 504, 502/network, malformed 200, timeout, local abort.                                                                                   | Mock/integration matrix with exact error codes.                           |
| Race conditions        | Out-of-order requests; mode changes; graph edits; workspace changes; Stop then next Run.                                                                          | Unit hook tests; wrong-context updates remain zero.                       |
| State ownership        | Mixed Preview/Live run list, no server run-history claims, no duplicate UI pages.                                                                                 | Browser screenshots/assertions.                                           |
| Security               | Injected HTML in `title/content`, crafted graph with unapproved params, duplicate IDs.                                                                            | Rendered as text; no executable HTML or request.                          |
| Actual PostgreSQL      | After read-only query, source rows/chunk IDs unchanged; no fixture network substitutions.                                                                         | SQL/API parity test from backend plus UI capture.                         |

**Metric gate:** Query-dependent source result difference is required, but qualitative semantic accuracy is **not** asserted in this task. TASK-EVAL-001 (separate planned evaluation task; document not checked in) computes quantitative lexical retrieval metrics.

## M. Acceptance Criteria

- [x] An explicit new keyword-search template imports/exports as `schemaVersion=1`; old Hybrid BM25 graph, its icon and its Preview results remain unchanged.
- [x] Live Run posts **exactly** `{query,top_k,profile_id,expected_profile_revision}` to the approved workspace; it never uploads editor graph JSON.
- [x] The approved matcher refuses extra nodes/edges/parameters and unsupported profiles **before** network calls.
- [x] Two different real queries return different PostgreSQL source/chunk identities, and the UI shows the exact server order, raw score, `postgres_ts_rank_cd`, `source_version_id` and server IDs.
- [x] `page` absent renders as unavailable, empty results are successful, and real stages/total are shown without invented node timings.
- [x] 400/404/409/429/503/504/proxy and cancellation are distinct, visible and do not substitute Preview fixtures or misstate server cancellation.
- [x] Existing `Validate` remains constructor validation (can be `unsupported`), while approved Live execution uses capability authorization, not a fake `valid` verdict.
- [x] Old Preview, graph import/export and validation tests pass; new contract, graph, hook and real-browser assertions pass with captured evidence.
- [x] No changes to Haystack core, persistent schema, backend retrieval algorithm or server profile identity were required.

## N. Documentation / Migration / Compatibility / Rollback

- Update [`apps/workbench/web/README.md`](../../apps/workbench/web/README.md) with a **truthful** split of Preview fixtures, constructor validation and Live lexical HTTP execution, including unsupported templates/graphs and score semantics. Link canonical runtime/API docs.
- Preserve `schemaVersion: 1`; extend only the existing safe kind/template allowlists, with round-trip tests of old and new graphs. New graphs may not import into older frontend builds: document forward compatibility and the error rather than silently rewriting old data.
- No SQL migration or API revision needed. Live runs are browser-memory only; future server run history would be a separate feature.
- Rollback by hiding new keyword Live template/execution and reverting frontend code only; **do not delete** PostgreSQL volume, documents, migrations or backend profile. Preview and existing validator must continue to work.
- Deferred: embeddings, RRF, rerank, ingestion and full arbitrary graph execution.

## O. Mandatory Completion Checklist

- [x] Reinspect relevant source files from this blueprint before coding; update any stale evidence/paths.
- [x] Record the approved graph matcher and four-field request mapping in tests.
- [x] Verify local Preview explicitly rejects new keyword node rather than making up an output.
- [x] Record actual response/visible result parity including `source_version_id`, nullable page, raw score and stage timings.
- [x] Verify no API call for unsupported graph; no fixture fallback on every negative path.
- [x] Run frontend typecheck/format/unit/build, old Preview smoke, validation smoke and new Live smoke.
- [x] Capture logs/test commands, status codes, trace IDs and browser evidence; redact source text where necessary.
- [x] Review accessibility, state races, session retention and backward graph compatibility.
- [x] Mark **COMPLETE** only when every applicable check is supported by executed evidence.

## P. Completion record — 2026-11-21

Implemented relative to the clean UI-001-complete base `1d082e043a7d7c8f89d7623cac321d7b83218f23`. The original blueprint's discovery-only assumptions were reconciled before editing: reuse the existing typed client, discovery state, authorized workspace and Preview/Live controls; extend them with search rather than add a second transport or shell.

Three agents owned graph/matcher safety, transport/lifecycle and presentation. Root integrated App/editor/Settings, mixed retention, browser smoke and documentation. Independent reviews covered stale responses, failure visibility during rediscovery, fixture provenance, local cancellation and separate constructor validation.

The final implementation adds `keyword-search` / `keyword`, an exact pure graph matcher, four-field search POST with runtime response validation, immutable Live records/generation guards, and source-discriminated session rendering in existing Results/Runs/Pipelines views. Existing catalog/createNode/connect/import/portableGraph, Preview hook, validator transport, shell controls and CSS/font tokens were reused. No provider SDK, API revision, graph schema version, SQL migration or backend change was necessary.

Verification passed: **233 tests across 8 files**, TypeScript, Prettier, production build; unchanged Preview and actual-validator browser scripts; new actual PostgreSQL Live smoke; existing discovery browser regression. Captured real queries `retention` and `GIN` produce different persisted sources; a no-match query is Completed. UI ranks/raw scores/identities/passages/JSON and stage/total durations match captured responses. Source listing/versions/counts/corpus revision remain unchanged. Live failures and local Stop are separately verified; their negative browser responses are explicitly identified as controlled injections.

See the [complete verification record](../evidence/live-search-verification-2026-11-21.md), [real HTTP/UI result parity and error cases](../evidence/live-search-browser-2026-11-21.json), [discovery regression](../evidence/live-search-discovery-smoke-2026-11-21.json) and [JUnit](../evidence/live-search-tests-2026-11-21.xml). The report links executed command outputs and 1440px/1100px screenshots, lists changed ownership/reuse and records remaining limitations.

Intentional UI changes: Live Run is enabled only for the approved graph; old Hybrid/indexing remain Preview, and keyword is not simulated. Live uses server stages rather than node outcomes, retains unrounded scores/JSON, labels missing pages, and has bounded mixed session history. Human-readable duration formatting preserves exact values in JSON/title/data attributes. Constructor issues can be inspected without blocking Output/Stages. Mode changes clear previous notifications and pending scope. Incompatible graphs remain editable, importable and exportable.

No Haystack core, backend retrieval algorithm, PostgreSQL/pgvector schema or data, existing fixture values, validator implementation or old Preview/validator smoke script changed. Full upstream Python tests and a full docs-site build were not run because those implementations were unchanged. Model inference, dense/hybrid retrieval, ingestion, Live document listing, durable run history and quantitative evaluation remain separate tasks. The canonical StageTiming example was corrected to its already implemented success/skipped DTO; no server contract changed.

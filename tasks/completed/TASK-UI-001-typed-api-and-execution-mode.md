# TASK-UI-001 — Typed execution API transport and explicit Preview/Live modes

**Created:** 2026-11-20  
**Updated:** 2026-11-21  
**Status:** COMPLETE — implemented and verified on 2026-11-21  
**Priority:** P0  
**Dependencies:** TASK-ARCH-001, TASK-API-001, TASK-DB-001, TASK-RAG-001; coordinate with completed TASK-VAL-001  
**Repository state inspected:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Deliverable location:** `tasks/TASK-UI-001-typed-api-and-execution-mode.md`  
**Next consumer:** TASK-UI-002 — execute Live lexical pipeline (separate planned task; document not yet checked in)

## A. Title

Introduce a contract-checked Workbench API client, truthful backend discovery, an authorized workspace selection and explicit execution-mode controls **without executing search in this task**.

## B. Context / Problem

The browser currently presents a functioning demonstration and a separate **real Haystack constructor validator**, but it has no execution API adapter. An operator must be able to select **Preview** (fixed, synthetic simulation) or **Live** (real PostgreSQL-backed execution, implemented by the next task) without mistaking one for the other. HTTP availability, constructor validity and executable readiness are three different facts.

Crucial distinctions established by the actual application:

1. `POST /api/pipelines/validate` on the validator service checks approved constructors and socket compatibility, not retrieval; its `capabilityVersion` is `workbench-components-v1` and its response uses `requestId` (camelCase).
2. The separate FastAPI service exposes `/api/v1/...` routes, `contract_revision: "rag-api-v1.0"`, `request_id` / `trace_id` (snake_case) and a **qualified** `postgres-fts-baseline` execution profile.
3. `GET /api/v1/capabilities` may return HTTP 200 with **no executable profiles** while `/api/v1/health/ready` returns 503. PostgreSQL status `ready` alone is insufficient.
4. `features.documents: true` currently means **read-only listing**, not upload. No job, source-detail, or chunk-detail HTTP API exists yet.
5. The Workbench's `settings.workspaceName` is editable presentation text, not an authorization claim. The only currently approved server-resolved workspace is `development`.

A naïve single `fetch('/api')` implementation or a reused validation-client schema would obscure these boundaries and permit misleading Live UI, stale capabilities, or insecure workspace selection.

## C. Current Repository State

### Inspected implementation inventory — direct links, not inferred components

| Source                                                                                                                                                                                                              | Verified functions / present behavior                                                                                                                            | Reuse / implication                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [web `App.tsx`](../apps/workbench/web/src/App.tsx)                                                                                                                                                                  | `App()` owns `pipelines`, `runs`, `settings`, `activeId`, pages, toast and `usePreview(setRuns)`; header hard-codes **PREVIEW** and **Local session**.           | Inject mode/discovery state here; reuse toast and navigation without a new app shell.                           |
| [web `domain/types.ts`](../apps/workbench/web/src/domain/types.ts)                                                                                                                                                  | `WorkbenchSettings`, `Pipeline`, `PreviewRun`, `PreviewDocument` are browser-owned models.                                                                       | Add typed execution-mode state; do **not** make `PreviewRun` an authoritative backend response.                 |
| [web `domain/fixtures.ts`](../apps/workbench/web/src/domain/fixtures.ts)                                                                                                                                            | `initialPipelines`, `previewDocuments`, `initialRuns`, `defaultSettings` seed the session.                                                                       | Leave fixtures available only for Preview.                                                                      |
| [web `hooks/usePreview.ts`](../apps/workbench/web/src/hooks/usePreview.ts) and [`domain/preview.ts`](../apps/workbench/web/src/domain/preview.ts)                                                                   | `runPipeline()`, `stop()`, deterministic fake node outputs/timings; `liveRunId` is misleadingly named although it tracks a preview run.                          | Preserve simulation; do not use this hook for live HTTP or interpret its timings as real.                       |
| [web `domain/validation.ts`](../apps/workbench/web/src/domain/validation.ts) and [`hooks/useValidation.ts`](../apps/workbench/web/src/hooks/useValidation.ts)                                                       | `requestValidation()` sends POST to `/api/pipelines/validate`; `ValidationRequests.invalidate()` prevents stale verdicts.                                        | Keep the separate validator transport/protocol. Reuse its generation/abort design without duplicating its code. |
| [web `vite.config.ts`](../apps/workbench/web/vite.config.ts)                                                                                                                                                        | Only `/api/pipelines/validate` is proxied to port **8010** for `server` and `preview`.                                                                           | Add a **non-overlapping** `/api/v1` proxy to port **8011**, preserving the existing validator.                  |
| [web `SettingsView.tsx`](../apps/workbench/web/src/views/SettingsView.tsx)                                                                                                                                          | Workspace name and Preview scenario/delay are editable session preferences.                                                                                      | Add mode and connection indicators; label scenario/delay Preview-only.                                          |
| [FastAPI `contracts.py`](../apps/workbench/api/contracts.py)                                                                                                                                                        | Strict Pydantic models: `Meta`, `ErrorResponse`, `CapabilitiesResponse`, `ExecutionProfile`, `WorkspacePage`, `SearchRequest`, `SearchResponse`, `DocumentPage`. | Source of truth for TS DTOs; copy **actual** spelling and required fields.                                      |
| [FastAPI `application.py`](../apps/workbench/api/application.py)                                                                                                                                                    | `create_app()`, `_Routes._live/_ready/_capabilities/_workspaces/_documents/_search`; ready is profile-qualified, not a generic database ping.                    | Call existing routes only. No server-code changes needed in the normal path.                                    |
| [FastAPI `profiles.py`](../apps/workbench/api/profiles.py)                                                                                                                                                          | `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`.                                                                                                    | Runtime must discover profile/revision; avoid scattering profile string constants through UI.                   |
| [FastAPI `boundary.py`](../apps/workbench/api/boundary.py)                                                                                                                                                          | `RequestBoundary`, nested sanitized errors, `X-Request-ID`, loopback CORS/host policy.                                                                           | Validate server correlation; do not display internal error traces.                                              |
| [published OpenAPI](../apps/workbench/api/openapi.json)                                                                                                                                                             | Serialized contract of implemented routes.                                                                                                                       | Compare DTO assumptions against published models.                                                               |
| [API contract tests](../apps/workbench/api/tests/test_http_contract.py) and [retrieval tests](../apps/workbench/api/tests/test_lexical_routes.py)                                                                   | Assert metadata/errors, profile readiness, database failures, request bounds and source authorization.                                                           | Reuse these as backend reference evidence; do not repeat entire backend suite in the frontend.                  |
| [web validation tests](../apps/workbench/web/src/domain/validation.test.ts), [Preview smoke](../apps/workbench/web/scripts/browser-smoke.js), [validation smoke](../apps/workbench/web/scripts/validation-smoke.js) | Existing regression coverage for local Preview and separate validation.                                                                                          | Preserve both workflows and assertions.                                                                         |

The canonical [runtime/API contract](../docs-website/docs/architecture/rag-runtime-contract.md), [lexical API guide](../docs-website/docs/architecture/postgres-lexical-search.md), [Workbench README](../apps/workbench/web/README.md) and [API README](../apps/workbench/api/README.md) describe the implemented boundaries. The older, locally drafted UI task referred to `/health` and an unspecified `/capabilities`; those are **incorrect** for the actual versioned API. No `src/api/` directory is present in the inspected frontend. No Live HTTP request has been executed by the frontend in this snapshot.

**Observed issue versus predicted failure:** there is currently no Live fetch, so an HTTP error originating in Live mode has not been observed. Without the proxy, a browser request to `/api/v1/capabilities` on Vite would not reach the existing API. Without discriminated execution-mode state, the current global PREVIEW badge could mislabel future HTTP results. These are reproducible integration risks, not claims of already measured incidents.

## D. Goal

At task completion, the browser can opt into Live mode, probe the actual FastAPI process, display whether the approved PostgreSQL lexical profile is available, select an authorized workspace returned by the server, and **fail visibly instead of substituting Preview fixtures**. The code offers one reusable, runtime-validated API transport for TASK-UI-002 and TASK-UI-003. The Run button remains Preview-only or explicitly unavailable in Live until TASK-UI-002 is implemented.

Success is observable without writing to the database: the network panel shows the real GET endpoints, the displayed capabilities match response fields, offline/503 states are unambiguous, and existing Preview and validation actions remain intact.

## E. Scope

- Typed transport and response decoders for current **read-only discovery**: liveness, readiness, capabilities and paginated workspaces; declare reusable search/document DTOs but invoke their operations only in their owner tasks.
- Explicit `ExecutionMode = "preview" | "live"` state, header/settings controls, accessible connection state and capability-backed workspace selection.
- Mode-specific UI semantics: Preview scenario/delay are clearly Preview-only; Live requires a healthy, advertised profile and a server-returned workspace, and is never implicitly selected on network recovery.
- Shared abort/deadline, safe error decoding, correlation, URL construction, pagination and stale-response protection for RAG API operations.
- Vite development + preview proxy addition; configuration and operator README.
- Pure frontend unit tests, contract tests, and browser smoke for selection/readiness/no fallback. No backend code change expected.

## F. Non-Goals

- **Do not execute** `/search` yet or invent live run/node outputs; TASK-UI-002 (separate planned task) owns this.
- No upload, deletion, job polling, source detail, persistent browser authentication, workspace creation, remote providers, or arbitrary graph execution.
- No rewriting or unifying the separately versioned constructor validator, no change to Haystack core/SQL migrations, and no frontend state-management framework replacement.
- No local caching of private backend responses across workspaces and no secret/DSN exposure through Vite variables.

## G. Architecture / Boundaries

```text
React App / Settings / Header
        | selects mode and authorized workspace
        v
useBackendDiscovery  ---------> UI API client (src/api/)
        |                                  |
        |                                  +-- GET /api/v1/health/live
        |                                  +-- GET /api/v1/health/ready
        |                                  +-- GET /api/v1/capabilities
        |                                  +-- GET /api/v1/workspaces
        v
Discovered executable profile + server workspace

Separate (unchanged): useValidation -> domain/validation.ts
                             -> /api/pipelines/validate (port 8010)
Separate (unchanged): usePreview -> domain/preview.ts (fixtures only)
```

- [ ] Domain/core: add only browser-owned view/state types; no provider SDKs.
- [ ] Application/orchestration: component lifecycle and discovery hook.
- [x] Contract boundary: new HTTP DTO/decoder boundary in `src/api/`.
- [ ] Provider adapter: none.
- [ ] Persistence/vector: none (existing PostgreSQL remains authoritative).
- [ ] Retrieval/RAG: discovery only, not execution.
- [ ] Agent runtime: N/A — no agent execution.
- [x] Security/governance: server-owned workspace/capability truth and safe errors.
- [x] Observability/evidence: request/trace IDs, transport diagnostics without payloads.
- [x] Infrastructure: Vite proxy config.
- [x] Documentation: Workbench runbook and mode semantics.

Browser DTOs may depend on a documented API, but backend policy cannot depend on UI components. `validation.ts` has its own valid transport because **it addresses a different service and contract**; the new client centralizes RAG execution API calls rather than duplicating validation logic.

## H. Contracts / Interfaces / Data Model

### Endpoint matrix — currently implemented (read only for this task)

| Call                                              | Status and important fields                                                                                                          | Correct UI behavior                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- |
| `GET /api/v1/health/live`                         | 200: `status="alive"`, `backend_revision`, `contract_revision`, `request_id`, `trace_id`                                             | Process is alive, **not** necessarily executable. |
| `GET /api/v1/health/ready`                        | 200: `status="ready"`, `ready_profile_ids[]`; 503: nested `error.code="NOT_READY"`                                                   | Gate Live capability; preserve 503 detail.        |
| `GET /api/v1/capabilities`                        | 200 even if unready; `profiles[]`, `features.{documents,search}`, `dependencies.database.status`, `service_state`, `deployment_mode` | Feature discovery, **not** an execution attempt.  |
| `GET /api/v1/workspaces?limit=50`                 | `items[{workspace_id,name,status}]`, opaque `next_cursor`, meta                                                                      | Select server-authorized workspace only.          |
| `POST /api/v1/workspaces/{workspace_id}/search`   | Existing, **not called** until TASK-UI-002                                                                                           | Declare type; leave execution disabled for now.   |
| `GET /api/v1/workspaces/{workspace_id}/documents` | Existing read-only list, **not used as Live Documents** until TASK-UI-003                                                            | Do not show fixtures as Live documents.           |

### Required DTO surface (suggested module naming; inspect before creating)

```ts
export type ExecutionMode = "preview" | "live";
export type ApiMeta = {
  contract_revision: "rag-api-v1.0";
  request_id: string;
  trace_id: string;
};
export type ApiFailure = ApiMeta & {
  error: {
    code: string;
    message: string;
    retryable: boolean;
    http_status: number;
    run_id?: string;
    fields?: Array<{ field: string; code: string }>;
  };
};
export type BackendProfile = {
  profile_id: string;
  profile_revision: string;
  kind: "lexical_search";
  workspace_ids: string[];
  corpus_id: string;
  score_type: "postgres_ts_rank_cd" | "bm25_raw";
  parameters: {
    query: { type: "string"; min_length: number; max_length: number };
    top_k: {
      type: "integer";
      default: number;
      minimum: number;
      maximum: number;
    };
  };
  limits: {
    max_request_bytes: number;
    timeout_ms: number;
    max_concurrent_searches: number;
    max_corpus_chunks: number;
    max_corpus_bytes: number;
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
export type WorkspacePage = ApiMeta & {
  items: Array<{
    workspace_id: string;
    name: string;
    status: "ready" | "unavailable";
  }>;
  next_cursor: string | null;
};
```

The types above express current semantics; implementation MUST verify them against [`contracts.py`](../apps/workbench/api/contracts.py) and [`openapi.json`](../apps/workbench/api/openapi.json). Additive future fields must not silently enable unsupported actions. **Do not equate** the validator's `requestId`/`capabilityVersion` with API `request_id`/`contract_revision`.

### Runtime contract verification

- Parse JSON as `unknown`; validate relevant discriminator fields, object/array types, bounded IDs and numbers **at runtime**. TypeScript `as BackendCapabilities` alone is insufficient.
- Reject unsupported `contract_revision`, invalid `service_state`, contradictory `ready_profile_ids`, missing workspace IDs, non-finite limits, duplicate profile IDs, malformed `next_cursor` and profile/score incompatibility.
- Validate `X-Request-ID`, if present, against `request_id`. Safe user-facing errors may show `error.code` and `trace_id`, never a raw HTML response or stack trace.
- Use a discriminated UI state, e.g. `unconfigured | checking | ready | not_ready | unavailable | incompatible`; keep `lastCheckedAt` and explicitly distinguish stale information from a new successful check.
- For this milestone, executable-ready means: 200 readiness response **and** running service **and** `features.search=true` **and** `dependencies.database.status="ready"` **and** advertised supported profile bound to a listed workspace. This may be stricter than just seeing a green liveness response.

### Transport and configuration

- Default base path: **`/api/v1`**, same-origin through proxy. Optional `VITE_WORKBENCH_API_BASE_URL` may override only the _public browser API origin/path_, never host a credential, database DSN or provider token.
- `createWorkbenchApiClient({ baseUrl?, fetchImpl? })` is a concrete, injectable test seam; `getCapabilities({signal})`, `getReady({signal})`, `listWorkspaces({cursor?,limit?,signal})`, `getLive({signal})`. Prefer one thin request helper; do not build a generic enterprise SDK.
- Abort reasons distinguish caller cancellation from an **application timeout**. No automatic retry of mutation requests; safe bounded explicit retry for discovery only. Respect `AbortSignal` supplied by callers.
- Validate returned URLs/opaque cursors without interpreting/decoding the cursor in the browser; encode as a query parameter via `URLSearchParams`.

## I. Repository Files / Components Impacted

| Path                                                                                                                                            | Action                           | Reason                                                                                                           |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `apps/workbench/web/src/api/contracts.ts` (**new; intentionally no link yet**)                                                                  | CREATE                           | Shared _wire_ DTOs, separate from Preview model.                                                                 |
| `apps/workbench/web/src/api/client.ts` (new)                                                                                                    | CREATE                           | Single request adapter, base path, abort, timeout, safe error/response decoding and correlation.                 |
| `apps/workbench/web/src/api/client.test.ts` (new)                                                                                               | CREATE                           | Fake-fetch protocol, timeout, error, contract-revision and header tests.                                         |
| `apps/workbench/web/src/hooks/useBackendDiscovery.ts` (new)                                                                                     | CREATE                           | Cancellable discovery/refresh and stale-generation protection.                                                   |
| [`apps/workbench/web/src/App.tsx`](../apps/workbench/web/src/App.tsx)                                                                           | MODIFY                           | Explicit mode and server-controlled workspace + status in existing shell.                                        |
| [`apps/workbench/web/src/domain/types.ts`](../apps/workbench/web/src/domain/types.ts)                                                           | MODIFY minimally                 | ExecutionMode/session state, no fake backend `PreviewRun` fields.                                                |
| [`apps/workbench/web/src/views/SettingsView.tsx`](../apps/workbench/web/src/views/SettingsView.tsx)                                             | MODIFY                           | Accessible mode selector, Readiness/Refresh, Preview-only preferences, workspace display/selection distinction.  |
| [`apps/workbench/web/src/views/views.css`](../apps/workbench/web/src/views/views.css), [`src/styles.css`](../apps/workbench/web/src/styles.css) | MODIFY minimally                 | Badge, disabled/empty/error status consistent with palette.                                                      |
| [`apps/workbench/web/vite.config.ts`](../apps/workbench/web/vite.config.ts)                                                                     | MODIFY                           | Add `/api/v1` -> `http://127.0.0.1:8011` for server/preview. Keep port 8010 validator proxy untouched.           |
| [`apps/workbench/web/README.md`](../apps/workbench/web/README.md)                                                                               | MODIFY                           | Start/probe instructions, service separation, no fallback, feature matrix.                                       |
| [`apps/workbench/web/scripts/browser-smoke.js`](../apps/workbench/web/scripts/browser-smoke.js)                                                 | REVIEW, minimal update if needed | Default Preview path must keep its baseline expectations. Add separate discovery smoke rather than repurpose it. |

**MUST NOT change:** [`apps/workbench/web/src/domain/preview.ts`](../apps/workbench/web/src/domain/preview.ts), [`apps/workbench/web/src/domain/validation.ts`](../apps/workbench/web/src/domain/validation.ts), [`apps/workbench/validator/`](../apps/workbench/validator/), [`apps/workbench/api/`](../apps/workbench/api/), [`haystack/`](../haystack/), PostgreSQL migrations and existing fixture contents. If a real contract issue is discovered, amend this task and identify a separately scoped backend fix before proceeding.

## J. Implementation Requirements — ordered blueprint

### J1. Freeze the actual contract and test seam

1. Open `apps/workbench/api/contracts.py`, `profiles.py`, `application.py`, `openapi.json`; list exact DTO fields and error statuses. Verify `GET /api/v1/capabilities` with/without configured database (or use repository's existing contract tests if runtime unavailable).
2. Preserve `domain/validation.ts` and its request-generation pattern; it is **not** the RAG API client.
3. Establish TS DTO ownership in `src/api/contracts.ts`, optionally a separate small `src/api/decode.ts` only if parsing cannot remain readable in `client.ts`. No unnecessary dependency if the existing TypeScript/Vitest toolchain suffices.
4. Add a test comparing required TS discriminator literals to the published OpenAPI schema or a checked-in valid response sample. Document changes to the API revision explicitly; avoid hard-coded optional field fantasies.

**Exit gate:** tests reject a correctly typed-looking but malformed JSON response, and a capabilities payload with zero profiles is a successful discovery of **unavailable execution**, not a transport failure.

### J2. Implement one typed HTTP boundary

1. Construct URLs with a validated public base; use `AbortSignal.any` or equivalent to merge caller cancel and per-request timeout. Do not leak timers after settling.
2. Centralize `Accept: application/json`, response JSON parsing, error status verification, `contract_revision` and correlation fields.
3. Map `ApiFailure` into a structured `WorkbenchApiError` (`code`, `httpStatus`, `retryable`, `traceId?`, `requestId?`, `runId?`); for 502/HTML/proxy-offline return a safe **transport error**, not an empty successful capabilities object.
4. Do not reuse response body parsing by copying `requestValidation()` into multiple feature views. Keep domain-specific methods on the client to prevent arbitrary endpoint call sites.
5. Add strict handling for interrupted requests, 200 invalid JSON, 503 `NOT_READY`, 409 stale-profile (future search use), invalid response shape, and unknown fields that would change behavior.

**Exit gate:** no RAG API `fetch()` appears outside the API boundary; no test silently resolves an unavailable dependency into fixture data.

### J3. Preserve and extend Vite routing

1. Add `/api/v1` route to port **8011** beside the existing validator proxy (`/api/pipelines/validate` -> **8010**); apply to both `server.proxy` and `preview.proxy`.
2. Run with validator absent and with API absent independently. Neither service's error may be mistaken for the other's readiness.
3. Expose no environment setting that marks a backend "ready" without querying the actual service.
4. Document a reverse-proxy requirement for a production/static build; a Vite-only proxy is not a deployment plan.

**Exit gate:** validation endpoint and API discovery route reach their **different** processes with distinct response formats.

### J4. Implement discovery state and authorization provenance

1. On explicit Live selection/Refresh, start a bounded request generation; abort older queries when mode changes or component unmounts.
2. Probe liveness and readiness, retrieve capabilities, verify common revision/profile consistency, then retrieve authorized workspace list (follow `next_cursor` only within the explicit pagination bounds).
3. Select a workspace only from `WorkspacePage.items` also authorized by the profile's `workspace_ids`; refuse to turn `settings.workspaceName` into an HTTP path identifier. `development` may be the only valid returned ID; do not hard-code it as an authority substitute.
4. Reject a stale `capabilities` object after a later 503/offline event. Clear the enabled Live action and selected profile on terminal incompatibility; preserve only safe status/details.
5. On explicit retry, restart discovery; do not auto-select Preview on offline recovery. Display `profile_id`, `profile_revision`, `score_type` and actual database state as read-only diagnostics.

**Exit gate:** mode changes and out-of-order responses cannot result in an old server profile/workspace being shown as current.

### J5. Wire the existing interface without promising execution

1. Add accessible Preview/Live segmented control in the header or Settings; keyboard operation and focus order must work.
2. Keep **PREVIEW** badge whenever Preview is selected, and show **LIVE — checking/offline/unready/ready** truthfully. Use `role="status"` for asynchronous discovery; use `role="alert"` only for actionable errors.
3. Label the existing Preview scenario and Step delay explicitly as simulation preferences; disabling/hiding them in Live must not destroy saved settings.
4. Keep the existing `onValidate -> useValidation` behavior and label it as **Haystack constructor validation**, not Live execution approval.
5. Until UI-002 is complete, a Live Run is disabled with a clear explanation: "Live search execution is not connected yet". Do not invoke `usePreview.runPipeline` from Live.
6. Preserve current React in-memory session behavior: navigating across pages retains chosen mode; refresh may reset to Preview. Do not add premature localStorage or cross-workspace persistence.

**Exit gate:** every screen identifies the selected mode; no Live success UI exists without a Live response.

### J6. Final smoke and documentation

1. Run existing Preview browser smoke (six default nodes, demo retrieval and simulated failure) and the existing validator browser smoke.
2. Run separate discovery smoke: API connected/readiness 200/profile visible; API disconnected; readiness 503; stale out-of-order responses; manual Preview selection.
3. Update frontend README startup order and a small behavior matrix. Record the actual backend response IDs and commands, not copied fixture payloads.

**Exit gate:** all acceptance checks in M and the completion record in O have evidence.

## K. Security / Governance / Observability

- **Credentials:** browser receives no DB DSN, provider secret, TEI token, admin environment, session password or private model configuration. `VITE_` values are public.
- **Authorization:** `workspaceName` remains a cosmetic preference. All workspace IDs come from authenticated/authorized backend discovery; current `single_workspace_dev` is not enterprise RBAC.
- **Tenant isolation:** clear discovery/profile state when changing workspace; avoid client-constructed workspace filters as authorization. Server still enforces `WorkspaceContext` and PostgreSQL RLS.
- **Untrusted input:** API responses and imported graph JSON are untrusted. Decode as `unknown`; render error strings and server text using React text nodes, not `dangerouslySetInnerHTML`.
- **Source authority:** capabilities advertise operation availability; the constructor validator does not authorize an operation.
- **Audit/tracing:** retain `request_id`/`trace_id` where supplied; do not invent a `run_id` for discovery.
- **Logging/redaction:** client logging (if necessary) may record operation name/status/latency/trace ID; never log response content, full URL query, document bodies or credentials.
- **Retention:** only transient in-memory discovery state. No storage, data deletion or new long-lived audit data in this task.

## L. Testing / Evaluation / Runtime Verification

### Frontend commands (repository's actual toolchain)

```powershell
cd apps/workbench/web
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
```

Do not replace existing Hatch configuration. If a backend regression is suspected, from repository root use `hatch --version`, then the targeted `workbench-api`/test environment commands from [`apps/workbench/api/README.md`](../apps/workbench/api/README.md); generic `ruff check src tests` / `pytest -q` are not valid universal commands for this repository layout.

### Unit/contract matrix — minimum

| Case                   | Mock/server arrangement                             | Assert                                                           |
| ---------------------- | --------------------------------------------------- | ---------------------------------------------------------------- |
| Healthy profile        | 200 ready + 200 capabilities + authorized workspace | Live ready; selected profile and workspace match actual payload. |
| Liveness only          | live 200, ready 503                                 | UI does **not** claim search ready.                              |
| Empty profiles         | capabilities 200, `profiles: []`                    | Mode remains Live but execution unavailable.                     |
| Database unavailable   | dependency status `unavailable`, ready 503          | No green Live success or fixture fallback.                       |
| Schema incompatible    | dependency `incompatible`                           | Error/badge with safe code and corrective action.                |
| Stale revision         | unexpected `contract_revision`/profile revision     | Explicit incompatibility, not coercion to known profile.         |
| Error contract         | 404/409/503/429/504 nested envelope                 | Safe status + `code` + `trace_id` retained, message sanitized.   |
| Proxy offline          | HTML/502/network rejection                          | Transport error, never accepted as JSON success.                 |
| Request correlation    | `X-Request-ID` inconsistent with payload            | Protocol error; no trusted Live state.                           |
| Timeout and abort      | delayed `fetch`, user switches Preview              | Abort observed, timeout distinguished, pending timer cleaned.    |
| Out-of-order           | first request resolves after new selection          | First result cannot overwrite newer mode, profile, or workspace. |
| Workspace forgery      | editable workspace display name is changed          | No request path contains that name.                              |
| Unauthorized workspace | workspace list does not include profile workspace   | Reject selection; no guess or fallback.                          |
| Preview regression     | API absent                                          | Existing fixture Run still works and remains labeled Preview.    |
| Validation regression  | validator separately absent/online                  | Validation shows its own status; execution discovery unchanged.  |

Add tests next to `src/api/client.ts` and `src/hooks/useBackendDiscovery.ts`; a browser harness may use `scripts/discovery-smoke.js` rather than rewriting `browser-smoke.js`. Verify `npm run format:check` covers new files; use the existing Prettier conventions.

**Runtime evidence required:** successful GET to `/api/v1/capabilities` and `/api/v1/workspaces` with real API; one ready 503/no-profile sample; screenshots/browser assertions of mode indicators; test command outputs. A mocked fetch is good for unit correctness, but is **not** evidence of live backend availability.

## M. Acceptance Criteria

- [x] An explicit Preview/Live selector survives page navigation; refreshing may reset to Preview, as documented.
- [x] With both services running, browser network logs show separate `/api/pipelines/validate` and `/api/v1/...` calls with their respective contract shapes.
- [x] Only server-returned workspace IDs may be selected; changing `workspaceName` cannot change authorization scope.
- [x] `/api/v1/health/ready = 503` or `profiles=[]` always disables Live execution and shows a truthful diagnostic.
- [x] `features.documents=true` is labeled as **read-only**; upload is not advertised before ingestion API support.
- [x] A 200 capability response with malformed revision, IDs, limits or mismatched request metadata is rejected by runtime parsing.
- [x] Preview remains functional when the API is offline; Live never invokes `completePreviewNode`, `previewResults`, or `previewDocuments` to hide that outage.
- [x] There is exactly one shared RAG API transport abstraction, while the existing constructor validator remains separate and unchanged.
- [x] Existing Preview + validator tests and new discovery/client tests pass; typecheck/format/build outputs and actual smoke evidence recorded.

## N. Documentation / Migration / Compatibility / Rollback

- Update [`apps/workbench/web/README.md`](../apps/workbench/web/README.md) to show three distinct systems (Vite, validator, API), exact local ports, setup and failure semantics. Reference the canonical [API contract](../docs-website/docs/architecture/rag-runtime-contract.md) rather than copying the dated OpenSearch plan.
- No database migration, graph schema migration, or backend contract change. Retain `schemaVersion: 1` graph import/export and current Preview behavior.
- Rollout: keep Preview as initial mode; opt into Live manually. If API is down, Live remains selected but reports unready; a user may explicitly switch back.
- Rollback: remove/hide new execution control and proxy while preserving Preview, Haystack validation, PostgreSQL corpus and all backend records. The next task must not rely on a successful Live execution in this one.
- If backend adds new required fields, update [`openapi.json`](../apps/workbench/api/openapi.json), regenerate/review DTO expectations and tests **before** unblocking Live.

## O. Mandatory Completion Checklist

- [x] Confirm exact repository snapshot and contracts again at implementation start; amend section C if code changed.
- [x] Explain precisely which existing files/logic were reused and why no duplicate validator client was introduced.
- [x] Capture UI-facing request/error JSON examples with sensitive fields redacted.
- [x] Capture UI unit tests, typecheck, Prettier, build, Preview smoke and validation smoke outputs.
- [x] Demonstrate healthy, offline, unready, stale and conflicting-workspace cases in a browser.
- [x] Link evidence under `tasks/evidence/` using Markdown artifacts or existing test reports; include actual commit identifier and date.
- [x] Confirm no backend/DB/fixtures were changed and no unsupported capabilities are advertised.
- [x] Only mark **COMPLETE** after observable checks in M pass. Until then status remains **PROPOSED**.

## P. Implementation and completion record — 2026-11-21

Re-inspected the clean base `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`, the Python DTOs, published OpenAPI, validator transport and current shell before implementation. Section C records that pre-change inventory; the implementation now adds `src/api/`, discovery state/hook and the shared header mode control. No backend-contract correction was needed.

The completed scope is discovery only: four typed GET operations, runtime decoders, safe correlated failures, bounded timeouts/pagination and cancellation generations; server-authorized workspace selection; explicit Preview/Live UI; disabled Live Run; Live document/run placeholders without fixture fallback. Existing Preview, graph history/import/export, validator hook and CSS/font tokens were reused. The validator's camelCase protocol remains separate from the RAG API's snake_case protocol. No backend, migrations, existing fixtures, core Haystack or graph schema changed.

Three agents implemented transport, discovery orchestration and browser verification in parallel; cross-reviewed transport/discovery/UI integration without reporting blockers. Root integrated the shell/settings/editor/proxies and documentation. No new package dependency or state-management framework was added.

Verification: TypeScript, Prettier, all **96 unit/contract tests**, production build, existing Preview smoke, existing real-validator smoke and new discovery smoke passed. Discovery browser evidence includes the real API, actual no-DSN API 503 payload replay, offline injection, workspace conflict, stale responses, keyboard focus and 1440px/1100px layouts. The primary PostgreSQL/API were not stopped. The temporary unconfigured8012 process was stopped after evidence capture.

See the [complete verification record](evidence/ui-discovery-verification-2026-11-21.md), [real HTTP samples](evidence/ui-discovery-http-2026-11-21.json), [browser results](evidence/ui-discovery-browser-2026-11-21.json) and [JUnit](evidence/ui-discovery-tests-2026-11-21.xml). The record links command outputs, screenshots, reused owners, boundaries and unrun checks. Full upstream Python tests and the full documentation-site build were not run because these server/core implementations were unchanged.

Intentional design changes: the header now selects mode and shows connection status; Settings exposes read-only backend diagnostics and authorized selection; Preview controls are disabled but retained in Live. Contract revision remains `rag-api-v1.0` and graph serialization remains `schemaVersion: 1`. Connection readiness is a point-in-time observation, not execution approval. Search execution, live document listing, ingestion, real embeddings and production authorization remain subsequent tasks.

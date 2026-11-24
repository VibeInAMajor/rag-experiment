# TASK-UI-CONFIG-001 — Add Configuration navigation and a persisted YAML editor

**Created:** 2026-11-22  
**Updated:** 2026-11-24  
**Status:** COMPLETE — automated checks and live browser/restart verification passed  
**Dependencies:** [CONFIG-001](TASK-CONFIG-001-document-splitting-and-default-language.md) is implemented and locally qualified; this task extends its existing contract.  
**Related:** `TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md`.

**Superseding user decisions, 2026-11-22:** Configuration must open immediately, without Operator access, additional keys or a lock action. Remove the separate **Application-wide** badge and shield from the header. These explicit requests supersede role/login/badge requirements below. The implemented local application uses the existing loopback/trusted-origin boundary, same-origin credential-free requests and the non-secret `X-Workbench-Request: configuration` header. No account/RBAC/session guarantee is claimed. API scope remains application-wide; the ordinary description explains it without a badge.

**Completion evidence:** the restored in-app browser was used on 2026-11-22 to complete the positive Save/Reload/refresh flow, two-tab conflict, invalid-save/discard checks, real API restart activation and desktop/mobile inspection. All 11 recorded browser checks passed. The original YAML was restored byte-for-byte and activated through a second API restart; the existing 12 sources and 22 chunks remained unchanged. See [browser verification](../evidence/configuration-editor-2026-11-22/browser-verification.json), [desktop](../evidence/configuration-editor-2026-11-22/browser-desktop.jpg), [mobile](../evidence/configuration-editor-2026-11-22/browser-mobile.jpg) and [restored HTTP/SQL state](../evidence/configuration-editor-2026-11-22/restored.json).

## A. Title

Add a **Configuration** entry to the application sidebar and a full-page YAML configuration editor with validation, persistence, and safe reload behavior.

## B. Context / Problem

The existing UI shows vertical navigation entries **Pipelines**, **Documents**, and **Runs**. Operators currently have no UI to inspect, paste, edit, and save the application's YAML configuration. Recursive splitter settings and the default sentence language are intended to become configurable under `TASK-CONFIG-001`, but that task has **not been implemented**. This task establishes a UI and API path for managing one potentially large YAML configuration document; it must not create a parallel source of truth or assume the config backend already exists.

## C. Current Repository State

**Repository audit, 2026-11-22, before implementation:** the document's original assumption that CONFIG-001 is unimplemented is superseded by the inspected checkout. Prior working-tree changes and concurrent task archival are preserved.

- `apps/workbench/web/src/App.tsx` owns in-memory page navigation. Its `navigation-main` has Pipelines/Documents/Runs; Settings is separate at the bottom. `lucide-react` is installed and supplies the requested `Wrench` icon. There is no URL router to duplicate.
- `src/views/SettingsView.tsx`, `src/styles.css` and `views/views.css` own current preferences, typography, blue accent, buttons and responsive rail. No YAML/code editor is installed in `package.json`.
- `src/api/client.ts`, `contracts.ts`, `decode.ts`, `errors.ts` provide bounded, correlated, runtime-validated HTTP. Vite already proxies `/api/v1` to 8011. Existing client deliberately omits credentials; operator configuration must use an explicit cookie-capable, scoped transport extension.
- `apps/workbench/configuration/document_processing.py` owns strict Pydantic settings, bounded SafeLoader parsing, duplicate/alias/tag rejection, exact profile mapping and trusted file/env precedence. It reads one selected operator YAML; `config.py`/`application.py` already inject approved settings into `IngestionService` at startup. There are no config read/write endpoints or revision store.
- `boundary.py` enforces loopback host, approved Origin, bounded JSON/upload transport and sanitized correlation; there is **no existing user session, RBAC or privileged operator authentication**. Workspace routing is a fixed development scope and cannot stand in for app-wide edit authorization.
- Existing authoritative persistence is the selected YAML (`apps/workbench/document_processing.yaml`, or the existing operator-selected file). Preserve this single source rather than introducing a competing database copy. Save uses locked compare-and-swap, atomic replacement and bounded local revision backups. Activation remains API restart; existing indexed versions are immutable.
- The initial operator-key/session proposal was implemented, then removed following the explicit user correction above. The final feature opens directly through trusted local application requests. Deployment-owned native asset paths, canonical validation, limits, atomic persistence and revision conflicts remain protected; credentials and YAML bodies are excluded from logs.
- Preserve all already-running PostgreSQL data and historical evidence. Fresh tests use disposable configuration files/keys and databases; new live artifacts have their own directory.

**UI direction:** one full-width editing surface using existing IBM Plex/JetBrains typography, calm borders and the existing blue action. Header orients scope/status; the editor is the dominant workspace; a compact footer presents validation/activation. Motion is limited to existing button/focus feedback and a short busy-state indicator, honoring reduced motion.

**Verified from the user-provided screenshot:** the sidebar has **Pipelines**, **Documents**, then **Runs**, with **Runs** as the last visible item. The requested Configuration navigation item belongs immediately below **Runs**, represented by a wrench icon. The user describes the existing UI as currently disconnected from the backend.

**Verified from the supplied `TASK-CONFIG-001` Markdown:** the proposed logical configuration includes `document_processing.default_language: en` and `document_processing.recursive_splitter` defaults of `split_length: 500`, `split_overlap: 50`, `split_unit: token`, `tokenizer_encoding: o200k_base`, ordered `separators`, and `sentence_splitter_params.language: en` / `keep_white_spaces: true`. The task calls for the existing repository configuration contract to be reused, not duplicated.

**Repository inspection status:** an initial connected GitHub code-search attempt did not return relevant paths; this is **not evidence that components are absent**. Before implementation, inspect the actual sidebar component, router, API layer, configuration loading/validation, persistence approach, workspace authorization, existing editor components, and tests. Record concrete paths, symbols, current functionality and gaps in this section. Do not infer file paths or claim backend operations exist without verification.

## D. Goal

An authorized operator can select **Configuration** from the sidebar, view the persisted YAML, paste or edit a large YAML document, validate it, save valid changes durably, reload the page without losing saved content, and receive explicit actionable feedback for invalid YAML, unsupported settings, conflicts, authorization errors, and unavailable backend services. The saved configuration is a single well-defined source of truth consumed by the existing configuration subsystem when wired up.

## E. Scope

1. Add a wrench-icon **Configuration** sidebar item immediately **under Runs**, respecting established icon size, active state, tooltip/label, spacing, theme tokens, keyboard interactions and responsive behavior.
2. Add a Configuration route/page with a large, monospaced YAML editor; syntax highlighting, line numbers, indentation, scrolling, and multiline paste. Reuse an installed editor component if one exists; avoid new heavyweight dependencies without justification.
3. Support **Load**, **Validate**, **Save**, **Reload/Discard changes**, visible dirty state, clear saving/loading/error/success feedback, and a confirmation when navigating away with unsaved edits.
4. Provide a backend read/validate/update contract (or reuse existing endpoints). Persist a **single application-level configuration document** for MVP; do not pretend that per-workspace overrides are implemented. Ensure authorized access and explicit scope labeling.
5. Define and implement a safe effective-configuration boundary: read the current persisted source, validate against the same schema/runtime rules as the application's actual config loader, and ensure the ingestion service receives the approved configuration through the established configuration system. If the existing config subsystem is unfinished, implement a minimal shared contract/adapter without duplicating its parsing, validation, defaults or profile-routing logic; document any integration dependency clearly.
6. Provide tests, usability/accessibility checks, failure-path behavior, security checks, and operator documentation.

## F. Non-Goals

- A visual form for every YAML key, a schema builder, a configuration marketplace, or multiple editable configuration profiles.
- Designing a second standalone settings service, overriding the existing config schema, or implementing all functionality of `TASK-CONFIG-001` / `TASK-RAG-CHUNK-001` here.
- Arbitrary runtime execution of YAML, user-supplied Python tags, shell commands or untrusted template expansion.
- Editing environment variables or secret values via the UI.
- Automatically reprocessing/reindexing existing documents after a chunking change.
- Full workspace-specific configurations, per-tenant inheritance, approval workflow, or hot-reload guarantees without verified runtime support.

## G. Architecture / Boundaries

- [x] Application / orchestration — config read/validation/save lifecycle and effective settings integration.
- [x] Port / interface / contract — provider-neutral config repository/API boundaries if not already present.
- [x] Security / governance — privileged access, validation, audit and no secret disclosure.
- [x] Observability / evidence — saves, errors, versions and correlation IDs without logging YAML contents.
- [x] Documentation — operation, rollout and limitations.
- [x] Infrastructure / CI/CD — durable backing store and reproducible deployment as needed.
- [x] Retrieval / RAG — only reuse/consume existing splitter configuration contract.
- [ ] Domain / core — only if an existing shared typed config model must change.
- [ ] Provider adapter — N/A; no provider-specific integration belongs in this UI task.
- [ ] Persistence / vector store — persistence for config may change; vector-store APIs do not.
- [ ] Agent runtime — N/A; no agent runtime behavior introduced.

**Dependency direction:** UI → existing application API → shared configuration schema/validation/application service → persistence adapter. Config consumers must use the existing effective configuration and versioning mechanism, not read UI state or call frontend code. Avoid task/milestone identifiers in source symbol names, environment variables and API names.

## H. Contracts / Interfaces / Data Model

**Proposed *logical* API**, to be adapted to existing API naming/auth/error conventions after repository audit (do not create competing endpoints):

```http
GET /api/configuration
→ 200 { "yaml": "...", "revision": "opaque-version", "scope": "application" }

POST /api/configuration/validate
{ "yaml": "..." }
→ 200 { "valid": true, "errors": [], "warnings": [] }
→ 200 { "valid": false, "errors": [{ "message": "...", "line": 12, "column": 4, "path": "document_processing.recursive_splitter.split_length" }], "warnings": [] }

PUT /api/configuration
{ "yaml": "...", "expected_revision": "opaque-version" }
→ 200 { "revision": "new-opaque-version", "status": "saved", "activation": "requires_restart_or_supported_reload" }
→ 400/422 invalid YAML/schema/semantic config
→ 401/403 unauthenticated/unauthorized
→ 409 revision conflict
→ 413 payload size exceeds documented limit
→ 503 storage/runtime unavailable
```

These are **example contracts**, not instructions to hard-code paths or error shapes if the repository already has equivalent conventions. Save must validate server-side even after client-side validation. Parser MUST use safe YAML loading and reject dangerous constructs, duplicate keys if the chosen loader can enforce them, malformed structure, and unsupported settings according to the canonical configuration contract. Set explicit limits for request size, nesting/alias expansion and parse time; preserve comments/order on ordinary editing as far as the editor and persistence permit. Do **not** deserialize YAML into arbitrary objects.

**Single-source-of-truth rule:** persist a complete YAML document in an established durable backend location, or a configuration store chosen consistently with the existing application architecture. Do not silently combine frontend local storage, a checked-in sample file and a database into competing writable sources. Document bootstrap defaults, precedence over deployment settings, schema version compatibility, and atomic write/transaction boundaries. Secrets remain references resolved at the appropriate adapter boundary and are never returned to the browser as secret values.

**Starter content:** when no persisted configuration exists, display an explicitly labeled starter YAML generated from the *canonical* configuration defaults (not an independently maintained UI copy), including the initial recursive splitter profile below **only after** its shared schema exists:

```yaml
document_processing:
  default_language: en
  recursive_splitter:
    split_length: 500
    split_overlap: 50
    split_unit: token
    tokenizer_encoding: o200k_base
    separators:
      - "\n\n"
      - sentence
      - "\n"
      - " "
    sentence_splitter_params:
      language: en
      keep_white_spaces: true
```

`o200k_base` measurement and the independent Qwen-native token-limit validation remain separate responsibilities of the chunking/config tasks; the editor MUST NOT reproduce their domain logic. **Saving configuration is distinct from activating it:** return/display the actual activation behavior (hot reload, next job, or restart required) that the backend supports; never promise immediate application without proof.

## I. Repository Files / Components Impacted

**Audited ownership before implementation:**

| Paths | Planned extension |
| --- | --- |
| `apps/workbench/web/src/App.tsx` | Wrench item directly below Runs, page selection and unsaved navigation guard. |
| `src/views/ConfigurationView.tsx`, `src/components/YamlEditor.tsx`, corresponding styles/tests | Dedicated accessible editing/validation/save/session experience, lightweight lazy-loaded modular editor. |
| `src/api/client.ts`, `contracts.ts`, `decode.ts` and tests | Add configuration/session DTOs and scoped cookie/CSRF methods to existing transport. |
| `apps/workbench/configuration/document_processing.py`, `config.py` | Extract reusable in-memory validation from the existing bounded parser; expose selected trusted file path without adding another schema. |
| `configuration.py`, `configuration_http.py` | Single-file CAS persistence, nonsecret policy and direct local HTTP lifecycle using the existing host/origin policy. No operator-key/session subsystem remains. |
| `application.py`, `boundary.py`, `contracts.py`, `openapi.json` | Compose routes, bounded JSON/Origin policy, common correlation/errors and typed contracts. |
| API/frontend tests, `pyproject.toml`, web package/lock files | Necessary dependencies and focused parser/auth/persistence/race/UI regression checks. |
| Current API/web READMEs, `docs-website/docs/architecture/document-processing-configuration.md`, project map/sidebar, release note, this task | Explain single authoritative file, app-wide privilege, restart activation, backups/recovery and executed evidence. |

The existing splitter, model tokenizer, vector store, pipeline graph semantics and workspace authorization remain owned by their current modules.

**To resolve and record from a repository audit:** navigation/sidebar component and icon library; route definitions; page layout and design tokens; shared form/editor widgets; API client and error handling; application configuration schema/defaults; server config read/write/validation layer; persistence deployment configuration; RBAC or authentication middleware; frontend/backend tests; operator documentation. Extend existing components when found. **Must not change:** unrelated pipeline editor logic, document content/retrieval semantics, embedding/tokenizer implementations, vector-store persistence, or workspace authorization policy beyond permissions required for this screen. Update this section with exact paths before coding.

## J. Implementation Requirements

1. MUST inspect relevant UI, router, backend config handling, tests and docs, documenting evidence before making design changes.
2. MUST place the wrench/Configuration item **directly after Runs** in the existing sidebar, consistent with visual and accessibility standards; it MUST have a usable accessible name and selected state.
3. MUST provide a YAML-friendly editor with full-text paste/edit capability, high-volume scrolling, line numbers, indentation, syntax highlighting and a responsive, readable layout. Consider the repository's existing editor dependencies first.
4. MUST provide explicit Save, Validate, Reload/Discard interactions; disable duplicate saves while a request is in flight; protect against accidental loss of unsaved edits.
5. MUST persist server-side and reload from the same authoritative store. Browser local storage MAY support a clearly labeled unsaved recovery draft but MUST NOT be the authoritative configuration.
6. MUST validate syntax and configuration schema/semantics on the backend using the same configuration validation contract as runtime; MUST reject invalid writes without altering the previous saved version. Client syntax assistance does not replace server validation.
7. MUST implement concurrency protection with an existing version/ETag/revision mechanism or equivalent compare-and-swap; never silently overwrite a concurrent update.
8. MUST apply existing authentication and privileged configuration-edit authorization; read vs update permissions should be separated when existing RBAC supports it. The app-wide scope must be prominent.
9. MUST handle network failures, unauthorized requests, stale revision, validation failures, empty/missing configuration, read-only/unavailable store and excessive payloads with understandable messaging.
10. MUST NOT send raw config bodies to application logs, telemetry, error monitoring, analytics or traces; use revision, operation, actor, time and correlation metadata instead.
11. MUST NOT hard-code splitter settings, duplicate a config schema, create an alternate YAML settings parser, or tie code symbols to task identifiers.
12. MUST show precise activation status; changes impacting chunking MUST communicate that **existing indexed documents are unaffected until re-ingestion/reindexing**.
13. MUST expose a config read/view experience even while related splitter-config implementation is pending only if the UI can present the backend's real current contract; otherwise use an explicit not-yet-configured/unsupported state, not a fake successful Save.

## K. Security / Governance / Observability

Application-level configuration can impact all workspaces; editing MUST be restricted to an explicitly authorized operator/admin role and audited. Reuse session/cookie auth and CSRF protections if present. Validate YAML safely with resource limits to mitigate malicious aliases, huge payloads and denial of service; guard against config-driven filesystem/path injection. Do not disclose secrets or environment-resolved credentials in the UI or logs. Persist only non-secret references. Record config revision, scope, editor actor, timestamp, outcome and error category; avoid logging YAML content. Ensure no cross-workspace privilege escalation occurs through this global feature. Define retention and rollback policy according to current infrastructure.

## L. Testing / Evaluation / Runtime Verification

### Executed verification and scope

- `test_configuration_editor.py` covers direct keyless loading, no session/cookie endpoint, canonical malformed/unsafe YAML refusal, comments/text round-trip, conflicts, origin/request-intent guards, payload bounds, content-free logs, parallel writers and atomic replacement failure.
- `test_configuration_editor_ingestion.py` uses fixture-owned real PostgreSQL: a Save leaves the old ingestion snapshot active, a fresh application consumes saved RU/80/15 settings, and old versions/fingerprints stay unchanged.
- `test_configuration_editor_process.py` saves and restarts an actual owned API subprocess on its own port with temporary config. Saved text/revision survive, and activation changes from requires_restart to active without keys/sessions. The development corpus is untouched.
- Frontend checks cover direct loading without Operator access/key/Lock/Application-wide badge, wrench placement after Runs, navigation/discard dialogs, multiline edits, validation diagnostics, pending duplicate-save refusal, conflicts, timeout draft retention, starters and load failures. The API client sends request intent automatically without cookies and refuses cross-origin configuration routing.
- The live website proxy returned configuration/validation/unchanged Save successfully **without a key or cookies**: [direct HTTP evidence](../evidence/configuration-editor-2026-11-22/direct-http.json). [Scoped SQL/proxy evidence](../evidence/configuration-editor-2026-11-22/direct-access.json) confirms the existing 12 sources/22 chunks are unchanged and default settings remain active.
- Actual CodeMirror accepted/validated 48,515 bytes with 53 rendered visible lines during the earlier browser check. After browser access was restored, live verification confirmed direct keyless loading without the removed badge/Lock, canonical overlap errors, invalid-save refusal, Escape/discard behavior, successful Validate/Save, persistence after page refresh and stale-tab conflict with both saved file and draft retained. Changing `keep_white_spaces` from true to false produced [requires_restart](../evidence/configuration-editor-2026-11-22/pending.json); a real API restart produced [active](../evidence/configuration-editor-2026-11-22/after-restart.json). The original YAML was then saved through the UI and activated through another restart; its SHA256 exactly matches the original. Every SQL snapshot matched the unchanged 12-source/22-chunk baseline.
- [Final desktop](../evidence/configuration-editor-2026-11-22/browser-desktop.jpg) and [390×844 mobile](../evidence/configuration-editor-2026-11-22/browser-mobile.jpg) screenshots were visually inspected. Mobile action buttons remain inside the viewport; document width is 390 pixels and the main panel has no horizontal overflow. Long YAML lines scroll inside the editor. The temporary viewport override was reset, the duplicate tab was closed and Configuration was left open in the side browser. Final console inspection returned no warnings or errors. [All 11 browser checks](../evidence/configuration-editor-2026-11-22/browser-verification.json) passed; no application code change was needed for this verification.
- Latest full results are in [backend JUnit](../evidence/configuration-editor-2026-11-22/backend-tests.xml), [backend log](../evidence/configuration-editor-2026-11-22/backend-tests.log), [frontend tests](../evidence/configuration-editor-2026-11-22/frontend-tests.txt), quality/type/build artifacts in the same directory. Earlier operator-session test artifacts in that directory predate the user correction and do not describe the final contract.

Full upstream Haystack tests, a documentation-site build and a public/remote deployment were not run. File locking/atomic replacement are qualified locally, not on a multi-host network filesystem.

- **Frontend unit/component:** placement under Runs; wrench icon, active navigation, keyboard accessibility, route load, paste/edit of multiline YAML, dirty indicator, save disabled while pending, validation markers, navigation warning and status messages.
- **API contract:** read/validate/save response shapes, server-side validation, authenticated read/authorized write, revision checking, status errors, full round-trip of YAML text and comments.
- **Persistence/integration:** save → refresh/restart process where applicable → GET returns saved YAML; invalid save retains prior revision; concurrent edit returns 409; backend config consumer reads effective approved values according to documented activation semantics.
- **Negative/security:** malicious YAML tags/aliases/duplicate keys, unsupported schema keys, invalid 500/50 parameter boundaries, too-large body, CSRF/auth failures, secrets redaction, storage outage, timeout, and partial-write recovery.
- **Regression:** existing Pipelines/Documents/Runs navigation and responsive layout are unchanged; no duplicate backend config route or schema is introduced.
- **End-to-end:** an authorized user changes a permitted setting from the sidebar, validates/saves, reloads, and sees the persisted result; an unauthorized user cannot save; a second simultaneous editor receives a conflict.
- **Baseline:** run repository-standard frontend lint/typecheck/test/build and backend tests; for Python components run `ruff check src tests` and `pytest -q` where applicable. Record concrete commands and results.

## M. Acceptance Criteria

- [x] **Configuration** appears immediately below **Runs** with a wrench icon and conforms to existing visual styles in desktop and responsive navigation.
- [x] Sidebar entry opens a dedicated, accessible Configuration page with a YAML editor supporting a large multiline configuration.
- [x] User can load, edit, paste, validate, save and reload a YAML document; the persisted result survives page refresh and a relevant backend restart.
- [x] Validation errors include actionable location/path information when available; invalid saves do not modify the previous saved revision.
- [x] Per explicit user correction: the local Configuration page opens without operator access/keys; separate Application-wide badge/shield and Lock action are removed. Trusted local request/origin guards remain, with no account-role claim.
- [x] Concurrent updates are protected with revision conflict handling, and stale clients cannot silently overwrite newer changes.
- [x] No YAML bodies or configured credential values are logged; rejected foreign-origin/request-intent calls receive no YAML. The selected local model has no account roles.
- [x] Editor uses the existing effective configuration schema/loader; no second splitter config implementation, duplicate parser or independent UI default table is introduced.
- [x] Starter/default config uses **English (`en`)** and the approved **500/50 token** profile **if and only if** the canonical schema provides them.
- [x] Save result accurately indicates whether settings are active now or require a restart/next run; existing indexed chunks are not claimed to be updated.
- [x] Automated normal, failure-path, local-request security, integration and regression checks pass: **872 backend tests, zero skips; 270 frontend tests**, TypeScript, Prettier, build, Ruff/format and mypy for 69 API files. The subsequent visible E2E/restart verification also passed; application code was unchanged, so the already-passing suites were not repeated.

## N. Documentation / Migration / Compatibility / Rollback

Document navigation, role requirements, sample YAML, syntax/schema validation, persistence location, scope, precedence, supported activation semantics, version conflicts and recovery procedure. Link to `TASK-CONFIG-001` and `TASK-RAG-CHUNK-001`. If the existing app uses immutable environment/deployment configuration, explicitly document the chosen transition, precedence and migration without silently overriding existing deployment settings. Back up or version saved revisions with the existing mechanisms; rollback restores the prior valid revision and activates it following the same supported lifecycle. Reverting splitter settings does **not** retroactively change indexed chunks; reindex/reingest is a separate deliberate operation.

**Dependency sequencing:** this task may deliver sidebar/editor UI before the related configuration task is implemented, but **must not claim end-to-end saved-and-effective behavior is complete** until the authoritative backend contract, validation, persistence and integration are in place. Prefer one shared implementation of settings/schema over two parallel teams defining incompatible formats.

## O. Mandatory Completion Checklist

- [x] Existing UI/backend/config repository evidence documented in C and I.
- [x] Wrench icon, navigation placement, route, large editor, basic keyboard/modal accessibility and final desktop/mobile screenshots verified.
- [x] Canonical YAML load/validate/save contract and durable persistence verified.
- [x] User-selected direct local access, trusted Origin/request-intent guards, parser limits and secret-value exclusion verified; no account-role model is claimed.
- [x] Revision conflict, error states and unsaved-change protection verified.
- [x] Effective config integration and accurate activation semantics documented and tested.
- [x] All applicable component, API, integration, security, E2E and regression tests pass.
- [x] Local operation docs, recovery/rollback and related-task dependencies updated, including both explicit user corrections.
- [x] Evidence recorded for every acceptance criterion; task set `COMPLETE` after live verification and restoration.

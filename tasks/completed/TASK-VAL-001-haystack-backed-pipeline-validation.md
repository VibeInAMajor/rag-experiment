# TASK-VAL-001 — Use Haystack as the Authoritative Workbench Pipeline Validator

**Created:** 2026-11-20  
**Updated:** 2026-11-24  
**Status:** COMPLETE  
**Priority:** High  
**Dependencies:** None; this task precedes general frontend–backend integration.  
**Target path:** `tasks/TASK-VAL-001-haystack-backed-pipeline-validation.md`

## A. Title

Replace Workbench-owned semantic pipeline validation with a thin validation-only boundary delegating to existing Haystack pipeline APIs, without introducing the full RAG backend.

## B. Context / Problem

Workbench currently decides whether graph connections and pipelines are valid using its own TypeScript implementation. Haystack already owns component registration, socket compatibility, connection rules, and pipeline input validation. Two independent sets of semantic rules will diverge as components and integration evolve. Establish **one authoritative semantic validator: the installed Haystack library**.

**Important architectural clarification:** A browser cannot invoke Python methods directly. A narrow, local Python validation endpoint (or equivalent controlled RPC boundary) is required. This is deliberately **not** document ingestion, retrieval, execution, or general backend integration. The frontend may retain local checks for UI structure and unsafe input, but MUST NOT claim that those checks establish Haystack compatibility.

## C. Current Repository State

Verified against repository source on 2026-11-20:

| Existing code | Evidence / implication |
| --- | --- |
| `apps/workbench/web/src/domain/graph.ts` | `validateConnection()` checks simplified `valueKind`, duplicate links, input multiplicity, and cycles; `validateGraph()` checks simplified required ports and catalog parameters; `topologicalNodeIds()` requires a DAG. |
| `apps/workbench/web/src/domain/graph.ts` | `importPipeline()` implements safe JSON parsing, schema version 1, strict fields, graph size caps (100 nodes / 300 edges), duplicate IDs and edge checks; import currently calls `validateConnection()`. **Retain structural safety independently of Python availability.** |
| `apps/workbench/web/src/domain/catalog.ts` | UI node metadata labels include `DoclingConverter`, `OpenAIDocumentEmbedder`, `OpenAITextEmbedder`, `InMemoryBM25Retriever`, `PgvectorEmbeddingRetriever`, `DocumentJoiner`, plus conceptual `Workspace files`, `Pipeline input` and `Pipeline output`. Labels are **not proof** that matching Python components are installed or have matching sockets/constructor parameters. |
| `apps/workbench/web/src/App.tsx` | `validateGraph()` is used for interactive Validate flow; preview is launched separately. |
| `apps/workbench/web/src/components/PipelineEditor.tsx` | `validateConnection()` is used on editor connection actions. |
| `apps/workbench/web/src/domain/preview.ts` and `src/hooks/usePreview.ts` | Fixture preview currently assumes local graph validation/topological sequencing; there are no real backend calls. |
| `apps/workbench/web/src/domain/graph.test.ts` | Tests enforce current DAG-based, port-category, import and preview behavior; update expectations intentionally rather than blindly deleting regressions. |
| `apps/workbench/web/README.md` | Explicitly documents fixture-only Workbench, no backend/API clients, and warns UI validation is not Haystack compatibility checking. |
| `haystack/core/pipeline/base.py` | Existing `PipelineBase.add_component()` validates registration; `connect()` validates socket existence and compatibility and raises `PipelineConnectError`; `validate_input()` validates **execution input data**, not arbitrary graph JSON. |
| `haystack/core/pipeline/pipeline.py` | Existing public `Pipeline` is the concrete pipeline type. |
| `haystack/core/serialization.py` / `serialization_security.py` | Existing serialization/deserialization and security safeguards MUST remain intact. |

**Identified mismatches / caveats:**

1. UI `valueKind` (`files`, `documents`, `text`, `embedding`) is coarser than Haystack's declared Python socket types.
2. Workbench enforces a DAG; Haystack supports pipeline loops in supported contexts. **Do not claim Haystack forbids all cycles.** This task may retain a deliberate *Workbench preview-mode DAG restriction*, but must label it as a UI/preview capability limit, never as Haystack validation.
3. Several UI nodes are conceptual source/sink elements, and some catalog labels refer to integrations that may not be installed in the repository. **Never fabricate a successful validation by replacing them with generic pass-through stubs.**
4. `Pipeline.validate_input()` cannot replace graph construction / socket validation; it has a narrower purpose.
5. Browser-side structural import checks and deterministic fixture preview should continue to work offline; offline status must not be misrepresented as Haystack-valid.

No runtime error measurements are supplied: the concern is evidenced rule duplication and potential semantic drift, not a proven production failure.

## D. Goal

For every fully supported pipeline submitted for authoritative validation, the **sole source of semantic validity** is a pipeline assembled with actual installed Haystack components using its public `Pipeline.add_component()` / `Pipeline.connect()` APIs, plus `validate_input()` **only if explicit execution input data is supplied and applicable**. The UI displays the returned outcome and mapped diagnostics, and it never substitutes client-side acceptance for a failed or unavailable authoritative validation.

## E. Scope

- Inventory current UI node kinds against real, importable Haystack components and ports; publish an explicit supported/unsupported mapping with evidence.
- Add the **minimum** isolated Python validation-only adapter, request/response contract, and frontend transport needed to call Haystack.
- Preserve editor responsiveness via lightweight structural checks; move semantic validity decisions to the Haystack adapter.
- Integrate authoritative Validate action and appropriate connection-check feedback; keep drafts editable.
- Make preview semantics explicit: fixture preview remains a demo and can run only under its own documented prerequisites; it MUST NOT masquerade as a backend-validated execution.
- Add focused Python, TypeScript and contract tests and update Workbench documentation.

## F. Non-Goals

- No ingestion, chunking execution, embeddings, LLM inference, retrieval, pgvector, workspace persistence, authentication service, multi-workspace backend, production deployment or real run execution.
- No wholesale Workbench redesign or typography/color change.
- No replacement/fork of Haystack internals; no duplicated Python graph-validity algorithm.
- No silent UI catalog expansion or arbitrary plugin installation.
- No acceptance of client-provided Python module paths or serialized executable objects.

## G. Architecture / Boundaries

- [x] Domain / core — existing Haystack `Pipeline` remains authoritative; **do not modify its rules**.
- [x] Application / orchestration — thin validator assembly/translation module.
- [x] Port / interface / contract — bounded graph validation request and typed response.
- [ ] Provider adapter — N/A: no model/provider calls.
- [ ] Persistence / vector store — N/A: read-only in-memory validation.
- [ ] Retrieval / RAG — N/A: not executed.
- [ ] Agent runtime — N/A: not executed.
- [x] Security / governance — strict allowlist, safe inputs, no arbitrary imports.
- [x] Observability / evidence — structured diagnostics and correlation ID.
- [x] Infrastructure / CI/CD — local startup/test scripts and contract checks.
- [x] Documentation — mapping, limitations and validation states.

```text
Workbench React UI
    | serialized graph (strictly bounded JSON)
    v
Thin validation transport (HTTP on loopback or equivalent)
    v
Strict graph-schema validator + explicit UI-kind-to-component registry
    v
Installed Haystack Pipeline.add_component() / Pipeline.connect()
    | (optionally validate_input() for actual supplied input payloads)
    v
Typed diagnostics response (valid / invalid / unsupported)
    v
Workbench diagnostics / node-edge annotations
```

The transport MUST NOT contain a second semantic graph-validation engine; the mapping layer may reject unmappable schema elements and incompatible UI concepts, and it MUST disclose these as **unsupported**, not as “valid.”

## H. Contracts / Interfaces / Data Model

Define a small versioned **validation-only** request; reuse existing Workbench schema types and serialization safety rules. The following is a *proposed contract*, not an already implemented endpoint:

```text
POST /api/pipelines/validate
request:  { schemaVersion: 1, graph: { nodes: [...], edges: [...] }, requestId?: string }
response: {
  status: "valid" | "invalid" | "unsupported",
  issues: [{ code: string, message: string, nodeId?: string, edgeId?: string, field?: string }],
  requestId: string,
  validator: "haystack",
  capabilityVersion: string
}
```

Transport or service unavailability is **not** `valid`, `invalid`, or `unsupported`: expose a distinct client-side `unavailable`/`error` state and an actionable retry. Do not invent validity when a request times out.

Contract requirements:

- `node.id` is a stable **UI identifier**, not automatically a safe Haystack component name. Map to deterministic safe internal names and preserve UI IDs for diagnostic mapping.
- Translate UI handles to actual runtime socket names via an **explicit reviewed registry**, not by assuming that a `valueKind` or display label matches Python types.
- Instantiate only approved, importable, safe components with deterministic constructor settings; no credentials, remote access, warm-up, inference, file reads or plugin discovery. If construction cannot be safely achieved, return `unsupported` and document why.
- Support both **draft checking** (partial graphs should be editable) and **complete validation** (report missing inputs/parameters) without inventing Haystack semantics for absent required inputs. Document the precise distinction and ensure `valid` means the requested level passed.
- Preserve current graph file `schemaVersion: 1` import/export semantics; avoid a breaking change. Unknown fields or malformed payloads must be rejected before conversion.
- Normalized error codes (e.g. `UNKNOWN_COMPONENT_KIND`, `UNSUPPORTED_COMPONENT`, `INVALID_PORT`, `INCOMPATIBLE_SOCKET`, `MISSING_REQUIRED_INPUT`, `VALIDATION_UNAVAILABLE`) MUST be stable and documented. Do not leak raw tracebacks or secrets.
- `capabilityVersion` must identify the validated mapping/catalog revision (not a task identifier); add a compatibility check to detect stale frontends.

## I. Repository Files / Components Impacted

**Existing files to inspect/change:**

- `apps/workbench/web/src/domain/graph.ts` — separate import/shape safety from semantic validation; remove misleading authoritative local validity.
- `apps/workbench/web/src/domain/types.ts` — add typed validation outcome/diagnostics, reusing established models.
- `apps/workbench/web/src/domain/catalog.ts` — align supported component/port metadata with reviewed server mapping; do not duplicate backend rules in TypeScript.
- `apps/workbench/web/src/App.tsx` — call authoritative validator and display explicit status.
- `apps/workbench/web/src/components/PipelineEditor.tsx` — adapt connection UX without blocking on fabricated local Haystack rules.
- `apps/workbench/web/src/domain/preview.ts`, `src/hooks/usePreview.ts` — decouple fixture-only preview from authoritative validation and retain honest labeling.
- `apps/workbench/web/src/domain/graph.test.ts` — adjust tests that incorrectly assume UI DAG/socket checks equal Haystack semantics.
- `apps/workbench/web/README.md` — document local validator dependency, offline behavior and known unsupported nodes.

**New files:** only the smallest cohesive Python validator module/entrypoint and frontend transport layer (locations to be selected **after repository inspection** and recorded here before implementation); corresponding focused tests and one mapping document.

**MUST NOT change:** Haystack core validation algorithms, existing security allowlists, upstream integration SDK code, design styling, unrelated docs/CI or the execution subsystem. Any material deviation requires updating this task first.

## J. Implementation Requirements

1. **Inventory first.** Build a matrix for every current `NodeKind`: UI kind, intended Haystack class, import location/package availability, actual input/output socket names and types, safe constructor requirements, mapping status, and rationale. Do not infer socket compatibility from UI labels.
2. **Reuse Haystack.** Construct the pipeline with `Pipeline()`; register allowlisted components with `add_component()`; connect explicit sockets via `connect()`. Capture errors from public Haystack exceptions and translate them to UI diagnostics. Use `validate_input()` only for its documented role; never call `run()` or `warm_up()` for validation.
3. **Support honest partial-state behavior.** Allow graph drafts and disconnected nodes to remain editable; distinguish *structural validity*, *runtime connection validity*, *completeness*, and *preview restrictions*. Full `valid` must not be inferred from successful `connect()` calls alone.
4. **Do not invent dummy runtime equivalents.** For UI-only source/sink nodes, choose an explicit, reviewed safe mapping or mark unsupported. If a conceptual node is not representable, its pipeline cannot receive a full `valid` result.
5. **Eliminate duplicate semantic checks.** Convert local validation helpers into strictly scoped shape/UX prechecks, rename them accordingly, and remove or deprecate old “Haystack-valid” behavior. Do not maintain a shadow socket-compatibility table in React.
6. **Keep UX responsive.** Prefer explicit Validate for full authoritative checking; optional debounced asynchronous edge checks must handle stale responses, cancellation and rapid graph edits. Do not optimistically mark a connection Haystack-valid before confirmation.
7. **Remain offline-safe.** File import shape and safety checks run without Python; when validation service is down, report `unavailable` and preserve draft editing without permitting a “validated” badge. Preview must stay clearly simulated.
8. **Bound resources.** Reuse max nodes/edges, payload size and schema checks. Add short timeouts, rate/concurrency limits appropriate to a localhost development tool, and no remote component instantiation.
9. **Single source of truth.** Avoid new provider-neutral factories unless required by a verified boundary. The exact Python component/port mapping lives in one place; derive any UI capability metadata from it or synchronize through contract tests.
10. **Keep changes scoped.** No actual backend integration or model-service requests in this task. All new symbols use meaningful domain names, never task IDs.

## K. Security / Governance / Observability

- **Secrets:** Do not request credentials; never log secrets, component parameter values containing sensitive data, document contents or full graph payloads.
- **Authorization:** Local loopback-only validation in this phase; no production authentication is implied. Explicitly block nonlocal binding/cross-origin use by default. Do not present this as a secure production service.
- **Workspace/tenant isolation:** N/A for backend data access — the validator must not access tenant data or storage. Tenant identity, if present in UI fixtures, cannot authorize anything.
- **Trust boundaries:** Treat all graph JSON as untrusted; disallow arbitrary Python imports, dynamic class names, user-supplied `module`/`type` paths and unsafe deserialization. Never bypass Haystack serialization allowlists.
- **Prompt injection / source authority:** No retrieved content or prompts are executed; ignore any instruction-like payload fields.
- **Audit/traceability:** Record request ID, outcome, supported/unsupported node counts, latency and sanitized issue codes. No full payload logging.
- **Retention:** In-memory only; no persisted validation payloads by default.
- **Operational evidence:** Structured logs for validation duration, failures, unmapped component kinds, cancellation/timeouts; unit/contract test output.

## L. Testing / Evaluation / Runtime Verification

**Python (repository-specific):** check `hatch --version`, use Hatch environments and **targeted** pytest, then required quality gates where feasible: `hatch run test:unit`, `hatch run test:types`, `hatch run fmt`. The generic project-instruction baseline `ruff check src tests` / `pytest -q` must be reconciled with the actual repository layout (`haystack/`, `test/`) and Hatch configuration rather than executed against nonexistent directories. Document exact commands and results.

**Frontend:** from `apps/workbench/web`, run `npm run typecheck`, `npm run format:check`, `npm test`, `npm run build`, and applicable documented browser-smoke scenario.

Required automated scenarios:

- Valid supported graph: adapter really calls `Pipeline.add_component()` and `Pipeline.connect()` with real installed components; reports `valid` only after complete validation.
- Invalid real socket name/type or duplicate incompatible input: Haystack rejects; response ties issue to correct UI node/edge.
- Missing mandatory input/parameter: draft remains editable; final/full validation does not report `valid`.
- Unsupported or uninstalled catalog component: returns `unsupported`, not `valid`; no fake substitute or network/model call.
- Malicious JSON/module path and oversized graph: rejected before component construction; no dynamic import.
- Rapid edits/out-of-order responses: stale validation results never overwrite a newer graph state.
- Service unavailable/timeouts: clear `unavailable`, no green validated state, draft import/edit continues.
- Existing import/export round-trip and undo/redo remain stable.
- Fixture preview remains marked PREVIEW; real retrieval, inference and index writes are never invoked.
- Compatibility tests assert registry socket definitions against real Haystack components, and frontend/server contract schemas stay synchronized.
- Document loop behavior explicitly: Haystack-compatible loops are not mislabeled invalid by Haystack; if preview stays DAG-only, that restriction is separate and clearly explained.

**AI/RAG evaluation:** N/A — no retrieval, generation, embeddings or evaluation workloads execute in this task.

## M. Acceptance Criteria

- [x] Published inventory covers **100% of existing Workbench node kinds**, distinguishing supported, unsupported and UI-only nodes, with verified Haystack ports and installation prerequisites.
- [x] For **every supported complete graph**, the authoritative semantic decision is derived from real Haystack `Pipeline` construction and connectivity checks, not local `valueKind` comparison.
- [x] No frontend path labels a graph **Haystack-valid** if validation has not succeeded against the validator, including offline, timeout and stale-response cases.
- [x] All unsupported/uninstalled nodes are reported explicitly; no fake pass-through replacement is used to claim success.
- [x] Existing safe JSON import (1 MB, supported schema/version, 100 nodes, 300 edges, blocked executable fields) and export semantics remain intact.
- [x] Editor drafts, undo/redo and fixture-only preview still operate with clearly separated status.
- [x] Validation diagnostics identify relevant node IDs and edge IDs when possible, with stable error codes and no raw tracebacks.
- [x] No Haystack core behavior, provider SDK code or design styling is modified.
- [x] Python and TypeScript unit/contract tests cover success, failure, unsupported, offline and adversarial scenarios; actual check results are recorded.
- [x] Documentation describes how to launch the validation-only service and distinguishes it from the later execution/backend integration milestone.

## N. Documentation / Migration / Compatibility / Rollback

- Update `apps/workbench/web/README.md`, project navigation documentation (if present), and mapping/contract docs; do not rewrite unrelated upstream Haystack documentation.
- **Migration:** No DB/schema migration. Retain portable graph file `schemaVersion: 1`; preserve old files and fail transparently when imported nodes lack a runtime mapping.
- **Compatibility:** The new authoritative verdict requires the validation service. Older offline Workbench behavior remains for editing/import/fixture preview only; a previously local “valid” indication is no longer equivalent to runtime compatibility.
- **Rollout:** Gate authoritative validation behind the successful launch/health of the local validation-only service. No fallback path may claim authoritative success.
- **Rollback:** Frontend can fall back to explicitly labeled local draft/fixture mode; do **not** silently restore local semantic checks as authoritative. No persistent data to restore.
- **Deferred:** General API backend, real execution, retrieval, workspace isolation, ingestion and observability integrations.

## O. Mandatory Completion Checklist

- [x] Existing source/tests/config rechecked and inventory evidence linked.
- [x] This task updated if repository facts or scope differ materially.
- [x] Public Haystack methods reused; no duplicated semantic validator introduced.
- [x] All supported, unsupported and UI-only mappings reviewed and documented.
- [x] Contracts, statuses, diagnostics and failure modes implemented and tested.
- [x] Security boundary and safe/no-execution guarantees verified.
- [x] Frontend build, targeted Python tests and contract checks executed; commands/results recorded.
- [x] Documentation, compatibility and rollback notes updated.
- [x] Final completion report records changed files, reused code, acceptance evidence and remaining limitations.

**Completion rule:** Do not mark this task `COMPLETE` until all applicable boxes are checked with evidence. An unsupported-node verdict or unavailable validator must never be counted as successful Haystack validation.

## Implementation record — 2026-11-20

Status: COMPLETE. The owner's request authorizes this specification as the implementation task; instruction-like example graph payloads are treated as data.

Repository routing correction: the newly supplied navigation documents are currently at `docs-website/PROJECT_MAP.md` and `docs-website/ENGINEERING.md`, not `docs/`. Existing user edits to those documents and AGENTS.md are preserved.

Selected locations after inspection:
- `apps/workbench/validator/`: isolated Python registry, strict schemas, assembly, loopback HTTP entrypoint, inventory and tests.
- `apps/workbench/web/src/domain/validation.ts` and `src/hooks/usePipelineValidation.ts`: frontend transport and stale-safe validation state (final names recorded on completion).
- `apps/workbench/web/vite.config.ts`: same-origin validation-only proxy for development and preview.

Contract refinement: requests and responses include explicit `mode` (`draft` or `complete`). Draft means real component construction and connection checking; complete additionally checks required external inputs. Optional execution inputs are validated using Haystack's public input validator. Capability revision is `workbench-components-v1`.

No ingestion, provider calls, execution, database or theme changes are authorized by this task.

## Completion evidence — 2026-11-20

Implemented locations: `apps/workbench/validator/{schemas,registry,validator,server,__main__}.py`, `web/src/domain/validation.ts`, `web/src/hooks/useValidation.ts`, existing editor/graph/preview modules, and `web/vite.config.ts`. The originally proposed hook filename was replaced by the meaningful `useValidation.ts`.

Public logic reused: real Haystack `Pipeline.add_component`, `connect`, `inputs`, and `validate_input`, plus Workbench portable graph serialization, structural JSON safety, history and fixture preview. No core files, deserialization allowlists, provider SDKs or style sheets changed. Existing user edits to AGENTS.md were preserved.

Verification:
- `hatch -e test run pytest apps/workbench/validator/tests -q`: 33 passed.
- `hatch run fmt-check apps/workbench/validator`: passed (Ruff check and format).
- `hatch run test:types --explicit-package-bases apps/workbench/validator`: passed, 7 source files.
- Workbench `npm run typecheck`, `npm run format:check`, `npm test` (29 passed), `npm run build`: passed. Existing third-party bundler directive warnings remain nonfatal.
- Playwright `scripts/browser-smoke.js`: passed editing, history, import/export, branches, preview-only loop rejection, success/error runs and document/run views.
- Playwright `scripts/validation-smoke.js`: actual Python valid/unsupported contract, edit invalidation and unavailable behavior passed through Vite.
- HTTP tests cover untrusted inputs, Host/Origin checks, resource limits and non-disclosure; catalog coverage and live installed socket contracts are checked.
- Full upstream Python suite was not run: the scope adds an isolated adapter and leaves framework internals unchanged; focused tests exercise the real framework APIs.

Intentional compatibility change: serialized file schema stays 1, but drafts can now preserve semantic mismatches and cycles; only fixture Preview retains DAG prerequisites. Authoritative validity is level-specific and never falls back to local checks. Default demo templates remain Unsupported because their conceptual and unavailable components have no approved runtime mapping. No generic stubs were added.

Limitations: validation-only, loopback development service; no production authentication, execution or RAG backend. Five approved core mappings and six explicit unsupported mappings are listed in the validator README. Complete validation with required external sockets needs explicit API input data; the current UI does not provide an execution-input form. Constructor-only validity does not guarantee successful execution.

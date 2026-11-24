# Engineering conventions

This reference expands the root [AGENTS.md](../AGENTS.md). Follow established module conventions when they are more specific, and check the [project map](PROJECT_MAP.md) before introducing code.

## Naming: domain meaning, not task IDs

- Names must explain **what a value represents** or **what a function does**, independently of the issue that caused its creation.
- Do not create identifiers such as `m9Data`, `M9_MODE`, `task12Cache`, `phase3Parser`, `run_BE04`, `handleUI01`, or `--m9-accent`.
- Prefer `activeWorkspaceId`, `documentVersionId`, `embeddingBatchSize`, `indexChangedDocuments`, `validateConnection`, `useGraphHistory`, `--color-action-primary`.
- Tracking codes can appear in issues, project plans, pull requests and changelogs; do not use them as variable, class, test fixture, API, SQL field, telemetry attribute, or CSS names.
- TypeScript/React: `camelCase` variables/functions; `PascalCase` components/types; `useXxx` React hooks; descriptive filenames following local convention. Python: PEP 8 `snake_case` functions/variables, `PascalCase` types, `UPPER_SNAKE_CASE` constants; `_` for private APIs where established. CSS: semantic, reusable classes/custom properties.
- Preserve external protocol names, existing persistent fields and upstream APIs for compatibility. Rename only with explicit migrations and tests.

## Reuse-first workflow

1. Identify the owning feature, behavior and source of truth using [PROJECT_MAP.md](PROJECT_MAP.md).
2. Search the repository for existing terms, symbols, interfaces, tests and callers. Inspect the implementation, not just its filename.
3. Prefer extending an existing module/hook/component or composing public Haystack components instead of copying logic.
4. Add an abstraction only for a distinct responsibility, meaningful reuse, or a verifiable simplification. In a PR, state what was examined and why it could not be reused.
5. Keep validation, schemas, catalog entries, defaults, configuration and design tokens centralized. Avoid a second source of truth in another view.
6. Limit the diff to the requested feature. Remove dead code, unused exports, unnecessary dependencies and speculative wrappers.

A shared UI validator does not replace mandatory independent server-side authorization/validation when backend integration is introduced.

### Workbench backend module ownership

`apps/workbench/api/` owns HTTP application composition, routes, request boundaries and response projection. Implementations live in their feature directories beside `api`: `embedding`, `postgres`, `parsing`, `chunking`, `ingestion`, `configuration`, `retrieval` and `sources`. The independent `validator` continues to own constructor-only Haystack validation. Shared DTOs belong to `contracts/schemas.py`, persistence records and the existing port to `persistence/models.py`, and operational event logging to `observability/events.py`.

Follow the repository-wide module placement rule in [AGENTS.md](../AGENTS.md). Use direct imports from the implementation owner; do not retain compatibility modules, forwarding functions or facade re-exports. Keep tests and fixtures with their owning module; shared backend test support belongs to `apps/workbench/testing/`. See the [project map](PROJECT_MAP.md#2-workbench-source-ownership-and-reuse-index) before adding files.

## Workbench: React, TypeScript and Vite

**Current status:** `apps/workbench/web` defaults to an in-memory Preview. Opt-in Live mode discovers the API and executes only the approved Keyword search graph; Live document listing remains pending. The app uses React 19, TypeScript, Vite 8, React Flow, Vitest and Prettier. Preview displays fixtures for documents, processing runs, scores and retrieval results. Never claim that preview data represents actual embeddings, retrieval, index writes or model calls.

### Module ownership

- `src/domain/types.ts`: graph, pipeline, node, preview, settings and result types.
- `src/domain/catalog.ts`: node kinds, ports, parameters, defaults, `catalog`, `getDefinition`, `createNode`.
- `src/domain/graph.ts`: pipeline templates, DAG ordering, connection/graph validation, safe pipeline import/export. Prefer `createPipeline`, `validateConnection`, `validateGraph`, `topologicalNodeIds`, `importPipeline`, `exportPipeline`.
- `src/domain/fixtures.ts` and `preview.ts`: test/demo data and deterministic preview functions (`createPreviewRun`, `completePreviewNode`, `finishPreviewRun`).
- `src/hooks/useGraphHistory.ts`: graph edit history, undo/redo. `src/hooks/usePreview.ts`: cancellable simulated run progression.
- `src/api/`: shared runtime-validated RAG API DTOs and transport; constructor validation retains its separate protocol. `src/domain/backendDiscovery.ts` and `src/hooks/useBackendDiscovery.ts`: bounded discovery, generation cancellation, supported-profile checks and server-returned workspace selection.
- `src/domain/approvedExecution.ts` matches the exact keyword graph; `src/domain/liveSearch.ts` and `src/hooks/useLiveSearch.ts` own immutable server-provenance records, local interruption and request generations. Live renders server stages, never synthetic canvas-node outcomes; mixed session history is bounded to 100 entries.
- `src/components/SourceName.tsx` and `sourceFiles.ts` own the single filename link, bounded lookups and local reveal request. Demo values stay plain text; only the API resolves a registered original under its configured local root. See [local originals](docs/architecture/local-source-reveal.md). React Flow measurement updates remain runtime state: apply them without recording history or serializing dimensions.
- `src/components/`: pipeline editor, inspector, nodes, results; `src/views/`: Pipelines, Documents, Runs, Settings; `src/App.tsx`: app coordination and local shared state.
- `src/styles.css` and `src/views/views.css`: current styling. Reuse existing CSS variables and component patterns.

### Contracts and safety

- Preserve graph serialization versioning, DAG rules, type-compatible ports, duplicate-edge detection, required parameters, bounded import size, and denial of unsupported/executable fields. Imported JSON is untrusted.
- Ensure keyboard-accessible alternatives, visible focus, reduced-motion behavior and usable empty/error states.
- Keep preview status and fixture origin explicit. Don't add fake HTTP integrations or hide failure states.
- Prefer typed domain data over `any`; use clear names, isolated side effects and meaningful error handling. Do not create shadow copies of pipeline state in each view.
- Extend `src/domain/graph.test.ts` for graph/import/preview behavior; add focused tests elsewhere as needed.

### UI design-system decisions

The **checked-in** UI uses IBM Plex Sans and JetBrains Mono (imported in `src/main.tsx`), with colors defined in `src/styles.css`. A separately discussed Manrope + Deep Plum `#221331`, Electric Violet `#7540F5`, Acid Lime `#D6FA4A` design system is **not yet implemented in this branch**. Treat a shift to it as a deliberate migration: define semantic tokens first, replace hardcoded values methodically, review contrast and interaction states, update font assets/licenses, and run visual/interaction tests. Do not introduce a second competing token system or new task-coded colors.

### Checks (from `apps/workbench/web`)

```bash
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
```

For interaction changes follow `apps/workbench/web/README.md` and `scripts/browser-smoke.js`; do not claim a browser check passed if it was not run.

## Haystack Python

- Use Hatch and the repository configuration; avoid system-global `python`/`pip` for project runs. Existing commands include `hatch -e test run python SCRIPT.py`, `hatch run test:unit`, `hatch run test:integration`, `hatch run test:types`, `hatch run fmt`. Prefer focused test selections before full suites.
- Honor Haystack's established 3.0 API choices: tool execution through `Agent`, pipelines through `Pipeline.run()`/`Pipeline.run_async()`. Do not resurrect removed `ToolInvoker`, `AsyncPipeline`, or non-chat generators.
- Maintain explicit and compatible public signatures; avoid adding positional arguments before existing ones. Use Haystack serialization helpers (`component_to_dict`, `default_from_dict`) and keep tool/toolset data nested under `data`; preserve round-trip behavior.
- Initialize clients and load models in idempotent `warm_up()`, not constructors. Only add `run_async` for genuinely asynchronous work; share pure logic between sync and async implementations.
- Prefer existing pipeline, component, preprocessor, document-store and testing primitives. Preserve source/page/chunk metadata. Use document-store capability mixins from `haystack/testing/document_store.py` rather than replicating the whole test suite.
- Keep structured logging with Haystack's named `{placeholder}` templates and keyword args. Follow configured imports, `__all__` package export conventions, and typing; use `T | None` and explain unavoidable suppressions.
- Do not widen library deserialization allowlists. Use explicit `allowed_modules=` or the documented `HAYSTACK_DESERIALIZATION_ALLOWLIST` configuration where appropriate.
- Update docstrings, examples, packaging metadata and release notes as required by `CONTRIBUTING.md` and scoped agent instructions. Read the existing `AGENTS.md` in affected subdirectories.

## RAG and future backend integration

The [canonical RAG runtime contract](docs/architecture/rag-runtime-contract.md) owns PostgreSQL + pgvector storage, the metadata/version registry, planned TEI embeddings and approved execution profiles. The dated architecture plan preserves superseded OpenSearch/Ollama decisions as history. Workbench has a validation-only API/client and a separate [read-only lexical API](docs/architecture/postgres-lexical-search.md) using Haystack over persisted PostgreSQL records. Follow the [database runbook](docs/architecture/postgresql-foundation.md) for explicit migrations/seed; startup must not recreate tables or seed data. Native `postgres_ts_rank_cd` scores are not BM25, and no Live in-memory fallback is allowed. The frontend defaults to Preview and supports approved Live keyword execution; Live document listing and model workflows require subsequent tasks.

- Enforce workspace scope **on the server** for ingestion, retrieval, document metadata and results; client filters are never authorization.
- Use stable document identity + content/version fingerprints for delta detection. Reuse compatible vectors for unchanged chunks, stage changes, validate, then publish atomically with rollback/recovery. Make idempotency and interruption behavior testable.
- Preserve source provenance. Distinguish observed retrieval quality/latency/throughput from demonstration metrics. Plan structured logs, trace/correlation IDs, stage-level diagnostics, evaluation fixtures and failures.
- Do not invent environment variables, SQL schemas, model dimensions, endpoint names or guarantees from milestone codes. Source real names from working code and versioned interfaces.

## Verification and PR readiness

Describe acceptance criteria before implementation. Extend relevant success, negative and regression tests. Inspect typecheck, format, test, build and integration outcomes; mention unrun checks. Assess compatibility, security and migration impacts. Keep code comments for non-obvious rationale rather than paraphrasing each line. Explain introduced abstractions and existing functions reused.

## Authoritative validation boundary (2026-11-20)

`apps/workbench/validator/` owns the reviewed Python component/socket bindings and validation-only HTTP boundary. Workbench's Validate action uses Haystack; browser graph checks are limited to safe draft structure and explicitly scoped fixture-preview prerequisites. Keep those outcomes distinct from an authoritative verdict. The Vite development/preview proxy forwards constructor validation to port 8010 and versioned API discovery/search to port 8011. See the validator README for supported mappings and the Workbench README for startup. Persistence belongs to the separate PostgreSQL adapter; neither constructor validation nor storage readiness enables an HTTP retrieval profile.

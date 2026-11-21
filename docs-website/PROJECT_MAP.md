# Project Map — RAG Experiment

**Created:** 2026-11-20  
**Updated:** 2026-11-21
**Status:** Repository-verified navigation document; not a runtime architecture specification.  
**Evidence:** GitHub recursive tree `5e7086364f62d4f15b7370e55767a8f84ed4dc14` (12,946 files; complete tree), plus relevant source and README files, inspected on 2026-11-20.

> **Use this map to find an existing owner before editing code.** File presence is evidence of code or documentation, **not** evidence that a corresponding service is deployed or integrated. Recheck the tree and files at implementation time.

**Application update:** PostgreSQL lexical HTTP implementation and real runtime evidence were checked on 2026-11-21 against working-tree base `7f19f4560012a47b812dfabe8f4b1fc53aa384e9` and the scoped retrieval changes. See the canonical contract and retrieval task for execution evidence rather than the historical tree snapshot above.

## 1. Repository shape (verified)

```text
rag-experiment/
├── AGENTS.md                       # Existing Haystack-wide agent instructions
├── CONTRIBUTING.md                 # Contribution and release-note policies
├── README.md                       # Upstream Haystack overview, not an RAG deployment guide
├── SECURITY.md
├── pyproject.toml                   # Python package, dependencies, Hatch/tooling
├── .pre-commit-config.yaml
├── .github/                        # CI workflows, review templates, utilities
├── apps/
│   └── workbench/
│       ├── api/                     # PostgreSQL persistence and approved Haystack lexical HTTP profile
│       ├── validator/               # Independent constructor-only Haystack validation
│       └── web/                     # Standalone React/TypeScript pipeline Workbench
│           ├── README.md
│           ├── package.json
│           ├── package-lock.json
│           ├── tsconfig.json
│           ├── index.html
│           ├── public/
│           ├── scripts/browser-smoke.js
│           └── src/
│               ├── main.tsx
│               ├── App.tsx
│               ├── styles.css
│               ├── domain/
│               │   ├── catalog.ts
│               │   ├── fixtures.ts
│               │   ├── graph.ts
│               │   ├── graph.test.ts
│               │   ├── preview.ts
│               │   └── types.ts
│               ├── hooks/
│               │   ├── useGraphHistory.ts
│               │   └── usePreview.ts
│               ├── components/
│               │   ├── Inspector.tsx
│               │   ├── NodeIcon.tsx
│               │   ├── PipelineEditor.tsx
│               │   ├── PipelineNode.tsx
│               │   └── ResultsPanel.tsx
│               └── views/
│                   ├── DocumentsView.tsx
│                   ├── PipelinesView.tsx
│                   ├── RunsView.tsx
│                   ├── SettingsView.tsx
│                   └── views.css
├── haystack/                        # Haystack Python framework (library)
│   ├── components/                  # Agents, converters, preprocessors, embedders, ...
│   ├── core/                        # Pipeline, component, serialization primitives
│   ├── dataclasses/                 # Document, chat messages, answers, etc.
│   ├── document_stores/             # Protocols and in-memory document store
│   ├── hooks/                       # Agent hooks, compaction, budget, etc.
│   ├── testing/                     # Reusable library test helpers
│   ├── telemetry/
│   ├── tracing/
│   └── tools/
├── test/                            # Python library tests; scoped AGENTS.md
├── e2e/                             # Python pipeline-level tests and samples
├── examples/                        # Haystack example applications
├── docs-website/                    # Documentation site (large; versioned content)
│   ├── AGENTS.md
│   └── docs/
│       ├── AGENTS.md
│       └── tasks/
│           └── RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md
├── docker/                          # Haystack base image/build files
├── scripts/                         # Repository maintenance scripts
├── releasenotes/                    # Release notes and local agent instructions
├── pydoc/                           # Python API doc resources
└── images/                          # Repo assets
```

**Not present:** `docs/PROJECT_MAP.md`, `docs/ENGINEERING.md`, a standalone `backend/` or `services/` implementation. The navigation documents live in `docs-website/`. The UI discovery task adds the RAG client in `apps/workbench/web/src/api/`; the tree above preserves its earlier coarse inventory.

## 2. Workbench: source ownership and reuse index

| User story / concern | Existing owner | Reuse / inspect first |
| --- | --- | --- |
| Start local site, API, validator and PostgreSQL | `start.ps1` | Existing Compose/environment helper and service entry points; see `apps/workbench/api/README.md`; no automatic migration or seeding |
| Application navigation, local pipeline/run/settings state, imports/exports | `apps/workbench/web/src/App.tsx` | Existing state and UI event handlers; avoid duplicate stores |
| Node definitions, component labels, port schemas, defaults | `apps/workbench/web/src/domain/catalog.ts` | `catalog`, `createNode`, `getDefinition` |
| Graph templates and mutations, validation, cycle/port checks | `apps/workbench/web/src/domain/graph.ts` | `createPipeline`, `validateGraph`, `validateConnection`, `topologicalNodeIds` |
| Graph JSON security and compatibility | `apps/workbench/web/src/domain/graph.ts` | `importPipeline`, `exportPipeline`; preserve input restrictions |
| Shared UI types and view models | `apps/workbench/web/src/domain/types.ts` | `Graph`, `Pipeline`, `WorkbenchNode`, `PreviewRun`, `WorkbenchSettings` |
| Demo documents, runs and default settings | `apps/workbench/web/src/domain/fixtures.ts` | Existing fixture exports; distinguish mock vs real data |
| Deterministic fake execution and sample passages | `apps/workbench/web/src/domain/preview.ts` | `createPreviewRun`, `completePreviewNode`, `finishPreviewRun` |
| Undo/redo and graph change history | `apps/workbench/web/src/hooks/useGraphHistory.ts` | `useGraphHistory` |
| Preview sequencing, cancellation and run state | `apps/workbench/web/src/hooks/usePreview.ts` | `usePreview`; **not** a backend executor |
| RAG HTTP contract, decoding and discovery transport | `apps/workbench/web/src/api/` | `createWorkbenchApiClient`; discovery GET methods and a strict four-field search POST |
| Preview/Live connection state and authorized workspace | `apps/workbench/web/src/domain/backendDiscovery.ts`, `apps/workbench/web/src/hooks/useBackendDiscovery.ts` | Cancellable generations, readiness/profile consistency and bounded workspace pagination |
| Approved graph matching and Live session lifecycle | `apps/workbench/web/src/domain/approvedExecution.ts`, `apps/workbench/web/src/domain/liveSearch.ts`, `apps/workbench/web/src/hooks/useLiveSearch.ts` | Exact keyword topology, immutable submitted graph, cancellation generations and mixed history bound to 100 entries |
| Click registered source name in Explorer | `apps/workbench/web/src/components/SourceName.tsx`, `apps/workbench/api/local_sources.py`, `apps/workbench/api/source_registration.py` | Reuse version metadata/RLS; explicit registration, safe metadata GET and Origin-protected native reveal; demo remains plain text |
| Graph canvas, edges and nodes | `apps/workbench/web/src/components/PipelineEditor.tsx`, `PipelineNode.tsx`, `NodeIcon.tsx` | Extend editor components; use `@xyflow/react` contracts |
| Component configuration | `apps/workbench/web/src/components/Inspector.tsx` | Existing inspector |
| Execution details and retrieval output | `apps/workbench/web/src/components/ResultsPanel.tsx` | Existing panel and model |
| Pages for pipelines, documents, runs and settings | `apps/workbench/web/src/views/*View.tsx` | Extend the specific page |
| Global style variables and typography | `apps/workbench/web/src/styles.css`, `src/views/views.css`, `src/main.tsx` | Current CSS variables, font imports and accessible state patterns |
| UI regression / browser smoke | `apps/workbench/web/src/domain/graph.test.ts`, `scripts/browser-smoke.js` | Extend tests for the changed contract |

### Workbench execution/data flow **today**

```text
main.tsx → App.tsx
                ├─ domain/catalog.ts + domain/types.ts
                ├─ domain/graph.ts → validation, templates, import/export
                ├─ hooks/useGraphHistory.ts → in-memory editor history
                ├─ hooks/usePreview.ts → domain/preview.ts → fixture-based runs
                ├─ domain/fixtures.ts → demo documents and seeded runs
                ├─ components/* → visual editor and inspector
                └─ views/* → pipelines, documents, runs, settings

useBackendDiscovery → api/client.ts → /api/v1 health/capabilities/workspaces
matchApprovedKeywordGraph → useLiveSearch → apiClient.search → PostgreSQL lexical profile
Separate: useValidation → /api/pipelines/validate.
```

### Verified Workbench boundaries

- Frontend stack: React, TypeScript, Vite, Vitest, Prettier, `@xyflow/react`, lucide-react. Confirm exact versions from `apps/workbench/web/package.json` before upgrading.
- Preview mode simulates results and errors. Running a pipeline does **not** call actual embeddings, retrieval, inference, database writes or a document parser. The separate approved Keyword search graph performs Live lexical retrieval; Hybrid/indexing graphs remain Preview.
- Current typography imports **IBM Plex Sans** and **JetBrains Mono** from Fontsource (`src/main.tsx`); CSS theme lives in `src/styles.css`. A Manrope/Plum/Electric redesign is a separate proposed change, not implemented here.
- Editor validation is **not** authoritative runtime/backend validation. Backend must independently enforce authorization and input constraints.

## 3. Haystack Python framework: where to look

| Concern | Source / existing building blocks | Boundary reminder |
| --- | --- | --- |
| Component API and sockets | `haystack/core/component/` | Build on existing `@component` contracts |
| Pipeline DAG, execution and component checks | `haystack/core/pipeline/` | Prefer `Pipeline.run()` / `Pipeline.run_async()` over a parallel executor |
| Serialization and deserialization safety | `haystack/core/serialization.py`, `haystack/core/serialization_security.py` | Do not loosen allowlists to accommodate user JSON |
| Document / answer / message models | `haystack/dataclasses/` | Keep source and page metadata |
| Agent orchestration | `haystack/components/agents/` | Reuse `Agent` and tools; do not recreate removed APIs |
| Document conversion and preprocessing | `haystack/components/converters/`, `haystack/components/preprocessors/` | Inspect existing converters/splitters before custom parsers |
| Embedding components | `haystack/components/embedders/` | Distinguish reusable framework components from configured TEI deployment |
| Retrieval / ranking / join | `haystack/components/retrievers/`, `rankers/`, `joiners/` | Evaluate existing behavior before implementing custom search glue |
| Writers and document stores | `haystack/components/writers/`, `haystack/document_stores/types/`, `in_memory/` | This checkout does **not** include a local PostgreSQL store implementation in `haystack/document_stores/` |
| Hooks and tool interfaces | `haystack/hooks/`, `haystack/tools/` | Reuse existing interfaces; no speculative provider-specific core |
| Logging / tracing / telemetry | `haystack/logging.py`, `haystack/tracing/`, `haystack/telemetry/` | Inspect supported hooks for observability integration |
| Shared document-store testing | `haystack/testing/document_store.py` | Prefer existing test mixins |

**Important:** PostgreSQL/pgvector, Qdrant, TEI and Langfuse appear in **documentation pages** under `docs-website/`, including integration references. Those pages do **not** establish that corresponding services or adapters are installed and running in this application. Verify dependencies and deployment separately.

## 4. Documentation, tests and development entry points

| What | Location | Action |
| --- | --- | --- |
| Existing repo-wide AI-agent guidance | `AGENTS.md` | Read first; already contains Haystack-specific compatibility rules |
| Scope-specific agent guidance | `docs-website/AGENTS.md`, `docs-website/docs/AGENTS.md`, `haystack/hooks/compaction/AGENTS.md`, `releasenotes/notes/AGENTS.md`, `test/AGENTS.md` | Apply closest instructions |
| Frontend overview, commands and limitations | `apps/workbench/web/README.md` | Run `npm ci` (if needed), then `npm run typecheck`, `npm run format:check`, `npm test`, `npm run build` |
| Frontend smoke | `apps/workbench/web/scripts/browser-smoke.js` | Use README's documented Playwright CLI scenario |
| Python tooling and dependencies | `pyproject.toml` | Use Hatch for Python tests/tooling, following root instructions |
| Python tests | `test/` and `e2e/` | Prefer focused suite before complete execution |
| CI and checks | `.github/workflows/`, `.pre-commit-config.yaml` | Inspect actual configured checks |
| Backend planning reference | `docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md` | Plan, **not evidence of implementation** |
| General contribution guide | `CONTRIBUTING.md` | Release notes, review conventions |

## 5. Planned RAG capabilities vs checked-in implementation

| Capability | Verified status in this checkout | Guidance |
| --- | --- | --- |
| Local pipeline editor + validation | Implemented in Workbench | Reuse `domain/graph.ts` |
| Local simulated runs and document lists | Implemented as demo fixtures | Do not present as production metrics |
| API liveness/readiness/capability discovery | Implemented; qualified `postgres-fts-baseline` is advertised only while storage/corpus/pipeline are ready | Use the Hatch environment and [API runbook](../apps/workbench/api/README.md) |
| Read-only lexical execution API | Implemented workspace/document/search routes over the existing PostgreSQL adapter and Haystack pipeline | Follow the [lexical guide](docs/architecture/postgres-lexical-search.md); approved Keyword search UI is connected; arbitrary graph execution remains unsupported |
| Workspace registry / storage scope | Implemented PostgreSQL composite FKs and forced RLS; single development resolver only | Production authentication/authorization remains future work |
| Registered local originals | Version metadata registration and filename-only Live link implemented for same-machine interactive Windows | See [local originals](docs/architecture/local-source-reveal.md); no ingestion or demo originals are invented |
| Chunk persistence / publication | Implemented app-owned PostgreSQL adapter and transactional source version publication | Ingestion and delta-detection workflows remain separate |
| PostgreSQL + pgvector | Dedicated Docker service, Alembic migrations, explicit seed and nullable synthetic-vector storage implemented | Follow the [PostgreSQL runbook](docs/architecture/postgresql-foundation.md); real TEI integration remains planned |
| PostgreSQL lexical retrieval | Implemented SQL primitive and HTTP profile with `simple`, GIN and `postgres_ts_rank_cd` | Native FTS is not BM25; real semantic/hybrid retrieval remains separate |
| BM25 + vector hybrid retrieval + RRF backend | UI template and simulation exist; **backend not verified** | Separate mock graph from real search |
| Observability / evaluation pipeline for this RAG app | Framework functionality exists; app-level integration **not verified** | Define trace and evaluation evidence |
| Answer generation | Planned; Workbench does not infer | Do not claim LLM responses are live |

The [canonical RAG runtime contract](docs/architecture/rag-runtime-contract.md) resolves storage, registry, TEI and first-slice BM25 choices; the dated plan preserves earlier decisions as history. This map does not turn an implementation decision into a verified runtime dependency.

## 6. Where new work belongs (decision guide)

1. **Find the owner** using the table above; search usages and tests. Reuse before creating classes, helpers or services. Keep ticket/milestone identifiers in planning metadata, **not** code symbols, API fields or CSS names.
2. **Graph behavior:** extend the domain's catalog, types and graph functions; add focused `graph.test.ts` cases. Keep React and simulated preview separate.
3. **Real integration:** first define provider-neutral API contracts, workspace policy and model/store capabilities; then implement adapters at boundaries. Do not import provider SDKs into domain/application policy. Place new files only after agreeing on actual directory ownership.
4. **UI:** extend existing components/views/hooks; preserve validation, accessibility and semantic styling. A global theme/font migration requires its own explicit scope.
5. **Documentation-only updates:** keep changes in Markdown and update this map when source paths change.
6. **Repository-changing work:** first create/update a complete A–O task specification per the project's task instructions; document observed source evidence, contracts, tests, security and acceptance criteria. Include **Created** and **Updated** in each task. Do not embed Git branch names in task specifications.
7. **Before completion:** run focused checks and report the actual commands and results; never infer passing tests from code inspection.

## 7. Maintainability rules for this map

- Keep it a **router**, not a full architecture textbook; link to source and the actual task/contract document for detail.
- Update **Updated** and the inspected Git tree/commit when refreshing.
- If a target file does not exist, say so explicitly. Do not provide dead internal Markdown links or manufacture future module paths.
- Distinguish **implemented**, **fixture-only**, **documented**, **planned**, and **verified running**.
- When new runtime services are introduced, add their real directories, configuration entry points, migration owner, interfaces, observability, tests and startup commands.

## Validation-only boundary (2026-11-20 implementation update)

The standalone editor now has an optional local authoritative validation boundary under `apps/workbench/validator/`. See [its mapping and contract](../apps/workbench/validator/README.md) and [the Workbench startup guide](../apps/workbench/web/README.md). This update supersedes the earlier statements that the application has no API client at all: the only client is for validation, not RAG execution or storage.

- Graph import/export and fixture-only preview remain owned by the web domain. Their checks do not establish Haystack compatibility.
- The Python allowlist constructs fresh real Haystack components and uses public Pipeline APIs; unsupported UI concepts are reported explicitly.
- No ingestion, embeddings, inference, retrieval, persistence, or authorization backend is introduced.
- `tasks/TASK-VAL-001-haystack-backed-pipeline-validation.md` records scope and acceptance evidence.

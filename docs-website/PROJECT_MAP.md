# Project Map — RAG Experiment

**Created:** 2026-11-20  
**Updated:** 2026-11-27
**Status:** Repository-verified navigation document; not a runtime architecture specification.  
**Evidence:** GitHub recursive tree `5e7086364f62d4f15b7370e55767a8f84ed4dc14` (12,946 files; complete tree), plus relevant source and README files, inspected on 2026-11-20.

> **Use this map to find an existing owner before editing code.** File presence is evidence of code or documentation, **not** evidence that a corresponding service is deployed or integrated. Recheck the tree and files at implementation time.

**Application update:** PostgreSQL lexical HTTP implementation and real runtime evidence were checked on 2026-11-21 against working-tree base `7f19f4560012a47b812dfabe8f4b1fc53aa384e9` and the scoped retrieval changes. See the canonical contract and retrieval task for execution evidence rather than the historical tree snapshot above.

**Parser update:** internal parser/format boundaries were inspected against base `81e17e404014ed054736826868c775e4800f8fd3` on 2026-11-21. See the [format matrix and handoff](docs/architecture/content-aware-chunking-strategy.md) and [parser task](../tasks/completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md). Internal qualification does not enable HTTP upload, chunking or ingestion.

**Chunking update:** internal token policy work was inspected against base `deb9fb63dde97f68db6dd856d1fc2a13a2af2255` on 2026-11-22. [CHUNK-001](../tasks/completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) owns the `prepare_chunks(...)` seam, truthful 500/50 `tiktoken:o200k_base` sizing, EN/RU sentence resources and explicit Ukrainian token fallback. Only `en`/`ru`/`uk` hints are accepted; other languages are deferred/refused. The separate [durable ingestion workflow](docs/architecture/durable-text-ingestion.md) now consumes this seam using an explicit locale-unqualified structural profile; local same-volume migration/upload/search/API-and-database-restart gates passed; final independent artifact audit passed. Internal chunk preparation alone grants no public capability.

**Live acceptance update:** [EVAL-001](../tasks/completed/TASK-EVAL-001-prove-vertical-slice.md) completed on 2026-11-22 against the same base plus recorded working-tree/build hashes. Its [report](docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) records 39 canonical browser/HTTP/SQL parity cases, stable 8-source/8-chunk same-volume recovery and separate real/mock faults. The ten exact cases hit 10/10 in each phase; the three lexical paraphrase misses remain explicit. This qualifies local synthetic acceptance, not production/remote semantic performance.

**Configuration update:** [CONFIG-001](../tasks/completed/TASK-CONFIG-001-document-splitting-and-default-language.md) owns strict external document-processing settings and their mapping to the existing splitter/native-counter seams. See the [operator reference](docs/architecture/document-processing-configuration.md). Implementation, offline/native-counter and local live/restart gates passed; 854 backend tests passed with zero skips. Prior metrics remain historical, with the [overwritten stability artifact limitation](docs/architecture/document-processing-configuration.md#test-artifact-isolation-and-historical-limitation) explicitly recorded.

## 1. Repository shape (verified)

**Standalone agent runtime (2026-11-27):** `apps/maf/` owns the independent Microsoft Agent Framework package, versioned JSON CLI and direct OpenAI Responses adapter. The synthetic smoke passed against `gpt-6.1-sol` through `semantic-review`. The Semantic Judge registers four typed modes and validates exact evidence locally. The evaluation caller owns source preparation, dataset scoring and artifacts. [Standalone runbook](../apps/maf/README.md) · [Semantic Judge contract](../apps/maf/SEMANTIC_JUDGE.md) · [Qualification status](../tasks/maf/TASK-MAF-002-semantic-judge-agent.md)

**Standalone reranker deployment (2026-11-26):** `apps/workbench/reranking/compose.yaml`, `start.ps1` and `README.md` own the local Qwen3-Reranker-0.6B vLLM service on loopback 8083. Root `start.ps1` starts stopped/missing containers and reuses running processes. See [deployment scope and checks](../tasks/TASK-OPS-002-local-reranker-container.md). No application adapter, database migration, executable reranking profile or quality qualification follows from starting this service.

**Live Dense update (2026-11-24):** `retrieval/dense.py` composes qualified query embedding and exact PostgreSQL retrieval over migration `0005`'s durable vectors. The [operator guide](docs/architecture/live-dense-search.md) describes the explicit measured-runtime launcher, immutable dense profile and capability gate. Source/profile/model/coverage fences remain server-owned; ordinary startup remains lexical. Actual SQL/HTTP/browser evidence is tracked in [DENSE-001](../tasks/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md). ANN and generated answers remain separate.

**Embedding qualification update (2026-11-23):** [EMBED-001](../tasks/TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md) adds the internal model-neutral embedding boundary, local TEI adapter and bounded shared qualification admission owner. The [operator guide](docs/architecture/local-embedding-provider.md) separates local model qualification from production TPM, durable vector ingestion and executable retrieval profiles. No new database migration or semantic HTTP capability follows from the provider boundary; see its evidence for actual live gate status.

**Dedicated deployment follow-up (2026-11-24):** the project target is its own `rag-workbench-embedding-1` TEI service on loopback `8082`. Its [startup and inference record](../tasks/evidence/embedding-2026-11-23/dedicated-report.md) is separate from the original shared-service `8081` evidence. The container still shares the physical GPU; this deployment record establishes no production TPM denominator. Current measured admission is tracked under EMBED-002 below.

**Durable embedding update (2026-11-24):** completed [EMBED-002](../tasks/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) adds migration 0005, leased work and generation-fenced tenant-local vectors. The [operator/quality guide](docs/architecture/durable-embedding-ingestion.md) distinguishes complete internal coverage, measured single-owner admission and exact diagnostics from executable Dense HTTP. Actual backfill/restarts/upload/reuse and fixed EN/RU/UK/code/source-provenance gates pass without a model judge. The ten-minute run passes its predeclared steady-window rule (median 92.141081157%, zero hard breaches); whole-run 91.992753788% remains explicitly below exact 92%. Broader TPM-001 and production truth/authorization remain separate.

**Generation update (2026-11-23):** inspected working-tree base `44866bb7e7dc01993bbaefefdec1ab1985951cc7`. [Persisted corpus generations](docs/architecture/persisted-index-generations.md) now establish lexical snapshots from a workspace manifest; publication and terminal jobs commit generations atomically. [INDEX-001](../tasks/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md) links real disposable PostgreSQL, 100k synthetic metadata and isolated restart evidence. Semantic coverage and ANN remain separate qualification work.

**PDF update (2026-11-23):** [CHUNK-003](../tasks/TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) is **PARTIALLY COMPLETE: Gate A COMPLETE, Gate B PENDING CONTENT-001**. The bounded text-layer subset uses the existing parser registry, shared resolver/PreparedChunk and durable PostgreSQL upload/jobs. The offline Docling worker, quota sandbox, pinned manifest and HybridChunker adapter remain the owners. Conditional `pdf_ingestion` capability discloses absent OCR, original evidence and visual understanding; pictures remain unprocessed geometry. The [initial qualification](docs/tasks/pdf-layout-qualification-2026-11-23.md) and [r2 follow-up](docs/tasks/pdf-two-column-numeric-integrity-2026-11-23.md) record actual public-PDF/live/restart proof, all 11 current extraction cases, 25 scored queries and successful numeric completeness. Gate B requires CONTENT-001's actual assets/representations; OCR and visual semantics are separate successors.

**Configuration editor update:** `App.tsx` owns the wrench entry below Runs; `ConfigurationView.tsx`, `YamlEditor.tsx` and `ConfirmationDialog.tsx` own the lazy editing surface and unsaved-change lifecycle. Existing client/DTOs add direct local configuration requests. `configuration/configuration.py` persists the selected YAML with atomic CAS/backups; `api/configuration_http.py` reuses the local trusted-origin boundary and a non-secret request-intent header. Operator login, keys and the Application-wide badge were removed at the user's explicit request. Configuration parsing remains owned by `configuration/document_processing.py`. See the [operator guide](docs/architecture/document-processing-configuration.md#edit-configuration-in-workbench) and [UI verification record](../tasks/completed/TASK-UI-CONFIG-001-yaml-configuration-editor.md).

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
│   ├── maf/                        # Independent Python agent runtime and JSON CLI
│   └── workbench/
│       ├── api/                     # HTTP composition, routes, boundaries and response projection
│       ├── embedding/               # Embedding domain, TEI adapter, admission, worker and deployment
│       ├── postgres/                # SQL adapter, migrations, seed and database deployment
│       ├── parsing/                 # Source inspection, format registry, AST annotations; pdf/ worker
│       ├── chunking/                # Chunk policy, splitters, provenance; pdf/ preparation
│       ├── ingestion/               # Durable ingestion orchestration and upload policy
│       ├── configuration/           # Application/document-processing settings and YAML editing
│       ├── retrieval/               # Lexical execution and approved versioned profile policies
│       ├── sources/                 # Registered originals, local reveal and registration CLI
│       ├── persistence/             # Shared records and existing persistence protocol
│       ├── contracts/               # Shared validated DTO implementations
│       ├── observability/           # Sanitized operational event logging
│       ├── testing/                 # Shared backend test support
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

**Not present:** `docs/PROJECT_MAP.md`, `docs/ENGINEERING.md`, a standalone `backend/` or `services/` implementation. The navigation documents live in `docs-website/`. The RAG client lives in `apps/workbench/web/src/api/`.

## 2. Workbench: source ownership and reuse index

### Backend module directories

All directories below are under `apps/workbench/`. Import implementations directly from their owner; removed `api.*` implementation paths have no compatibility facade or forwarding file. HTTP paths, response shapes and named Hatch operator commands retain their existing contracts.

| Module | Implementation owner |
| --- | --- |
| `api/` | `application.py`, HTTP route modules, `boundary.py`, `database_dependency.py`, `projection.py`, `upload_transport.py`, listener entry point and OpenAPI schema |
| `embedding/` | `embedding*.py`, `model_token_counter.py`, embedding fixtures, TEI Compose/startup files |
| `postgres/` | `postgres*.py`, `db_*.py`, all Alembic/SQL migrations, development seed fixture and PostgreSQL Compose/environment helpers |
| `parsing/` | `parsing.py`, `parsing_adapters.py`, `parser_registry.py`, Python AST annotations in `python_code.py`; `pdf/` owns parser models, worker, sandbox, assets and manifest |
| `chunking/` | `chunking.py`, adapters and profiles, Python splitting in `python_code.py`; `pdf/` owns PDF splitting and chunk preparation |
| `ingestion/` | `ingestion.py`, `upload_policy.py` and durable ingestion orchestration |
| `configuration/` | `config.py`, `configuration.py`, `document_processing.py`; selected operator YAML files remain at the Workbench root |
| `retrieval/` | `lexical.py`, `profile_registry.py`, `profiles.py`, `services.py` and lexical evaluation fixture |
| `sources/` | `local_sources.py`, `source_registration.py` |
| `persistence/` | `models.py`: existing records, errors and persistence protocol |
| `contracts/` | `schemas.py`: existing validated DTO implementations |
| `observability/` | `events.py`: existing sanitized `log_event` implementation |
| `validator/` | Independent constructor-only validation, reviewed component registry and HTTP process |

Tests and fixtures live with their module; cross-module HTTP acceptance stays in `api/tests/`, while shared test support lives in `testing/`. `apps/workbench/__init__.py` disables Haystack telemetry and content tracing before any direct module import; package initializers do not re-export implementation facades.

| User story / concern | Existing owner | Reuse / inspect first |
| --- | --- | --- |
| Start local site, API, validator and PostgreSQL | `start.ps1` | Existing Compose/environment helper and service entry points; see `apps/workbench/api/README.md`; no automatic migration or seeding |
| Qualify local query/document embeddings | `apps/workbench/embedding/embedding.py`, `embedding_adapters.py`, `embedding_dispatch.py`, `embedding_config.py`; `scripts/workbench_embedding_qualify.py` | Immutable neutral requests/profile, existing exact native counter, default-disabled `apps/workbench/embedding_profiles.yaml`, explicit runtime verifier and one exclusive bounded qualification owner; no executable semantic HTTP profile |
| Execute qualified Live Dense | `apps/workbench/retrieval/dense.py`, `api/application.py`, `api/projection.py`; `scripts/workbench_dense_serve.py`, `workbench_dense_evaluate.py` | Fixed Haystack query embedding/exact SQL composition; reuse durable vectors, current generation, native tokenizer and one measured admission owner; profile/coverage/model availability gates capability |
| Start/reuse the dedicated Workbench TEI process | Root `start.ps1`, `apps/workbench/embedding/compose.yaml`, `apps/workbench/embedding/start.ps1` | Running containers stay untouched; stopped/missing model loads in background. Ignored local `.env` persists first-time source location; project endpoint 8082 and pinned project ownership |
| Provision/verify Linux model-asset cache | `scripts/workbench_embedding_cache.py`, `scripts/workbench_embedding_qualify.py` | Nine approved source assets, project-owned read-only runtime volume, atomic verified revision publication; measured startup/qualification in the separate optimization record; no model conversion or download |
| Durable embedding jobs and complete generation coverage | `apps/workbench/embedding/embedding_jobs.py`, `embedding_ingestion.py`, `apps/workbench/postgres/postgres_embeddings.py`; migration 0005 | Existing lexical publisher remains intact; immutable input/profile/processing keys, leased cursor and active-source fences; no inference inside write transactions |
| Measured shared embedding admission | `apps/workbench/embedding/embedding_capacity.py`; `scripts/workbench_embedding_capacity_benchmark.py`, `workbench_embedding_backfill.py` | One measured expiring deployment owner for query/document traffic; actual 0.92/0.95 proof depends on live evidence, not configuration |
| Objective original-source retrieval evaluation | `scripts/workbench_embedding_evaluate.py`, `apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json` | Fixed graded relevance, actual persisted exact cosine, source/version/tenant/hash/generation audits; no answer generator or LLM judge |
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
| Click registered source name in Explorer | `apps/workbench/web/src/components/SourceName.tsx`, `apps/workbench/sources/local_sources.py`, `apps/workbench/sources/source_registration.py` | Reuse version metadata/RLS; explicit registration, safe metadata GET and Origin-protected native reveal; demo remains plain text |
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
- Preview mode simulates results and errors. A Preview run does **not** call actual embeddings, retrieval, inference, database writes or a document parser. Approved Live Keyword and qualified Dense graphs use their server profiles; Hybrid/indexing graphs remain Preview.
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
| Standalone agent runtime and tests | [MAF runbook](../apps/maf/README.md) | Run `hatch run check`, `hatch run test`, and `hatch run types` from `apps/maf/`. Live smoke requires explicit opt-in |
| Python tests | `test/` and `e2e/` | Prefer focused suite before complete execution |
| CI and checks | `.github/workflows/`, `.pre-commit-config.yaml` | Inspect actual configured checks |
| Backend planning reference | `docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md` | Plan, **not evidence of implementation** |
| Live lexical browser acceptance | [EVAL-001 task](../tasks/completed/TASK-EVAL-001-prove-vertical-slice.md), [dated report/runbook](docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) | Canonical 10+3 labels, actual UI/HTTP/SQL parity and same-volume restarts; new execution evidence under `tasks/evidence/eval-vertical-2026-11-22/` |
| General contribution guide | `CONTRIBUTING.md` | Release notes, review conventions |

## 5. Planned RAG capabilities vs checked-in implementation

| Capability | Verified status in this checkout | Guidance |
| --- | --- | --- |
| Local pipeline editor + validation | Implemented in Workbench | Reuse `domain/graph.ts` |
| Local simulated runs and document lists | Implemented as demo fixtures | Do not present as production metrics |
| Live Documents UI | Implemented over existing persisted list/detail/chunks/upload/jobs; TXT/Markdown/Python and runtime-qualified text-layer PDF; actual browser/HTTP/SQL and same-volume restart acceptance passed | [UI-003 task and evidence](../tasks/TASK-UI-003-live-document-management.md); shared client and `useLiveDocuments`; original binary evidence remains separate |
| API liveness/readiness/capability discovery | Implemented; qualified `postgres-fts-baseline` is advertised only while storage/corpus/pipeline are ready | Use the Hatch environment and [API runbook](../apps/workbench/api/README.md) |
| Read-only lexical execution API | Implemented workspace/document/search routes over the existing PostgreSQL adapter and Haystack pipeline | Follow the [lexical guide](docs/architecture/postgres-lexical-search.md); approved Keyword search UI is connected; arbitrary graph execution remains unsupported |
| Workspace registry / storage scope | Implemented PostgreSQL composite FKs and forced RLS; single development resolver only | Production authentication/authorization remains future work |
| Registered local originals | Version metadata registration and filename-only Live link implemented for same-machine interactive Windows | See [local originals](docs/architecture/local-source-reveal.md); no ingestion or demo originals are invented |
| Internal format inspection and parser registry | Bounded byte-only TXT/Markdown adapters, immutable typed elements and planned-format refusals | `apps/workbench/parsing/parsing.py` and `parser_registry.py`; [format matrix](docs/architecture/content-aware-chunking-strategy.md); no public upload/format capability |
| Internal chunk preparation | Versioned prose-token and Python AST policies with bounded Haystack orchestration; prose EN/RU/UK with 500/50 tiktoken defaults, EN/RU sentences and explicit UK/resource fallback; `.py` uses fixed effective-line grouping | `apps/workbench/chunking/chunking.py`, `chunking_profiles.py`, `python_code.py` and reviewed adapters; [policy decision](docs/architecture/content-aware-chunking-strategy.md#token-budgeted-chunking-policy); preparation itself has no SQL writes or served-model parity claim |
| Chunk persistence / publication | Implemented PostgreSQL writer reused by atomic ingestion version/job publication | `postgres/postgres.py`, `postgres/postgres_ingestion.py`; delta detection remains separate |
| Document-processing settings | Strict selected YAML/env precedence, required EN(default)/RU sentences and independent native guard; local runtime/854-test acceptance passed | `apps/workbench/configuration/document_processing.py`, `config.py`, `apps/workbench/document_processing.yaml`; [operator reference](docs/architecture/document-processing-configuration.md); no request/workspace override |
| Durable TXT/Markdown ingestion | Implemented synchronous multipart transport, parser/chunker orchestration, idempotent fenced jobs and additive migration 0002; local same-volume migration/upload/search/restart gates passed; final independent artifact audit passed | `ingestion/ingestion.py`, `ingestion/upload_policy.py`, `api/ingestion_http.py`, `api/upload_transport.py`, `postgres/postgres_ingestion.py`; [runbook](docs/architecture/durable-text-ingestion.md); connected Live Documents UI reuses these routes |
| PostgreSQL + pgvector | Dedicated Docker service, explicit migrations/seed and durable tenant-local real Qwen vector mappings implemented | Follow the [PostgreSQL runbook](docs/architecture/postgresql-foundation.md) and [Live Dense guide](docs/architecture/live-dense-search.md); no ANN index |
| PostgreSQL lexical retrieval | Implemented SQL primitive and HTTP profile with `simple`, GIN and `postgres_ts_rank_cd` | Native FTS is not BM25; real semantic/hybrid retrieval remains separate |
| Persisted corpus/index generations and reconciliation | Implemented lexical-only workspace manifest, per-source contributions and immutable ledger in additive `0003`; constant metadata qualification, explicit legacy rollback and operator repair | [`postgres_indexes.py`](../apps/workbench/postgres/postgres_indexes.py), [`0003`](../apps/workbench/postgres/migrations/0003_index_generations.up.sql), [`PostgresPersistence.current_index_generation()` / `corpus_summary()`](../apps/workbench/postgres/postgres.py); [operations and evidence](docs/architecture/persisted-index-generations.md). Future dense/ANN must bind their own qualified model/coverage to this source generation; the current manifest does not enable them |
| Approved versioned retrieval profiles | Immutable provider-neutral definitions, workspace rollout/audit state in additive `0004`, live revision/SQL fences and a client selector; qualified FTS and explicitly composed exact dense qualify | [`profile_registry.py`](../apps/workbench/retrieval/profile_registry.py), [`postgres_profiles.py`](../apps/workbench/postgres/postgres_profiles.py), [`profiles.py`](../apps/workbench/retrieval/profiles.py); [profile operations](docs/architecture/profile-registry.md) and [Dense operations](docs/architecture/live-dense-search.md). Stored definitions do not activate absent runtimes |
| BM25 + vector hybrid retrieval + RRF backend | UI template and simulation exist; **backend not verified** | Separate mock graph from real search |
| Observability / evaluation pipeline for this RAG app | Framework functionality exists; app-level integration **not verified** | Define trace and evaluation evidence |
| Answer generation | Planned; Workbench does not infer | Do not claim LLM responses are live |

The [canonical RAG runtime contract](docs/architecture/rag-runtime-contract.md) resolves storage, registry, TEI and first-slice BM25 choices; the dated plan preserves earlier decisions as history. This map does not turn an implementation decision into a verified runtime dependency.

## 6. Where new work belongs (decision guide)

1. **Find the owner** using the table above; search usages and tests. Reuse before creating classes, helpers or services. Keep ticket/milestone identifiers in planning metadata, **not** code symbols, API fields or CSS names.
2. **Graph behavior:** extend the domain's catalog, types and graph functions; add focused `graph.test.ts` cases. Keep React and simulated preview separate.
3. **Real integration:** first define provider-neutral API contracts, workspace policy and model/store capabilities; then implement adapters at boundaries. Do not import provider SDKs into domain/application policy. Place new files only after agreeing on actual directory ownership.
4. **Agent execution:** register agents in the standalone MAF application and use its versioned invocation contract. MAF owns provider configuration and credentials. A RAG evaluator owns its transport adapter and evaluation policy.
5. **UI:** extend existing components/views/hooks; preserve validation, accessibility and semantic styling. A global theme/font migration requires its own explicit scope.
6. **Documentation-only updates:** keep changes in Markdown and update this map when source paths change.
7. **Repository-changing work:** first create/update a complete A–O task specification per the project's task instructions; document observed source evidence, contracts, tests, security and acceptance criteria. Include **Created** and **Updated** in each task. Do not embed Git branch names in task specifications.
8. **Before completion:** run focused checks and report the actual commands and results; never infer passing tests from code inspection.

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

### Python code ingestion qualification

[TASK-RAG-CHUNK-002](../tasks/completed/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md) extends the existing document upload workflow for `.py`. `parsing/python_code.py` owns bounded declaration annotations; `chunking/python_code.py` owns the lossless adapter to the existing Haystack `PythonCodeSplitter` / line `DocumentSplitter`. `parsing/parser_registry.py` owns the exact MIME allowlist, `chunking/chunking.py` owns policy selection and common native admission, and `ingestion/ingestion.py` retains the only publication workflow. See the [AST policy](docs/architecture/content-aware-chunking-strategy.md#python-ast-ingestion). Running-server qualification ingested real project source, checked SQL/line/Qwen parity and restart/replay, and displayed real Live results; synthetic retrieval comparison is recorded separately.

# Haystack Workbench · UI-01

A pipeline editor with an optional, validation-only Haystack service. All documents, runs, scores, and processing reports remain demonstration fixtures. Editing, JSON import/export and Preview run offline; authoritative Validate requires the local Python service. No database, model or credentials are needed.

An independent [Workbench API](../api/README.md) provides PostgreSQL lexical retrieval through Haystack. The UI connects to its read-only discovery endpoints in **Live** mode. Live search execution and document listing are not connected yet; Run remains available only in Preview.

## Start

Requires Node.js 22.12 or later and npm. From the repository root:

```powershell
cd apps/workbench/web
npm ci
npm run dev
```

Open the local URL printed by Vite (normally http://127.0.0.1:5173). The server binds to loopback only. Package installation needs network access; the running application, including its bundled fonts, does not.

```powershell
npm run typecheck
npm run format:check
npm test
npm run build
npm run preview
```

`build` creates the independent static application in `dist`. `preview` serves that build locally. It is not a backend service.

### Optional application lexical API

After explicit PostgreSQL setup/migration/seed, load `. ./apps/workbench/postgres/use-dev-env.ps1` from the repository root and launch `hatch run workbench-api:serve`. It listens on `127.0.0.1:8011`, independently of the constructor validator on port 8010. Qualified schema/index/corpus/pipeline state produces readiness 200 and advertises only `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`; missing/unavailable dependencies produce readiness 503 with no executable profile. Without database configuration, liveness/discovery still work. See the [API runbook](../api/README.md), [lexical request guide](../../../docs-website/docs/architecture/postgres-lexical-search.md) and [database operations guide](../../../docs-website/docs/architecture/postgresql-foundation.md). The UI uses discovery only; execution remains a subsequent task.

### Execution modes and API discovery

Start the API and optional validator in separate terminals, then start Vite. Select **Live** in the header and open Settings to inspect the server-returned workspace, database state, profile/revision and score type. **Refresh connection** starts a new check. The workspace display name remains a browser preference and never grants API access.

| Service               | Local port              | Browser route             | Purpose                                         |
| --------------------- | ----------------------- | ------------------------- | ----------------------------------------------- |
| Vite                  | 5173 dev / 4173 preview | `/`                       | Interface                                       |
| Constructor validator | 8010                    | `/api/pipelines/validate` | Haystack constructor/socket validation          |
| Workbench API         | 8011                    | `/api/v1/...`             | Discovery; backend also supports lexical search |

Both Vite modes proxy `/api/v1` to port 8011, independently of the validator route. A static production deployment must provide equivalent trusted same-origin routing; Vite's development proxy is not part of the built assets. The optional public `VITE_WORKBENCH_API_BASE_URL` overrides the browser API origin/path at build time. Never put credentials, tokens or a database DSN in a `VITE_` value. Cross-origin deployment must also satisfy the API's allowed-origin policy.

| Selected mode / state             | Behavior                                                                 |
| --------------------------------- | ------------------------------------------------------------------------ |
| Preview, API offline or online    | Fixture Run, documents and history; no discovery requests                |
| Live, ready                       | Server profile/workspace shown; Run disabled until execution integration |
| Live, readiness 503 / no profiles | Not ready; no fixture fallback                                           |
| Live, network failure             | Offline; select Preview explicitly or refresh                            |
| Live, incompatible contract       | Incompatible; profile and selection cleared                              |

Discovery checks liveness, readiness, capabilities and bounded workspace pagination. Ready requires consistent responses, a running service, ready database, search support and a supported profile bound to an authorized workspace. A green liveness response alone is insufficient. No search or document-list request is made by this UI milestone. Preview preferences are retained but disabled in Live. Changing mode cancels pending discovery and stops an active Preview; recovery never changes the selected mode automatically. Mode survives navigation; refreshing resets it to Preview.

### Authoritative validation

From the repository root, in a separate terminal:

```powershell
hatch --version
hatch -e test run python -m apps.workbench.validator
```

The validation-only service binds to `127.0.0.1:8010`. Restart Vite after adding its validation proxy. Both `npm run dev` and `npm run preview` forward `/api/pipelines/validate` to this loopback service; static deployments need an equivalent trusted same-origin proxy. A missing service produces Unavailable, never a successful local verdict. Retry with Validate after starting it.

Each validation uses a fresh real Haystack Pipeline and only approved components. Nothing is executed or warmed up. The API distinguishes `draft` connection checking from `complete` checks of mandatory external inputs. The UI requests complete validation; optional execution inputs may be supplied by API callers. A valid verdict describes the requested validation level, not a guarantee that execution will succeed.

Conceptual file/query/result nodes and unavailable or unmapped integrations are explicitly Unsupported. The two demonstration templates include such nodes and therefore cannot currently receive a full Haystack-valid verdict. The mapping, supported ports, error codes and limitations are documented in [the validator inventory](../validator/README.md).

Changing a graph invalidates its prior verdict. Requests are bounded and timed out; stale responses, incompatible capability revisions and service errors cannot mark a newer graph valid. Fixture Preview is independent: its local DAG restriction is a preview limitation, not a Haystack rule about loops.

### Browser smoke

With the dev server running, execute the repeatable browser scenario from this directory:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench open http://127.0.0.1:5173
npx --yes --package @playwright/cli playwright-cli -s=workbench resize 1440 1000
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/browser-smoke.js
```

The first invocation can download the CLI/browser. The scenario checks graph editing, undo/redo, export/import, branch connections, the preview-only DAG restriction, successful preview output, document chunks, shared run history, and the configured failure scenario. It resets the preview session at the start. Browser artifacts and downloads are not production data.

## Try the editor

1. Open the initial hybrid retrieval pipeline. Select a component to edit its name and parameters.
2. Add components from the library with a click, keyboard, or drag. Connect ports by dragging or by selecting outputs in the inspector's Connections fields. Single-input selectors replace the existing connection; multi-input selectors add a branch.
3. Select Validate for an authoritative Haystack result. With the service unavailable the graph stays editable. Run uses separate fixture prerequisites; preview restrictions do not establish Haystack compatibility.
4. Select Run. The Preview indicator applies to the entire application: this replays sample node results and never performs retrieval, inference, or index writes.
5. Inspect Output, Nodes, and Errors. Open Runs to find the same execution and its captured graph.
6. Export a graph to JSON; restore it with Import pipeline or Import JSON on Pipelines. Positions, parameters, connections, and viewport are included.

Pipelines supports both Document indexing and Hybrid retrieval templates, plus blank graphs. Documents includes sample content, chunk excerpts, parsing reports, and failed documents. Settings changes apply immediately; select the Error scenario to inspect failure handling or increase Step delay to test Stop.

## State and keyboard

State lives in memory for the current page session and survives navigation between sections. Refreshing resets it to the fixtures. Export graphs before refreshing if you want to retain your work. Run history and original documents are not included in graph exports.

| Action                       | Shortcut              |
| ---------------------------- | --------------------- |
| Undo / redo                  | Ctrl+Z / Ctrl+Shift+Z |
| Duplicate selected node      | Ctrl+D                |
| Export current pipeline      | Ctrl+S                |
| Delete selected node or edge | Delete / Backspace    |
| Move a focused node          | Arrow keys            |
| Deselect                     | Escape                |

Library buttons and connection selectors provide alternatives to drag operations. Native dialogs support Escape. The interface respects system reduced-motion preferences and the local Reduced motion setting.

## Boundaries and next tasks

- `src/domain` owns view models, catalog, graph validation, JSON parsing, fixtures, and deterministic preview scenarios.
- `src/hooks` owns editor history and cancellable preview progression.
- `src/components` owns the editor; `src/views` owns Pipelines, Documents, Runs, and Settings.
- The frontend has separate constructor-validation and read-only execution-discovery API boundaries. Safe import and editor structure checks remain browser-owned; component/socket compatibility belongs to Haystack. The separate FastAPI application exposes persisted document lists and live PostgreSQL lexical search; frontend Live execution and model adapters remain future tasks.

The canonical implementation contract is [RAG runtime contract](../../../docs-website/docs/architecture/rag-runtime-contract.md). It defines the planned execution profiles, API, source identities, score meanings and error semantics. The dated [RAG MVP Architecture and Implementation Plan](../../../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md) remains a historical planning reference; its OpenSearch and Ollama-embedding choices do not override the canonical contract.

### Persistent foundation and lexical API

PostgreSQL is the durable corpus: composite workspace/source/version keys, forced RLS, explicit atomic eight-source development seed and nullable pgvector columns. The live API's `postgres-fts-baseline` profile uses PostgreSQL `simple` FTS with `ts_rank_cd` and score type `postgres_ts_rank_cd`; it is not BM25. Requests require query, integer top-k, profile ID and expected profile revision. Results include authoritative source/chunk/version identity, corpus revision and measured timings. No raw editor graph is executed.

The existing BM25 node, indexing and hybrid templates remain fixture previews. They are not executable Live bindings for native PostgreSQL FTS. A future UI adapter must explicitly recognize the approved profile and reject unsupported graphs without changing their meaning from display labels. Settings cannot select a database or grant workspace access.

Preview runs contain illustrative passages, scores and stage durations. Authoritative Validate checks component compatibility without execution. Live API requests execute the approved backend search and return actual results and timings. These remain three separate behaviors; validation or browser Preview cannot be reported as live search.

Workbench graph files remain portable editor documents with `schemaVersion: 1`; they are not executable Haystack YAML or a general backend execution contract. Import/export, drafts and preview behavior do not require a migration for this documentation decision.

The durable metadata/version registry and nullable vector columns exist in PostgreSQL + pgvector. Ingestion/indexing workflows and real embedding generation remain future work. TEI is the selected embedding transport with an expected 2560-dimensional Qwen3-Embedding-4B profile; model/tokenizer revision, endpoint health, token accounting and actual output still require qualification. The initial enabled vector profile is synthetic and three-dimensional; a synthetic 2560-dimensional storage test does not validate model output. None of these services is connected by the current UI. Dense/hybrid retrieval and generation remain deferred. Detailed decisions belong to the canonical contract.

| Task      | Deliverable                                                                                           |
| --------- | ----------------------------------------------------------------------------------------------------- |
| ARCH-01   | Publish the canonical runtime decisions and integration contract                                      |
| Retrieval | PostgreSQL lexical HTTP profile implemented; frontend Live integration remains separate               |
| BE-01     | PostgreSQL foundation implemented; extend ingestion and operational guarantees through separate tasks |
| BE-02     | Document ingestion, structural parsing, and reports                                                   |
| BE-03     | Chunking and validated 2560-dimensional TEI embeddings                                                |
| BE-04     | Delta indexing, vector reuse, and safe publication                                                    |
| BE-05     | BM25, dense retrieval, and RRF                                                                        |
| BE-06     | Diagnostics, recovery, throughput and quality evaluation                                              |
| INT-01    | Connect this UI to the backend in a separate task                                                     |
| GEN-01    | Add answer generation after retrieval MVP                                                             |

## Font licensing

IBM Plex Sans and JetBrains Mono are bundled through Fontsource. Their SIL Open Font License notices are retained in `public/licenses/` and shipped alongside production assets. React Flow's attribution remains visible.

### Validation smoke

With the local validator and Vite running, this additional browser check exercises the actual Python boundary, supported/unsupported verdicts, edit invalidation, and service unavailability:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/validation-smoke.js
```

Focused Python checks from the repository root:

```powershell
hatch -e test run pytest apps/workbench/validator/tests -q
hatch run fmt-check apps/workbench/validator
hatch run test:types --explicit-package-bases apps/workbench/validator
```

The whole upstream Haystack test suite is not required for this boundary-only change; the targeted suite verifies real public Pipeline calls without executing the graph.

### Discovery smoke

Run the primary API on 8011 with its qualified PostgreSQL corpus and the built frontend on 4173. For the real unconfigured/503 sample, start a second API in a separate terminal from the repository root:

```powershell
Remove-Item Env:WORKBENCH_DB_DSN -ErrorAction SilentlyContinue
$env:WORKBENCH_API_PORT = "8012"
hatch run workbench-api:serve
```

From `apps/workbench/web`, with the Playwright browser session open at the frontend:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/discovery-smoke.js
```

The scenario checks real discovery, keyboard mode selection, 1440px/1100px layouts, server-owned workspace selection, the second API's actual 503/no-profile payload, injected offline/conflicting/stale responses, explicit Preview recovery and absence of search/document requests. It saves screenshots under `output/playwright/` relative to the browser CLI's working directory. Stop the smoke-only 8012 process afterward. Recorded task evidence distinguishes actual HTTP responses from injected browser failures.

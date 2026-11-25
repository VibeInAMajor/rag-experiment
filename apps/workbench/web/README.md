# Haystack Workbench · UI-01

A pipeline editor with offline Preview, separate Haystack constructor validation and opt-in Live lexical search. Preview documents, scores and processing reports are fixtures. Editing, JSON import/export and Preview need no backend; Live search requires the qualified PostgreSQL-backed API.

An independent [Workbench API](../api/README.md) provides PostgreSQL lexical retrieval through Haystack. **Live** mode executes the approved Keyword search graph and connects Documents to persisted sources, active chunks and synchronous uploads. The initial Hybrid graph remains Preview.

Qualified deployments also advertise **Dense search**, profile `postgres-dense-exact` / `postgres-dense-exact-r1`. Its new-pipeline template appears only in Live when the authorized workspace has this capability. Select the dense execution profile in Settings, then create the four-component graph **Search query → Query embedding → Dense search → Search results**. Query embedding accepts no browser model settings; the server owns the qualified local model and input policy. The request retains exactly `query`, `top_k`, `profile_id`, and `expected_profile_revision`.

Dense output preserves raw `cosine_distance` (lower is better), source/version/chunk identities, embedding profile revision, index generation, model/tokenizer digests, input policy and trace. Server `query_embedding`, `vector_search`, and `projection` stages carry measured timings and timestamps. Incomplete generations, provider failure or provenance drift never produce Preview results. Dense and query-embedding components cannot execute in Preview. Reverting the frontend requires no index deletion or reindex. The real qualified API browser check is `npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/dense-search-smoke.js`; its outage check explicitly injects HTTP 503 and is not a model performance measurement.

The Dense browser scenario runs ten actual EN/RU/UK queries and records response-body-ready → result DOM commit and → second animation-frame callback p50/p95 independently from server stages. These browser metrics include JSON decoding, React scheduling and frame scheduling; they exclude provider, SQL and network time and do not claim pure component CPU or guaranteed paint duration. It also adds an unsupported graph component and verifies zero search POSTs. For an isolated API on a different local port, open `http://127.0.0.1:4173/?dense_api_port=8013` before the scenario; the harness forwards API requests to that real loopback service and restores its interception afterward.

## Application configuration

Select **Configuration**, the wrench directly below Runs, to open the server YAML immediately. No operator key, login or extra access screen is required. The Application-wide badge and Lock action are removed. This page uses the real same-origin API in either Preview or Live mode; browser preferences remain under Settings.

The lazy CodeMirror editor supports multiline paste, indentation, syntax highlighting, line numbers, undo and virtualized scrolling. Tab indents; Escape followed by Tab moves focus out. Validate uses the canonical server schema and Save revalidates with the loaded revision. Conflicts retain edits. Reload/navigation ask before discarding unsaved work; refreshing warns too. In-flight saves cannot be duplicated. A timeout is unconfirmed: reload before retrying.

The selected YAML is the only persisted source. Save reports whether settings already match the active process or require an **API restart**. Existing documents adopt a changed profile only through explicit guarded re-ingestion. The local API checks request intent and trusted origins without accounts/cookies. See the [operator reference](../../../docs-website/docs/architecture/document-processing-configuration.md#edit-configuration-in-workbench) for limits, persistence and recovery.

## Start

For the complete local application after the [one-time database setup](../api/README.md#optional-persistent-development-database), run from the repository root:

```powershell
.\start.ps1
```

Open <http://127.0.0.1:4173/>. The launcher starts PostgreSQL, the API and constructor validator, builds the site when starting it, and reuses healthy services. Background services continue after the command returns; logs are in `output/workbench-services/`. It never migrates or seeds the database. For launcher prerequisites and restricted PowerShell execution policies, see [the API startup guide](../api/README.md#start).

For frontend development only:

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

After explicit PostgreSQL setup/migration/seed, load `. ./apps/workbench/postgres/use-dev-env.ps1` from the repository root and launch `hatch run workbench-api:serve`. It listens on `127.0.0.1:8011`, independently of the constructor validator on port 8010. Qualified schema/index/corpus/pipeline state produces readiness 200 and advertises only `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`; missing/unavailable dependencies produce readiness 503 with no executable profile. Without database configuration, liveness/discovery still work. See the [API runbook](../api/README.md), [lexical request guide](../../../docs-website/docs/architecture/postgres-lexical-search.md) and [database operations guide](../../../docs-website/docs/architecture/postgresql-foundation.md). Live Documents uses this API's existing document and ingestion routes; upload, details and jobs each require their own runtime capability.

### Execution modes and API discovery

Start the API and optional validator in separate terminals, then start Vite. Select **Live** in the header and open Settings to inspect the server-returned workspace, database state, profile/revision and score type. **Refresh connection** starts a new check. The workspace display name remains a browser preference and never grants API access.

| Service               | Local port              | Browser route             | Purpose                                    |
| --------------------- | ----------------------- | ------------------------- | ------------------------------------------ |
| Vite                  | 5173 dev / 4173 preview | `/`                       | Interface                                  |
| Constructor validator | 8010                    | `/api/pipelines/validate` | Haystack constructor/socket validation     |
| Workbench API         | 8011                    | `/api/v1/...`             | Discovery and approved Live keyword search |

Both Vite modes proxy `/api/v1` to port 8011, independently of the validator route. A static production deployment must provide equivalent trusted same-origin routing; Vite's development proxy is not part of the built assets. The optional public `VITE_WORKBENCH_API_BASE_URL` overrides the browser API origin/path at build time. Never put credentials, tokens or a database DSN in a `VITE_` value. Cross-origin deployment must also satisfy the API's allowed-origin policy.

| Selected mode / state             | Behavior                                                                       |
| --------------------------------- | ------------------------------------------------------------------------------ |
| Preview, API offline or online    | Fixture Run, documents and history; no discovery requests                      |
| Live, ready                       | Approved Keyword search graph can run; other graphs are explicitly unsupported |
| Live, readiness 503 / no profiles | Not ready; no fixture fallback                                                 |
| Live, network failure             | Offline; select Preview explicitly or refresh                                  |
| Live, incompatible contract       | Incompatible; profile and selection cleared                                    |

Discovery checks liveness, readiness, capabilities and bounded workspace pagination. Ready requires consistent responses, a running service, ready database, search support and a supported profile bound to an authorized workspace. A green liveness response alone is insufficient. Live search and Documents use the existing versioned API. Preview preferences are retained but disabled in Live. Changing mode cancels pending requests and stops active local progression; recovery never changes the selected mode automatically. The current page and explicitly selected mode are recorded in the URL as `page` and `mode`, and restored on refresh. A fresh URL without a mode starts in Preview. Restoring Live rechecks discovery without rerunning a search or upload. The legacy `#configuration` link remains supported.

In **Settings → Backend connection → Execution profile**, select a currently qualified lexical profile and inspect its exact ID, revision, score type and maximum results. The baseline remains the initial default when available. Other approved IDs require an explicit selection; a retired or withdrawn selection does not silently switch to another profile. Refresh obtains the current revision of the selected logical profile. Profile/workspace changes interrupt pending local runs and clear their visible submitted context. Only compatible PostgreSQL lexical semantics are executable in this client; planned dense, ANN, hybrid and BM25 definitions do not become Live options.

### Run a Live keyword search

1. Start the qualified API and select **Live**. Open **Pipelines → New pipeline → Keyword search**.
2. Edit **Search query → Question**. The template starts with `retention`, an exact term in the development corpus, not a promised answer.
3. Set **Keyword search → Maximum results** and **Search results → Result limit**. Both values must fit the selected profile's advertised maximum (at most 50); Live sends the smaller value. The Preview Settings result limit does not apply.
4. Select **Run**. Output shows server rank, raw `postgres_ts_rank_cd` score, persisted source/version/chunk identity and page availability. **Stages** shows measured server operations, and **Execution details** contains correlation, profile and corpus IDs. JSON retains exact numeric values.

The approved graph has exactly three nodes and two connections: query → keyword-search → results. Additional nodes, parameters, unsupported profiles or invalid values disable Live Run before any search request. The client sends only `query`, `top_k`, `profile_id` and `expected_profile_revision`; it never sends editor graph JSON. Native PostgreSQL FTS is not BM25 and its raw score is not confidence or a percentage.

**Validate** still checks Haystack constructors separately. Conceptual query/results and the keyword binding can be Unsupported there while the approved Live profile is executable. The new keyword node is explicitly unsupported in Preview; existing Hybrid/indexing fixtures retain their previous behavior.

Stop marks the request **Interrupted locally**; server cancellation is not confirmed. Graph edits, mode/profile/workspace changes, pipeline changes and unmount invalidate pending responses. Pan/zoom only changes the viewport and does not cancel execution. Failures preserve safe codes/correlation and never substitute fixtures; 404/409/503 refresh discovery without retrying the search. Retry manually after reviewing the error.

Runs and pipeline summaries show mixed, explicitly labeled Preview/Live **session** history, limited to 100 entries across both modes. Completed results retain their submitted graph snapshot; edited graphs cannot display an obsolete response as their own. Refresh clears history; there is no server-side run-history API. Graph exports retain `schemaVersion: 1`, including the new keyword kind/template. Older frontend builds reject these new kinds rather than rewriting them; old graph files remain supported.

### Manage persisted documents

Select **Live → Documents** after connecting to the authorized development workspace. Preview Documents remains fixture data. Live loads 50 source rows per request; **Load more documents** follows the server's opaque cursor. **Filter loaded documents** and status filters affect only rows already loaded. Counts are loaded rows, not an asserted corpus total. An expired cursor or changed corpus clears the old pages and restarts the snapshot once; errors stay visible without fixture fallback.

The document list groups folder selections into collapsible folders and subfolders, with folder icons and recursive ready/total counts. Counts and status come from documents actually present in the corpus, aggregated by the API before pagination. Folder **Ready** requires all persisted descendants to be ready; documents in processing or error prevent it. Failed, skipped or unconfirmed upload attempts that did not create a document remain in the upload queue and TXT report, and do not affect folder readiness or appear as corpus files. Active uploads remain visible while running. Filters do not recalculate readiness from the filtered subset. Same-named folders selected in separate operations remain separate groups. New selections retain their hierarchy after refresh. Existing documents require a known saved path or verified original-file recovery; filenames alone do not identify a folder.

Select a source to inspect its active version. **Indexed text** and **Chunks** show actual indexed passages, chunk IDs/hashes, section paths, and page/line metadata only when returned. This inspection loads 50 chunks per request, up to 1,000 chunks in memory; an explicit notice identifies additional server chunks at that limit. Individual text and metadata displays also report truncation. **Parse report** shows returned parser/processing policy and warnings. Markdown cards use one-based fragment labels and inclusive source-line ranges from recorded metadata; they omit the page placeholder. Missing line metadata is not guessed. PDF cards retain the actual server page number. Indexed text is not the original file.

When **Upload** is available, use **Choose files** for one or more files, or **Choose folder (including subfolders)** for every file in a directory tree. Review the queue, then select **Upload N files**. Each `.txt`, `.md`, `.markdown` or `.py` file is limited to **1 MiB**. Text must be nonempty UTF-8 and Python must pass server syntax validation; uploaded code is never executed. PDF is offered only when `pdf_ingestion.available=true`, with the server's **8 MiB / 32-page** ceiling and pinned local model assets. This is text-layer processing: no OCR, visual understanding or original evidence. Unsupported formats and oversized files appear as **skipped**, with a reason; valid files continue independently. Empty folders contribute no files. The [parser registry](../parsing/parser_registry.py) and [ingestion operations guide](../../../docs-website/docs/architecture/durable-text-ingestion.md) own server qualification and recovery.

The file byte limit is separate from chunking limits. Large Markdown quotes, lists, tables and fences are split into bounded source-exact raw fragments, with an explicit warning in Parse report; they are not interpreted as code or structured table cells. Actual processing limits report `DOCUMENT_PROCESSING_LIMIT_EXCEEDED`, and workspace capacity reports `CORPUS_LIMIT_EXCEEDED`, rather than describing either as an oversized file.

The Upload window opens wide by default, supports dragging its bottom-right resize handle, and offers compact/wide header controls. If files fail, are skipped or have an unconfirmed outcome, **Download error report (.txt)** exports every affected relative path, status, reason and error code as a UTF-8 text file, including entries beyond the visible queue page. Successful and waiting entries are excluded.

The asynchronous browser queue admits at most two simultaneous upload requests, matching the HTTP boundary. Closing the dialog or switching application pages keeps it running. Each file shows its relative folder path and confirmed result or error. For new folder selections, the API persists the selection ID, relative path and recursive expected-file counts in source metadata. Documents remain independent records; folder metadata never identifies a server filesystem location. The queue releases successfully uploaded file references and refreshes the document list after the batch settles. **Stop queue locally** pauses waiting files and interrupts active requests with an **unconfirmed** server outcome. Retry individual uncertain/retryable operations with their original key; **Upload N files** resumes files that were never submitted. Keep the browser tab open: closing or refreshing it loses the session queue. This does not add a server-side background queue. The optional multipart field `upload_location` is JSON with `group_id`, `path` and `folder_totals`; document list/detail responses return the persisted location. The client sends this field only when the API advertises `features.upload_folders=true`. Older APIs continue accepting file/folder uploads, with grouping retained only in the current browser session; restart the updated API for durable hierarchy.

Each confirmed operation retains one idempotency key and its file in this page session. **Retry same operation** reuses both after a timeout, offline response or local Stop; the server may already have committed. A local Stop never confirms rollback or a failed job. Choosing a file again starts an explicit new operation and may create another source. **Replace file** binds the request to the selected source's loaded active version. A conflict preserves the file and operation; refresh/review current details, then explicitly choose the file again before a new replacement. Failed terminal jobs replay their original failure; after correcting its cause, choose the file again to start an intentional new attempt.

Successful replacement reports the actual outcome/replay flag, source/version/job IDs, count and measured server stages, then reloads the list, selected source, chunks and known job. Queue entries report each confirmed outcome and job ID. Every confirmed publication clears the current Live search display so an old result cannot represent the changed corpus. Jobs for the single-file replacement flow are fetched by their known ID, with last-confirmed status/stage/timestamps and **Inspect confirmed job status** for a manual refresh. There is no automatic polling, percentage progress or global job history. **Search this source** opens the existing Keyword search graph: enter a unique term from its indexed text and compare returned source/version IDs.

Navigating away interrupts pending document reads and single-file replacement requests locally, retaining the same-workspace replacement intent for recovery; the file/folder queue continues. Closing Upload alone leaves either flow running; use the explicit local Stop control to interrupt it. Mode/workspace changes stop and clear the queue, private files and passages; a browser refresh clears all session intent and keys. Persisted sources and durable jobs remain in PostgreSQL. Original bytes cannot be downloaded through these routes. A registered version-specific filename link only reveals a local original on the API host, as described in [Local source names](#local-source-names).

For rollback, disable the Live Documents entry and retain explicit Preview mode, PostgreSQL source/version/chunk/job rows, local registrations and the named database volume. No database downgrade, reseed or volume deletion is required.

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
4. With Preview selected, Run replays sample node results. Select Live and the dedicated Keyword search graph for actual read-only lexical retrieval.
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
- `src/hooks` owns editor history, discovery and separate cancellable Preview/Live progression. `src/domain/approvedExecution.ts` owns exact graph matching; `src/domain/liveSearch.ts` owns immutable Live session records and request generations. `useLiveDocuments` and `src/domain/liveDocuments.ts` own document snapshots, request generations and recoverable upload operations.
- `src/components` owns the editor; `src/views` owns Pipelines, Documents, Runs, and Settings.
- The frontend has separate constructor-validation and typed RAG API boundaries. Safe import and exact approved-graph matching remain browser-owned; component/socket compatibility belongs to Haystack. Live search uses the fixed server profile; Documents consumes existing PostgreSQL ingestion routes. Model adapters remain future work.

The canonical implementation contract is [RAG runtime contract](../../../docs-website/docs/architecture/rag-runtime-contract.md). It defines the planned execution profiles, API, source identities, score meanings and error semantics. The dated [RAG MVP Architecture and Implementation Plan](../../../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md) remains a historical planning reference; its OpenSearch and Ollama-embedding choices do not override the canonical contract.

### Persistent foundation and lexical API

PostgreSQL is the durable corpus: composite workspace/source/version keys, forced RLS, explicit atomic eight-source development seed and nullable pgvector columns. The live API's `postgres-fts-baseline` profile uses PostgreSQL `simple` FTS with `ts_rank_cd` and score type `postgres_ts_rank_cd`; it is not BM25. Requests require query, integer top-k, profile ID and expected profile revision. Results include authoritative source/chunk/version identity, corpus revision and measured timings. No raw editor graph is executed.

The existing BM25 node, indexing and hybrid templates remain fixture previews. They are not executable Live bindings for native PostgreSQL FTS. The strict Keyword search adapter recognizes the approved profile and rejects unsupported graphs without changing their meaning from display labels. Settings cannot select a database or grant workspace access.

Preview runs contain illustrative passages, scores and stage durations. Authoritative Validate checks component compatibility without execution. Live API requests execute the approved backend search and return actual results and timings. These remain three separate behaviors; validation or browser Preview cannot be reported as live search.

Workbench graph files remain portable editor documents with `schemaVersion: 1`; they are not executable Haystack YAML or a general backend execution contract. Import/export, drafts and preview behavior do not require a migration for this documentation decision.

The durable metadata/version registry and nullable vector columns exist in PostgreSQL + pgvector. Bounded TXT/Markdown/Python ingestion and conditionally available PDF ingestion publish active lexical chunks through the existing writer. Real embedding generation remains future work. TEI is the selected embedding transport with an expected 2560-dimensional Qwen3-Embedding-4B profile; model/tokenizer revision, endpoint health, token accounting and actual output still require qualification. The initial enabled vector profile is synthetic and three-dimensional; a synthetic 2560-dimensional storage test does not validate model output. TEI inference is not connected by the current UI. Dense/hybrid retrieval and generation remain deferred. Detailed decisions belong to the canonical contract.

| Task      | Deliverable                                                                                               |
| --------- | --------------------------------------------------------------------------------------------------------- |
| ARCH-01   | Publish the canonical runtime decisions and integration contract                                          |
| Retrieval | PostgreSQL lexical HTTP profile and approved Keyword search UI implemented; dense/hybrid remains separate |
| BE-01     | PostgreSQL foundation implemented; extend ingestion and operational guarantees through separate tasks     |
| BE-02     | Document ingestion, structural parsing, and reports                                                       |
| BE-03     | Chunking and validated 2560-dimensional TEI embeddings                                                    |
| BE-04     | Delta indexing, vector reuse, and safe publication                                                        |
| BE-05     | BM25, dense retrieval, and RRF                                                                            |
| BE-06     | Diagnostics, recovery, throughput and quality evaluation                                                  |
| INT-01    | Connect this UI to the backend in a separate task                                                         |
| GEN-01    | Add answer generation after retrieval MVP                                                                 |

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

### Live search smoke

With the primary API8011, its existing qualified PostgreSQL corpus, constructor validator8010 and production frontend4173 running:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/live-search-smoke.js
```

The scenario captures actual POST responses for `retention`, `GIN` and a no-match query without replacing real search traffic. It compares DOM order, IDs, raw scores, passages, JSON and timings to those responses, checks the unchanged source registry, keyword import/export and explicit Preview refusal, then separately injects 400/404/409/429/503/504, gateway/network, malformed-success and delayed-Stop cases. It checks 1440px/1100px layouts and mixed Live session history. Negative injections are test arrangements, not observed backend incidents. Existing `browser-smoke.js` and `validation-smoke.js` remain unchanged and must pass separately. This smoke does not reset or seed the database.

### Live lexical acceptance evaluation

The completed [acceptance task](../../../tasks/TASK-EVAL-001-prove-vertical-slice.md) and [dated report/runbook](../../../docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) qualify the existing local browser → Haystack → persisted PostgreSQL edge. With the real qualified API and frontend running, open the dedicated session from this directory:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=eval20261122 open http://127.0.0.1:4173
```

Then run the operator helpers from the repository root; the probe requires the existing app-only environment:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:python -m scripts.workbench_evaluation_probe baseline
./scripts/run_workbench_live_evaluation.ps1 -Phase baseline
./scripts/run_workbench_recovery_evaluation.ps1 -Service api
./scripts/run_workbench_recovery_evaluation.ps1 -Service database
./scripts/run_workbench_live_evaluation.ps1 -Phase mock-races -Harness resilience
```

The phase runner loads the **existing** canonical gold fixture, injects `window.__workbenchEvaluationInput`, saves sanitized reports and retains failed-harness evidence. The guarded recovery runner supervises verified API/database owners, restores services and repeats browser/SQL checks without seeding or deleting a volume. Do not invoke `live-evaluation-smoke.js` directly without its runner configuration.

Each real phase runs ten exact questions, three diagnostic paraphrases and one explicit no-match query via actual UI actions, comparing DOM/JSON to actual HTTP results. Final observations: **10/10 exact hits and MRR@5=1.0**, **0/3 diagnostic hits and MRR@5=0.0**, in all three phases; **39 canonical browser/HTTP/SQL parity cases**, three extra browser/HTTP empty cases, stable 8-source/8-chunk corpus through API/database restarts, and zero false Live completion/fixture fallback. Backend tests: **38 passed, zero skips**; frontend tests: **259 passed**, with typecheck/format/build and independent Preview/validator smokes passing.

Expected-source-hit-rate/MRR retain all attempts and their separate group denominators. Nearest-rank server/browser latencies state sample counts and warm-service conditions; observed coarse-clock zero-ms values are not missing samples. Actual 400/404/409 request arrangements and real API 502/database 503 outages are separate from nine mock error shapes, local Stop and strengthened query/mode history races. The browser finishes on a real unmocked Live search. New machine artifacts remain local under the existing `tasks/evidence/` ignore policy; the report documents commands, versions, automation incidents and limits. This qualifies the tested synthetic local lexical slice, not a remote server, semantic recall or production readiness.

## Local source names

For a registered real original, the **Source** value in Live output/session details is its filename as a text link. Clicking or pressing Enter selects the original in Windows Explorer. Demo/synthetic/unregistered sources remain plain text; no new button, icon, menu or file picker is added. A failed click shows concise error feedback only.

Original registration and `WORKBENCH_LOCAL_SOURCE_ROOT` belong to the local API operator; see the [local originals guide](../../../docs-website/docs/architecture/local-source-reveal.md). The current eight-source demo corpus has no originals and intentionally stays noninteractive. This uses the API host's interactive Windows desktop, not a remote browser client's filesystem. Search results and graph schemas are unchanged.

With the primaryAPI8011 and productionUI4173 running, a supervised real-original smoke can be prepared from the repository root:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:python -m scripts.workbench_source_reveal_fixture
```

This harness creates only its own disposable PostgreSQL database and temporary original on8014. From this frontend directory, use the documented Playwright session:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/source-name-smoke.js
```

The scenario first proves actual main demo names are plain text, then points its own browser traffic to the isolated real corpus, verifies the actual filename/keyboard click and native POST `{}`, and checks a separately injected failure. It opens Explorer for that temporary original. Stop the fixture afterward and verify its cleanup marker; abrupt termination may require verified cleanup of the exact owned database printed by the harness. Never reset the main corpus. The temporary original remains for the opened Explorer window.

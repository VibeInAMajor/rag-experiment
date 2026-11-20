# Haystack Workbench · UI-01

A standalone pipeline editor. All documents, runs, scores, and processing reports are local demonstration fixtures. No backend, Docker, database, model, credentials, or Python environment is needed.

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

### Browser smoke

With the dev server running, execute the repeatable browser scenario from this directory:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=workbench open http://127.0.0.1:5173
npx --yes --package @playwright/cli playwright-cli -s=workbench resize 1440 1000
npx --yes --package @playwright/cli playwright-cli -s=workbench run-code --filename=scripts/browser-smoke.js
```

The first invocation can download the CLI/browser. The scenario checks graph editing, undo/redo, export/import, branch connections, cycle rejection, successful preview output, document chunks, shared run history, and the configured failure scenario. It resets the preview session at the start. Browser artifacts and downloads are not production data.

## Try the editor

1. Open the initial hybrid retrieval pipeline. Select a component to edit its name and parameters.
2. Add components from the library with a click, keyboard, or drag. Connect ports by dragging or by selecting outputs in the inspector's Connections fields. Single-input selectors replace the existing connection; multi-input selectors add a branch.
3. Select Validate. Required parameters, missing inputs, incompatible ports, and cycles produce actionable messages.
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
- There are no API clients, network requests, server schemas, or model adapters in UI-01. Graph validation checks the editor's supported port categories, not Haystack runtime compatibility. A future integration task must replace preview progression, map server data to these view models, and add authoritative backend validation.

The backend reference is [RAG MVP Architecture and Implementation Plan](../../../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md). Its OpenSearch and Ollama-embedding choices are superseded by the agreed PostgreSQL + pgvector storage and existing TEI embeddings service. Answer generation comes after retrieval MVP.

| Task    | Deliverable                                                         |
| ------- | ------------------------------------------------------------------- |
| ARCH-01 | Reconcile the backend reference and establish integration contracts |
| BE-01   | PostgreSQL migrations, workspaces, and isolation                    |
| BE-02   | Document ingestion, structural parsing, and reports                 |
| BE-03   | Chunking and validated 2560-dimensional TEI embeddings              |
| BE-04   | Delta indexing, vector reuse, and safe publication                  |
| BE-05   | BM25, dense retrieval, and RRF                                      |
| BE-06   | Diagnostics, recovery, throughput and quality evaluation            |
| INT-01  | Connect this UI to the backend in a separate task                   |
| GEN-01  | Add qwen3.8:27b answer generation after retrieval MVP               |

## Font licensing

IBM Plex Sans and JetBrains Mono are bundled through Fontsource. Their SIL Open Font License notices are retained in `public/licenses/` and shipped alongside production assets. React Flow's attribution remains visible.

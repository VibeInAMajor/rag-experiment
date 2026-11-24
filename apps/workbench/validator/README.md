# Workbench construction validator

This isolated HTTP boundary assembles **real installed Haystack components**. It does not execute, warm up, parse files, resolve credentials, load models, access storage, or perform inference. The browser's fixture preview remains a separate demo.

From the repository root:

```powershell
hatch --version
hatch -e test run python -m apps.workbench.validator
```

The only binding is `127.0.0.1:8010`; no remote binding flag exists. `GET /health` reports availability. Browser origins are restricted to `http://localhost` or `http://127.0.0.1` on ports 5173, 4173, and 8010. Vite proxies `/api/pipelines/validate` to this service. CLI requests without Origin still require a loopback Host. This is a local development boundary, not production authentication.

## Contract

`POST /api/pipelines/validate` takes `schemaVersion: 1`, `graph`, optional `requestId`, `mode` (`complete` default or `draft`), and optional `inputs`. Graph nodes/edges use the portable Workbench JSON shape, without React Flow selection, measurement, or executable metadata.

Response fields: `status` (`valid`, `invalid`, `unsupported`), `issues`, echoed/generated `requestId`, `validator: haystack`, `capabilityVersion: workbench-components-v1`, and `mode`. The capability revision names this mapping contract; it is not a task identifier or Haystack package version. The client must reject unknown capability revisions.

- **Draft:** approved component constructors and real `Pipeline.connect()` calls passed. Disconnected mandatory runtime inputs may remain. This is not complete/executable validity.
- **Complete:** draft checks plus constructor parameter completeness and all remaining mandatory runtime inputs from `Pipeline.inputs()`. The supplied `inputs`, if present, are mapped from UI IDs to safe names and checked with `Pipeline.validate_input()`. No inference is run and no claim about data-dependent runtime success is made.
- A graph containing any unsupported node never gets `valid`. It returns explicit diagnostics; supported subgraphs are not substituted for the requested graph.
- HTTP errors/timeouts or an unavailable service are transport failures, never authoritative validity.

User node IDs map to generated `n_0`, `n_1`, … names. UI handle mappings below are explicit; Python socket compatibility is owned solely by `Pipeline.connect()`. No DAG check exists here. Haystack-supported loops can pass draft construction; fixture preview's DAG limit is independent.

## Reviewed node inventory (all current kinds)

| Kind | Actual class / availability | UI handles → real sockets | Constructor projection / status |
|---|---|---|---|
| `files` | UI concept, no runtime component | None | Unsupported: file source resolution is not implemented |
| `query` | UI concept, no runtime component | None | Unsupported: no generic pass-through substitute; explicit runtime `inputs` remain available |
| `results` | UI projection, no runtime component | None | Unsupported: no output component substitute |
| `parser` | Intended DoclingConverter external integration | None approved | Unsupported: no approved installed parser integration; no plugin discovery |
| `writer` | Core DocumentWriter exists, persistent resource binding absent | None approved | Unsupported: substituting an empty memory store would misrepresent the selected knowledge base |
| `vector` | Intended PgvectorEmbeddingRetriever external integration | None approved | Unsupported: no approved pgvector/resource constructor binding |
| `keyword-search` | Approved Live lexical API composition | None approved | Unsupported: the constructor validator does not bind the Live workspace/profile |
| `query-embedding` | Qualified local Live query embedding | None approved | Unsupported: no provider/model or admission initialization in constructor validation; accepts no model parameters |
| `dense-search` | Approved Live exact cosine API composition | None approved | Unsupported: qualified generation and workspace binding are owned by the Live API; only `topK` is a recognized parameter |
| `chunker` | `haystack.components.preprocessors.DocumentSplitter` | `documents` → `documents` in/out | `split_by=token`, `size` → `split_length`, `overlap` → `split_overlap`; no warm-up. Constructor requires installed tiktoken; absent dependency returns unsupported |
| `bm25` | `haystack.components.retrievers.in_memory.InMemoryBM25Retriever` | `query` → `query`; output `documents` → `documents` | `topK` → `top_k`; isolated empty `InMemoryDocumentStore(shared=False)`. `collection` is a bounded UI resource label only: no documents or knowledge-base lookup occurs |
| `joiner` | `haystack.components.joiners.DocumentJoiner` | `documents` → `documents` in/out | RRF mode, `topK` → `top_k`; actual input is variadic |
| `text-embedder` | `haystack.components.embedders.OpenAITextEmbedder` | `text` → `text`; `embedding` → `embedding` | Fixed supported Qwen profile label; constructor stores configuration and leaves sync/async clients unset |
| `document-embedder` | `haystack.components.embedders.OpenAIDocumentEmbedder` | `documents` → `documents` in/out | Fixed Qwen profile label, `batchSize` → `batch_size`; no credential resolution or client construction |

Evidence: core constructor implementations in `haystack/components/preprocessors/document_splitter.py`, `embedders/openai_text_embedder.py`, `embedders/openai_document_embedder.py`, `retrievers/in_memory/bm25_retriever.py`, and `joiners/document_joiner.py`; runtime socket metadata is checked against installed components in the validator tests. Additional real component outputs such as embedding `meta` are deliberately not exposed as UI handles in this revision. Component labels do not imply a deployed provider.

Default Workbench templates contain UI-only or unsupported nodes, so their authoritative result is **unsupported**. A supported complete example is BM25 → DocumentJoiner with an explicit BM25 `query` input. No generic components are invented to make templates appear valid.

## Safety and diagnostics

Pydantic rejects extra fields, executable/prototype keys, non-finite coordinates, malformed identifiers, unknown structural fields, duplicate IDs and missing edge endpoints before construction. Graph limits remain 100 nodes, 300 edges and a 1,000,000-byte HTTP body. Constructor parameters are allowlisted by kind; only fixed imports occur. Component objects are fresh per request; temporary BM25 stores are shut down. Telemetry is disabled for this isolated validation package.

Two concurrent admitted validations and sixty requests/minute bound local resource use. Request reads time out after five seconds. Constructors are deterministic bounded core code; there is no model warm-up, arbitrary code or external operation to cancel. Browser request cancellation prevents stale UI state; an admitted constructor-only request may finish and be discarded.

Stable issue codes: `UNKNOWN_COMPONENT_KIND`, `UNSUPPORTED_COMPONENT`, `INVALID_PARAMETER`, `EMPTY_GRAPH`, `INVALID_PORT`, `INCOMPATIBLE_SOCKET`, `INVALID_RUNTIME_INPUT`, `MISSING_REQUIRED_INPUT`. Issues optionally carry `nodeId`, `edgeId`, and `field`. No raw exception text or traceback is returned. HTTP errors use `INVALID_GRAPH`, `PAYLOAD_TOO_LARGE`, `LOCAL_REQUEST_REQUIRED`, `VALIDATION_BUSY`, `VALIDATION_TIMEOUT`, or `VALIDATION_ERROR`. Logs contain request ID, outcome, duration and issue codes, not graph content or parameter values.

No migration is needed. Portable graph file schema version remains 1. Stopping this service preserves offline graph editing/import and simulated preview, but authoritative validation becomes unavailable; there is no local-success fallback.

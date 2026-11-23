# TASK-UI-003 — Connect Workbench Documents to persisted uploads, chunks and jobs

**Created:** 2026-11-20  
**Updated:** 2026-11-23  
**Status:** PROPOSED — backend routes are implemented; Live Documents frontend integration remains to be built  
**Priority:** P1 · frontend integration and contract-compatibility gate  
**Dependencies:** [completed UI-001](completed/TASK-UI-001-typed-api-and-execution-mode.md), [completed UI-002](completed/TASK-UI-002-execute-live-lexical-pipeline.md), [completed EVAL-001](completed/TASK-EVAL-001-prove-vertical-slice.md), [completed RAG-002](completed/TASK-RAG-002-ingest-text-and-markdown.md), [completed CHUNK-002 Python](completed/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md); PDF is runtime-conditional via [CHUNK-003](TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md)  
**Repository snapshot inspected:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Target:** `tasks/TASK-UI-003-live-document-management.md`  
**Backend contract:** [`contracts.py`](../apps/workbench/api/contracts.py), [`ingestion_http.py`](../apps/workbench/api/ingestion_http.py), [OpenAPI](../apps/workbench/api/openapi.json)

## A. Title

**Implement the missing Live Documents frontend over the already implemented FastAPI document/upload/chunk/job API**, with precise runtime DTO decoding, approved upload formats, cursor and idempotency controls, and no Preview fixture fallback. This is a frontend/integration task; the backend endpoints it consumes already exist.

## B. Context / Problem

The previous blueprint described the document upload/detail/job API as **not implemented**. That premise is now false. [RAG-002 completed](completed/TASK-RAG-002-ingest-text-and-markdown.md), and Python AST ingestion is also [completed](completed/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md). The source under [ingestion_http.py](../apps/workbench/api/ingestion_http.py) exposes the real routes; [contracts.py](../apps/workbench/api/contracts.py) gives exact models. The missing delivery is the **React Live Documents experience and typed client methods**, not another backend writer.

The frontend is currently misleading in a different way: [App.tsx](../apps/workbench/web/src/App.tsx) renders `DocumentsView` only for Preview and a separate “Live document listing is not connected yet” placeholder for Live, while [DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx) consumes `PreviewDocument[]` fields which have **no equivalent** on a real list response (pages, size label, parser strings, full content and fake chunk snippets).

There are two distinct original-source capabilities: [LocalSources](../apps/workbench/api/local_sources.py) supports narrowly scoped, registered host-local file reveal; [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) and [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) will supply durable asset/evidence resolution later. **Neither implies byte-for-byte original download is provided by the current document detail route.**

The target task is therefore: keep Preview fully functional; make Live show exactly what PostgreSQL confirms; perform real uploads and active-chunk inspection through the shared client; and display distinct missing/partial/evidence status instead of inventing data.

## C. Current Repository State

### C1. Source inspection — verified current API, web entry points and tests

**Repository inspected:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`, 2026-11-23. The backend features in this table are **implemented**, not merely proposed by RAG-002. The Live Documents frontend is **not implemented** in the inspected snapshot.

| File / symbol | Existing verified behavior | Required UI action |
| --- | --- | --- |
| [`api/contracts.py`](../apps/workbench/api/contracts.py) `Features`, `CapabilitiesResponse`, `PdfIngestionCapabilities` | `features` exposes `documents/search/upload/document_details/jobs`; `pdf_ingestion` separately reports `available/text_layer/page_provenance/table_rows/original_evidence=false/ocr=false/visual_understanding=false/max_bytes=8388608/max_pages=32`. | Extend typed capabilities/decoder **without fabricating PDF/OCR or original asset support**. |
| [`api/application.py`](../apps/workbench/api/application.py) `_documents`, `_capabilities` | GET document list is real PostgreSQL; `limit=1..100`, cursor opaque and corpus-revision-bound. Capability upload requires service+schema+parser readiness; PDF depends additionally on pinned local assets. | Reuse; do not create second documents listing or assume `features.documents` authorizes writes. |
| [`api/ingestion_http.py`](../apps/workbench/api/ingestion_http.py) `IngestionRoutes.upload/detail/chunks/job` and `register_ingestion_routes` | **Existing** POST upload and GET detail, active chunks and job status. 201 new, 200 updated/unchanged/replayed. Chunk cursor invalidation yields 400 INVALID_CURSOR. | Use these routes verbatim; no new document REST family. |
| [`api/upload_transport.py`](../apps/workbench/api/upload_transport.py) `read_upload` | One file, strict multipart, header `Idempotency-Key` 8–128 `[A-Za-z0-9_-]`; optional `source_id` AND `expected_active_version_id` together. | Submit browser-owned multipart boundary; preserve operation key across uncertain retry. |
| [`api/upload_policy.py`](../apps/workbench/api/upload_policy.py) | Text/Python 1 MiB file limit; PDF candidate up to 8 MiB; 8 MiB+64 KiB total multipart guard. | Match verified formats and advisory client caps; never enable planned Office/CSV formats from extension alone. |
| [`api/parser_registry.py`](../apps/workbench/api/parser_registry.py) `parser_descriptors` | TXT, Markdown and Python are qualified. PDF `docling-pdf-r2` descriptor is qualified but availability depends on model assets/runtime; OCR and visual semantic understanding remain unavailable. Other formats are only catalogued, not qualified. | Allow `.txt/.md/.markdown/.py` per verified MIME rules; enable `.pdf` only if `pdf_ingestion.available=true`. Never claim arbitrary format support. |
| [`api/contracts.py`](../apps/workbench/api/contracts.py) `DocumentDetail`, `ActiveChunkPageResponse`, `IngestionResponse`, `IngestionJobResponse` | Real metadata: `processing_profile`, `processing_profile_fingerprint`, `document_processing`, `source_content_sha256`, `source_bytes`, `parsed_element_count`, `language_policy`, `parser`, `warnings`; chunk `order/content_hash/section_path/metadata/page?`; upload `replayed`; job `reserved_version_id/outcome/status/stage/timestamps`. | Decode fields with strict types and nullable/optional semantics, no `PreviewDocument` cast. |
| [`web/src/api/contracts.ts`](../apps/workbench/web/src/api/contracts.ts) | `BackendCapabilities.features` declares only `documents/search`; no typed upload/detail/job/chunk models; `ApiFailure` omits optional `error.job_id`. | Extend wire types additively. Do not change `rag-api-v1.0` revision without backend approval. |
| [`web/src/api/decode.ts`](../apps/workbench/web/src/api/decode.ts) | `decodeCapabilities` **drops** `upload/document_details/jobs/pdf_ingestion`, even when returned by backend; no document page/upload/detail/chunks/jobs runtime decoder. | Implement strict decoding and error `job_id`; capability false-closed if unavailable. |
| [`web/src/api/client.ts`](../apps/workbench/web/src/api/client.ts) `request` | Currently JSON-serializes `transport.body`, adds `Content-Type: application/json`, and rejects **all** successful statuses except 200. No document methods, multipart or upload timeout up to PDF duration. | Extend shared transport to support `FormData` and **201** for upload without regressing JSON or search; no second generic fetch inside view. |
| [`web/src/App.tsx`](../apps/workbench/web/src/App.tsx) | Preview Documents uses fixtures; Live shows explicit “not connected” placeholder. Workbench mode and authorized workspace supplied by existing `useBackendDiscovery`; `useLiveSearch` already handles abort/stale search. | Route a mode-discriminated Documents component and reuse scope/mode controller. |
| [`web/src/views/DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) | Fixture-only `PreviewDocument[]`, local filter and status + content/chunks/report tabs. | Reuse table and tabs, add real Live states and upload. Do not create a competing Live page. |
| [`web/src/components/sourceFiles.ts`](../apps/workbench/web/src/components/sourceFiles.ts), [`api/local_sources.py`](../apps/workbench/api/local_sources.py) | Version-scoped optional registered **local-file reveal** with guarded operating-system behavior; not general evidence storage. | Optional “Reveal in Explorer” only when `can_reveal` true for exact source/version. Never treat hint as original asset bytes. |
| [`api/tests/test_ingestion_routes.py`](../apps/workbench/api/tests/test_ingestion_routes.py), [`test_pdf_ingestion.py`](../apps/workbench/api/tests/test_pdf_ingestion.py), [`test_local_sources.py`](../apps/workbench/api/tests/test_local_sources.py) | Executable tests for real upload/replace/replay/errors, PDF candidate and local file hint. | Reuse as backend source of truth; add browser tests, not duplicate SQL ranking logic. |

### C2. Concrete contract drift and failures it would cause

1. **Stale precondition:** the old task says backend POST/detail/chunks/jobs are absent. They are implemented. Following the old blueprint could create duplicate API handlers/tables.
2. **Frontend capability loss:** `decodeCapabilities` discards real `features.upload`, `document_details`, `jobs` and `pdf_ingestion`; a UI that trusts the old frontend DTO would incorrectly disable qualified upload or might infer it from read-only listing.
3. **Transport incompatibility:** `client.request` forces JSON and checks `response.status !== 200`. A naïve `FormData` call will send the wrong wire body, and a genuine POST 201 will be misclassified as invalid backend response. **This must be fixed before UI upload.**
4. **Unsupported source types:** old spec assumes only TXT/Markdown; Python AST is already qualified and PDF text-layer parser is conditionally qualified. Office/CSV/YAML from pending PARSE tasks are not.
5. **Incorrect chunk schema:** `ActiveChunkItem` has `chunk_id`, `order`, `content`, `content_hash`, `page?`, `section_path[]`, `metadata{}`. `source_version_id` belongs to the **page envelope**, not to every chunk. Creating `chunk.sourceVersionId` as a required wire field causes decoder failure on valid backend response.
6. **Misleading provenance:** `DocumentDetail.original_content_available` is currently `false`. A local source `can_reveal` hint is not a binary download. Original Asset/Evidence APIs must be implemented separately.
7. **OpenAPI detail caveat:** [ingestion_http.py](../apps/workbench/api/ingestion_http.py) still has historical multipart description “One UTF-8 TXT or Markdown, at most 1 MiB” despite qualified Python and conditionally qualified PDF. **The request schema is correct but its prose is stale**; fix this documentation-only inconsistency in a small backend API-doc patch, with a schema regression test. UI must follow runtime capabilities, not that obsolete prose.
8. No new actual browser E2E was run for this audit; these are source-proven contract mismatches and prospective UI failure modes, not observed production outage counts.

## D. Goal

In **Preview**, Documents remains the existing deterministic fixture experience. In **Live**, the user sees only authorized PostgreSQL source rows, real source/version/parser/chunk metadata and durable job information; uploads TXT, Markdown and Python, plus PDF **only when runtime-available**; retries uncertain network operations with the same idempotency key; and verifies new source discoverability through the existing Live PostgreSQL FTS pipeline.

When the service, storage, decoder or format capability is unavailable, the UI shows the accurate error/unsupported state without injecting fixtures, fake pages, fabricated source bytes or fake progress.

A previously indexed real source remains visible across browser/API/DB restart on the same persistent volume. The new UI does not claim semantic embeddings, original asset storage, OCR, visual graph understanding, asynchronous workers, production multi-tenant authentication or model-based answer generation.

## E. Scope

- Extend the shared typed client and `decodeCapabilities` to cover **existing server** document/read/write, parser and job DTOs and `error.job_id`.
- Add the actual document routes and multipart transport: `listDocuments`, `getDocumentDetail`, `listActiveChunks`, `uploadDocument`, `getIngestionJob`, with source/version-safe optional `getLocalFile` reuse.
- Refactor the existing DocumentsView (no duplicate page) using discriminated Preview/Live props and one state owner `useLiveDocuments` or an equivalent tested hook, with workspace/mode/corpus revision and abort generation boundaries.
- Implement real list/cursor paging, selection/detail/chunks, actual processing report/warnings and bounded page/meta presentation.
- Upload one file via same-origin multipart with idempotency and guarded update; conditionally allow runtime PDF and show real parser scope. A single request represents synchronous publication; do not invent progress percentages or queue polling.
- Show real terminal `job_id`, `reserved_version_id`, `outcome`, timestamps and error `job_id` when available; job fetch is **by ID**, not a nonexistent global jobs list.
- Optional registered local source hint: reuse existing sourceFilesRequests and strict local-only reveal contract; no original blob download.
- Build frontend decoder, controller, upload/HTTP, security and real browser/PostgreSQL tests. Update Workbench README and (separately) stale OpenAPI prose without altering backend business behavior.

## F. Non-Goals

- No backend source writer/migration/independent ingestion implementation; RAG-002 and PDF parser are already implemented at their respective qualification levels.
- No PDFs scanned/OCR, Mermaid graph extraction or image asset visualization; those are CONTENT/CHUNK successors. This UI may display metadata such as `visual_processing_status=incomplete` **only** when returned.
- No original content download endpoint: current detail `original_content_available=false`; CONTENT-001/005 + EVIDENCE-001 own future secure original asset serving.
- No unsupported DOCX/PPTX/HTML/XLSX/CSV/YAML/EML uploads until their separately qualified PARSE tasks and capability handshake exist.
- No background queue/202 processing or fake percentage; current endpoint is synchronous 201/200; server job records can be inspected separately.
- No duplicate generic fetch wrapper, new global UI state library, provider SDK in React, new SQL source registry or arbitrary Haystack graph execution.
- No cross-workspace auth editor; current server supports only authorized development scope.

## G. Architecture / Boundaries

**Ownership:** FastAPI `contracts.py` and `ingestion_http.py` are the wire authority; `PostgresPersistence` is source/index authority; shared `web/src/api/client.ts` owns HTTP and `decode.ts` runtime validation; `useLiveDocuments` owns request lifecycle; `DocumentsView` owns accessible presentation. Existing `App.tsx` owns Preview/Live and server-returned workspace selection.

```text
App.ExecutionMode
  ├─ Preview -> DocumentsView(previewDocuments) : fixture-only
  └─ Live -> useLiveDocuments(serverWorkspace, capabilities)
               -> shared typed client (/api/v1)
                    GET /workspaces/{workspace}/documents
                    GET /workspaces/{workspace}/documents/{source}
                    GET /workspaces/{workspace}/documents/{source}/chunks
                    POST /workspaces/{workspace}/documents (multipart)
                    GET /workspaces/{workspace}/jobs/{job}
               -> current FastAPI IngestionRoutes -> PersistencePort -> PostgreSQL
               -> existing LiveSearch for uploaded unique-term verification

Registered host-local original hint -> existing SourceFilesRequests
Original immutable assets / evidence -> future CONTENT-001/005, NOT this task
```

- API response envelope `contract_revision=rag-api-v1.0` remains unchanged.
- Workspace source/version and RLS authorization remain server-owned; filenames and UI metadata are never access tokens.
- Source/detail/chunk/job decoders reject wrong identity, missing required fields, invalid status/time/number or contradictory corpus revision; frontend never converts valid `null` page into page 0/1.
- Cancellable UI requests must be invalidated by a **generation token** as well as AbortController because some test transports ignore abort.
- Idempotency key survives a retried **same operation**; it is not a per-attempt value. Local fetch cancellation does not guarantee backend rollback.

## H. Contracts / Interfaces / Data Model

### H1. Existing HTTP API contract — not proposed

| Method | Exact existing path | Response | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/capabilities` | `CapabilitiesResponse` | `features.documents/search/upload/document_details/jobs`; `pdf_ingestion` separate, runtime qualified |
| GET | `/api/v1/workspaces` | `WorkspacePage` | Only authorized development workspace now |
| GET | `/api/v1/workspaces/{workspace_id}/documents?limit=50&cursor=...` | `DocumentPage` | 1..100 limit; opaque revision-bound cursor |
| POST | `/api/v1/workspaces/{workspace_id}/documents` | `IngestionResponse` | Multipart; **201 new**, **200 updated/unchanged/replayed** |
| GET | `/api/v1/workspaces/{workspace_id}/documents/{source_id}` | `DocumentDetail` | Real metadata, no original bytes |
| GET | `/api/v1/workspaces/{workspace_id}/documents/{source_id}/chunks?limit=50&cursor=...` | `ActiveChunkPageResponse` | 1..100; active version only; 400 INVALID_CURSOR |
| GET | `/api/v1/workspaces/{workspace_id}/jobs/{job_id}` | `IngestionJobResponse` | Last durable state by ID only, not global queue |
| GET | `/api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file` | `LocalSourceFileResponse` | Optional registered host-local hint, no byte response |
| POST | `.../local-file/reveal` | `RevealSourceResponse` | Local guarded native behavior, no remote evidence download |

Use [OpenAPI](../apps/workbench/api/openapi.json), [contracts.py](../apps/workbench/api/contracts.py) and [ingestion_http.py](../apps/workbench/api/ingestion_http.py) as authoritative. **Do not add a new API route family.**

### H2. Exact wire DTOs and browser view models

**DocumentPage:** `contract_revision,request_id,trace_id,workspace_id,corpus_revision,items[{source_id,title,media_type,status:"ready"|"processing"|"error",active_version_id?,chunk_count,updated_at,error_code?}],next_cursor`.

**DocumentDetail:** common Meta + `workspace_id,corpus_revision,source_id,title,media_type,status,active_version_id,chunk_count,updated_at`; optional `processing_profile:JsonValue map|null`, `processing_profile_fingerprint`, `ingestion_policy_revision`, `language_policy ("unqualified_source_locale"|"configured_sentence_language"|"configured_structural_boundaries"|null)`, `default_language ("en"|"ru"|null)`, `document_processing:JsonValue map|null`, `source_content_sha256`, `source_bytes`, `parsed_element_count`, `parser:JsonValue map|null`, `warnings[]`; **`original_content_available=false`**. Do not assert `original_content_available=true` based on any local reveal hint.

**ActiveChunkPageResponse:** `workspace_id,source_id,source_version_id,corpus_revision,items[{chunk_id,order,content,content_hash,page?,section_path[],metadata{}}],next_cursor`. `source_version_id` is **PAGE-LEVEL**, not an `ActiveChunkItem` field. `metadata` is a server-allowlisted JSON object that can include heading, section, page/bbox, AST symbol, token policy, PDF processing/warning and `original_excerpt`; do **not** treat metadata content as sanitized HTML or a verified original binary.

**IngestionResponse:** `workspace_id,source_id,source_version_id,job_id,outcome:"created"|"updated"|"unchanged",status:"completed",chunk_count,corpus_revision,stages[{stage:"parsing"|"chunking"|"publication",duration_ms}],replayed:boolean`.

**IngestionJobResponse:** `workspace_id,job_id,source_id,source_version_id|null,reserved_version_id,status/stage:"pending"|"parsing"|"chunking"|"publishing"|"completed"|"failed",retryable,error_code|null,chunk_count|null,outcome|null,created_at,updated_at,finished_at|null,stages[]`.

**ErrorResponse:** nested `error.code,message,retryable,http_status,run_id?,job_id?,fields?` plus `request_id,trace_id` (correlate `X-Request-ID`). A client abort/network failure **has no authenticated server ID** and must not invent a job ID or claim abort rolled back publication.

Frontend models should be separate discriminated `PreviewDocument` vs `LiveDocumentItem/Detail/Chunk/UploadOperation` and retain source IDs/corpus revision in the Live view context. Do not map a real `ready` into “embedded” or “fully multimodally understood”; it means current **lexical ingest** publication was confirmed.

### H3. Multipart transport and idempotency

Browser sends `FormData` with `file` and optional **both** `source_id` and `expected_active_version_id`, plus required `Idempotency-Key: [A-Za-z0-9_-]{8,128}` generated with `crypto.randomUUID()` (or equivalent secure operation ID). Browser MUST NOT set `Content-Type: multipart/form-data` manually; browser supplies boundary.

Existing shared `client.request` is JSON-only and `response.status !== 200` is currently treated as invalid success. Extend it **without weakening JSON/configuration/search behavior**: allow `FormData` passthrough only for this approved route, keep `Accept: application/json`, and allow HTTP 201 **only** where exact upload client contract authorizes it. Use a separate bounded upload timeout: base JSON request is 5 seconds and `timeoutMs` constructor currently caps at 60 seconds, whereas qualified PDF backend may run up to ~210 seconds. Explicitly choose/document an upload timeout at or above backend PDF deadline (e.g. 240 seconds) without extending ordinary search timeouts; unknown network outcome must be recoverable through same-key retry.

The operation stores the initial `File` object and key in memory until definitive outcome. Same-key + same request parameters replay must return same job/version (and `replayed=true`), with **no duplicate active version**. Same-key changed bytes/fields gives 409 IDEMPOTENCY_CONFLICT; stale `expected_active_version_id` gives 409 VERSION_CONFLICT. `status=completed` on HTTP response only after commit; no fake 202/background queue.

### H4. Format capability policy (current implementation)

| Format | Backend qualification | Initial Live UI gate |
| --- | --- | --- |
| `.txt` (`text/plain`) | Qualified | Allow if `features.upload` true; <=1 MiB |
| `.md`, `.markdown` (`text/markdown`, approved text aliases) | Qualified | Allow if `features.upload` true; <=1 MiB |
| `.py` (`text/x-python`/approved MIME aliases) | Qualified | Allow if `features.upload` true; <=1 MiB, AST source shown with line references |
| `.pdf` (`application/pdf`) | Text-layer Docling parser qualified **when runtime models available**, 8 MiB/32 pages; no OCR/visual semantic claims | Allow only if `features.upload && pdf_ingestion.available`; show text-layer-only and `original_evidence/ocr/visual_understanding=false`. Display parser warnings and incomplete visual coverage. |
| `.docx/.pptx/.html/.xlsx/.csv/.json/.yaml/.eml/.srt/.vtt` | Catalogued or under review, but not qualified today | **Disabled until separately completed PARSE-002..005 and explicit runtime capability**; no extension-only opt-in. |

The current `CapabilitiesResponse` does not publish a generalized list of all upload formats; for this release the explicit app-supported allowlist above must be reviewed against [parser_registry.py](../apps/workbench/api/parser_registry.py) and covered by integration tests. A future general `supported_upload_formats` discovery contract is a **separate, additive backend/API task**, not a field the frontend may invent now. If new parser formats become qualified before UI implementation, update this task and tests first.

### H5. Cursor, list filtering and job behavior

Document list cursor is signed and bound to current workspace/corpus revision; chunk cursor is bound to workspace, source and corpus revision. Treat as opaque, `limit` 1..100 (default 50), max cursor length 512. On 400 INVALID_CURSOR discard prior loaded pages and restart first page **once** with visible notice. Do not append a page from a different `corpus_revision` or show old selected chunks after source version change.

The current API provides no server-side title search for document listing and **no paginated jobs history route**. A title/status filter operates only on loaded pages; explicitly label `Filter loaded documents`. Job status is available only by a known `job_id` from upload/error/session context.

### H6. Error and error-state matrix

| Trigger | Existing response | UI requirement |
| --- | --- | --- |
| Successful no documents | HTTP 200 `items:[]` | Honest Live empty state, no fixtures |
| Upload new/update/replay | 201/200 + terminal `IngestionResponse` | Validate `source_id/version/job/replayed`, refresh list and active selection |
| Invalid file or multipart / missing key / wrong update fields | 400 safe code | Field correction; no automatic new operation key |
| Unsupported MIME/extension | 415 | Show allowed qualified formats |
| Too many bytes | 413 | Show actual per-format bound |
| Foreign/missing workspace/source/job | 404 (safe) | No foreign content or existence leak |
| Stale expected source version / same key different payload | 409 | Explicit re-fetch, no blind overwrite |
| Expired/tampered cursor | 400 INVALID_CURSOR | Clear/restart first page once |
| Busy/limited capacity | 429 when returned | Honor retryable and no fake progress |
| DB/service dependency unavailable | 503 | Live error, optional explicit retry, no Preview fallback |
| Deadline | 504 | Local outcome may remain unknown; consult known `job_id` or retry same operation/key |
| Transport cancel/offline after POST | No guaranteed server outcome | Show `outcome unknown`; no claim of persisted FAILED or cancellation |
| Valid HTTP 200/201 with wrong contract | Decoder error | `CONTRACT_MISMATCH`, never partly populate UI fields |

All server errors preserve actual `error.job_id` and trace/request IDs if provided; unsupported capability must fail **before** expensive network submission.

## I. Repository Files / Components Impacted

| Repository file | Required action |
| --- | --- |
| [`web/src/api/contracts.ts`](../apps/workbench/web/src/api/contracts.ts) | MODIFY: add `features.upload/document_details/jobs`, `PdfIngestionCapabilities`, `IngestionResponse`, `DocumentDetail`, `ActiveChunkPageResponse`, `IngestionJobResponse`, optional `error.job_id`. Preserve existing search wire type. |
| [`web/src/api/decode.ts`](../apps/workbench/web/src/api/decode.ts) | MODIFY: robust runtime decoding and independent validation of new capability/DTOs; do not discard feature flags. |
| [`web/src/api/client.ts`](../apps/workbench/web/src/api/client.ts) | MODIFY: add five real document methods; bounded form transport and 201 permitted only for upload; reuse `request`, correlations, timeouts and AbortController. |
| [`web/src/hooks/useBackendDiscovery.ts`](../apps/workbench/web/src/hooks/useBackendDiscovery.ts) | READ/MODIFY minimally: server-owned workspace and capabilities are sole Live authority; don't duplicate GET capabilities. |
| [`web/src/hooks/useLiveSearch.ts`](../apps/workbench/web/src/hooks/useLiveSearch.ts) | READ/reuse stale-run control pattern, no duplicate lexical logic. |
| `apps/workbench/web/src/hooks/useLiveDocuments.ts` | **CREATE** (unless existing equivalent at implementation start): mode/scope-bound list/detail/chunks/job/upload operations, abort/generation, cursor and errors. |
| [`web/src/App.tsx`](../apps/workbench/web/src/App.tsx) | MODIFY: replace Live “not connected” placeholder with mode-aware DocumentsView and shared state, keep Preview and other pages. |
| [`web/src/views/DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) | MODIFY: reuse table/tabs/search and accessible headings; real documents in Live, separate Preview fixture UI. |
| [`web/src/views/views.css`](../apps/workbench/web/src/views/views.css) and [`web/src/styles.css`](../apps/workbench/web/src/styles.css) | MODIFY minimal tokens/styles; no palette reset. |
| [`web/src/components/sourceFiles.ts`](../apps/workbench/web/src/components/sourceFiles.ts) | REUSE only for optional registered host-local source hint/reveal; do not equate with CONTENT evidence download. |
| `apps/workbench/web/src/api/documents.test.ts`, `src/hooks/useLiveDocuments.test.ts`, `scripts/live-documents-smoke.js` | **CREATE** contract, race, upload/timeout, real browser/API/PostgreSQL tests. |
| [`web/src/api/client.test.ts`](../apps/workbench/web/src/api/client.test.ts), [`web/src/api/sourceFiles.test.ts`](../apps/workbench/web/src/api/sourceFiles.test.ts) | EXTEND existing JSON transport/local hint regression where needed. |
| [`api/ingestion_http.py`](../apps/workbench/api/ingestion_http.py) `register_ingestion_routes` | **Docs-only conditional patch:** correct outdated OpenAPI multipart prose listing only TXT/Markdown, with strict schema test; no upload behavior change in frontend task. |
| [`api/tests/test_ingestion_routes.py`](../apps/workbench/api/tests/test_ingestion_routes.py), [`test_pdf_ingestion.py`](../apps/workbench/api/tests/test_pdf_ingestion.py), [`test_local_sources.py`](../apps/workbench/api/tests/test_local_sources.py) | RUN existing API/Postgres test baselines; no duplicate SQL writer. |
| [`api/openapi.json`](../apps/workbench/api/openapi.json), [`web/README.md`](../apps/workbench/web/README.md), [`durable-text-ingestion.md`](../docs-website/docs/architecture/durable-text-ingestion.md) | UPDATE generated schema only for docs correction and frontend operator guide; backend contract is already published. |

**MUST NOT modify:** `haystack/` core, applied migrations `0001/0002`, `PostgresPersistence._publish` transaction owner, embedding model service, PDF/OCR/VLM workers, ranking profile, other parser adapters, `previewDocuments` fixture contents or unsupported workspace authorization. If new API endpoints or generic format discovery become necessary, amend this A–O task **before** implementing them.

## J. Implementation Requirements — ordered blueprint

### J1. Freeze actual backend/CI and frontend contract drift

1. Read [contracts.py](../apps/workbench/api/contracts.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [application.py](../apps/workbench/api/application.py) and their OpenAPI exports. Confirm `rag-api-v1.0`, all five methods, `pdf_ingestion`, local-source hint and true 200/201/4xx states. Inspect the current `parser_registry` and built runtime for PDF qualification; do not infer from filename alone.
2. Run existing `test_ingestion_routes.py`, `test_pdf_ingestion.py` and `test_local_sources.py` against a **disposable** DB/asset environment; record actual output. If they fail, classify backend defect separately instead of adding a duplicate server implementation.
3. Inspect current [App.tsx](../apps/workbench/web/src/App.tsx), [DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx), client and decoder. Snapshot current Preview document interactions and status filters. The source confirmed the Live placeholder and missing multipart support; do not claim UI3 is implemented.

**Gate:** backend contract and tested formats are the authority; the work list excludes reinventing REST/SQL routes.

### J2. Extend shared typed contracts and runtime decoders

1. Add `BackendCapabilities.features.{upload,document_details,jobs}` and `pdf_ingestion` with runtime validators. Validate Boolean flags, max_bytes/max_pages, false-only OCR/visual/original-evidence fields while those types are `Literal[False]`. Missing required keys in valid backend v1 must fail `CONTRACT_MISMATCH`; unsupported future additions may be ignored only as explicitly additive fields.
2. Add strict wire DTOs as listed in H2, preserving snake_case at network boundary and only camelCase in UI view-model adapters. The `ActiveChunkItem` decoder takes source version from its **envelope**, not a nonexistent per-item key; require `content_hash` and `order`.
3. Parse `DocumentDetail.processing_profile/document_processing/parser` as bounded unknown JSON, not uncontrolled arbitrary React markup. Display only approved fields with safe values. Preserve actual `source_bytes` optional or unknown; do not invent size from chunk count.
4. Decode `ErrorResponse.error.job_id` when server supplies it; preserve `request_id/trace_id`, match `X-Request-ID` from response. Client-side abort does not fabricate a server job/trace.
5. Type tests for extra backend fields, missing/null `page`, optional `parser`, unknown `language_policy`, `replayed`, empty list, invalid timestamps, negative/nonfinite stage timings and wrong workspace/corpus identity.

**Gate:** every valid backend fixture decodes; malformed success cannot be rendered as partial Live.

### J3. Extend JSON request transport for upload without breaking existing routes

1. Reuse `createWorkbenchApiClient` and existing `request` helper; add a transport discriminant for JSON vs `FormData`. Keep other routes using `application/json` and status 200. For multipart do **not** `JSON.stringify` or set `Content-Type`; let browser supply boundary and send `Accept:application/json`.
2. Permit **201/200** only for `uploadDocument`. Validate both status and `IngestionResponse.outcome`; a `200` with `outcome=created` and `replayed=false` should be flagged inconsistent, as should `201` with replayed=true. Preserve `response.headers X-Request-ID` matching.
3. Add exact resource-ID validation/encoding and query `URLSearchParams` with `limit=1..100`, opaque cursor (max 512). Client provides `listDocuments/getDocumentDetail/listActiveChunks/getIngestionJob/uploadDocument` and optional existing `getLocalFile`, not new arbitrary URL access.
4. Use a dedicated bounded `uploadTimeoutMs` that can cover the server PDF path (~210 s) without widening general 5 s JSON or 15 s search, with an explicit max (e.g. 240 s). Failed fetch after POST may mean server committed, so show uncertainty and preserve same-key retry.
5. Unit tests capture real `FormData` instance/header (must have NO manual multipart content type), POST return 201, replay 200, per-format cap, 429/503/504/transport/abort and malformed content type; verify existing configuration PUT/search JSON unaffected.

**Gate:** browser network inspector shows one correctly formed multipart POST and accepted 201 without a second duplicated client implementation.

### J4. State and workspace/cursor/version lifecycles

1. Add one `useLiveDocuments` controller that accepts server `workspaceId`, mode, capabilities and client. Model `loading/ready/empty/unavailable/error`, loaded pages, pending detail, selected source/version, active chunk pages, job by known ID and last upload operation.
2. Entering Live triggers initial authorized GET list once; switching workspace/mode, changing profile/corpus or leaving page invalidates all list/detail/chunk results via `AbortController` plus monotonic request generation. No stale Live data may display in Preview and vice versa.
3. For document list use keyset opaque `next_cursor`, add pages only with matching `workspace_id/corpus_revision`, dedup `source_id` by one snapshot; do not report loaded count as full corpus count. Local filter must be called “Filter loaded documents” when more pages exist.
4. Detail fetch and chunk page fetch are independent; opening source B while A pending must never display A's chunk content under B. If active_version_id changes on refresh, clear existing chunk pages and reselect verified source version.
5. On `400 INVALID_CURSOR`, clear old pages/cursor and refetch page one **once**, with safe visible notice. On new publication refresh first list and selected source, not append stale pages to a new corpus revision.
6. Job fetch is **by explicit job_id only**; do not create fake job history, do not continuously poll a synchronous upload. If a known job ID appears on error, allow explicit status inspection/retry.

**Gate:** race tests for stale workspace/source/version, pagination restart and server outage demonstrate zero cross-scope content.

### J5. Preserve existing DocumentsView and truthful metadata

1. Refactor the **existing** [DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx) to accept discriminated `Preview` and `Live` model. Keep table, filter, tabs, keyboard navigation and current palette; label PREVIEW and LIVE explicitly.
2. Preview stays `PreviewDocument[]` with existing fake docs and statuses. Live table uses actual `DocumentPage.items`: `source_id`, `title`, `media_type`, `ready/processing/error`, actual `chunk_count`, `updated_at`; show `size` only when `DocumentDetail.source_bytes` actually exists.
3. Live Content tab becomes **Indexed text** (actual chunks) and never claims original file exact bytes. Chunk tab shows actual chunk content, `chunk_id`, `order`, `content_hash`, `section_path`, optional 1-based page and allowlisted `metadata`, plus Load more.
4. Report tab presents actual `processing_profile`, parser ID/revision, `language_policy`, default language, PDF `visual_processing_status` and `original_evidence_status` if present, warnings and measured stages only. If a property is absent, show “Not reported”; never invent Docling pages/false OCR.
5. For exact registered **local** original, optionally reuse [SourceFilesRequests](../apps/workbench/web/src/components/sourceFiles.ts) with current source_version and separate local reveal hint. If `can_reveal=false`, do not show a clickable fake file. Do not call this a downloadable original or CONTENT Evidence API.
6. Render source title, Markdown, JSON metadata and Mermaid-like text as inert React text without `dangerouslySetInnerHTML` or network URL execution. Include accessible empty/loading/errors with ARIA live regions and focus restoration.

**Gate:** Live never reads `previewDocuments` and required `DocumentDetail.original_content_available=false` is never misrepresented.

### J6. Implement bounded upload, replacement and truthful job status

1. Display Upload only when `mode=live`, authorized workspace known and `features.upload=true`; allow `.txt/.md/.markdown/.py` with appropriate MIME and 1 MiB advisory bound. PDF additionally requires `pdf_ingestion.available=true`, 8 MiB/32-page backend enforced; show text-layer-only limitation. Other formats are intentionally disabled.
2. User confirms upload; generate one secure `Idempotency-Key` and preserve it with the file and operation until terminal success/failure or explicit new file choice. Prevent accidental double-click duplicate submits. On uncertain network outcome offer same-key retry, never mint a replacement key for same bytes blindly.
3. For replacement, require existing source ID and its **current** `active_version_id`; submit both form fields. On `409 VERSION_CONFLICT` refresh authoritative detail and ask for explicit new user action; do not overwrite silently. On `409 IDEMPOTENCY_CONFLICT`, explain same-key different payload.
4. Do not show simulated `Preparing 67%`. While synchronous POST pending, show an **indeterminate** stage. On validated 201/200 terminal `IngestionResponse`, display `outcome`, `replayed`, source/version/job ID, real `chunk_count` and measured `stages`; refresh first list and selected detail/chunks.
5. For `error.job_id` or known completed upload job allow explicit `GET /jobs/{job_id}`, showing `reserved_version_id`, `source_version_id`, `status/stage`, last-confirmed timestamps and retryability; it does not mean there is a distributed worker.
6. Offer “Search this source” into **existing approved Live lexical** pipeline for unique identifiers, verifying returned `source_id`/`source_version_id`. Avoid duplicating search SQL in Documents.
7. On user Stop or navigation during POST, display “Request stopped locally; server outcome may be unknown.” Do not declare job FAILED or upload rolled back unless backend confirms; no leaked File bytes in logs/localStorage.

**Gate:** fresh TXT/MD/Python uploads and PDF (only when runtime qualified) create real persistent rows, and same-key retry never creates another source version.

### J7. Contract-doc correction, tests, evidence and safe rollback

1. Fix only stale descriptive upload OpenAPI text in [ingestion_http.py](../apps/workbench/api/ingestion_http.py): it currently says TXT/Markdown <=1 MiB even though Python and optional PDF are accepted. Keep transport/body structure and security unchanged; regenerate [openapi.json](../apps/workbench/api/openapi.json) and add schema test. If backend source moved, revise task Section I first.
2. Add detailed frontend tests and the real browser smoke, run source in a **disposable PostgreSQL** database with explicit seed and pinned PDF assets where qualified. Never use `docker compose down -v` or re-run demo seed against user data. Capture HTTP source/job/version/chunk IDs.
3. Test signed cursor mismatch, malformed 201/200, POST already committed then browser network abort, wrong workspace, PDF capability false, 8 MiB candidate file, invalid MIME, 413/415/400/404/409/429/503/504, XSS, local hint unavailable and Preview regressions.
4. Run full frontend typecheck/format/test/build, existing Preview/validator Live search smokes and backend ingestion/PDF/source tests. Record actual command outputs, NOT TESTED where environment absent.
5. Update [Workbench README](../apps/workbench/web/README.md) with exact startup/scope, files/limits, idempotent retry, synchronous jobs, original download limitations, user-visible warnings and rollback.

**Gate:** all measurable acceptance criteria and reports pass; no false status based on spec-only source review.

## K. Security / Governance / Observability

- Tenant authorization remains server-owned and reinforced by forced PostgreSQL RLS; browser workspace label is not an access token. The current deployment is `single_workspace_dev`, not authenticated multi-tenant.
- Persisted documents, chunks, Python code and PDF metadata are **untrusted data**; render escaped, no embedded HTML/scripts or unsafe links; never run uploaded Python, Mermaid or document code.
- No filenames, source bytes, chunk text, DSN, credentials, token vectors, original assets or stack traces in browser logs/telemetry. Show only safe `request_id/trace_id/job_id/source_id` and server `error.code`.
- Client file validation is advisory; the backend enforces actual max bytes/MIME, key, timeout and source update ownership.
- A fetch abort is local; the server could still publish. Safe retry reuses operation key, no auto new-key flood.
- LocalSourceFile reveal is guarded for a registered host file and exact source/version, **not** CONTENT-001/005; remote PDF/image evidence is a separate feature.
- Scope is mode/workspace/source/version/corpus revision, with controller abort+generation checks. Revoke any created object URLs and clear private File/Chunk data on scope change.
- If a future server exposes dynamic format discovery, backend owns it; until then do not infer Office/CSV capabilities from installed Haystack converters.

## L. Testing / Evaluation / Runtime Verification

### L1. Repo-scoped commands and preconditions

Use the existing [API README](../apps/workbench/api/README.md) and [database runbook](../docs-website/docs/architecture/postgresql-foundation.md); test upload against an **isolated disposable** database and temporary resources. Existing API tests must be run, not rewritten. Example commands from repository root:

```powershell
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types

Set-Location apps/workbench/web
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
```

Do not claim these commands passed until actually executed. For browser E2E use the current Playwright script pattern in [web/scripts](../apps/workbench/web/scripts/live-evaluation-smoke.js); implement `live-documents-smoke.js` and record browser/network/SQL parity with sanitized fixture inputs.

### L2. Mandatory contract/unit/security test matrix

| Case | Stimulus | Observable result |
| --- | --- | --- |
| Capabilities decoder drift | Backend reports `features.upload/document_details/jobs` and `pdf_ingestion` | Frontend typed flags present; no silent drop; PDF gate respects `available` |
| Shared HTTP JSON unchanged | Existing search/configuration request | `Content-Type:application/json`, HTTP 200 decoder and search semantics unchanged |
| Multipart 201 | TXT upload `FormData` | No manually set multipart Content-Type, accepted `201` + `created` body |
| Replay 200 | Same bytes/key/fields | `replayed=true`, same source/version/job/count and no duplicate publication |
| Guarded update | Correct source + expected active version | Real 200 updated/unchanged; changed source only after commit |
| Invalid op | File too large, wrong MIME/UTF-8, missing key, only one update field | 413/415/400, no fake success or mutation |
| Conflicts | Same key/different bytes, stale expected version | 409 with safe code; no automatic overwrite |
| PDF readiness | Assets present vs missing | Upload gated by `pdf_ingestion.available`; text-layer-only, no invented OCR |
| No documents | 200 with `items=[]` | Live empty, no `previewDocuments` |
| List pagination | Two pages same revision and 400 invalid cursor | Stable IDs/order, old pages cleared and first page fetched once |
| Detail active version | Switch selected A to B while A pending | No stale A content under B; actual metadata and optional fields only |
| Chunk metadata | Python AST line range, PDF page/bbox, Markdown heading | Actual `order/content_hash/section_path`; page optional, no false per-item version |
| Job status | GET known `job_id` | `reserved_version_id`, outcome/status/timestamps correct; no global history invented |
| Error `job_id` | Server error with nested `error.job_id` | Decoder retains job ID/correlation; local network errors invent none |
| Local original hint | Registered file / missing file | Optional version-scoped reveal through existing client only; not binary download |
| Unsafe source text | Markdown/HTML/JS-like source titles/chunks | Render inert text, no JS or URL exfiltration |
| Async stale state | Mode/workspace/source/corpus revision switch while request pending | Abort+generation prevents stale commits or cross-workspace leakage |
| Backend outage | 503, malformed 200/201, offline, timeout, canceled POST | Truthful Live status, no auto-switch/fake job cancellation |
| Existing regressions | Original Preview, validation-only API and Live keyword | All relevant tests remain green |

### L3. Real E2E evidence

Upload at least TXT, Markdown and Python via browser against disposable PostgreSQL; add **PDF only when `pdf_ingestion.available` and correct pinned assets are present**. For each supported file capture status, request/trace IDs, operation key hash (NOT key secret), job/source/version IDs, chunk IDs/count/hashes, reported parser/processing profile, `corpus_revision` and matching Live lexical result IDs. Restart API and database **without deleting the volume**, verify same source/version and job. Negative mocked browser fault injection must be reported separately from real API/DB outage evidence. Measure browser network duration separately from server `stages[].duration_ms`.

## M. Acceptance Criteria

- [ ] [RAG-002](completed/TASK-RAG-002-ingest-text-and-markdown.md) and actual API `IngestionRoutes` are **reused**; no second backend upload/details/chunks/jobs implementation or document store.
- [ ] `BackendCapabilities` and runtime `decodeCapabilities` preserve `upload/document_details/jobs/pdf_ingestion` and fail closed on invalid data; `rag-api-v1.0` remains the server contract.
- [ ] Shared frontend request helper handles **FormData** and success **201 for upload only**, while existing JSON/search/configuration/client errors remain unchanged.
- [ ] Typed `DocumentDetail`, `ActiveChunkPageResponse`, `IngestionResponse`, `IngestionJobResponse` and nested `error.job_id` decoders agree with actual Pydantic schema; no fictitious per-chunk source_version_id.
- [ ] Live Document page displays only server-owned list/detail/chunks/jobs, correct empty/loading/error states and preview fixture separation, including signed cursor/revision restarts.
- [ ] Supports TXT, Markdown, Python (each <=1 MiB) and conditionally qualified PDF (<=8 MiB/32 pages) only when server runtime gates pass; unsupported Office/YAML/CSV not advertised.
- [ ] Upload 201/200 returns true outcome/replayed/source/version/job/count; same-key uncertain retry does not duplicate; stale update 409 never silently overwrites current version.
- [ ] No fictitious source bytes, pages, OCR, chart/diagram interpretation, original-download endpoint or background job progress; optional registered local reveal is clearly distinct.
- [ ] No stale request or unauthorized workspace/source/version data is committed to UI after change; malicious document content rendered inert.
- [ ] Actual browser/PostgreSQL E2E for three qualified types and conditional PDF, API/DB restart, unsafe/error tests and existing Preview/validator/lexical regressions executed with evidence.
- [ ] Obsolete OpenAPI description is corrected by docs-only adjustment/test or separately tracked as an explicit backend-doc blocker; no server business change required.
- [ ] Frontend typecheck/format/unit/build and backend focused tests pass; operator README and task evidence updated with actual status.

## N. Documentation / Migration / Compatibility / Rollback

- **Compatibility:** backend upload/detail/chunk/job endpoints are implemented; this task consumes them. No new API release, migration or source table is required to connect Live Documents. Additive typed frontend contracts must use existing `rag-api-v1.0` fields. A new backend generalized format discovery, if needed later, requires separately approved schema/version work.
- **OpenAPI prose:** update the stale multipart narrative in `ingestion_http.py` (says only TXT/Markdown) to list qualified Python and PDF **conditional availability** without changing its schema or existing request validation. Regenerate OpenAPI in a controlled docs change and run API contract tests.
- **Documentation:** update [Workbench README](../apps/workbench/web/README.md), [durable ingestion operations](../docs-website/docs/architecture/durable-text-ingestion.md) and links to [parser registry](../apps/workbench/api/parser_registry.py); explain single-workspace development scope, file limits, PDF model asset conditions, no original asset API and local-source reveal limitation.
- **Rollout:** enable Live listing first, detail/chunks second, multipart+jobs third; each behind real `features` and client test gate. Mode remains explicit; never turn Live failure into Preview success.
- **Rollback:** disable only Live Documents UI and return to preview-only; preserve all PostgreSQL source/version/chunk/job rows, existing FastAPI ingestion, local original registrations and named DB volume. No `down -v`, no reseed, no destructive downgrade.
- **Future integration:** CONTENT-001/005 plus EVIDENCE-001 will provide original binary/diagram viewing. PARSE-002..005 can add formats only after format-qualified backend and capability changes. Async ingestion/202 requires its own durable worker/task and cannot be inferred from current jobs.

## O. Mandatory Completion Checklist

- [ ] Actual API and client source/contract/test inventory rechecked at implementation time; all historic “endpoints absent” assumptions eliminated.
- [ ] One shared frontend transport/decoder supports FormData 201 without weakening JSON request handling or server error correlations.
- [ ] Live/Preview discriminated presentation and server-owned workspace/mode state proven.
- [ ] Live list/detail/chunks/job displays authoritative PostgreSQL data; signed cursor and source-version drift safely handled.
- [ ] TXT/Markdown/Python and conditional PDF format gates verified; no unqualified file type shown as supported.
- [ ] Exact idempotency operation replay, guarded update, abort uncertainty and known job ID states tested.
- [ ] Original source local hint never impersonates a byte download or a future EvidenceReference.
- [ ] Browser security/accessibility and no HTML/code execution from documents verified.
- [ ] App/backend/full regression and restart smoke executed with recorded results.
- [ ] Docs and OpenAPI prose updated, release gate/evidence linked; mark COMPLETE only after real UI and all Section M checks pass.

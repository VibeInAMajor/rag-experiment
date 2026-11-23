# TASK-UI-003 — Connect Workbench Documents to persisted uploads, chunks and jobs

**Created:** 2026-11-20  
**Updated:** 2026-11-21  
**Status:** PROPOSED — detailed frontend implementation blueprint; upload/detail/job endpoints are not currently implemented  
**Priority:** P1 · first interactive content-management slice  
**Dependencies:** TASK-UI-001, TASK-UI-002, TASK-EVAL-001, TASK-RAG-002  
**Repository state inspected:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Deliverable location:** `tasks/TASK-UI-003-live-document-management.md`  
**Required backend blueprint:** [TASK-RAG-002](TASK-RAG-002-ingest-text-and-markdown.md)

## A. Title

Replace only the **Live-mode** Documents fixtures with the real, authorized PostgreSQL document list, source details, paginated active chunks, synchronous TXT/Markdown upload results and durable ingestion job diagnostics, while preserving the standalone Preview experience.

## B. Context / Problem

A working retrieval UI is not a usable RAG knowledge workbench unless the operator can see **which actual documents** are indexed, upload new content, inspect its extraction and validate that searches return it. Today the Documents page is a static fixture view. If it were merely fed `GET /documents` into the existing `PreviewDocument` model, the UI would invent fields such as original content, parser, page count and chunk previews that do not exist in the read-only API. If it simply enables an Upload button before backend ingestion is qualified, it would promise functionality not present.

The backend has already implemented GET document metadata backed by PostgreSQL, but it has **not implemented upload/detail/chunks/jobs routes** in the inspected repository. Those routes must be delivered and contract-tested by [TASK-RAG-002](TASK-RAG-002-ingest-text-and-markdown.md) before this frontend work can claim success. Upload is a **synchronous** terminal operation in that blueprint; the UI must not invent a background queue, percent completion or polling loop just because there is a job ID.

**Critical boundary:** Preview and Live are distinct sources of truth. A 503, 404, bad cursor, malformed response or network timeout in Live must show a real error/empty state, **never** fall back to `previewDocuments`, even when Preview is otherwise functional.

## C. Current Repository State

### Actual source inventory — explicit entry points

| File | Inspected behavior | Implementation impact |
| --- | --- | --- |
| [web `src/App.tsx`](../apps/workbench/web/src/App.tsx) | Page switch uses `page === "documents"` and `<DocumentsView documents={previewDocuments} />`; `settings.workspaceName` is cosmetic. | Route mode-specific props into existing page; use server-selected workspace ID, not editable display label. |
| [web `src/views/DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) | Accepts only `PreviewDocument[]`, local search/status filters, detail selection and tabs `content`, `chunks`, `report`; all detail data come from local object. | Keep existing layout/keyboard behavior; use discriminated mode-specific view model and callbacks, never populate missing Live fields from fixtures. |
| [web `src/domain/types.ts`](../apps/workbench/web/src/domain/types.ts) | `PreviewDocument` includes `content`, `pages`, `parser`, `sections`, `warnings`, `chunkPreviews`; `WorkbenchSettings` includes display `workspaceName`. | Introduce separate `LiveDocumentListItem`/`LiveDocumentDetail`/`LiveChunk`; do not expand Preview type with untruthful server values. |
| [web `src/domain/fixtures.ts`](../apps/workbench/web/src/domain/fixtures.ts) | `previewDocuments` includes canned PDFs, DOCX, text, fake sections/chunks and statuses. | Used **only** when `ExecutionMode === "preview"`; never treated as server records. |
| [web `src/views/views.css`](../apps/workbench/web/src/views/views.css) and [`src/styles.css`](../apps/workbench/web/src/styles.css) | Existing data table, status badge, detail panels, tabs, responsive controls. | Extend minimal classes for upload, request state and errors; retain palette and accessibility. |
| [web `src/views/SettingsView.tsx`](../apps/workbench/web/src/views/SettingsView.tsx) | Browser-only workspace label and Preview scenario/delay. | Reuse explicit mode + authorized server workspace selection provided by UI-001; do not create a second workspace selector. |
| [web `src/domain/validation.ts`](../apps/workbench/web/src/domain/validation.ts) | Independent construction validator API, not document/content service. | Do not use validator capability/version or port 8010 to infer Live ingestion. |
| [web `src/hooks/usePreview.ts`](../apps/workbench/web/src/hooks/usePreview.ts) | Drives simulated runs; does not fetch documents. | Leave alone; only Preview Documents use fixture contents. |
| [web `vite.config.ts`](../apps/workbench/web/vite.config.ts) | Initially only validator proxy; UI-001 must add `/api/v1` API proxy. | Use shared API client; do not put hardcoded `http://127.0.0.1:8011` directly in view. |
| `apps/workbench/web/src/api/contracts.ts` | **Not present in inspected baseline; proposed by UI-001.** | Extend the real client built by UI-001; inspect its final code before implementing this task. |
| [FastAPI `application.py`](../apps/workbench/api/application.py) | `_documents()` already offers **GET list**, and `_workspaces()` offers authorized workspace list. No POST upload, source detail, active chunk list, job routes yet. | Reuse GET list now; require the new RAG-002 routes for the rest. |
| [FastAPI `contracts.py`](../apps/workbench/api/contracts.py) | `DocumentPage` has `workspace_id`, `corpus_revision`, `items`, opaque `next_cursor`; `DocumentItem` has `source_id`, `title`, `media_type`, `status`, `active_version_id`, `chunk_count`, `updated_at`, `error_code?`. | Do not map `active_version_id` to fake page count or `content` to an empty string. |
| [FastAPI `boundary.py`](../apps/workbench/api/boundary.py) | Strict host/origin and `X-Request-ID`; multipart CORS must be added by RAG-002. | Client sends `Idempotency-Key`; browser owns multipart boundary/Content-Type. |
| [FastAPI `persistence.py`](../apps/workbench/api/persistence.py) and [`postgres.py`](../apps/workbench/api/postgres.py) | Real `CorpusSnapshot`, `DocumentRecord`, active-version `get_chunk` and transactionally published sources. | Display authoritative version/count/last-update; never synthesize chunks from source title. |
| [FastAPI `lexical.py`](../apps/workbench/api/lexical.py) | Approved `postgres-fts-baseline` search over currently active PostgreSQL chunks. | Verify distinctive uploaded terms in already-integrated UI-002 Live search; no duplicate retrieval logic in Documents. |
| [API OpenAPI](../apps/workbench/api/openapi.json) and [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) | Published v1 shapes and server-qualified features; no current upload capability. | Generate/additive decode against RAG-002 output; fail feature-closed if missing. |
| [Preview smoke](../apps/workbench/web/scripts/browser-smoke.js) and [validator smoke](../apps/workbench/web/scripts/validation-smoke.js) | Existing UI regressions. | Must continue to pass; build independent Live Documents smoke. |

**Important correction to previous task draft:** a live `GET /documents` response does **not** contain `content`, `warnings`, `pages`, `parser` or `chunkPreviews`. Existing `PreviewDocument` requires those fields. A blind `as PreviewDocument` type cast is both incorrect and misleading. The backend **does not** store a byte-for-byte original Markdown file in migration `0001`; detail can show indexed extracted chunks and recorded provenance, not a fictitious original download.

**Dependency and status warning:** `features.documents: true` already means read/list is ready, not that upload is allowed. RAG-002 must add separate qualified flags such as `upload`, `document_details` and `jobs`. A missing flag means not supported, never `true` by default. Browser must not treat HTTP **400** as framework-generated 422 or infer 200 from a Vite HTML fallback.

## D. Goal

A user can choose **Live** mode, see exactly the documents returned by the authorized backend workspace, paginate them, select a document to see actual active chunks and job status, upload one TXT/Markdown file with idempotent retry semantics, and verify the uploaded source is immediately discoverable by the existing Live lexical search. If server or PostgreSQL is unavailable, the user sees an explicit scoped error with safe correlation identifiers; Preview fixtures never leak into Live.

**Success requires:** real HTTP/SQL evidence for uploaded source/version/chunk/job identities, no fictitious parser/page/content fields, unchanged Preview regressions, accessible loading/errors and proper cancellation/stale-response protection.

## E. Scope

1. Extend the shared UI-001 typed API client with **existing** GET document list and **new RAG-002** POST upload, GET document detail, GET chunks, GET job methods.
2. Extend capability decoding additively; upload controls must be guarded by explicit `features.upload`, details/jobs by corresponding flags.
3. Implement a single cancellable Live Documents data hook/controller for list/detail/chunks/job/selection, pagination and refresh; avoid direct feature-specific `fetch()` in JSX.
4. Reuse the current Documents panel and filters for both modes through a strict discriminated props/view-model boundary; keep Preview self-contained.
5. Add accessible TXT/Markdown file picker, explicit upload (and safe retry) action, status, terminal job outcome, warnings and actual backend errors.
6. Provide real content/chunk/source provenance presentation; mark original file unavailable instead of generating `content`.
7. Add unit/contract/interaction and actual browser+PostgreSQL E2E tests, and update operator documentation.

## F. Non-Goals

- No PDF/DOCX/OCR, scanned-file processing, Docling, TEI embeddings, hybrid/reranking, external file sources, delete UI, source version restoration, multi-user ACL editor or remote credential connection.
- No new backend upload route or job persistence in this frontend task—those are **RAG-002 blockers**. If backend contract differs, update the A–O task before coding against assumptions.
- No persistent browser cache of document contents, service worker, Redux/Zustand replacement, duplicate client implementations, fake upload percentage or websocket/polling for a nonexistent background queue.
- No original byte-for-byte file download without a backend original-object storage design.
- No renaming of existing `PreviewDocument` fields merely to fit `DocumentItem` or auto-fallback to Preview upon Live failure.

## G. Architecture / Boundaries

```text
[App: ExecutionMode + authorized workspace from UI-001]
                 |
        [DocumentsView]
          /            \
[PreviewDocument[]]  [useLiveDocuments]
   fixture-only              |
                     [shared typed API client]
                              |
              GET list/detail/chunks/jobs + POST multipart
                              |
              [FastAPI RAG API /api/v1 (port 8011)]
                              |
                    [PersistencePort / PostgreSQL]
                              |
                   [active source/version/chunks]

[Separate Live Run path (UI-002)] --> real lexical verification
[Separate constructor validation] --> no ingestion authority
```

- Domain/front-end UI owns presentation, temporary file selection and current request lifecycle; **not** authoritative source IDs, status, version publication, job completion or tenant authorization.
- API client owns every HTTP call, decoder, sanitized error/correlation handling and request timeout; hooks own orchestration and lifecycle; components own accessible rendering.
- Backend owns `corpus_revision`, `source_id`, `source_version_id`, `job_id`, stage, timestamps and actual chunk metadata. Use the same server-chosen workspace context as Live Run.
- Preview data remain in [`fixtures.ts`](../apps/workbench/web/src/domain/fixtures.ts) and continue to use `PreviewDocument` views/semantics.

## H. Contracts / Interfaces / Data Model

### H1. Existing read-only GET contract — source of truth

```http
GET /api/v1/workspaces/development/documents?limit=50
Accept: application/json
```

Backend response (illustrative IDs):

```json
{
  "contract_revision": "rag-api-v1.0",
  "request_id": "<server-issued>",
  "trace_id": "<server-issued>",
  "workspace_id": "development",
  "corpus_revision": "corpus-<digest>",
  "items": [{
    "source_id": "demo-backup",
    "title": "Database backups",
    "media_type": "text/plain",
    "status": "ready",
    "active_version_id": "demo-backup-v1",
    "chunk_count": 1,
    "updated_at": "2026-11-20T22:00:40.812201Z"
  }],
  "next_cursor": null
}
```

List: `limit` in 1..100, default 50; `cursor` opaque and signed, bound to workspace and corpus/list revision. Do not parse, assemble or globally cache it. The current backend returns **400 INVALID_CURSOR** for stale/tampered cursor; restart first page and inform user without displaying mixed revisions. Real current `DocumentItem.status` is `ready | processing | error`—the Preview labels `Indexed | Processing | Failed` are **presentation-only**. No original `content`/`parser`/`warnings`/`page` on list response.

### H2. Proposed new backend contracts (must be finalized by RAG-002)

See [RAG-002 section H](TASK-RAG-002-ingest-text-and-markdown.md#h-contracts--interfaces--data-model) for the required design. This frontend task must consume **actual implemented OpenAPI**, not blindly bake these proposed shapes into a release:

| Operation | HTTP contract | UI dependency |
| --- | --- | --- |
| Source detail | `GET /api/v1/workspaces/{workspace_id}/documents/{source_id}` | Real title, type, active version, extracted metadata, warnings if persisted. |
| Active chunks | `GET .../documents/{source_id}/chunks?limit=50&cursor=…` | Real chunk texts/section paths, order, optional page, revision. |
| Upload new/replace | `POST /api/v1/workspaces/{workspace_id}/documents`, bounded `multipart/form-data`, `Idempotency-Key` | Terminal 201/200 with server-issued `source_id`, `source_version_id`, `job_id`, committed count and real stage timings. |
| Durable job | `GET /api/v1/workspaces/{workspace_id}/jobs/{job_id}` | Actual `pending/parsing/chunking/publishing/completed/failed` last-known status and safe error, not an animation. |
| Capabilities | `GET /api/v1/capabilities` | `features.{documents,search,upload,document_details,jobs}` with explicit per-feature truth. |

Upload multipart form: `file` required; `source_id` optional for guarded replacement; `expected_active_version_id` required when replacing. Server returns 201 create, 200 updated/unchanged or same-key replay. `Idempotency-Key` must be generated once **per user-initiated operation** and reused for uncertain-network retries of that **same** operation; never generate a new key on an automatic retry while the result might have committed. Uploading the same file as a separate *new* document is a distinct action and may create a new source.

**No automatic background polling:** RAG-002 proposes synchronous terminal responses; GET job status is for inspection/verification or after an uncertain network outcome. Do not show “67% indexed” or `Processing` forever just because a request is pending. If RAG-002 changes to `202`, add a separate task to define durable worker, polling deadline and recovery contract before frontend code relies on it.

### H3. Proposed TypeScript models (new, not part of current baseline)

```ts
type LiveDocumentListItem = {
  sourceId: string;
  title: string;
  mediaType: string;
  status: "ready" | "processing" | "error";
  activeVersionId: string | null;
  chunkCount: number;
  updatedAt: string;
  errorCode?: string;
};

type LiveChunk = {
  chunkId: string;
  sourceVersionId: string;
  content: string;
  sectionPath?: string[];
  page: number | null; // null when genuinely absent
  order: number;
};

type LiveDocumentDetail = {
  sourceId: string;
  title: string;
  mediaType: string;
  activeVersionId: string | null;
  chunkCount: number;
  parser?: string;
  warnings: string[];
  originalContentAvailable: false;
  chunks: LiveChunk[]; // present only after actual chunk fetch
};

type UploadState =
  | { status: "idle" }
  | { status: "validating" | "submitting"; operationKey: string; filename: string }
  | { status: "completed"; jobId: string; sourceId: string; sourceVersionId: string; chunkCount: number }
  | { status: "failed"; errorCode: string; traceId?: string; retryable: boolean; operationKey?: string };

type DocumentsPresentation =
  | { mode: "preview"; documents: PreviewDocument[] }
  | { mode: "live"; workspaceId: string; list: LiveDocumentListItem[];
      status: "loading" | "ready" | "empty" | "unavailable" | "error";
      error?: WorkbenchApiError };
```

These are **browser view models** and must be mapped from strict wire models in the shared client. A Live `ChunkPage` has no public embedding vector and need not return `page`; treat it as optional. Prefer preserving JSON `source_version_id` and `chunk_id` in the network DTO and using camelCase only within the UI; do not combine two inconsistent naming conventions in a single contract.

### H4. Rendering ownership: existing tabs versus actual backend data

| Existing Documents UI | Preview behavior (unchanged) | Live behavior (new) |
| --- | --- | --- |
| Document table | `previewDocuments` fixtures, demo status | Real `DocumentPage.items`, server status, active version, count; no fallback |
| Search field | Local filter over demo titles | Local title filter over **loaded** real list page(s); label `Filter loaded documents` unless backend adds server-side search |
| Status filter | Demo `Indexed/Processing/Failed` values | Explicit translation for real `ready/processing/error`, without changing server values |
| Content tab | Fake `PreviewDocument.content` paragraph | **Extracted/Indexed chunks** from backend; never call it original full source |
| Chunks tab | Demo `chunkPreviews[]` | Server `ChunkPage` with real text, stable IDs, optional page and cursor |
| Parse report tab | Demo parser/pages/warnings | Actual stored processing profile, structural warnings and last job, or `Not reported`; no fabricated page count |
| Upload | No request | Real bounded `.txt/.md` selection, safe terminal POST + job ID |
| Error view | Demo scenario | `WorkbenchApiError` code, retryable, safe message, trace/request ID |
| Mode label | PREVIEW | LIVE / server status clearly visible |

If source detail or chunks are not available in capabilities, the tabs should indicate **Not supported by backend** rather than fill fields with demo data. Do not infer page number from file type or chunk ordinal.

### H5. Error state mapping and upload retry contract

| Condition | Response | UI reaction |
| --- | --- | --- |
| Successful list | 200 with `items=[]` | Real **No documents** empty state, not demo list |
| Successful upload | 201/200 + durable job | Show verified completed job and source/version, refresh list and active details |
| Empty/invalid body | 400 `INVALID_REQUEST`/`INVALID_DOCUMENT` | Show correction message and field; allow new selection |
| Wrong type | 415 `UNSUPPORTED_MEDIA_TYPE` | Explain `.txt/.md` only; no retry loop |
| Too large | 413 `PAYLOAD_TOO_LARGE` | Display server limit, prevent repeated upload |
| Foreign workspace/source | 404 | Clear stale detail and show inaccessible/not found, without foreign metadata |
| Conflicting key/version | 409 | Explain conflict; never silently choose a new key/overwrite active version |
| Invalid pagination cursor | 400 `INVALID_CURSOR` | Drop pages and cursor, fetch first page again once; never merge old/new revisions |
| Unavailable DB/API | 503 / transport failure | Live error; explicit retry; **never** fixture fallback |
| Processing deadline | 504 `INGESTION_TIMEOUT` | Use safe error and job ID if issued; inspect job rather than asserting commit |
| Client-side abort | AbortSignal | Discard stale state, show local interruption; do **not** declare backend upload rolled back |
| Valid HTTP 200 with malformed payload | Decoder failure | Visible contract mismatch, no partial UI record |

The browser **does not** cancel a committed synchronous upload merely by aborting `fetch`. A user may retry the identical body/operation with the same saved `Idempotency-Key` after consulting the job if known; it must not retry under a fresh key until the operation's outcome is understood. If application is reloaded and the key is lost, show uncertainty rather than claim safe exactly-once upload.

## I. Repository Files / Components Impacted

| Path | Expected action | Why |
| --- | --- | --- |
| [`apps/workbench/web/src/App.tsx`](../apps/workbench/web/src/App.tsx) | MODIFY | Mode/workspace-aware Documents presentation and state invalidation on switches. |
| [`apps/workbench/web/src/views/DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) | MODIFY | Reuse table/detail/tabs; add upload and mode-aware truthful content without a second page. |
| [`apps/workbench/web/src/domain/types.ts`](../apps/workbench/web/src/domain/types.ts) | MODIFY minimally | Keep Preview types; define discriminated Live presentation when appropriate. |
| `apps/workbench/web/src/api/contracts.ts` (**from UI-001**) | MODIFY | Extend `DocumentPage`, `UploadResponse`, `DocumentDetail`, `ChunkPage`, `JobResponse` wire types; runtime decode. |
| `apps/workbench/web/src/api/client.ts` (**from UI-001**) | MODIFY | One shared GET/POST API: list, detail, chunks, job, upload; safe correlation/timeout. |
| `apps/workbench/web/src/hooks/useLiveDocuments.ts` | **CREATE** | Abort/generation, paginated list/detail, selected source, upload and explicit refresh orchestration. |
| `apps/workbench/web/src/domain/liveDocuments.ts` | **CREATE only if useful** | Pure adapter/view mapping and status model; no duplicated API schemas. |
| `apps/workbench/web/src/domain/liveDocuments.test.ts` | **CREATE** | Pure DTO mapping, missing metadata and cursor behavior. |
| `apps/workbench/web/src/hooks/useLiveDocuments.test.ts` | **CREATE** | Fetch mock races, upload retry idempotency, mode/scope invalidation. |
| [`apps/workbench/web/src/views/views.css`](../apps/workbench/web/src/views/views.css) / [`src/styles.css`](../apps/workbench/web/src/styles.css) | MODIFY minimally | Upload, status, focus/empty/error styles using existing tokens. |
| [`apps/workbench/web/src/views/SettingsView.tsx`](../apps/workbench/web/src/views/SettingsView.tsx) | READ/MODIFY minimally | Display server workspace and new truthful feature capability flags; do not duplicate selector. |
| `apps/workbench/web/scripts/live-documents-smoke.js` | **CREATE** | Real browser–API–PostgreSQL upload+inspect+search evidence. |
| [`apps/workbench/web/scripts/browser-smoke.js`](../apps/workbench/web/scripts/browser-smoke.js) | KEEP PASSING | Preview fixtures, keyboard and independent demo behavior. |
| [`apps/workbench/web/scripts/validation-smoke.js`](../apps/workbench/web/scripts/validation-smoke.js) | KEEP PASSING | Constructor validation is not document ingestion. |
| [`apps/workbench/web/README.md`](../apps/workbench/web/README.md) | MODIFY | Start, UI Upload guide, no background queue, data-retention/original limitations. |
| [`apps/workbench/api/openapi.json`](../apps/workbench/api/openapi.json) / [`contracts.py`](../apps/workbench/api/contracts.py) | READ, do not silently modify | Source contracts delivered by RAG-002; mismatches require task revision or backend fix. |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) / [`postgres.py`](../apps/workbench/api/postgres.py) | READ, do not silently modify | Backend scope, idempotent publication and SQL authority. |

**MUST NOT modify:** Haystack core `haystack/`, applied migration `0001`, separate constructor validator API, Preview fixtures, backend query ranking, run-history persistence, SQL schema for UI convenience or unrelated color/layout systems. If expanded scope is required, update A–O before coding.

## J. Implementation Requirements — executable blueprint

### J1. Verify backend contract and reuse the UI-001 foundation

1. Confirm RAG-002 is COMPLETE with **actual** passing PostgreSQL upload/job/detail/chunk tests, 0002 migration, updated OpenAPI and documented `features.upload`/`document_details`/`jobs`. A task document or Swagger example alone is not sufficient.
2. Inspect final UI-001 `apps/workbench/web/src/api/client.ts` and DTO/decoder implementation. Reuse its `getCapabilities`, `listWorkspaces`, request/error helper and abort semantics; **never** create another standalone `fetch` wrapper in `DocumentsView`.
3. Reconcile finalized field names, required/optional values, status codes and limits against **actual** [`openapi.json`](../apps/workbench/api/openapi.json). If schema differs from proposed RAG-002 H, amend H/I/J and dependent frontend code before implementing.
4. Recheck current [`App.tsx`](../apps/workbench/web/src/App.tsx) and UI-001 `ExecutionMode` ownership. Live document data is keyed by **server-returned workspace ID**; `settings.workspaceName` remains presentation only.
5. Use `GET /api/v1/capabilities` to gate actions: list can be available when upload is not. Missing addon flags must be treated as false. Never derive upload availability from `features.documents` or validator's constructor version.

**Gate:** an unqualified backend exposes **no Upload button**; a qualified backend permits browsing without Preview data contamination.

### J2. Implement one client with typed list/detail/chunk/job/upload methods

1. Extend the shared API client using `listDocuments(workspaceId,{limit,cursor,signal})`, `getDocument(workspaceId,sourceId,{signal})`, `listDocumentChunks(workspaceId,sourceId,{limit,cursor,signal})`, `getIngestionJob(workspaceId,jobId,{signal})`, `uploadDocument(workspaceId,{file,sourceId?,expectedActiveVersionId?,idempotencyKey,signal})`.
2. URL-encode **validated** opaque workspace/source/job IDs with `encodeURIComponent`. Never accept a full caller-provided URL, SQL query, arbitrary endpoint or raw graph in this client.
3. Existing GET list uses `limit=50` initially, bounds 1..100; treat `cursor` as an opaque string and pass via `URLSearchParams`, not JSON parse/decode.
4. All responses are parsed as `unknown` with runtime validation against the exact wire schema. Reject contradictory `workspace_id`, missing `source_id`, invalid dates, non-finite chunk counts, malformed `next_cursor`, or success that lacks committed `source_version_id`/job ID.
5. For POST upload build `FormData`, append exactly one `file` and optional `source_id` and `expected_active_version_id`. Send `Idempotency-Key` generated by the operation controller. **Do not set** `Content-Type: multipart/form-data` manually: browser must supply boundary. Use `Accept: application/json` and same-origin route.
6. Preserve `ErrorResponse` nested codes, `request_id`, `trace_id`, `X-Request-ID` checks, and abort/deadline distinction. If HTTP returned 200/201 but payload is malformed, show `CONTRACT_MISMATCH` and do not declare success.
7. No browser credentials/DSN in localStorage, environment variables or logs. No automatic retry of mutating POST; explicit retry reuses the exact same idempotency key and bytes if network outcome is uncertain.

**Gate:** one typed API boundary handles all new calls, and a network inspection confirms no other document request code was introduced.

### J3. Build scoped, cancellable document state and pagination

1. Add `useLiveDocuments({workspaceId,mode,capabilities,client})` or equivalent existing hook pattern. Model `idle/loading/ready/empty/unavailable/error`, cached loaded pages keyed to current workspace/corpus revision, `nextCursor` and selected source/detail/chunks/job separately.
2. On entering Live, request initial list **once** for current workspace; on explicit Refresh, abort old requests, invalidate generation, clear cursor and reload from first page. On leaving Live or switching workspace, abort every pending list/detail/chunk/job/upload display update and purge cross-scope state.
3. For Load more, fetch the server cursor and append only if `workspace_id` and `corpus_revision` equal currently displayed page; deduplicate by `source_id` within one revision. Reject server duplicates and mismatched cursor responses as protocol errors.
4. On 400 `INVALID_CURSOR`, discard accumulated pages/cursor and retry first page **once** after visible notice; never merge a stale page with a new corpus revision. Keep filters applied to loaded pages only and label as such.
5. When a user opens a document, fetch details and first chunk page separately; while pending, show an accessible loading state, not the old document's content. If selection changes before response, ignore outdated response even if network cancellation is not honored.
6. Selected record disappears after upload/update or workspace switch: clear selection safely, or reselect verified `source_id` and refetch fresh active version. If latest `corpus_revision` differs, invalidate old chunks/cursors to avoid mixing versions.
7. Keep data in memory per session; do not store raw source content in URL, localStorage or sessionStorage, and do not cache across authorized workspace boundaries.

**Gate:** racing pagination/detail responses cannot render stale text or cross-workspace data; cursor expiry recovers deterministically.

### J4. Reuse DocumentsView without inventing absent data

1. Refactor the **existing** [`DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) to accept a discriminated Preview/Live props model (or small typed controller with mode). Keep the existing table, search/filter, detail panel, tabs, keyboard behavior and ARIA structure.
2. Preview path remains `PreviewDocument[]` exactly as before; label **PREVIEW** prominently. No API required; fixture status/content behavior unchanged.
3. Live table receives `DocumentPage.items`, maps real statuses to visible labels, and shows actual `chunk_count`, media type and updated time. Do not claim that `status=ready` means embeddings/generation completed.
4. Live “Content” should be relabeled to `Indexed text` or `Extracted chunks`; show actual chunks only after successful GET. If the backend does not expose original source bytes, display `Original file unavailable` in an honest secondary note rather than pretending `content` contains an original.
5. Live “Chunks” displays `chunk_id`, source version, ordinal/order, section path and actual indexed content, with optional page only if server supplied it; render missing page as `—`/`Not available`, never `Page 0` or `Page 1` by default. Provide Load more cursor control.
6. Live “Parse report” displays **only persisted** processing profile, warnings, job stage/status and measured timings. If not supplied, show `Not reported by backend`, not `Docling`, not fake pages, and not example warnings from fixtures.
7. Preserve local search/status filtering but make scope explicit: `Filter loaded documents`, since current list API has **no server-side title search parameter**. When pagination is incomplete, do not display filtered count as total corpus size.
8. Ensure document text/title from server is rendered by React as text, not `dangerouslySetInnerHTML`, Markdown renderer with executable HTML, URL links from untrusted metadata or dynamic script insertion.
9. Accessible error/empty/loading states: `aria-live` for upload errors/status, `role="alert"` for actionable failures, keyboard-operable file picker/refresh/Load more/tab navigation, focus restoration when upload dialog closes.

**Gate:** current Preview browser smoke still passes; Live page never displays any `previewDocuments` title/content without that same text actually coming from PostgreSQL.

### J5. Implement bounded upload, guarded replacement and honest job visibility

1. Show Upload only when Live selected, authorized workspace known and `features.upload=true`. Enable `.txt/.md` picker with **client-side advisory** size/type/empty checks matching the backend's 1 MiB bound; server remains authoritative.
2. A confirmed user Upload creates one `Idempotency-Key` and one operation object `{file,sourceId?,expectedActiveVersionId?,key}`; do not regenerate the key on an uncertain retry of the same operation.
3. Set UI state `validating` → `submitting`; show only a spinner/indeterminate progress and actual labels (`Uploading`, `Processing` if confirmed), never fabricated percentage or imaginary parsing stages while one HTTP request is running.
4. On HTTP 201/200 with validated terminal `completed`, display real `source_id`, `source_version_id`, `job_id`, committed chunk count and server-measured timings. Refresh source list from first page, then source detail and chunk pages. For `unchanged`, label correctly and do not imply a new version.
5. For replacement, offer an explicit action only if backend supports it and detail has an `active_version_id`; submit existing `source_id` and `expected_active_version_id`, and explain that a version conflict requires refetch/review, not blind overwrite.
6. For 409 idempotency/version conflict, show safe error, current source context and explicit `Refresh details`. Do **not** silently mint a new idempotency key and resubmit. For 413/415/400, show a human-readable correction and preserve enough state for user to choose a new file.
7. For transport failure or local cancel after POST started, mark outcome `unknown`/`interrupted locally` rather than definite server failure. Where a `job_id` was returned, use `GET /jobs/{job_id}` to check; otherwise allow intentional same-key retry with the original file bytes. Never auto-retry with a fresh key.
8. `GET /jobs` may show last-known completed/failed/interrupted stage. **Do not** start a background poll timer for the synchronous RAG-002 contract; allow explicit refresh/inspection. Persisted jobs are not a promise of queued processing.
9. After upload success, offer a clear path to existing **Live** keyword-search template; query a distinctive term and verify returned `source_id` and `source_version_id` match the upload result. Do not implement retrieval a second time inside Documents.
10. Handle UI scope changes during upload carefully: abort local display updates and clear file bytes, but tell the user the server may still commit. On next discovery, reload list from authority rather than assuming rollback.

**Gate:** new TXT/Markdown source survives reload, appears with true committed counts/job and is retrievable by UI-002; safe retry has no duplicate record.

### J6. Tests, browser evidence, documentation and rollback

1. Unit-test wire decoders and adapters for null/missing page, valid/invalid status, source/version mismatch, malformed 200, 400/404/409/413/415/503/504, empty items and invalid cursor.
2. Test hook races: two overlapping detail fetches, list Load more after new corpus revision, workspace switch, Preview/Live switch, cancelled upload, old response arriving late, expired cursor reset once.
3. Test upload operation key lifetime, multipart body and no manual `Content-Type`; ensure exact key reused after a simulated network failure and distinct key for a new user action.
4. Browser real-lane: start API against actual PostgreSQL disposable test database + existing seed; select Live; inspect source list; upload TXT and MD; verify server IDs, chunks, job state and search result match. Re-run after API and DB restart without deleting volume or reseeding.
5. Browser mocked negative-lane: rejected media/size/conflict, invalid cursor, malformed response, transport timeout/offline. Label these as simulated errors, not backend performance evidence.
6. Keep old Preview and constructor validator smoke tests intact, plus UI-001/UI-002 tests. Run typecheck, format, unit tests and production build; inspect responsive focus/ARIA and no unsafe HTML.
7. Update the Workbench README with precise startup commands, supported formats, original-content limitation, synchronous jobs, status semantics, authorization and failure recovery, and link canonical backend runbooks.
8. Record screenshots/network IDs with safe redaction, actual source/version/chunk/job IDs, error codes and command outcomes; block completion on any failed gate.

**Gate:** all Section M acceptance criteria pass and evidence records real data provenance without a second backend or data store.

## K. Security / Governance / Observability

- **Workspace authority:** use only server-authorized `workspace_id` from capability/list response. `settings.workspaceName` is never an access token or tenant scope. All paths are formed by shared validated client; backend still enforces RLS.
- **XSS/HTML:** titles and chunk text are untrusted; always escape/render as text. Do not follow hyperlinks or execute Markdown code from retrieved documents.
- **Privacy:** never log file bytes, chunk content, full query, multipart bodies, database DSNs, API tokens, privileged internal errors or raw stack traces in browser console/evidence. Sanitize error text while preserving `error.code`, `trace_id`, `request_id`.
- **Idempotency:** request key belongs to an upload operation, not to the file name or source ID; an uncertain response does not authorize a different key retry. No silent double submissions from double-click.
- **Data retention:** no browser localStorage/sessionStorage persistence for document text or file bytes; clear them on scope/mode changes and when upload has unambiguously settled.
- **Observability:** show real `job_id`, `source_id`, `active_version_id`, `chunk_id`, `corpus_revision` and server times where present; distinguish local network elapsed from server stages.
- **Feature gates:** missing/upload false capability results in “not available”, never deceptive successful disabled request; `features.documents` does not imply mutation rights.
- **Trust boundary:** neither frontend filters nor local validation are authorization; destructive operations and cross-workspace access cannot be unlocked from UI state.

## L. Testing / Evaluation / Runtime Verification

### L1. Frontend baseline commands

```powershell
cd apps/workbench/web
npm ci
npm run typecheck
npm run format:check
npm test
npm run build
```

For the backend/database use [PostgreSQL runbook](../docs-website/docs/architecture/postgresql-foundation.md), [API runbook](../apps/workbench/api/README.md), and the implemented RAG-002 test commands. Use a **disposable** integration database with explicit seed; never upload throwaway test documents into user data by default. A future `scripts/live-documents-smoke.js` can reuse the Playwright CLI runner documented in [`apps/workbench/web/README.md`](../apps/workbench/web/README.md).

### L2. Minimum automated test matrix

| Case | Test stimulus | Required observation |
| --- | --- | --- |
| Live initial load | Server `DocumentPage` with 8 demo sources | Exact server source IDs/counts/status, not Preview fake files |
| Live empty list | Real `items=[]` | `No documents`, no fixtures |
| Real source details | Select known active source | Authenticated details and server-derived version/metadata |
| Chunk pagination | First and next cursor from API | Stable ordered chunks, identical revision, no duplicates |
| Expired cursor | Server 400 INVALID_CURSOR | Clear old rows and retry page 1 once, visible notice |
| Filter loaded data | Search title/status on partial page | Clearly labeled local filtering; no false corpus-wide count |
| TXT upload | Small UTF-8 with distinctive term | 201 completed, source/version/job saved, search verifies source |
| Markdown upload | Heading + table/code + unique term | Source indexed, actual heading/chunk provenance, no fake pages |
| Replacement | Guarded `source_id` and expected version | New active version; older result hidden, conflict guarded |
| Same-key replay | Simulated uncertain network then same key/body | Same job/source/version; no duplicate active chunks |
| Server error | 400/404/409/413/415/503/504/malformed response | Safe UI errors, zero preview results |
| Offline and abort | Backend unreachable, mode/workspace changed | No stale results or fake failure claims about server commit |
| Capability disabled | `features.upload=false` | Upload disabled, readable supported list remains usable |
| Persistence | API and DB restart same volume | Same uploaded source, chunks, active version, durable job; no reseed |
| Security presentation | HTML/JS-like source title or chunk | Escaped as text, no injected script or unsafe URL |
| Preview regression | Existing fake documents + keyboard tab | Original Preview works unchanged |
| Validator regression | Separate constructor Validate | No false relation to document readiness |

### L3. E2E measurement and evidence

For at least **two actual newly uploaded files**, record names/hashes of non-sensitive test fixtures, response status, request/trace/job/source/version IDs, count and hashes of returned chunks, final job outcome, `corpus_revision` and matching lexical-search source IDs. Use server `duration_ms` only if provided by the specific endpoint, and do not invent uploaded byte percentages or per-stage timings. Report browser/network latency separately with sample count.

For faults, record **which tests used mocked responses** and which caused genuine HTTP/DB failures. A screenshot of a fake error envelope is not proof of a PostgreSQL outage. Confirm the real service's API test evidence from RAG-002 remains green.

## M. Acceptance Criteria

- [ ] Live Documents displays only authorized `DocumentPage` rows from real FastAPI/PostgreSQL, including empty list and backend unavailable states; no fixture fallback.
- [ ] Existing preview-only Document UI, navigation, keyboard tabs, local search/filter and current Preview smoke remain functional.
- [ ] Details/chunks/job tabs use actual **new RAG-002** endpoints, display real version/chunk/job IDs and warnings only where persisted, and explicitly mark original file unavailable.
- [ ] Load-more cursor, source change, corpus revision change and `INVALID_CURSOR` are handled without mixing stale pages/versions or leaking another workspace.
- [ ] Only qualified Live upload capability enables TXT/Markdown upload; client-side 1 MiB check is advisory and server validates bytes/type/identity authoritatively.
- [ ] New TXT and Markdown uploads return true terminal 201/200 results with real source/version/job IDs and committed chunk count; exact matching source/version IDs appear in subsequent Live lexical search.
- [ ] Same-key uncertain retry does not duplicate published chunks; stale guarded replace and same-key different body produce clear 409 conflict, no silent fresh-key overwrite.
- [ ] 400/404/409/413/415/503/504/offline/malformed JSON and local abort show safe truthful states, no dummy server cancellation or fake progress.
- [ ] Workbench retains shared typed API client, no `fetch` copied into DocumentsView, no duplicated PostgreSQL service or Preview fixtures in Live.
- [ ] On API/DB restart, source/chunks/job persist on same volume; browser refetches from authority without rerunning seed.
- [ ] Accessibility, XSS text rendering, no client raw content persistence, focus controls and scoped state cleanup have passing tests.
- [ ] Frontend typecheck/format/unit/build, Live Documents browser integration and existing Preview/validator/Live search regression gates are actually executed and recorded.

## N. Documentation / Migration / Compatibility / Rollback

- **Backend dependency:** consume RAG-002's actual published versioned contract and explicit migration `0002`; no migrations originate from frontend. If RAG-002 is incomplete, keep UI controls unsupported and leave this task BLOCKED rather than inventing fake endpoints.
- **Frontend compatibility:** retain existing editor graph JSON `schemaVersion: 1`, history and settings. `PreviewDocument` and fixture content remain valid exclusively in Preview; Live document metadata is a separate domain model.
- **API compatibility:** preserve current read-only `/documents` list semantics, and extend shared client for new routes/feature flags. React should tolerate additive capability fields while rejecting unknown contract revisions or malformed required data.
- **Operator documentation:** update [`apps/workbench/web/README.md`](../apps/workbench/web/README.md) with mode selection, exact supported formats/limits, read/write API availability, idempotent retry handling, original-blob limitation and no fabricated percentages. Link [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and [ingestion blueprint](TASK-RAG-002-ingest-text-and-markdown.md).
- **Rollback:** hide only Live Documents upload/detail integration or revert frontend code; retain backend migration, committed PostgreSQL records, job history and named database volume. Preview/validator/Live read-only search continue. Never run `down -v` or `db-seed` against a populated corpus to make UI look empty again.
- **Deferred:** async worker/progress, delete/version restore, provenance link to original object bytes, richer parsing, semantic vectors/LLM answers, production authentication and multi-workspace RBAC.

## O. Mandatory Completion Checklist

- [ ] RAG-002 implementation and OpenAPI actually verified, not merely assumed from the blueprint.
- [ ] Same shared UI-001 HTTP adapter used for list/detail/chunks/jobs/upload with rigorous runtime decoding.
- [ ] Preview/Live domain/view models remain separate and workspace selection is server-owned.
- [ ] Real list pagination, cursor expiry, revision changes, detail/chunk requests and selected-document races tested.
- [ ] Server terminal upload, idempotency retry and guarded replacement verified with actual SQL/source IDs.
- [ ] No fictitious original content/page, parser report, upload percentage, fake status or Live fixture fallback.
- [ ] Browser security, accessibility, outage/timeout and local abort paths tested.
- [ ] Frontend tests/build and existing Preview/validation/Live search regressions pass with recorded evidence.
- [ ] Restart persistence verified without data reset; docs updated with safe operation/rollback guidance.
- [ ] Mark **COMPLETE** only with observed runtime/network/SQL evidence linked in this task.

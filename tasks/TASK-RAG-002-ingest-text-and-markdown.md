# TASK-RAG-002 — Durable TXT/Markdown ingestion into the existing PostgreSQL RAG corpus

**Created:** 2026-11-20\
**Updated:** 2026-11-22\
**Status:** COMPLETE — bounded local TXT/Markdown ingestion and all required acceptance gates qualified\
**Priority:** P1 · first real document-write vertical slice\
**Dependencies:** TASK-ARCH-001, TASK-API-001, TASK-DB-001, TASK-RAG-001, TASK-EVAL-001, TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001\
**Repository state inspected:** implementation base `deb9fb63dde97f68db6dd856d1fc2a13a2af2255` plus preserved working-tree changes; original blueprint snapshot `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`\
**Deliverable location:** `tasks/TASK-RAG-002-ingest-text-and-markdown.md`\
**Previous gate:** [TASK-EVAL-001](TASK-EVAL-001-prove-vertical-slice.md)\
**Next consumer:** TASK-UI-003 Live document management, a separate task not present at the inspected base.

## A. Title

Add an explicit, bounded, recoverable **TXT/Markdown upload → parse → chunk → atomic PostgreSQL publication → lexical search** workflow that reuses the existing persistent schema/adapter and provides truthful source, chunk, parse and durable job status APIs.

## B. Context / Problem

The backend already supports real **read-only** PostgreSQL full-text search and document listing. That is sufficient to prove the first Live query but not sufficient for a knowledge product: users must upload their own files and inspect actual chunks. The existing Workbench `DocumentsView` demonstrates those screens using fixtures; it cannot create an actual source in PostgreSQL. We must connect a write path to the **same** rows, active-version policy and workspace restrictions used by the existing retriever, not create an alternative ingestion-only table or in-memory search corpus.

This workflow has nontrivial failure boundaries: an upload can be retried, parsing can yield no text, chunk generation can exceed column/corpus limits, a process can restart, and a new document version must not displace the previous good version until its entire chunk set is valid. We need durable job status and explicit idempotency from the beginning.

**Scope decision:** the first revision processes small TXT/Markdown uploads synchronously within a bounded HTTP request, persists job transitions, and responds only after committed publication or a recorded failure. An asynchronous queue and a `202 Accepted` background path are **not** part of this first implementation. This decision makes client/server semantics testable without pretending that a process-local background task survives a crash. Later worker-based ingestion must introduce a durable queue and its own acceptance tests.

## C. Current Repository State

### Repository evidence — confirmed symbols and missing pieces

**Reinspection on 2026-11-22:** the completed PARSE/CHUNK seams and local EVAL gate supersede the dated blueprint's direct-converter/word-split assumptions. This full task merges the earlier repository handoff's verified parser, 500/50 token policy, immutable provenance and shared publication boundary. Existing AGENTS, parser/chunker and EVAL work/evidence are preserved. No production upload UI is included; live verification uses actual HTTP upload and the existing Live keyword browser.

| Actual repository path | Verified existing implementation | Required work / constraint |
| --- | --- | --- |
| [API `application.py`](../apps/workbench/api/application.py) | `create_app()`, `_Routes._workspaces`, `_Routes._documents`, `_Routes._search`; GET document list and POST lexical `/search` already exist. | **Add** POST document upload, GET source detail, GET source chunks, GET durable job status. Do not replace existing routes. |
| [API `contracts.py`](../apps/workbench/api/contracts.py) | Pydantic strict `ContractModel`, `Meta`, `DocumentItem`, `DocumentPage`, `SearchRequest`, `SearchResponse`, nested `ErrorResponse`. | Extend contracts additively using snake_case and `rag-api-v1.0`; preserve existing JSON behavior. |
| [API `boundary.py`](../apps/workbench/api/boundary.py) | `RequestBoundary` strict host/origin/CORS and **32 KiB JSON search** body framing; OPTIONS allows POST only for the search route. | Multipart needs a separate **bounded route policy** and CORS allowlist. Do not weaken lexical JSON handling. |
| [API `config.py`](../apps/workbench/api/config.py) | Loopback-only API host and allowed origins; DB DSN is secret and validated. | Reuse config pattern; explicit ingestion limits may be added with validation, never a force-ready flag. |
| [API `persistence.py`](../apps/workbench/api/persistence.py) | `WorkspaceContext`, `Source`, `SourceVersion`, `Chunk`, `DocumentRecord`, `CorpusSnapshot`, `PersistencePort`; `publish_source`, `list_sources`, `get_chunk` already declared. | Extend the existing port minimally with durable job/idempotency and source-detail/chunk-list operations. |
| [API `postgres.py`](../apps/workbench/api/postgres.py) | `_transaction`, `_require_workspace`, `_verify_schema`, `_publish`, `publish_source`, `get_chunk`, `lexical_search_snapshot`, `corpus_snapshot`; SQL bounded pool and transactions. | Reuse **one** publication implementation. Make commit of new active version + job COMPLETE atomic; preserve RLS. |
| [SQL migration `0001`](../apps/workbench/api/migrations/0001_initial.up.sql) | `workbench.workspaces`, `sources`, `source_versions`, `chunks`, `embedding_profiles`; compound FKs, forced RLS, GIN `tsvector` and single-active-version index. | **Keep immutable**; new job/ingest metadata through migration `0002`. |
| [Migration manager](../apps/workbench/api/db_migrations.py) and [Alembic versions](../apps/workbench/api/migrations/versions/0001_initial.py) | Current status/checksum code is based on applied `0001`; migrations are explicit, not automatic. | Extend revision/checksum validation for `0002` while preserving historic compatibility and disposable-only rollback. |
| [API `lexical.py`](../apps/workbench/api/lexical.py) and [`profiles.py`](../apps/workbench/api/profiles.py) | Fixed approved `postgres-fts-baseline` Haystack pipeline and `postgres-fts-baseline-r1`. | A newly indexed term must be searchable **without** a second corpus or graph executor. |
| [API `projection.py`](../apps/workbench/api/projection.py) | Projects authoritative source/version/chunk IDs, raw `postgres_ts_rank_cd` and timing. | Reuse unchanged for search verification. |
| [Readiness integration](../apps/workbench/api/database_dependency.py) | Distinguishes schema/data dependency from executable search profiles. | Add truthfully separate ingestion availability; a running database is not proof that upload is enabled. |
| [Qualified parsing](../apps/workbench/api/parsing.py), [registry](../apps/workbench/api/parser_registry.py), [adapter](../apps/workbench/api/parsing_adapters.py) | Bounded verified TXT/Markdown, immutable typed elements/raw protected spans, byte SHA256 and versioned parser evidence already exist. | Call `parse_source()` once; do not duplicate MIME, extension, Unicode or structural classification. |
| [Prepared chunks](../apps/workbench/api/chunking.py), [profiles](../apps/workbench/api/chunking_profiles.py) | Real 500/50 `tiktoken:o200k_base` preparation, source coverage, protected-span refusals, immutable IDs/metadata and existing `Chunk` projection. | Call `prepare_chunks(...)` through the reviewed explicit structural token profile for unknown upload locale; no word-size substitute or language guessing. |
| [Haystack TXT converter](../haystack/components/converters/txt.py) | `TextFileToDocument.run(sources)` returns documents but **logs and skips** invalid text input. | Must detect missing result and record FAILED; no successful empty ingestion. |
| [Haystack Markdown converter](../haystack/components/converters/markdown.py) | `MarkdownToDocument` may flatten Markdown structure and also **skip/log** invalid input. | Must not silently discard headings or failures; use selected structural extraction strategy and validate output. |
| [Haystack Markdown header splitter](../haystack/components/preprocessors/markdown_header_splitter.py) | `MarkdownHeaderSplitter` is already qualified behind the CHUNK adapter. | Consume parser-authoritative heading paths through `prepare_chunks`; do not rerun a conflicting Markdown parser or fabricate pages. |
| [Haystack recursive splitter](../haystack/components/preprocessors/recursive_splitter.py) | The existing CHUNK adapter qualifies real token sizing and Unicode-safe validation/repair. | Reuse the app seam at 500 tokens/target overlap 50; these are tiktoken units, not Qwen-native counts. |
| [SQL/HTTP tests](../apps/workbench/api/tests/test_postgres_persistence.py) and [lexical route tests](../apps/workbench/api/tests/test_lexical_routes.py) | Have real PostgreSQL transaction, version and ranking tests, plus request failures/cancellation. | Extend in the existing test style with disposable database and live API. |
| [Development seed](../apps/workbench/api/db_seed.py) and [database runbook](../docs-website/docs/architecture/postgresql-foundation.md) | Explicit, immutable 8-source demo seed. **Re-running seed after adding real sources will refuse modified data.** | Upload must never call seed and must not require reseeding after restart. |
| [Canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) | PostgreSQL + pgvector, TEI **planned**, actual lexical-only capability, local single `development` workspace. | Preserve model neutrality, no vectors/inference fabricated during lexical ingestion. |

**Important existing behavior:** `PostgresPersistence._publish()` inserts new source/version/chunks and changes the previous active version to superseded within one transaction. It expects `SourceVersion` and `Chunk` with matching workspace/source/version IDs and validates optional embeddings; it **does not itself** own a durable ingestion job or idempotency reservation. That missing piece must be added, not implemented as a second independent writer.

**Known failure causes to guard:** converters can skip bad input; the qualified parser already rejects empty/changed extraction. Tiktoken and exact Qwen counts are distinct, and lexical ingestion requires no Qwen counter/inference. Filename-based identity collides and leaks meaning. Blank source stubs, blanket startup failure of live jobs, same-key replay after a successful guarded update, workspace-wide corpus limits and worker cancellation all require explicit invariants. Never delete/reseed the volume to repair a migration.

## D. Goal

A user can upload a small UTF-8 TXT or Markdown file to a server-authorized development workspace. The backend validates the request, creates a durable job reservation, extracts and chunks real file bytes using reviewed Haystack components, and **atomically** publishes a source version and its COMPLETE job. The returned `source_id`, `source_version_id`, `chunk_id` and `job_id` refer to actual PostgreSQL rows and persist after API/DB restart. An explicit update replaces one source's active version without ever exposing a partially indexed replacement. The newly uploaded distinctive term is found by the already implemented Live lexical API and has the same authoritative provenance.

Upload failures are visible through a safe HTTP error and a persistent terminal job when a job was reserved. An identical idempotency-key replay is safe and does not create a duplicate version. None of this uses an in-memory Live corpus, a demo progress animation, generated vectors or an unapproved provider.

## E. Scope

1. Extend current HTTP v1 with upload, document detail, source chunks and durable job inspection (no delete route in this task).
2. Implement bounded, audited multipart transport; explicit allowed media types, byte limits, UTF-8 validity and filename treatment.
3. Add additive `0002` job-state/idempotency migration, PostgreSQL RLS and state management; make migration tooling properly revision-aware.
4. Reuse the existing `Source`, `SourceVersion`, `Chunk` and `PersistencePort` owner. Implement atomic version+job publication without duplicating `_publish`.
5. Compose the existing qualified parser/chunker in a compact ingestion service; stable provenance and an explicit structural token policy for unqualified source locale.
6. Support create and guarded replace/update, stable retry identity, unchanged-content detection and crash-interrupted job resolution.
7. Add truthful capability discovery fields for upload, details and jobs; existing read-only `features.documents` must not be misrepresented as upload availability.
8. Write integration, failure-path, concurrency, migration and restart tests using disposable PostgreSQL; document limits, status policy and run commands.

## F. Non-Goals

- No PDF/DOCX/PPTX/OCR, web crawl, external connectors, arbitrary source sync, automatic directory watching, true semantic embeddings, TEI/Ollama inference, vector ANN, RRF, reranker or generation.
- No customer-grade authentication or multi-workspace management: the existing loopback single `development` scope remains server-owned. Do not pretend a UI-entered workspace name grants access.
- No background distributed queue, task processor, websocket progress or speculative `202` return. This first API completes or fails synchronously within its bounded deadline.
- No generalized arbitrary graph execution, no change to provider-neutral Haystack core or external `pgvector-haystack` automatic-configuration tables.
- No delete/purge UI, content-retention scheduler or hard-delete of historical versions.

## G. Architecture / Boundaries

```text
[Frontend UI / API client]                 (implemented in separate task)
            |
  bounded multipart POST + Idempotency-Key
            v
[FastAPI RequestBoundary / auth scope]
            |
[Upload controller: validation + request correlation]
            |
[Ingestion orchestration: parse -> section split -> chunk -> classify]
            |                               |
            |                               +--> Haystack converters/splitters
            |
[PersistencePort: reserve job / transition / complete_ingestion_with_publication]
            |
[PostgresPersistence: one transaction + RLS + _publish]
            |
[workbench.jobs + sources + source_versions + chunks]
            |
[existing Haystack lexical search -> active chunks]
            v
[GET source detail / chunk pages / job status]
```

**Ownership and dependency direction**:

- HTTP request framing, status codes and output schemas belong to [`application.py`](../apps/workbench/api/application.py), [`boundary.py`](../apps/workbench/api/boundary.py) and [`contracts.py`](../apps/workbench/api/contracts.py).
- Content parsing/chunking/rules belong to an **app-owned orchestration module**, not SQL and not the React component. It uses Haystack building blocks with explicit parameters.
- `PersistencePort` defines neutral atomic job/source operations; PostgreSQL adapter implements them. Parsing service must not import `psycopg` or SQLAlchemy.
- Authorization remains at server-resolved [`WorkspaceContext`](../apps/workbench/api/persistence.py) plus forced RLS. Frontend provides no authoritative permissions.
- No SDK-specific provider class in application interfaces; lexical ingestion creates `embedding=None`, `embedding_profile_id=None`, `dimensions=None`.
- Job status reflects real transactions and process state; a user-visible percentage requires actual completed/total work evidence, not simulated stage timers.

## H. Contracts / Interfaces / Data Model

### H1. Additive HTTP contract (qualified local runtime)

| Method | Route | Existing/new | Semantics |
| --- | --- | --- | --- |
| GET | `/api/v1/workspaces` | existing | Authorized workspace list; unchanged. |
| GET | `/api/v1/workspaces/{workspace_id}/documents?limit=…&cursor=…` | existing | Page of persisted sources; unchanged shape. |
| POST | `/api/v1/workspaces/{workspace_id}/documents` | **NEW** | Create or guarded replace via multipart; synchronous terminal outcome (201 create, 200 updated/unchanged). |
| GET | `/api/v1/workspaces/{workspace_id}/documents/{source_id}` | **NEW** | Source/version summary + real available extracted/chunk statistics, not reconstructed original file download. |
| GET | `/api/v1/workspaces/{workspace_id}/documents/{source_id}/chunks?limit=…&cursor=…` | **NEW** | Paginated bounded active-version chunk text/provenance from existing rows; no vectors. |
| GET | `/api/v1/workspaces/{workspace_id}/jobs/{job_id}` | **NEW** | Server-owned durable last-known stage/status/error. |
| POST | `/api/v1/workspaces/{workspace_id}/search` | existing | Existing `postgres-fts-baseline` must find uploaded terms without adapter duplication. |
| GET | `/api/v1/capabilities` | existing, additive | Advertise `features.upload`, `features.document_details`, `features.jobs` only when implemented+qualified. |

Do not introduce a second URL family or change existing `/api/v1/workspaces/{workspace_id}/documents` GET response fields. Keep response `contract_revision = "rag-api-v1.0"`; additive optional discovery and new route schemas must not silently reinterpret existing fields. If a revision bump is necessary after final contract review, update canonical contract and all clients/tests **before** release.

### H2. Upload request — implemented bounded multipart

```http
POST /api/v1/workspaces/development/documents
Idempotency-Key: upload_f7b8a48c37f74e12a9201d9b5c4f7b91
Content-Type: multipart/form-data; boundary=<browser-generated>

file              : <one UTF-8 .txt or .md file>
source_id         : optional existing server-issued source identity (update only)
expected_active_version_id : required if source_id is supplied
```

- `Idempotency-Key` required, ASCII `[A-Za-z0-9_-]` and bounded length **8..128**. Replays are scoped by the server-resolved workspace and compare a cryptographic fingerprint of file bytes plus normalized operation parameters; same key + different request fails **409 IDEMPOTENCY_CONFLICT**.
- The client must not specify a new source ID: server issues an opaque ID when `source_id` absent. `source_id` in update requires ownership and active-version checks. `expected_active_version_id` mismatches fail **409 VERSION_CONFLICT** to prevent lost updates.
- Reuse the registry's qualified `.txt`, `.md`/`.markdown` aliases. TXT accepts `text/plain` or absent MIME; Markdown accepts `text/markdown`, `text/x-markdown`, `text/plain` or absent MIME. UTF-8/BOM, safe basename, known signatures, NUL/control and empty-content checks remain parser-owned. No caller `language`, profile, regex, model, metadata or path field is accepted. The server selects `language_policy="unqualified_source_locale"` and a structural **token** profile with no sentence model; EN/RU/UK content is tested without claiming automatic language detection.
- File parts require a plain `filename`; extended-only RFC 5987 `filename*` is refused with 400 by pinned multipart transport, not classified as an unsupported document format.
- Hard cap: **1 MiB raw file bytes** for this first slice, strict UTF-8 with optional BOM (`utf-8-sig`), no NUL, reject empty/whitespace-only content. Multipart full request also bounded (e.g. <=1 MiB + 64 KiB overhead), max one file and exact allowlisted fields, finite parser/deadline memory. Verify `Content-Length` if present but enforce the limit while streaming even if absent.
- Synchronous transport/processing is bounded to **30 seconds**, at most **two uploads** admitted per process. Missing/incorrect length framing cannot bypass the streamed full-body cap of 1 MiB + 65,536 bytes; the file is separately capped at 1 MiB. Workers retain their own bound until actual completion and have no persistence continuation after cancellation. Timeout handling reserves bounded failure-persistence time. No `202`/background queue is introduced.

### H3. Upload response (new contract, sample; values illustrative)

```json
{
  "contract_revision": "rag-api-v1.0",
  "request_id": "<server-issued>",
  "trace_id": "<server-issued>",
  "workspace_id": "development",
  "source_id": "<server-issued>",
  "source_version_id": "<current-active-version>",
  "job_id": "<durable-job-id>",
  "outcome": "created",
  "status": "completed",
  "chunk_count": 3,
  "corpus_revision": "<actual-committed-corpus-revision>",
  "stages": [
    { "stage": "parsing", "duration_ms": 12.4 },
    { "stage": "chunking", "duration_ms": 2.1 },
    { "stage": "publication", "duration_ms": 9.8 }
  ]
}
```

`outcome` is `created | updated | unchanged`; `status` is terminal `completed`. HTTP 201 is only a fresh created publication; updates/unchanged/replays return 200. `replayed` identifies an existing terminal job. Identity and job stage timings remain the original durable result while request/trace IDs are fresh. The replay's version/corpus revision is the job's committed result, not a promise it is still the current active version after later writes; GET detail is current-state authority. `chunk_count` remains the actual effective active-version count for unchanged content; zero new rows is not reported as an empty active version. Post-reservation errors carry `error.job_id`; framing errors may have no job.

### H4. Durable job and new migration `0002`

Migration `0002` adds application-owned `workbench.ingestion_jobs`, with:

```text
ingestion_jobs
  workspace_id, job_id, source_id?
  idempotency_key, request_fingerprint, operation  (create|update)
  expected_active_version_id?, effective_version_id?
  status   (pending|parsing|chunking|publishing|completed|failed)
  stage, error_code?, retryable
  created_at, updated_at, finished_at?
  source_content_sha256, processing_profile_fingerprint
  chunk_count?, stage_timings_jsonb
  PRIMARY KEY (workspace_id,job_id)
  UNIQUE (workspace_id,idempotency_key)
  FOREIGN KEY for known (workspace_id,source_id)
  workspace-scoped CHECK constraints
  ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY
```

Implemented reservation stores immutable `reserved_source_id`/`reserved_version_id`; published `source_id` is nullable for create until atomic publication, preserving scoped FKs without an empty source stub or a prepublication corpus change. Updates reference an existing scoped source. Session advisory ownership is held through processing; transitions/publication are fenced to that owner. Terminal jobs are immutable. Failed jobs retain their last confirmed stage, error and `finished_at`; they are not a queue payload.

**State machine:**

```text
pending -> parsing -> chunking -> publishing -> completed
           |          |            |
           +----------+------------+------> failed
```

`failed` is terminal for a key; retry processing with a **new key** after diagnosis. Same-key lookup precedes stale-version checks and excludes deployment policy from the request fingerprint, preserving terminal replay across publication/redeployment. The fingerprint covers original-byte SHA256, NFC filename, normalized declared MIME and guarded operation parameters; multipart boundary bytes never participate. Recovery fails only ownerless jobs as `INTERRUPTED`, using the crash-released advisory lock. Startup and lazy job inspection can diagnose abandonment after a database restart without killing another live request. Original bytes are not durable and never automatically replayed. A failed `retryable` result still needs a new key, not same-key reprocessing.

### H5. Job and document detail responses (new)

```text
IngestionJobResponse: Meta + workspace_id, job_id, source_id, source_version_id?,
             reserved_version_id, outcome?,
             status, stage, retryable, error_code?, chunk_count?,
             created_at, updated_at, finished_at?, stages[]
DocumentDetail: Meta + workspace_id, corpus_revision, source_id,
                title, media_type, status, active_version_id?, chunk_count,
                updated_at, processing_profile?, processing_profile_fingerprint?,
                ingestion_policy_revision?, language_policy?, source_content_sha256?,
                source_bytes?, parsed_element_count?, parser?, warnings[],
                original_content_available: false
ActiveChunkPageResponse: Meta + workspace_id, source_id, source_version_id,
           corpus_revision, items:[{chunk_id,order,content,page?,
           section_path,content_hash,metadata}], next_cursor
```

- **Source detail is not original-file download.** Migration `0001` stores title/media type/version/chunk content/metadata but not the original raw file blob. Do not pretend original Markdown bytes can be reconstructed exactly from chunks; surface extracted content and metadata honestly.
- Page is `null`/omitted for TXT/Markdown unless the converter provides genuine page information. Do not return page `0` or artificial page `1` as provenance.
- Chunk lists must select **active version only**, stable keyset ordering, `limit` 1..100 and opaque cursor scoped to workspace/source/corpus revision. Reuse current signed cursor pattern in [`application.py`](../apps/workbench/api/application.py); a stale cursor returns **400 INVALID_CURSOR** and client restarts at first page. Avoid exposing vector embeddings by default.
- Add `features.upload`, `features.document_details`, `features.jobs` as distinct booleans. Existing `features.documents` continues to mean list/read; the existing [UI-001](TASK-UI-001-typed-api-and-execution-mode.md) decoder already tolerates additive capabilities; no production UI change is required. If ingestion migration is missing, advertise upload **false** even when lexical search remains ready.

### H6. Immutable source/chunk identity and versioning

- `source_id`: generated by server from a secure opaque identifier; no filename, tenant name, Git path or document title is part of its public identity.
- New `source_version_id` is reserved once. `SourceVersion.content_hash` is the exact **original-byte SHA256**, including BOM if present; normalization/processing policy is separate version metadata. Byte-identical content and the current aggregate ingestion fingerprint reuse the active version with no source/version/chunk inserts. The completed new job retains the effective existing version and its actual chunk count.
- Chunk content identity: compute `content_hash` from actual indexed text; stable per-ingestion `chunk_id` derived from stable job/version identity plus deterministic chunk ordinal/content fingerprint, respecting the 128-character identifier contract and unique `(workspace_id,chunk_id)` key. Never rely on Haystack's ephemeral auto-generated ID or filename alone.
- Preserve CHUNK metadata and its core `processing_fingerprint`. Version/job `processing_profile_fingerprint` is a distinct aggregate over `txt-markdown-structural-v1`, `unqualified_source_locale`, exact UTF-8-sig normalization policy and core chunking fingerprint. Chunks add `ingestion_processing_fingerprint` and `ingestion_policy_revision`; never equate aggregate and core hashes. Request identity excludes this deployment policy so same-key replay survives a policy change, while a new key can deliberately reprocess under a changed policy.
- A **failed update** cannot change `active_version_id`. A successful update cannot leave two active versions. Historical versions are retained under the existing schema; deletion/retention is a later explicit feature.
- Explicit lexical-only profile: `embedding`, `embedding_profile_id`, `dimensions` remain **NULL**; a future TEI/Qwen profile will handle vector migration/reindexing separately.

### H7. Error policy and backward compatibility

| Failure | HTTP | Code / behavior |
| --- | ---: | --- |
| Missing/invalid fields, NUL, invalid UTF-8, empty extraction | 400 | `INVALID_REQUEST` or `INVALID_DOCUMENT`; include safe field metadata only |
| Unsupported extension/MIME | 415 | `UNSUPPORTED_MEDIA_TYPE` |
| File/body exceeds limit | 413 | `PAYLOAD_TOO_LARGE` (checked **during** stream) |
| Missing/foreign workspace or source | 404 | `WORKSPACE_NOT_FOUND` or `DOCUMENT_NOT_FOUND`; no cross-scope disclosure |
| Same idempotency key with conflicting request | 409 | `IDEMPOTENCY_CONFLICT`; no duplicate job/source |
| Stale expected version / concurrent conflicting write | 409 | `VERSION_CONFLICT`; previous active unchanged |
| Identical key held by a live owner | 409 | `INGESTION_IN_PROGRESS` with the reserved safe `job_id`; never start a duplicate writer |
| Database down/schema missing/job migration missing | 503 | `DEPENDENCY_UNAVAILABLE`/`NOT_READY`; no memory fallback |
| Upload admission capacity | 429 | `INGESTION_BUSY`, bounded `Retry-After`; no unaccounted worker |
| Total processing deadline | 504 | `INGESTION_TIMEOUT` with durable failure where reserved |
| Unexpected parser/DB failure | 500/503 | sanitized code and correlation; never leak original document text/stack/DSN |

Use `ErrorResponse` from existing API, including matching `X-Request-ID`, not a second error envelope. Current FastAPI normalizes invalid requests to HTTP **400**, not automatic 422. Preserve unchanged `/search` failure semantics and its bounded 32 KiB JSON body path.

## I. Repository Files / Components Impacted

| Target path | Change type | Exact responsibility |
| --- | --- | --- |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) | Modify | Add named upload/detail/chunk/job routes, request scope validation, response status mapping; reuse `_context`, `_failure`, `_Cursors`. |
| [`apps/workbench/api/boundary.py`](../apps/workbench/api/boundary.py) | Modify | New distinct bounded multipart request policy and POST/CORS preflight; preserve current search JSON rejection policies. |
| [`apps/workbench/api/contracts.py`](../apps/workbench/api/contracts.py) | Modify | Typed upload, job, detail, chunk-list models; add distinct feature booleans. |
| [`apps/workbench/api/config.py`](../apps/workbench/api/config.py) | Modify if needed | Validated upload/file/deadline limits, no secrets in response. |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | Modify | Neutral durable job/idempotency and active chunk-list/detail interfaces; preserve existing method semantics. |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | Modify | Scoped job reservation/transitions; refactor `_publish` reuse into atomic version+job commit; new scoped reads, cursor-friendly pagination. |
| [`apps/workbench/api/db_migrations.py`](../apps/workbench/api/db_migrations.py) | Modify | Multi-revision compatibility/checksum and migration status; no tampering with applied `0001`. |
| [`apps/workbench/api/migrations/0001_initial.up.sql`](../apps/workbench/api/migrations/0001_initial.up.sql) | **MUST NOT modify** | Historical migration checksum and existing data. |
| `apps/workbench/api/migrations/0002_ingestion_jobs.up.sql` | **Create** | Durable jobs table, RLS, indexes, constraints. |
| `apps/workbench/api/migrations/0002_ingestion_jobs.down.sql` | **Create for disposable verification** | Reversible **test-only** migration; never automatically drop production data. |
| `apps/workbench/api/migrations/versions/0002_ingestion_jobs.py` | **Create** | Alembic revision with explicit upgrade; ensure tool supports ordered migration. |
| `apps/workbench/api/ingestion_http.py`, `upload_transport.py`, `upload_policy.py` | **Create** | Named HTTP orchestration, exact multipart fields and centralized byte ceilings. |
| `apps/workbench/api/postgres_ingestion.py` | **Create** | Scoped reservations, owner fencing, transitions, lazy recovery and shared atomic publication. |
| `scripts/workbench_ingestion_smoke.py`, `apps/workbench/api/tests/test_ingestion_stability.py` | **Create** | Main-volume HTTP replay collector and 25-case disposable stability measurements, with sanitized evidence. |
| `apps/workbench/api/ingestion.py` | **Create** | App-owned orchestration: parse, section/chunk, identity, processing fingerprint, failure state. |
| `apps/workbench/api/tests/test_ingestion_routes.py` | **Create** | Real HTTP multipart, idempotency, status, pagination, malformed input, authorization, restart. |
| `apps/workbench/api/tests/test_ingestion_persistence.py` | **Create** | Job transaction concurrency, atomic replacement, failure recovery, force RLS, migration upgrade. |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../apps/workbench/api/tests/test_lexical_routes.py) | Extend narrowly | Search actual new uploaded terms through existing Haystack pipeline, old seed preserved. |
| [`apps/workbench/api/openapi.json`](../apps/workbench/api/openapi.json) | Regenerate with tested schema | New routes and codes; retain old contract parity. |
| [`apps/workbench/api/README.md`](../apps/workbench/api/README.md), [`docs-website/docs/architecture/rag-runtime-contract.md`](../docs-website/docs/architecture/rag-runtime-contract.md), [`postgres-lexical-search.md`](../docs-website/docs/architecture/postgres-lexical-search.md), [`postgresql-foundation.md`](../docs-website/docs/architecture/postgresql-foundation.md) | Update | Operator contract, migration/recovery instructions, true feature flags. |

**Do not modify:** `haystack/` implementations, production frontend editor/fixtures, TEI/Ollama adapters, unrelated databases, migration `0001`, existing search scores or validator. Frontend upload/Live Documents integration belongs to separate TASK-UI-003, not an implemented UI in this task.

## J. Implementation Requirements — executable blueprint

### J1. Confirm the existing corpus and implement migration `0002`

1. Re-open [migration `0001`](../apps/workbench/api/migrations/0001_initial.up.sql), [`db_migrations.py`](../apps/workbench/api/db_migrations.py), [`PersistencePort`](../apps/workbench/api/persistence.py) and the existing `postgres.py` writer. Record exact schema revision and tests before edits.
2. Choose an additive `ingestion_jobs` table whose `(workspace_id, job_id)`, `(workspace_id, idempotency_key)` and optional `(workspace_id, source_id)` access paths are indexed. Include status transition constraints and safe error_code retention.
3. Apply `ENABLE/FORCE ROW LEVEL SECURITY` with the existing `current_setting('workbench.workspace_id', true)` policy. The app role must not have schema/role owner privileges or bypass RLS. Test pool session leakage after one workspace operation.
4. Add Alembic `0002` without rewriting either `0001_initial.up.sql` or its applied historical checksum. Update `db_migrations.py` checksum/status logic to reason about each **applied revision** rather than hardcoding one up/down pair; regression-test migration from a real `0001` database preserving its rows.
5. Upgrade using the explicitly documented database-admin command; API process must **not auto-migrate**. Old lexical route should keep returning data even if ingestion capability is unavailable during rollout; readiness policy must be documented and tested.
6. Test re-applying head migration (no-op), incompatible checksum rejection, and disposable-only downgrade guards. No `down -v` or demo seed reset.

**Gate:** migrated existing seed is intact, old `/search` is unchanged, and ingestion jobs are scoped/readable only through the app role.

### J2. Add neutral durable job and atomic publication operations

1. Define minimal typed `IngestionJob`/`UploadReservation` data under `persistence.py`, plus `reserve_ingestion`, `transition_ingestion`, `complete_ingestion_with_publication`, `fail_ingestion`, `get_ingestion_job`, `get_source_detail`, `list_active_chunks` contracts. Match naming conventions and remove unnecessary abstractions if existing methods already cover a responsibility.
2. `reserve_ingestion()` is transactional: server-scope workspace, compute `request_fingerprint`, enforce unique idempotency key, freeze target source/expected version and issue a stable `job_id`. A repeated identical key returns the existing reservation/result, never restarts the write.
3. For an update, acquire source-row lock and validate **server-owned** current active version against `expected_active_version_id`. Concurrent independent replacements must serialize and stale ones fail 409 before publication.
4. Record `parsing`, `chunking` and `publishing` only after a real transition; each checkpoint committed in a bounded transaction so GET job shows the latest known stage.
5. Refactor the existing [`PostgresPersistence._publish`](../apps/workbench/api/postgres.py) to be reused **inside** a transaction that also sets the reserved job `completed`, chosen active version and final chunk count. Never call the current standalone `publish_source()` followed by a separate job success commit—crash between them would report false job state.
6. If the existing active content and processing fingerprint are unchanged, commit an `unchanged` terminal job with current version and **zero** new chunks; do not duplicate an identical active version. The same key returns identical job/source/version identities.
7. On parse/validation/SQL failures, leave old version active; mark reserved job terminal `failed` via a safe separate transaction where possible. If database is down, do not claim a persisted failure without verification; the recovery scan handles abandoned jobs after restoration.
8. Startup recovery may mark stale in-progress jobs `failed/INTERRUPTED` under server scope; no automatic content replay because original file bytes are not durable. Add a stress test for process stop between reservation and publish.

**Gate:** replace failure preserves previous query results and exactly one active version; job version/count/terminal status commit atomically with source publication.

### J3. Consume qualified deterministic parsing and chunking

1. Keep request payload bytes in memory only within the explicit 1 MiB bound (or spill to an app-owned protected temp area with guaranteed cleanup). Decode `utf-8-sig`, reject invalid sequences, NUL, empty/blank documents and path/filename injection.
2. Call existing `parse_source(...)` once. It reuses `TextFileToDocument` through its reviewed byte adapter and requires exactly one nonempty, source-preserving result; no duplicate converter/classifier.
3. Pass that immutable `ParsedDocument`, exact decoded text and reserved server identities to `prepare_chunks(...)`. Preserve parser-authorized heading/protected boundaries and warnings. Existing Haystack header/recursive adapters remain behind that seam; do not flatten Markdown or invent tables/pages.
4. Select the centralized `structural_token_profile()` at **500 `tiktoken:o200k_base` tokens / target overlap 50**, with actual overlap reported and no sentence locale. This explicit source-locale-unqualified upload policy supersedes the dated word500/50 proposal. It does not impose English Punkt, accept a caller language field, infer language, require Qwen or call a model. Oversized protected spans fail safely.
5. Enforce every chunk has nonblank text and <=32,768 **characters** for the current `Chunk` contract, and the resulting active corpus remains within the existing 10,000 chunk / 50 MiB bounds. Prevent an upload from silently causing the entire search profile to go unready.
6. Compute raw-source SHA-256, distinct chunk-text hashes and explicit profile version; generate stable source/version/chunk IDs per H6 and ensure no duplicate IDs in one upload.
7. Preserve type, safe original title, headings/sections, chosen splitter parameters, parse warnings and optional legitimate page metadata in source/version/chunk records. Never fabricate `page=1` for text files.
8. Set all embedding fields NULL; no call to TEI/Ollama/OpenAI. Test a distinctive uploaded identifier is indexed by the existing PostgreSQL `simple` tokenizer.

**Gate:** a real Markdown heading and TXT identifier survive extraction, source metadata and lexical retrieval; corrupt input records failure rather than zero-success.

### J4. Expose safe HTTP upload and read APIs

1. Add bounded multipart framing to [`RequestBoundary`](../apps/workbench/api/boundary.py) for the **exact** upload path; enforce byte limit while reading, only allowlisted fields, no duplicate `file`, and origin/host checks before backend mutation. Keep `/search` 32 KiB JSON handling unchanged.
2. Configure preflight for `POST` plus `Content-Type`, `Idempotency-Key` on upload; keep current search/GET/validator route proxy behavior intact. Do not enable wildcard credentialed CORS or remote host access.
3. Implement synchronous `POST` route in [`application.py`](../apps/workbench/api/application.py): resolve workspace, validate op/header/body, reserve job, invoke ingestion service under deadline, then return 201/200 only after publication commit. A failed request emits a structured sanitized error with real request/trace IDs.
4. Add `GET` detail/chunks/jobs route implementations using `PersistencePort` scoped reads. Chunk pagination reuses existing `_Cursors` HMAC/opaque revision behavior and returns `INVALID_CURSOR` after content publication or restart.
5. Respond with real parser warnings/stage timings, not fixture `sections`, fake page counts or simulated progress. The application can expose `stages` only when timings actually measured.
6. Add capability flags only once migration and operations are verified. Maintain existing `features.documents` read-only meaning and existing lexical execution profile separate from write authorization.
7. Regenerate [`openapi.json`](../apps/workbench/api/openapi.json) from the app, compare to contract models, and write request examples that match exact status codes.
8. Document original-bytes availability truthfully: the initial schema stores processed chunks, not a retrievable exact source blob; do not expose a nonexistent `/download` API.

**Gate:** real HTTP upload yields durable source/job records and subsequent GET detail/chunks/job + `/search` agree on identities.

### J5. End-to-end mutation, negative security and recovery tests

1. Create disposable-db test fixtures using the established `conftest.py` pattern; do not modify the user's development database to run unit tests.
2. Upload a TXT and a Markdown document with different unique identifiers; assert 201 terminal job, actual active versions, real split chunks, `embedding IS NULL`, and search hits via existing `/search`.
3. Re-submit same `Idempotency-Key` and bytes; compare job/source/version IDs and exact active chunk count. Submit same key with different bytes or target source and require 409 without mutation.
4. Test guarded update using `source_id` and `expected_active_version_id`, then query that **old unique term disappears** and new unique term appears; after simulated parsing/DB failure old term remains and new partial chunks are invisible.
5. Simulate concurrent uploads for the same source with different expected versions; exactly one valid replacement can win; no dual active versions, no lost idempotency record.
6. Verify source/job/chunk API authorization and RLS with foreign-workspace URL/source IDs; avoid 403/404 differences exposing foreign data.
7. Test corrupt UTF-8, BOM, NUL, whitespace-only, zero-output converter, oversized file/body without Content-Length, duplicate multipart field, invalid filename/MIME, huge chunk, unapproved profile, invalid idempotency key.
8. Interrupt the process after reserving job and before commit; upon safe recovery, job is terminal failed/INTERRUPTED, no new active version and old version remains queryable. Replacing a source must not corrupt previously successful searches.
9. Restart API and PostgreSQL using **same** named volume and assert uploaded source/chunk/job persisted and search returns the same source identity; do not rerun `db-seed` after user data exists.
10. Assert old lexical regression, backend API discovery, distinct validator service and UI Preview remain unaffected; no new `InMemoryDocumentStore` in Live path.

**Gate:** test matrix in L and measurable acceptance list M passes with actual SQL/API evidence.

### J6. Document operational lifecycle and release safety

1. Update the existing API/database/lexical runbooks and canonical contract to describe the four new routes, additive flags, exact MIME/idempotency/deadline and preservation/recovery policy.
2. Document explicit database upgrade to `0002` and rollback only on disposable databases; preserve volumes/data in application rollback.
3. Record body/storage bounds, RLS decisions, same-key retry contract, `failed` job semantics and file retention (original bytes not retained).
4. Capture real time/parse/chunk/publication counts and safe trace IDs in task-local completion evidence; no “real model embeddings” claim.
5. Review whether existing global readiness of search could be impacted by a file that exceeds corpus count/bytes; refuse oversized publication before changing active version rather than silently making Live unavailable.
6. Record the final route/DTO handoff for the separate TASK-UI-003 before a production upload UI binds it; that task file was not present at the inspected base. Existing browser Live search can prove uploaded-term retrieval without implementing upload controls.

**Gate:** another developer can upload, inspect, search, reproduce an error and recover the same database without manual schema edits or destructive seed reset.

## K. Security / Governance / Observability

- **Tenant boundary:** workspace authorization is `resolve_development_workspace` at API boundary; forced PostgreSQL RLS is defense-in-depth. Never accept tenant IDs, DB table names or arbitrary metadata filters in multipart fields.
- **Document trust:** treat upload bytes and Markdown as untrusted data. Do not execute embedded scripts, shell code, YAML instructions, arbitrary parser plugins, external HTML fetches or source filenames as paths.
- **Resource limits:** bounded upload bytes, concurrent operations, parsing time, number/length of chunks, database statement duration, idempotency-key length and pagination. Parser and DB failures have bounded retry semantics.
- **Secrets and privacy:** no upload bytes, full text, passwords, DSNs, embedding vectors, private path or stack traces in application logs. Log only `event`, workspace/source/job IDs, stage, bytes/chunks counts, duration and safe error_code.
- **Immutability/provenance:** `source_id` decoupled from title, `source_version_id` immutable, `content_hash`, `processing_profile_fingerprint` persisted. Preserve observed parse warnings; never silently skip a document.
- **Idempotency:** compare request hash in database within transaction. Prevent client-modifiable state transitions or repeated writes from retried network operations.
- **Retention:** job rows and historical source versions persist under documented initial development retention until a later explicit policy/migration exists; do not claim automatic deletion.
- **Observability:** reuse `RequestBoundary.log_event` and server `request_id`/`trace_id`, not a new uncorrelated logger; `job_id` follows every stage and error after reservation. Avoid fake per-node timing.

## L. Testing / Evaluation / Runtime Verification

### L1. Required commands and setup

Run the pinned database first using [`apps/workbench/postgres/compose.yaml`](../apps/workbench/postgres/compose.yaml) and the [runbook](../docs-website/docs/architecture/postgresql-foundation.md). Use Hatch, not direct `python`/`pip` calls:

```powershell
hatch --version
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
# Explicitly apply the reviewed new migration to the identified volume:
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
```

Use scoped Hatch backend test and lint commands from [API README](../apps/workbench/api/README.md). Implemented focused tests:

```powershell
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
# For focused debugging, invoke pytest in the same Hatch environment once
# test dependencies and test database DSNs are configured:
hatch -e workbench-api run pytest -q apps/workbench/api/tests/test_ingestion_routes.py
hatch -e workbench-api run pytest -q apps/workbench/api/tests/test_ingestion_persistence.py
hatch -e workbench-api run pytest -q apps/workbench/api/tests/test_lexical_routes.py
```

The three `hatch run workbench-api:*` commands are configured scripts; integration cases require explicit disposable administrator/application test DSNs. Record actual checker/test output, not just the command list. `db-seed` is **not** a post-upload recovery command and must not be used to clear a failed test.

### L2. Test matrix and release gates

| Test | Setup / stimulus | Expected authoritative evidence |
| --- | --- | --- |
| Fresh upload TXT | UTF-8 file with distinctive ID | 201, terminal job, one active version, indexed chunks with correct source and no vectors |
| Fresh upload Markdown | ATX headings + Unicode + code/table blocks | Header context and complete nonempty text retained; actual chunks and warnings |
| Search after upload | Existing `postgres-fts-baseline` | New unique identifier found with same SQL `source_id`/`source_version_id`; raw `ts_rank_cd` |
| Idempotent retry | Same workspace/key/body/params | Same `job_id`, `source_id`, version, count; no new active version |
| Conflicting retry | Same key with changed body or target | 409 `IDEMPOTENCY_CONFLICT`, zero extra rows |
| Unchanged content | New key, same source bytes and parsing profile | 200 unchanged; no new chunks or version |
| Guarded replacement | Correct `source_id` + `expected_active_version_id` | Exactly one new active version; old chunk result hidden |
| Concurrent/stale replacement | Competing expected version | One valid winner, other 409; old version safe until commit |
| Parser failure | Invalid UTF-8/empty/converter skip | Clear safe failure; **no successful empty** output |
| Upload protection | >1 MiB/unsupported media/duplicate multipart | 413/415/400 respectively, no job/source unless reserved |
| Workspace scope | Non-approved URL/source/job IDs | 404 and no cross-workspace content; forced RLS enforced |
| Durable job | Kill process mid-operation | Interrupted last stage becomes terminal failed on recovery; no half-published active version |
| Restart | API + DB restart, named volume kept | Same source/chunk/version/job; lexical retrieval works; no reseed |
| Migration | Upgrade from populated `0001` to `0002` | Existing 8 demo sources preserved; stable checksum and no-op rerun |
| Existing behaviors | GET docs/search, validation and Preview | Existing suites pass, search remains actual FTS |

### L3. Quality and load measurements

Record at least 20 small upload cases across supported types **in disposable test database(s)** and include all successful/failed cases in count. Report `parse_ms`, `chunk_ms`, `publication_ms`, `total_ms`, file bytes, chunk count, chunk UTF-8 byte distribution, active corpus bounds and source/version IDs. This is a functional stability baseline, not an ingestion throughput SLA or measured GPU/TPM efficiency.

Do not report vector Recall or model capacity from lexical-only uploads. Record whether Markdown headings/tables/code are preserved or structurally degraded, with example test document references.

### L4. Executed evidence — local qualification complete

Evidence is local and sanitized under [`tasks/evidence/ingestion-2026-11-22/`](evidence/ingestion-2026-11-22/). The main-volume migration has been observed: updated API on `0001` retained lexical readiness with upload false; explicit upgrade to `0002` retained all eight seed source/version/chunk tuples and the unchanged `0001` ledger. Two synthetic nonce uploads subsequently produced ten sources, fifteen active chunks and two completed jobs; all three HTTP phases and visible browser baseline/fresh post-restart searches passed, preserving actual IDs, content and scores. The same PostgreSQL container/image/volume survived the real database restart without reseeding.

The disposable actual-process test (`process-crash-tests.xml` / `.log`) killed API PID 72792 during parsing and restarted PID 60136. The existing job became terminal `INTERRUPTED`; old active source/version/chunk and corpus remained unchanged, the unpublished term had zero hits and same-key replay returned 409. This is an actual isolated process termination, separate from main-volume completed-upload restart qualification, with no production pause hook.

The 25-case disposable stability artifact reports 23 completed uploads, two expected empty refusals and no unexpected verification failures. Per-case raw file bytes/hash, source/version/job/chunk IDs, stage timings, UTF-8 chunk distributions and active corpus bounds are retained in `stability.json`; absent stages are null rather than fabricated durations. The full API suite passed 735 tests with zero skips; a separate actual-process test passed once. Ruff/mypy qualified 60 application files. Frontend 259 tests/typecheck/format/build passed. Optional local Qwen assets exercised tokenizer regression only, without embedding inference. The final independent [evidence audit](evidence/ingestion-2026-11-22/evidence-audit.json) passed at 13:11:47 UTC: 28 artifacts, current 123-source/73-build/four-served-byte hashes, zero configured-credential or complete source/upload body matches.

The first main collector attempt failed before any POST because its strict Pydantic enum DTO used Python-object rather than JSON-mode response validation. The collector was corrected; this was a proof-tool incident without an application failure or data write, and the failed attempt is retained rather than counted as successful coverage.

The [live collector](evidence/ingestion-2026-11-22/live-http.json) records canonical exact queries 10/10, MRR 1 and separate paraphrases 0/3, MRR 0 in each phase. [Visible baseline](evidence/ingestion-2026-11-22/browser-baseline.json) and [fresh post-restart searches](evidence/ingestion-2026-11-22/browser-after-restarts.json) verify uploaded TXT/Markdown provenance/content/ranks/scores. [Database outage](evidence/ingestion-2026-11-22/database-outage.json) records real 200 liveness / 503 readiness / 503 `NOT_READY` upload with no job. [SQL evidence](evidence/ingestion-2026-11-22/evidence-audit.json) checks seed preservation, new raw hashes, core/aggregate policy metadata, NULL vectors, HTTP/SQL score parity and stable restart tuples. [Source/build manifest](evidence/ingestion-2026-11-22/source-build-manifest.json) binds the inspected checkout/build/served bytes; no implementation commit is invented.

Detailed nearest-rank timing sample counts and UTF-8 chunk-size statistics are in the [observed local acceptance section](../docs-website/docs/architecture/durable-text-ingestion.md#observed-local-acceptance--2026-11-22). Historic EVAL evidence remains unchanged. This qualifies a local synthetic development corpus, not upload UI, remote deployment, semantic quality or a throughput SLA.

## M. Acceptance Criteria

- [x] `0002` applies on top of real `0001` without modifying old migration or losing eight seeded sources; forced RLS extends to jobs and privileged cross-workspace reads are not exposed through app role.
- [x] HTTP POST TXT and Markdown uses bounded multipart, strict UTF-8, safe source identity and durable idempotency; exact response/status schemas are published and tested.
- [x] 201/200 only after **committed** `complete_ingestion_with_publication`; job/source active version, count and source revision agree in database and API.
- [x] Existing active version stays searchable when replacement parse/chunk/DB transaction fails; no partial new chunks become active.
- [x] Identical key replay causes **zero new jobs/versions/chunks**; mismatched replay/stale update produce 409 with no data mutation.
- [x] Real TXT and Markdown distinctive identifiers are retrieved by existing Haystack→PostgreSQL lexical `/search` with matching source/version/chunk provenance and `postgres_ts_rank_cd` (not BM25).
- [x] All lexical-ingested embeddings remain NULL; no TEI/Ollama/OpenAI inference or fake pipeline timings.
- [x] `GET` source, active chunks and durable jobs show real, bounded data, safe statuses and opaque pagination; missing page is not fabricated.
- [x] API/DB restart retains content and jobs; interrupted jobs are terminally diagnosed without automatic non-durable replay or reseeding.
- [x] Invalid UTF-8, zero-result converter, unsupported media, oversized input, malicious filenames, foreign workspaces and duplicate multipart fields fail safely.
- [x] Existing `postgres-fts-baseline` readiness, search, 10+3 evaluation baseline, and other API/validator behavior remain compatible.
- [x] OpenAPI, API/database docs, migration commands, test output and sanitized trace evidence are updated; all applicable quality checks pass.

## N. Documentation / Migration / Compatibility / Rollback

The [durable ingestion guide](../docs-website/docs/architecture/durable-text-ingestion.md) records the implemented contract and explicit upgrade. New evidence belongs under `tasks/evidence/ingestion-2026-11-22/`; earlier parser, chunker and local lexical acceptance artifacts are not overwritten. Local migration/restart/HTTP/browser outcomes passed. The guide records exact scope, measurements and proof-tool incidents; the final independent artifact audit passed.

- **Forward schema:** additive `0002` migration; existing rows and `0001` checksum remain unchanged. Protect job state with RLS and indexes; define explicit schema compatibility for API versions before and after migration.
- **API compatibility:** preserve existing `GET /documents` and lexical `POST /search`. Add new routes and typed capabilities flags; do not silently change the meaning of `features.documents` or the `rag-api-v1.0` envelope.
- **Data compatibility:** version IDs and processing profile fingerprints must remain stable; future embedding/delta tasks can reuse the existing source/version/chunk identity and job metadata.
- **Documentation:** update [canonical contract](../docs-website/docs/architecture/rag-runtime-contract.md), [API runbook](../apps/workbench/api/README.md), [PostgreSQL operations](../docs-website/docs/architecture/postgresql-foundation.md) and this A–O task with observed completion evidence.
- **Rollback:** disable new upload/detail/job routes and associated capability flags; preserve PostgreSQL named volume, source rows, completed jobs, and old lexically searchable data. Do **not** run destructive migration downgrade on a live database. If back-level application code cannot tolerate `0002`, use a reviewed forward compatibility repair rather than editing `0001`.
- **Deferred scope:** object storage for originals, async ingestion queue/retry, delta detector, PDF/Docling, real Qwen embeddings, ANN and multi-user authorization require separate tasks.

Completion evidence: [735-test backend JUnit](evidence/ingestion-2026-11-22/backend-tests.xml), [actual process-crash test](evidence/ingestion-2026-11-22/process-crash-tests.xml), [259-test frontend JUnit](evidence/ingestion-2026-11-22/frontend-tests.xml), [quality](evidence/ingestion-2026-11-22/backend-quality.txt), [types](evidence/ingestion-2026-11-22/backend-types.txt), [live phases](evidence/ingestion-2026-11-22/live-http.json), [independent audit](evidence/ingestion-2026-11-22/evidence-audit.json). Full upstream Haystack tests and a Docusaurus build were not run; this is an application-only implementation with checked local documentation links and sidebar syntax.

## O. Mandatory Completion Checklist

- [x] Source/migration/port implementation re-inspected immediately before coding; no duplicate writer added.
- [x] Upload and job contracts finalized against actual API and documented **before** frontend UI-003 binds them.
- [x] `0002` schema/migration/RLS/unique idempotency/transaction invariants tested on disposable DB.
- [x] TXT/Markdown conversion cannot silently produce successful empty output; headings/provenance retained.
- [x] Safe bounded multipart + CORS routing does not relax existing `/search` transport policy.
- [x] Old and new source identities/versions remain atomic and guarded across updates, conflicts and crashes.
- [x] Real PostgreSQL ingestion, search, detail/chunk/job and restart E2E checks completed and recorded.
- [x] No fixture response or in-memory Live corpus, no fabricated embeddings, pages or timings.
- [x] All negative/security/availability tests and existing regression suites pass; documentation is updated.
- [x] Mark **COMPLETE** only with linked executed tests, migration and runtime evidence, not merely this blueprint.

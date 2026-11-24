---
title: Durable document ingestion
description: Bounded uploads, immutable provenance, atomic publication and recoverable PostgreSQL jobs.
---

# Durable document ingestion

**Created:** 2026-11-22\
**Updated:** 2026-11-23\
**Qualification:** COMPLETE for local bounded TXT/Markdown ingestion; migration, upload, search, restart and independent evidence audit passed.

The [ingestion task](../../../tasks/completed/TASK-RAG-002-ingest-text-and-markdown.md) adds synchronous uploads to the existing PostgreSQL corpus. The service composes the qualified parser and chunker, then atomically publishes a complete source version and its completed job through the existing persistence writer. The [lexical profile](postgres-lexical-search.md) searches those same active chunks. Workbench Live Documents consumes these existing upload, detail, active-chunk and job routes; Preview remains separate fixture data. The original RAG-002 qualification below is historical TXT/Markdown evidence. [Python AST ingestion](content-aware-chunking-strategy.md#python-ast-ingestion) and [runtime-conditional PDF ingestion](../tasks/pdf-layout-qualification-2026-11-23.md) have separate qualification records.

## Current processing-policy successor

[CONFIG-001](document-processing-configuration.md) externalizes the active ingestion profile. Normal startup loads the shipped operator YAML: English sentences by default, explicit Russian, 500/50 tiktoken tokens and enabled independent native admission. It uses `txt-markdown-configured-v2` / `configured_sentence_language`; new configured sentence languages fail closed, with no automatic detection. Its full application, offline-resource and local live/restart qualification passed. The parsing/policy and measured acceptance sections below record the original qualified RAG-002 `txt-markdown-structural-v1` baseline and are retained as history. Existing persisted versions and terminal job replay keep that original evidence; a new policy requires explicit guarded re-ingestion with a new key.

## Upgrade an existing volume

Use the existing administrator credentials and preserve the named volume. Stop old application writers, check status and explicitly apply the current migration `0003`; API startup and the launcher never migrate or seed:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
```

Do not run `db-seed` to refresh a populated workspace: its immutable demo guard deliberately refuses changed data. Revision `0002` adds durable jobs and their RLS/constraints; `0003` adds persisted workspace generations and advances the manifest in the source-publication/job transaction. Default persisted snapshot mode requires `0003`; explicit legacy mode can read older schemas, with ingestion features false on `0001`. Checksums validate each applied migration. An older API cannot serve an unknown upgraded schema. Use a compatible binary or reviewed forward repair; destructive downgrade remains disposable-only. Follow the [operations runbook](postgresql-foundation.md) for backups and the [generation guide](persisted-index-generations.md) for reconciliation and explicit read-path rollback.

Provision verified tokenizer assets explicitly with `hatch run workbench-api:chunking-setup`. Start the API in an application-only terminal and inspect capabilities. Additive `upload`, `document_details` and `jobs` booleans describe their dependencies; existing `documents` still describes listing. These ingestion flags are checked independently of executable lexical profiles, so an empty corpus does not by itself disable first-upload availability; lexical readiness still requires a usable corpus.

## Workbench Live Documents

Start the existing API and frontend using the [Workbench startup guide](../../../apps/workbench/web/README.md#start), select **Live**, then **Documents**. The server owns the authorized `single_workspace_dev` workspace. Listing, details, upload and jobs each require their respective capability. A backend failure remains a visible Live error; the browser never substitutes fixture documents. **Filter loaded documents** affects only fetched rows. Lists and active chunks load 50 items per request through opaque corpus-bound cursors. Expired cursors clear the old snapshot and restart once; changing mode/workspace invalidates pending replies even when a transport ignores abort.

**Upload → Confirm upload** sends one TXT, Markdown or Python file up to 1 MiB. The PDF option is present only when `pdf_ingestion.available=true`; the backend must have its pinned local assets and enforces 8 MiB / 32 pages. PDF text-layer processing has no OCR, original evidence or visual-understanding guarantee. Read returned warnings and processing metadata. The [parser registry](../../../apps/workbench/parsing/parser_registry.py) defines qualified MIME aliases; Office, CSV, YAML and other catalogued formats are not enabled by this UI.

An operation retains its file and idempotency key in memory. **Retry same operation** reuses them after timeout, offline failure or local Stop because publication may already have committed. Stop or closing a pending upload dialog means interruption locally, not server rollback. Navigation within the same workspace preserves recoverable intent; mode/workspace change or browser refresh clears private file/session data. Avoid these resets while an outcome is unknown. Choosing a file again explicitly starts a new key. After a confirmed terminal failure, correct the cause and choose the file again for an intentional new attempt; replaying its old key repeats its durable result.

**Replace file** submits the selected source and its loaded active-version ID together. A 409 preserves selection/file/key, reloads authoritative details and requires explicit file selection before a new operation; it never silently updates the guard and resubmits. Successful upload shows real `outcome`, `replayed`, source/version/job IDs, chunk count and measured stages; it invalidates the current Live search display and reloads list/detail/chunks/known job. **Search this source** opens the existing approved Keyword search graph. Enter a distinctive indexed term and compare returned source/version IDs; filenames alone do not guarantee a match.

**Indexed text** is active chunk content, not a reconstruction or download of original bytes. Inspection is bounded to 1,000 loaded chunks, 12,000 displayed characters per chunk and 6,000 characters per metadata block, with truncation/limit notices. Optional pages remain absent when the server does not report them. Registered local originals can expose a version-bound filename link that reveals the file on the API host through the [existing local-source capability](local-source-reveal.md); this does not provide remote binary assets or an Evidence API.

Job status is fetched only by a known upload/error `job_id`. **Inspect confirmed job status** performs one manual lookup of last-confirmed status/stage, reserved/published version IDs, timestamps, safe errors and measured timings. There is no global job history, background queue, simulated progress or continuous polling. The browser's session operation is not a durable upload-byte replay mechanism.

To roll back this frontend integration, disable Live Documents and retain explicit Preview operation. Preserve the existing API, source/version/chunk/job rows, local-original registrations and named PostgreSQL volume. No reseed, destructive downgrade or volume deletion is required. Current integration evidence and remaining gates belong to [UI-003](../../../tasks/TASK-UI-003-live-document-management.md), separately from the historical backend qualification below.

## HTTP operations

All routes use the existing `rag-api-v1.0` correlation envelope and server-authorized `development` workspace:

| Method and suffix under `/api/v1/workspaces/{workspace_id}` | Result |
| --- | --- |
| `POST /documents` | Bounded multipart upload; committed result or safe error |
| `GET /documents/{source_id}` | Current active-version metadata and processing evidence |
| `GET /documents/{source_id}/chunks` | Actual active chunk content/provenance with pagination |
| `GET /jobs/{job_id}` | Durable state and measured stage timings |

Multipart requires a plain `filename` parameter on its file part; an extended-only RFC 5987 `filename*` is refused with 400 by the pinned multipart transport. Multipart permits exactly one `file`, plus optional `source_id` and `expected_active_version_id` together for guarded replacement. Duplicate/unknown fields, including language/model/profile overrides, are refused. Supply one `Idempotency-Key` header matching `[A-Za-z0-9_-]{8,128}` and an allowed Origin. Use `curl.exe` so it generates the multipart boundary:

```powershell
curl.exe -X POST 'http://127.0.0.1:8011/api/v1/workspaces/development/documents' -H 'Origin: http://127.0.0.1:4173' -H 'Idempotency-Key: example-upload-20261122-01' -F 'file=@C:/path/to/notes.md;type=text/markdown'
```

Replace the example path/key. A replacement adds `-F 'source_id=SOURCE_ID' -F 'expected_active_version_id=VERSION_ID'`. A title or filename never selects source identity.

Accepted text extensions are `.txt`, `.md`, `.markdown`, `.py`. TXT accepts `text/plain`; Markdown accepts `text/markdown`, `text/x-markdown`, `text/plain`; Python accepts `text/x-python`, `application/x-python-code`, `text/plain`. An omitted MIME is inspected by the same registry. Text must be nonempty valid UTF-8, optionally BOM-prefixed; Python also requires valid syntax. `.pdf` with `application/pdf` is additionally accepted only when runtime-qualified by `pdf_ingestion.available`. The safe bounded basename is metadata, never a destination path. Source content is never executed; inspection does not guarantee universal polyglot detection. See the [Python AST policy](content-aware-chunking-strategy.md#python-ast-ingestion) for code-specific provenance and overflow.

Text/Python limits are **1 MiB per file** and a **30-second operation deadline**. Conditional PDF permits **8 MiB / 32 pages** through its longer bounded processing path; total multipart admission is **8 MiB + 64 KiB** with three bounded parts and **two concurrent uploads**. The browser uses a dedicated 240-second upload timeout, independent of the ordinary JSON request deadline. Active corpus limits remain **10,000 chunks / 50 MiB UTF-8 content**. Overflow refuses without truncation. Safe errors use 400 for invalid request/document, 404 absent scope/source, 409 stale version/key conflict/in-progress replay, 413 size/protected-span/corpus overflow, 415 unsupported media, 429 `INGESTION_BUSY` admission, 503 unavailable dependency and 504 deadline. A reserved failure includes `error.job_id`; transport rejection has no invented job.

Success returns `source_id`, `source_version_id`, `job_id`, `outcome` (`created`, `updated`, `unchanged`), `status: completed`, actual `chunk_count`, committed `corpus_revision`, `stages` and `replayed`. Unchanged content creates no new source/version/chunks but reports the actual current count. Identical terminal key replay returns the original committed job snapshot, even after later updates; GET detail is current-state authority. Changed requests conflict. Failed terminal replay repeats its safe failure; intentional retry uses a new key.

## Original RAG-002 parsing, tokens and provenance

`parse_source()` runs once, followed by `prepare_chunks(...)` on exact UTF-8-sig decoded source. The explicit server structural profile uses **500 `tiktoken:o200k_base` tokens**, target overlap **50**, confined to compatible spans. Uploads neither declare nor infer locale: `language_policy: unqualified_source_locale` and `sentence_language: null` avoid imposing English Punkt. EN/RU/UK Unicode content is tested without claiming detected language. The separately qualified language-aware internal seam remains described in the [chunking decision](content-aware-chunking-strategy.md#token-budgeted-chunking-policy).

Heading paths come from the verified parser subset. Fences, tables and unsupported Markdown structures retain protected raw content/warnings; oversized indivisible blocks fail. No physical page numbers are fabricated. Ingestion invokes no Qwen, TEI or embedding inference; embeddings remain absent and tiktoken sizing is not a Qwen-native guarantee.

`SourceVersion.content_hash` is SHA256 of **original bytes**, including a BOM. Core `chunking_profile_fingerprint` captures parser/chunker policy. Version/job `processing_profile_fingerprint` additionally hashes ingestion revision `txt-markdown-structural-v1`, locale policy and normalization policy `utf8-sig-exact-decoded-source-v1`; chunks retain their core fingerprint and add ingestion fingerprint/revision. Request fingerprints include original bytes, normalized filename, declared MIME and update fields, excluding deployment policy so terminal replay remains immutable across upgrades.

GET detail exposes source byte/hash/element counts, parser revisions, warnings, processing profile/fingerprint, ingestion/language policy and `original_content_available: false`. Chunk pages expose `chunk_id`, order, content, content hash, optional page, section path and filtered metadata. Limit is 1–100; cursors bind authorized source, active version/corpus and process signing key. Changed state/restart returns 400 `INVALID_CURSOR`. Render content/headings as text.

Original upload bytes are not retained/downloadable. Separately registered local originals remain version-bound; a replacement never inherits an older version's pointer.

## Jobs and recovery

Reservation precedes processing without inserting a blank source stub. A scoped PostgreSQL session advisory lock and fenced owner token guard key ownership and transitions. States progress pending → parsing → chunking → publishing → completed or failed. Failed jobs retain the last confirmed stage and safe code. Publication and completed-job state commit together; failed replacements preserve the old active version.

Startup and job lookup recover abandoned work only after proving its owner lock absent. Lazy GET-job recovery also handles database restart. Another live API's lock prevents wrongful recovery. There is no durable byte replay, background queue or `202` promise. Cancelled pure workers cannot publish later and retain admission until actual completion. Job/history retention is indefinite in this initial revision.

## Qualification and operator probes

Evidence lives under ignored local `tasks/evidence/ingestion-2026-11-22/`. The disposable stability test covers all 25 curated inputs (23 accepted, two empty refusals) with no unexpected verification failures. It produced 96 new chunks; UTF-8 sizes were 8–4,644 bytes, mean 1,719.646, nearest-rank p50 2,015 and p95 4,590. Including the seed, the disposable active corpus held 104 chunks / 166,894 bytes. No remote deployment is claimed.

The collector intentionally creates two synthetic nonce documents only during `baseline`. Follow-up phases read persisted jobs/details/chunks and search. It never migrates, seeds, creates a database or restarts a service:

```powershell
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke baseline
# After operator-controlled API restart:
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke after-api
# After operator-controlled database restart using the same volume:
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke after-database
```

Each phase also attempts ten canonical exact lexical queries and three separate paraphrase diagnostics. Misses remain in the denominator; diagnostic hits imply no semantic-recall promise. Historic EVAL evidence retains its eight-source/schema-0001 snapshot and is not overwritten or rerun under those stale corpus assumptions after ingestion.

### Observed local acceptance — 2026-11-22

The [HTTP collector](../../../tasks/evidence/ingestion-2026-11-22/live-http.json) passed baseline, after-API and after-database phases. Updated API rollout on `0001` retained search while upload remained false; explicit migration retained all eight source/version/chunk tuples and the original ledger. Two real synthetic uploads produced ten sources, fifteen active chunks and two completed jobs. All source/version/chunk/job tuples, corpus revision and scores persisted across the API restart and PostgreSQL restart using the same container/image/volume, without reseeding.

The canonical exact query set remained **10/10, MRR 1** in all three HTTP phases; paraphrase diagnostics remained **0/3, MRR 0**. Distinctive TXT/Markdown terms matched actual SQL provenance and raw `postgres_ts_rank_cd`. Visible browser searches checked both sources before restart and fresh server runs after both restarts, with DOM/JSON content, identity, rank and score parity: [baseline](../../../tasks/evidence/ingestion-2026-11-22/browser-baseline.json), [after restarts](../../../tasks/evidence/ingestion-2026-11-22/browser-after-restarts.json).

During an actual database stop, process liveness stayed 200 while readiness returned 503 and upload returned 503 `NOT_READY`, with no job created. The separate [actual-process test](../../../tasks/evidence/ingestion-2026-11-22/process-crash-tests.xml) killed a disposable API during parsing: recovery produced `INTERRUPTED`, preserved the old active corpus, returned no unpublished-term hit and refused same-key replay with 409.

The full API suite passed **735 tests, zero skips**; the separate actual-process test passed once. Ruff and mypy qualified **60 application files**. The frontend passed **259 tests**, type checking, formatting and build. Optional local Qwen tokenizer regression tests used explicitly supplied local assets; no embedding inference ran. The source/build manifest records 123 source files, 73 build files and four served-byte comparisons. The final [independent artifact audit](../../../tasks/evidence/ingestion-2026-11-22/evidence-audit.json) passed at 13:11:47 UTC across 28 artifacts: current source/build/served hashes, preserved seed/ledger and no configured credentials or complete stored/upload source bodies in evidence.

Measured sequential disposable uploads used nearest-rank quantiles (`sorted[ceil(p*n)-1]`). Failure cases remain in total/file/parse denominators; chunk/publication timings exist only for 23 completed cases. Server stages and client elapsed are separate observations, not a throughput SLA:

| Measurement | Samples | Mean | p50 | p95 |
| --- | ---: | ---: | ---: | ---: |
| Parse ms | 25 | 1.519 | 1.491 | 2.303 |
| Chunk ms | 23 | 17.796 | 16.879 | 27.309 |
| Publication ms | 23 | 21.696 | 16.000 | 31.000 |
| Client total ms | 25 | 86.840 | 94.000 | 109.000 |
| File bytes | 25 | 5,945.720 | 252 | 21,120 |

Two proof-tool corrections were kept distinct from product behavior. The first collector attempt used Python-object validation for a strict enum DTO and failed before any POST; JSON-mode validation corrected it and the failed attempt remains recorded. An initial browser comparison treated JSON object-key serialization order as meaningful; comparison by actual fields then confirmed parity. Neither incident changed the application or uploaded duplicate content.
### Later stability-artifact limitation

During CONFIG-001's first combined run, the old stability test's fixed output path overwrote this original run's ignored `stability.json`; its original raw bytes were not recoverable. The recorded statistics above describe the original RAG-002 run and were not replaced with current-policy numbers. See the [configuration evidence limitation](document-processing-configuration.md#test-artifact-isolation-and-historical-limitation) for the retained current-run copy and corrected explicit test-output directory. Other historical artifacts were untouched; complete raw stability-evidence preservation is not claimed.

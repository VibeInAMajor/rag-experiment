# Workbench RAG API

An independent FastAPI process with bounded durable TXT/Markdown/Python and text-layer PDF ingestion, plus approved read-only PostgreSQL lexical Haystack profiles over persisted records. The default remains `postgres-fts-baseline`. The [canonical contract](../../../docs-website/docs/architecture/rag-runtime-contract.md) owns API semantics; the [lexical search guide](../../../docs-website/docs/architecture/postgres-lexical-search.md) covers requests, scores and limits, and the [profile registry guide](../../../docs-website/docs/architecture/profile-registry.md) covers immutable policy identity, workspace rollout and qualification. The [PostgreSQL operations runbook](../../../docs-website/docs/architecture/postgresql-foundation.md) covers setup, migrations, backup and recovery.

## Text-layer PDF setup and limits

The application Hatch environment declares Docling 2.151.1 and its reviewed runtime pins. Provision the fixed layout/TableFormer assets explicitly; uploads never download them:

```powershell
hatch run workbench-api:pdf-setup --download
hatch run workbench-api:pdf-setup --verify-only
```

For offline deployment, copy a verified installation with `--from-directory PATH`. `WORKBENCH_PDF_MODEL_DIRECTORY` is a trusted deployment setting, defaulting to `.cache/workbench-pdf/models`. The committed `pdf_asset_manifest.json` fixes model repository revisions, byte sizes and SHA256 values; each worker verifies the required local files before loading weights. Missing packages/assets disable `capabilities.pdf_ingestion.available`; upload failures remain explicit.

PDF files require a safe `.pdf` basename, compatible `application/pdf` MIME when supplied, and `%PDF-` bytes. The separate PDF ceiling is 8 MiB / 32 pages; the multipart ceiling is 8 MiB + 64 KiB. Each TXT/Markdown/Python file retains its 1 MiB cap. The parser uses one child at a time, 180 seconds wall time, 640 CPU seconds and 6 GiB process memory; the HTTP operation ceiling is 210 seconds. Parser concurrency returns `PDF_BUSY`, rather than queuing unbounded model work.

Only text-layer layouts are qualified. Encrypted documents, embedded active content, image-only scans, unsupported rotations/crops, uncertain tables and detected numeric extraction loss are refused without replacing the old active version. Dense documents can hit the runtime cap below the page limit. This is local development qualification, not a promise to parse every 32-page PDF.

`page_layout` selects bounded `pdf-page-layout-r1` children (768 `tiktoken:o200k_base` tokens, zero overlap) with the table-aware overlay. Original rows remain intact, column context repeats and an indivisible oversized row returns `TABLE_OVERFLOW`. The existing independently configured native Qwen counter counts the final embedding input; no embedding generation or LLM chunking is implied. Original excerpts and retrieval strings have separate SHA256 values. Table cell metadata omits default `false` header flags; missing flags mean `false` under `PdfCell`.

GET document details exposes actual page/table/resource counts and visual regions. GET chunks exposes 1-based page numbers, block geometry, row ranges, headings, captions, original excerpts and warning codes. Coordinates are top-left PDF points on an unrotated, zero-origin MediaBox; transformed pages are refused. A table child's source span covers its original table block (`source_span_scope=source_block`); its exact excerpt is identified by row/cell locators and its separate hash. Prose spans identify their exact original excerpts.

Visual detection is incomplete and explicitly `unverified`; every accepted PDF reports `visual_processing_status=incomplete`, `VISUAL_UNDERSTANDING_UNAVAILABLE` and `VISUAL_EVIDENCE_UNAVAILABLE`. A detected region is geometry, never an inferred arrow, chart value or evidence link. CONTENT-001 original assets/representations, CONTENT-002 OCR, CONTENT-003 visual interpretation and CONTENT-005 evidence resolution remain separately gated. There is no PDF-specific blob store or fabricated asset ID. Rollback disables PDF qualification/capability and restarts the API, preserving existing versions and the database volume.

See the [PDF qualification record](../../../docs-website/docs/tasks/pdf-layout-qualification-2026-11-23.md) for measured scope and known refusals.

Parser `docling-pdf-r2` additionally handles the qualified two-column sentence layout. The normal cell-matching mode is preserved for ordinary tables. Only a numeric-coverage failure in a candidate two-column block permits one recovery attempt with native cell text, inside the same process/resource deadline. Unaffected primary blocks are retained. Recovered complete sentence columns have real page/box provenance and `PDF_NATIVE_CELL_RECOVERY`, `PDF_COLUMNS_PROJECTED_AS_TEXT`, `PDF_COLUMN_ORDER_GEOMETRIC` warnings; inferred table headers are not published. Numeric checks compare complete number occurrences as well as digit counts. Existing indexed versions require explicit re-ingestion to apply the new parser revision. See the [live numeric verification](../../../docs-website/docs/tasks/pdf-two-column-numeric-integrity-2026-11-23.md).

## Start

For the complete local application, after the one-time database setup below, run from the repository root:

```powershell
.\start.ps1
```

Requires Windows PowerShell 5.1 or PowerShell 7, Hatch, Node.js >=22.12, npm and Docker Desktop with Compose. The launcher checks Hatch, starts Docker Desktop if necessary (standard installation location), waits for the existing PostgreSQL container, starts the API and constructor validator, and builds/starts the site at <http://127.0.0.1:4173/>. It installs locked frontend dependencies only when Vite is absent. Healthy services are reused; an occupied unhealthy port produces an error without stopping its owner. API readiness is checked through the website proxy. No migrations, seeds, credential regeneration or database resets run automatically.

It also ensures the owned TEI container is running. Running models stay untouched; stopped/missing models start in the background without waiting for model readiness; UI/API readiness stays independent. First-time model setup needs the installed pinned image, NVIDIA-capable Docker and the local model path in ignored `apps/workbench/embedding/.env`; the confirmed host is already configured. Approved assets are cached in a read-only Linux Docker volume. See the [model setup and measured startup guide](../../../docs-website/docs/architecture/local-embedding-provider.md) for separate provisioning/startup costs.

If Windows blocks script execution, allow this invocation only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

This does not change persistent execution policy. Services run in hidden background processes after the command returns. Logs are written to `output/workbench-services/{api,validator,web}.{stdout,stderr}.log`. Re-running the launcher does not rebuild or restart healthy services; after source changes, stop the relevant service before starting again. Preserve the ignored database `.env` and volume. Optional `WORKBENCH_LOCAL_SOURCE_ROOT` is inherited; the launcher does not invent a source directory.

To start only the API manually, run from the repository root with Hatch:

```powershell
hatch --version
hatch run workbench-api:serve
```

The `workbench-api` Hatch environment gets its pinned API/PostgreSQL dependencies and this repository's Haystack 3.5.0 source from the root [pyproject.toml](../../../pyproject.toml). It does not require the broad library test environment or a running model service. Without database configuration, health/discovery starts but advertises no executable profile. The development listener is `http://127.0.0.1:8011`. Stop it with Ctrl+C.

This is separate from the constructor validator at `127.0.0.1:8010`. Workbench Live calls discovery and approved lexical search through this API. Starting or stopping it has no effect on offline editing, JSON import/export or fixture Preview.

### Optional persistent development database

From the repository root, with Docker Desktop running:

```powershell
& ./apps/workbench/postgres/create-dev-env.ps1
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml up -d --wait
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-bootstrap
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
hatch run workbench-api:db-seed
```

The ignored local environment contains separate administrator and application credentials; generation refuses to overwrite it. PostgreSQL 17.10 + pgvector 0.8.2 are pinned by image digest and bound to `127.0.0.1:55432`. Explicit seed inserts eight synthetic sources; an unchanged repeat inserts zero. Startup never migrates or seeds. Preserve both credentials and the named volume; see the operations runbook before backup, rollback or repair.

Start the API in a separate terminal with only application credentials:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
```

## Durable TXT/Markdown ingestion

The [ingestion contract and upgrade guide](../../../docs-website/docs/architecture/durable-text-ingestion.md) owns multipart fields, job state, fingerprints and recovery. Explicitly upgrade an existing volume through migration `0004` using `db-status`, `db-migrate`, `db-status` with the existing administrator environment; stop old application writers first. Never reseed populated data. Persisted corpus metadata was introduced in `0003`, while current profile execution also requires `0004` governance. Explicit `WORKBENCH_CORPUS_SNAPSHOT_MODE=legacy` selects the prior bounded corpus read; it does not bypass profile governance. See the [generation operations guide](../../../docs-website/docs/architecture/persisted-index-generations.md) and [profile rollout guide](../../../docs-website/docs/architecture/profile-registry.md) before rollout or rollback. Preparation assets require explicit `hatch run workbench-api:chunking-setup`; no model inference is needed.

Upload accepts one UTF-8 `.txt`/`.md`/`.markdown` file and a required `Idempotency-Key`; optional `source_id` plus `expected_active_version_id` guard replacement. No language/model/profile field is accepted. The server now uses the [operator processing configuration](../../../docs-website/docs/architecture/document-processing-configuration.md): shipped defaults are 500/50 `o200k_base` tokens, English sentence segmentation and independent local-Qwen admission. Explicit Russian is supported; other configured sentence languages refuse. The original RAG-002 locale-unqualified structural evidence remains historical; no automatic language detection or UI locale change is implied. The file is capped at 1 MiB plus 64 KiB transport overhead, two admitted uploads and 30 seconds. Completed jobs and source versions publish atomically; unchanged/replayed results retain truthful actual chunk counts. Reserved errors expose `error.job_id`.

Local same-volume migration, real uploads, lexical search, visible browser checks and API/database restart qualification passed; final independent artifact audit passed. The opt-in collector intentionally creates two synthetic nonce documents only in its baseline phase, then performs read/search replay after operator-controlled restarts:

```powershell
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke baseline
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke after-api
hatch run workbench-api:python -m scripts.workbench_ingestion_smoke after-database
```

It does not migrate, seed or restart services. Existing Live keyword search can query uploaded content; upload/document-management UI remains separate.

## Routes and readiness

| Route                                             | Purpose                                                             |
| ------------------------------------------------- | ------------------------------------------------------------------- |
| `GET /api/v1/health/live`                         | Process liveness, independent of PostgreSQL                         |
| `GET /api/v1/health/ready`                        | 200 with a qualified executable profile; otherwise 503 `NOT_READY`  |
| `GET /api/v1/capabilities`                        | Approved profiles, actual feature availability and dependency state |
| `GET /api/v1/workspaces`                          | Server-authorized development workspace metadata                    |
| `GET /api/v1/workspaces/{workspace_id}/documents` | Persisted source/version/chunk metadata and corpus revision         |
| `POST /api/v1/workspaces/{workspace_id}/documents` | Durable bounded TXT/Markdown upload and guarded replacement |
| `GET /api/v1/workspaces/{workspace_id}/documents/{source_id}` | Current source/version processing metadata |
| `GET /api/v1/workspaces/{workspace_id}/documents/{source_id}/chunks` | Actual active chunks and scoped cursor |
| `GET /api/v1/workspaces/{workspace_id}/jobs/{job_id}` | Durable status and measured stages |
| `POST /api/v1/workspaces/{workspace_id}/search`   | Actual PostgreSQL lexical retrieval through Haystack                |
| `GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file` | Registered original name and native reveal availability; no local path |
| `POST /api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file/reveal` | Select the registered original in local Windows Explorer |

A running process and an open connection are insufficient. Qualification verifies schema/checksum/extension, the restricted role, forced workspace RLS, valid GIN index, a complete bounded active corpus and the actual allowlisted pipeline. Capabilities separately exposes `dependencies.database.status`. Outages disable profile advertisement and produce truthful 503 responses, without Preview fallback.

Capabilities uses `contract_revision: "rag-api-v1.0"`, `deployment_mode: "single_workspace_dev"` and a lifecycle `service_state`. The default remains `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`; additional immutable lexical policies appear only while their workspace rollout and actual dependencies qualify. Draft/retired/unready policies are omitted. With no executable profile, profiles are empty and document/search features false. All responses carry generated request/trace IDs and `X-Request-ID`; safe errors add code, message, retryability and HTTP status. Additive `features.upload`, `features.document_details` and `features.jobs` report their separately verified migration/resource requirements. The backend revision is independent of the constructor validator's revision.

Inspect typed schemas in the checked-in [OpenAPI artifact](openapi.json), generated from `create_app(settings=ApiSettings()).openapi()`. A contract test checks application parity. OpenAPI is a repository artifact rather than another public route. Unknown routes and unexpected failures retain safe correlation envelopes without exception internals.

Manual probes from another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/live
curl.exe -i http://127.0.0.1:8011/api/v1/health/ready
Invoke-RestMethod http://127.0.0.1:8011/api/v1/capabilities
```

Liveness/discovery work without a configured database; readiness then returns 503. With the migrated, seeded database and qualified profile, readiness returns 200. To execute the native lexical path:

```powershell
$lexicalCapabilities = Invoke-RestMethod http://127.0.0.1:8011/api/v1/capabilities
$lexicalProfile = $lexicalCapabilities.profiles | Where-Object profile_id -EQ 'postgres-fts-baseline' | Select-Object -First 1
if ($null -eq $lexicalProfile) { throw 'No approved lexical profile is ready.' }
Invoke-RestMethod 'http://127.0.0.1:8011/api/v1/workspaces/development/documents?limit=3'
$lexicalRequest = @{
    query = 'backups'
    top_k = 5
    profile_id = $lexicalProfile.profile_id
    expected_profile_revision = $lexicalProfile.profile_revision
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8011/api/v1/workspaces/development/search' -ContentType 'application/json' -Body $lexicalRequest
```

All four fields are required: trimmed query 1–4096 code points, integer `top_k` 1–50, approved profile and advertised revision. Invalid input/unknown fields return 400; profile/revision mismatch returns 409. The body is at most 32 KiB. At most two searches execute concurrently, each with a 10-second admitted deadline; busy requests return 429. Authenticated pagination cursors expire when state changes or the API restarts, with 400 `INVALID_CURSOR`. See the lexical guide for full errors and pagination examples.

## Document processing configuration

Normal startup reads `apps/workbench/document_processing.yaml`. Precedence is typed defaults < selected YAML < `WORKBENCH_DEFAULT_LANGUAGE`, which synchronizes both language fields. `WORKBENCH_DOCUMENT_PROCESSING_CONFIG` selects another local file; relative paths are repository-rooted. Invalid/missing files and unsupported settings refuse explicitly. Changes require an API restart and explicit guarded re-ingestion to change stored chunks; terminal idempotency replay remains immutable. See the [full operator reference](../../../docs-website/docs/architecture/document-processing-configuration.md) for validation and rollback.

The shipped YAML enables the independent native guard at 32768 tokens and `.cache/workbench-chunking/qwen3-embedding-4b`; plain `ApiSettings()` typed construction leaves it disabled, while normal `from_env()` startup loads the shipped policy. Provision assets explicitly; startup/ingestion never download:

```powershell
hatch run workbench-api:chunking-setup --qwen-from-directory 'A:/AI/TEI/qwen3-4b'
hatch run workbench-api:chunking-setup --verify-only
# Offline import from an already prepared core tree plus approved local native JSON:
hatch run workbench-api:chunking-setup --from-directory 'C:/offline-bundle/chunking' --qwen-from-directory 'C:/offline-bundle/qwen'
```

These example source paths are operator choices. Only three hash-pinned Qwen JSON assets are copied; no weights, model downloads or inference occur. Missing enabled-guard assets disable upload readiness. English/Russian Punkt models and the token encoding retain their existing hashes. Configuration-focused live qualification passed with 854 backend tests and real upload/restart/browser checks; earlier ingestion acceptance below retains its original policy and counts.

## Configuration

The Workbench Configuration editor reads the selected document-processing YAML directly through GET `/api/v1/configuration`, validates through POST `/api/v1/configuration/validate`, and saves with PUT `/api/v1/configuration`. No operator keys, login/session routes or cookies are used, per the user's local-app requirement. The client automatically sends `X-Workbench-Request: configuration`; the existing loopback/trusted-origin boundary remains enforced and writes require an approved Origin plus JSON. See [access, persistence and recovery](../../../docs-website/docs/architecture/document-processing-configuration.md#edit-configuration-in-workbench). Save uses canonical validation, revision CAS, a flushed atomic file replacement and ten prior backups; it reports actual restart requirements.

Settings are parsed before startup; malformed or nonlocal configuration fails instead of silently widening access.

| Environment variable             | Default                                                             | Constraint                                                                                   |
| -------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `WORKBENCH_API_HOST`             | `127.0.0.1`                                                         | `127.0.0.1`, `localhost` or `::1`; no public bind                                            |
| `WORKBENCH_API_PORT`             | `8011`                                                              | Integer from 1 to 65535                                                                      |
| `WORKBENCH_API_BACKEND_REVISION` | `workbench-api-lexical-v1`                                          | Opaque ASCII identifier, 1–128 characters                                                    |
| `WORKBENCH_API_ALLOWED_ORIGINS`  | HTTP origins for `localhost` and `127.0.0.1` on ports 5173 and 4173 | Comma-separated exact loopback origins; no wildcard, credentials, paths or duplicate entries |
| `WORKBENCH_DB_DSN`               | Unset                                                               | Secret local PostgreSQL URI for the restricted application role; loaded by `use-dev-env.ps1` |
| `WORKBENCH_DOCUMENT_PROCESSING_CONFIG` | `apps/workbench/document_processing.yaml` | Alternate bounded local document-processing YAML; relative to repository root |
| `WORKBENCH_DEFAULT_LANGUAGE` | YAML value (`en` shipped) | Explicit `en` or `ru`; synchronizes default and sentence language |
| `WORKBENCH_LOCAL_SOURCE_ROOT` | Unset (local originals unavailable) | Explicit absolute local directory; same-machine interactive Windows for native selection |

Administrator-only commands use `WORKBENCH_DB_ADMIN_DSN` and `WORKBENCH_DB_APP_PASSWORD`, loaded with `-IncludeAdmin`. Keep those out of the API terminal. There is no feature-enable switch; actual storage, corpus and pipeline binding must qualify.

The default pool uses one to four connections, at most 16 waiters, and three-second acquisition/statement/lock timeouts. Each search reads its persisted workspace generation and active-version hits in one read-only REPEATABLE READ transaction, through a fresh Haystack pipeline with genuine async SQL. Search snapshot qualification no longer enumerates and hashes every active chunk. Cancellation reaches transaction cleanup before its admission slot is released. Synchronous component execution explicitly refuses this loop-bound pool. The [generation operations guide](../../../docs-website/docs/architecture/persisted-index-generations.md) covers migration, reconciliation, benchmark boundaries and recovery.

PostgreSQL `simple` FTS + GIN uses case-folded AND terms with raw `ts_rank_cd`, score type `postgres_ts_rank_cd`. It is not BM25 or a probability. Responses expose authoritative source/chunk/version identity, corpus revision and measured corpus-load/retrieval/projection stages. Synthetic-vector storage tests do not enable semantic search or qualify TEI/model output.

## Local security and diagnostics

This service is local development infrastructure, not authenticated production access or tenant isolation. CORS uses an explicit loopback origin allowlist rather than wildcard credential access. Future remote deployment requires its own authentication, TLS, origin policy and operational limits.

Operational diagnostics contain bounded IDs, operation/status metadata, counts and timings. They omit query/document bodies, credentials, vectors and exception internals. Haystack telemetry, content tracing and external tracing are disabled. The deployment owner controls console capture and must define access, retention and deletion before persisting logs.

## Checks

### Real HTTP parser smoke

With the local API already ready on port 8011, run from the repository root:

```powershell
hatch run workbench-api:python -m scripts.workbench_parser_smoke
```

This starts a temporary, token-protected loopback Uvicorn subprocess and sends real byte bodies to its diagnostic parser route. It calls the application `parse_source()` and the installed Haystack converter without mocks. The smoke reads a real repository Markdown document and TXT file, verifies BOM/Cyrillic/CRLF, headings and protected table/code spans, deterministic replay, the 1 MiB boundary, and explicit negative responses. It checks the main API's readiness, capabilities and corpus revision before/after, then stops its own server and verifies its listener is closed. Evidence contains hashes, counts and safe decisions rather than document bodies.

The default evidence artifact is `tasks/evidence/parser-runtime-2026-11-22.json`; use `--evidence PATH` for another output and `--main-url http://127.0.0.1:PORT` for another local main API. Evidence remains local under the repository's existing ignore rule. This verifies the internal parser in a real HTTP server process. Internal parser-to-chunk preparation is now qualified separately; the main API now has the separate [durable ingestion workflow](../../../docs-website/docs/architecture/durable-text-ingestion.md), whose migration/live gates are independent of this historic diagnostic evidence. The diagnostic route is never installed in the main API or advertised through its capabilities.

### API regression checks

Run the focused application checks from the repository root:

```powershell
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
```

Tests cover HTTP/schema/security contracts, persistence and the lexical profile. Container-backed tests require `WORKBENCH_TEST_ADMIN_DSN` and `WORKBENCH_TEST_APP_DSN`; otherwise they skip. The [operations runbook](../../../docs-website/docs/architecture/postgresql-foundation.md#checks-and-evidence) gives environment-loading commands. Quality evidence compares ten labeled exact-term queries and direct SQL scores; paraphrases remain diagnostics. Record actual results; unit-only success is not storage or model evidence.

## Implemented versus planned

The internal [local embedding qualification](../../../docs-website/docs/architecture/local-embedding-provider.md) adds a model-neutral port, explicit TEI deployment attestation and one shared bounded admission owner for operator-run query/document smoke. It does not enable vector ingestion or semantic HTTP search. Unknown sustainable TPM remains unqualified; provider-reported usage is distinguished from local tokenizer estimates. See the guide and [execution record](../../../tasks/evidence/embedding-2026-11-23/report.md) before running the explicit qualification command.

The project-owned TEI service uses `rag-workbench-embedding-1` on `127.0.0.1:8082`; it has separate [startup and model evidence](../../../tasks/evidence/embedding-2026-11-23/dedicated-report.md). The original `8081` qualification artifacts describe an existing shared service and remain historical. A dedicated container shares the physical GPU and does not establish production TPM capacity.

Root `start.ps1` also ensures the owned embedding container is running: a running model is left in place, and a stopped/missing service loads in the background. Its ignored local `.env` persists the source directory for first-time setup; ordinary launches need no repeated path. UI/API startup does not wait for model readiness. See the [launcher/cache follow-up](../../../tasks/evidence/embedding-2026-11-23/optimized-report.md) for measured behavior and remaining qualification gates.

- **API:** health/discovery, authorized workspace/document lists and Haystack-orchestrated PostgreSQL lexical search, with bounded admission and safe metadata/errors.
- **Persistence:** pinned PostgreSQL + pgvector, explicit migrations/seed, forced workspace RLS, atomic publication and consistent active-version snapshots.
- **Internal parsing boundary:** immutable static parser registry and bounded UTF-8 TXT/Markdown inspection/projection under `parsing.py` and `parser_registry.py`; consumed by the separate durable ingestion routes. See the [format matrix and parser/chunking handoff](../../../docs-website/docs/architecture/content-aware-chunking-strategy.md).
- **Internal chunk preparation:** `prepare_chunks(...)` consumes the verified parser result and server-owned source/version identity; versioned default sizing is 500 tokens with target overlap 50, counted by `tiktoken:o200k_base`. Only English (`en`), Russian (`ru`) and Ukrainian (`uk`) hints are accepted. EN/RU combine their NLTK sentence boundaries with token sizing; UK uses explicit structural token fallback. Other languages return `UNSUPPORTED_LANGUAGE`. No upload route or SQL write is introduced.
- **Existing independent validator:** real Haystack construction/connectivity checks, without execution; see [validator documentation](../validator/README.md).
- **Existing UI:** fixture document displays, Preview and approved Live keyword search; see [Workbench documentation](../web/README.md).
- **Ingestion:** synchronous durable backend passed local migration/upload/search/restart gates; upload UI remains separate.
- **Planned:** Live document-management UI, genuine BM25 if separately justified, durable embedding ingestion, production embedding capacity control, dense/hybrid retrieval and generation. Each needs its own qualification gate.

The initial database migration is explicit; no Haystack public API changes are introduced. Application rollback is stopping the optional API while preserving its database volume. Destructive schema rollback is restricted to explicitly confirmed disposable databases; the constructor validator and standalone UI remain independent.

### Internal parser limits

The parser accepts in-memory bytes and an untrusted basename/MIME, not a path or URL. Qualified TXT/Markdown adapters reuse Haystack `TextFileToDocument` through `parsing_adapters.py` and require exactly one nonempty, source-preserving extraction. The conservative unindented single-line ATX/Setext heading subset retains hierarchy; fences, tables, multiline Setext titles and complex/container syntax remain protected raw spans with warnings. Known-signature checks do not claim universal executable/polyglot detection; no source code or content link is executed. Planned PDF/Office/non-Python-code/media entries cannot dispatch even if an upstream converter is installed. Python now has the separately qualified AST policy below.

Reviewed defaults are 1 MiB, 4,096 elements and a shared 2,000 ms cooperative deadline. These synchronous checks do not provide process isolation or preempt a blocked dependency. Safe failures and operational metadata omit content and raw filenames. Chunking and ingestion must consume the verified immutable result without a second MIME classifier; workspace resolution, version publication and public format advertisement remain consuming-workflow responsibilities.

### Internal chunking contract

The [chunking policy decision](../../../docs-website/docs/architecture/content-aware-chunking-strategy.md#token-budgeted-chunking-policy) owns profile/counter/resource identity, protected span handling and the ingestion handoff. The pure resolver lives in `chunking_profiles.py`; `chunking.py` orchestrates the reviewed Haystack/tokenizer adapter. Source text cannot select an executable strategy. Markdown headings and protected spans come from the verified parser, and overlap remains within a section/prose span. Oversized protected blocks fail safely; unpaginated sources do not gain fabricated page metadata.

The baseline counter is independent of optional exact-model admission. `LocalQwenTokenCounter` qualifies the operator-configured `Qwen3-Embedding-4B` tokenizer revision and three JSON asset hashes without weights, downloads or inference. Its serialized NFC/postprocessor appends `<|endoftext|>` ID 151643, rather than guessing from config EOS 151645. This proves local counting, not served-TEI parity. `ModelTokenAdmission.embedding_input(content, heading_path=...)` composes prefix, optional per-chunk heading context, content and suffix; admission and the future embedding caller must use the same input. Configured exact overflow refuses with `MODEL_TOKEN_LIMIT_EXCEEDED`, without truncation or automatic rechunking. The separate [ingestion workflow](../../../tasks/completed/TASK-RAG-002-ingest-text-and-markdown.md#j3-consume-prepared-chunks) publishes through the existing persistence port.

The 25 curated inputs in `tests/fixtures/chunking/manifest.json` exercise EN/RU sentence segmentation, UK token fallback, real token budgets, Unicode/CRLF safety, repeated offsets, headings/protected blocks and refusal paths. Arbitrary Unicode characters do not qualify extra languages. Other language hints are tested as refusals. Actual baseline/local-Qwen HTTP measurements qualify internal preparation, not public upload readiness or retrieval-recall gains. Normal preparation must not download sentence/tokenizer assets unexpectedly; setup is explicit.

Provision the reviewed EN/RU Punkt tables and offline `o200k_base` encoding once, explicitly:

```powershell
hatch run workbench-api:chunking-setup
```

The app-only dependencies pin NLTK 3.10.4 and tiktoken 0.14.0. Setup verifies fixed official-asset hashes and writes only allowlisted resources under ignored `.cache/workbench-chunking/`; runtime verifies those assets without downloads. Missing sentence resources yield a recorded token-based fallback or a required-sentence refusal; missing counter assets refuse token preparation. See the architecture guide for resource revision, pinned Haystack adapter and Unicode-safe native-output repair limitations.

To exercise parser and chunker through actual diagnostic HTTP, with the main local API ready:

```powershell
hatch run workbench-api:python -m scripts.workbench_parser_smoke --chunking --evidence tasks/evidence/chunking-2026-11-22/runtime.json
```

The optional actual-counter run requires an operator-selected local asset directory; this example is the user's existing location, not an application default:

```powershell
hatch run workbench-api:python -m scripts.workbench_parser_smoke --chunking --qwen-tokenizer-dir 'A:\AI\TEI\qwen3-4b' --evidence tasks/evidence/chunking-2026-11-22/runtime-qwen.json
```

Final [recorded results](../../../tasks/evidence/chunking-2026-11-22/) show **255 focused tests passed** and **579 API tests passed, 69 database-DSN skips**. All 18 local-counter tests ran using explicit `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; those requiring assets skip when it is unset. Baseline and local-Qwen HTTP runs completed **142 requests**, each accepting 23 cases and producing 95 chunks sized 3–500 tiktoken tokens. Both preserved the ready main API/corpus/capabilities and closed their temporary listener.

Same-formatted-input examples measure 500 tiktoken tokens versus **501 English / 745 Russian / 667 Ukrainian Qwen tokens**. The actual Qwen-budget refusal tests confirm that 500-tiktoken splitting does not guarantee a 500-Qwen budget. Diagnostic routes exist only in the subprocess; no public ingestion/database publication or served-model parity is claimed.

## Registered local originals

Live result Source values can become filename text links for real active versions registered beneath `WORKBENCH_LOCAL_SOURCE_ROOT`. Demo/synthetic sources stay ordinary text. There is no extra action menu or file picker. Native selection is independent of search availability and never changes the retrieval profile or result scores.

Set the allowed root in the API/CLI terminals, then explicitly bind an existing real source/version:

```powershell
$env:WORKBENCH_LOCAL_SOURCE_ROOT = 'C:\Documents\Sources'
hatch run workbench-api:source-register --source-id report --version-id report-v1 --file 'C:\Documents\Sources\report.pdf'
```

These are example IDs/paths; registration creates no source and performs no ingestion. It stores a relative original pointer and byte SHA256 in the existing version metadata. Exact retry is idempotent; conflicting binding, foreign/inactive/demo records and disallowed paths fail. Changed registration advances the persisted corpus generation in the same transaction and expires old corpus-bound cursors. Exact retry leaves that generation unchanged. The application requires its current corpus-generation migration; registration adds no separate original-file schema.

The metadata GET returns only `name`, `can_reveal`, optional safe `reason` and correlation. A reveal POST accepts only JSON `{}`, requires an explicit allowed Origin and rechecks current scope/version, allowed-root containment, regular-file identity and byte SHA before native dispatch. Originals are limited to 512 MiB with a five-second verification deadline. UNC/device/ADS/reparse paths and network drives are refused. The browser never submits/receives the local path. See the [local originals guide](../../../docs-website/docs/architecture/local-source-reveal.md) for exact errors, deployment limits and verification.

## Python source ingestion

The existing multipart `POST /api/v1/workspaces/{workspace_id}/documents` also accepts strict UTF-8 `.py` with `text/x-python`, `application/x-python-code`, `text/plain`, or an omitted MIME. Contradictory MIME, unsupported languages and invalid source refuse explicitly. A `.txt` containing code remains prose. The same job, idempotency key, workspace/RLS and atomic publication rules apply; no migration, provider or new upload endpoint is introduced.

Python selects immutable `python_ast` / `python-ast-r1`, a 60-effective-line primary grouping target and bounded 60/5 physical-line secondary windows. GET chunks exposes exact line ranges and symbol metadata without page numbers. Native tokenizer admission remains separate and uses actual final input; no model inference or code execution occurs. See the [policy, measured splitter exceptions and limits](../../../docs-website/docs/architecture/content-aware-chunking-strategy.md#python-ast-ingestion). The existing Documents page remains a fixture view; Live keyword search can find the newly stored code.

Real-server qualification uses `hatch run workbench-api:python -m scripts.workbench_python_probe upload` after loading the application database environment, then `after-restart` after an explicit API restart. It uploads the actual project `ingestion.py`, checks persisted source slices and native counts, refuses a corrupted update, preserves existing rows, and verifies replay after restart. It writes distinct, non-overwriting local evidence under `tasks/evidence/python-ast-2026-11-22/`; it is an intentional corpus write, not a diagnostic route or automatic startup action.

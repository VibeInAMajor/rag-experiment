# Workbench RAG API

An independent FastAPI process with bounded durable TXT/Markdown ingestion and the approved, read-only `postgres-fts-baseline` Haystack profile over persisted PostgreSQL records. The [canonical contract](../../../docs-website/docs/architecture/rag-runtime-contract.md) owns API semantics; the [lexical search guide](../../../docs-website/docs/architecture/postgres-lexical-search.md) covers requests, scores and limits. The [PostgreSQL operations runbook](../../../docs-website/docs/architecture/postgresql-foundation.md) covers setup, migrations, backup and recovery.

## Start

For the complete local application, after the one-time database setup below, run from the repository root:

```powershell
.\start.ps1
```

Requires Windows PowerShell 5.1 or PowerShell 7, Hatch, Node.js >=22.12, npm and Docker Desktop with Compose. The launcher checks Hatch, starts Docker Desktop if necessary (standard installation location), waits for the existing PostgreSQL container, starts the API and constructor validator, and builds/starts the site at <http://127.0.0.1:4173/>. It installs locked frontend dependencies only when Vite is absent. Healthy services are reused; an occupied unhealthy port produces an error without stopping its owner. API readiness is checked through the website proxy. No migrations, seeds, credential regeneration or database resets run automatically.

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

The [ingestion contract and upgrade guide](../../../docs-website/docs/architecture/durable-text-ingestion.md) owns multipart fields, job state, fingerprints and recovery. Explicitly upgrade an existing volume to migration `0002` using `db-status`, `db-migrate`, `db-status` with the existing administrator environment. Never reseed populated data. The updated API still supports `0001` lexical reads with upload disabled. Preparation assets require explicit `hatch run workbench-api:chunking-setup`; no model inference is needed.

Upload accepts one UTF-8 `.txt`/`.md`/`.markdown` file and a required `Idempotency-Key`; optional `source_id` plus `expected_active_version_id` guard replacement. No language/model/profile field is accepted. The server uses 500/50 tiktoken structural preparation with `language_policy: unqualified_source_locale`, `sentence_language: null`; EN/RU/UK Unicode content does not imply guessed language or an English sentence model. The file is capped at 1 MiB plus 64 KiB transport overhead, two admitted uploads and 30 seconds. Completed jobs and source versions publish atomically; unchanged/replayed results retain truthful actual chunk counts. Reserved errors expose `error.job_id`.

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

Capabilities uses `contract_revision: "rag-api-v1.0"`, `deployment_mode: "single_workspace_dev"` and a lifecycle `service_state`. A qualified configuration advertises only `postgres-fts-baseline`, revision `postgres-fts-baseline-r1`, with document/search features true. Otherwise profiles are empty and those features false. All responses carry generated request/trace IDs and `X-Request-ID`; safe errors add code, message, retryability and HTTP status. Additive `features.upload`, `features.document_details` and `features.jobs` report their separately verified migration/resource requirements. The backend revision is independent of the constructor validator's revision.

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

## Configuration

Settings are parsed before startup; malformed or nonlocal configuration fails instead of silently widening access.

| Environment variable             | Default                                                             | Constraint                                                                                   |
| -------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `WORKBENCH_API_HOST`             | `127.0.0.1`                                                         | `127.0.0.1`, `localhost` or `::1`; no public bind                                            |
| `WORKBENCH_API_PORT`             | `8011`                                                              | Integer from 1 to 65535                                                                      |
| `WORKBENCH_API_BACKEND_REVISION` | `workbench-api-lexical-v1`                                          | Opaque ASCII identifier, 1–128 characters                                                    |
| `WORKBENCH_API_ALLOWED_ORIGINS`  | HTTP origins for `localhost` and `127.0.0.1` on ports 5173 and 4173 | Comma-separated exact loopback origins; no wildcard, credentials, paths or duplicate entries |
| `WORKBENCH_DB_DSN`               | Unset                                                               | Secret local PostgreSQL URI for the restricted application role; loaded by `use-dev-env.ps1` |
| `WORKBENCH_LOCAL_SOURCE_ROOT` | Unset (local originals unavailable) | Explicit absolute local directory; same-machine interactive Windows for native selection |

Administrator-only commands use `WORKBENCH_DB_ADMIN_DSN` and `WORKBENCH_DB_APP_PASSWORD`, loaded with `-IncludeAdmin`. Keep those out of the API terminal. There is no feature-enable switch; actual storage, corpus and pipeline binding must qualify.

The default pool uses one to four connections, at most 16 waiters, and three-second acquisition/statement/lock timeouts. Each search reads its corpus fingerprint and active-version hits in one read-only REPEATABLE READ transaction, through a fresh Haystack pipeline with genuine async SQL. Cancellation reaches transaction cleanup before its admission slot is released. Synchronous component execution explicitly refuses this loop-bound pool.

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

- **API:** health/discovery, authorized workspace/document lists and Haystack-orchestrated PostgreSQL lexical search, with bounded admission and safe metadata/errors.
- **Persistence:** pinned PostgreSQL + pgvector, explicit migrations/seed, forced workspace RLS, atomic publication and consistent active-version snapshots.
- **Internal parsing boundary:** immutable static parser registry and bounded UTF-8 TXT/Markdown inspection/projection under `parsing.py` and `parser_registry.py`; consumed by the separate durable ingestion routes. See the [format matrix and parser/chunking handoff](../../../docs-website/docs/architecture/content-aware-chunking-strategy.md).
- **Internal chunk preparation:** `prepare_chunks(...)` consumes the verified parser result and server-owned source/version identity; versioned default sizing is 500 tokens with target overlap 50, counted by `tiktoken:o200k_base`. Only English (`en`), Russian (`ru`) and Ukrainian (`uk`) hints are accepted. EN/RU combine their NLTK sentence boundaries with token sizing; UK uses explicit structural token fallback. Other languages return `UNSUPPORTED_LANGUAGE`. No upload route or SQL write is introduced.
- **Existing independent validator:** real Haystack construction/connectivity checks, without execution; see [validator documentation](../validator/README.md).
- **Existing UI:** fixture document displays, Preview and approved Live keyword search; see [Workbench documentation](../web/README.md).
- **Ingestion:** synchronous durable backend passed local migration/upload/search/restart gates; upload UI remains separate.
- **Planned:** Live document-management UI, genuine BM25 if separately justified, qualified embeddings, dense/hybrid retrieval and generation. Each needs its own qualification gate.

The initial database migration is explicit; no Haystack public API changes are introduced. Application rollback is stopping the optional API while preserving its database volume. Destructive schema rollback is restricted to explicitly confirmed disposable databases; the constructor validator and standalone UI remain independent.

### Internal parser limits

The parser accepts in-memory bytes and an untrusted basename/MIME, not a path or URL. Qualified TXT/Markdown adapters reuse Haystack `TextFileToDocument` through `parsing_adapters.py` and require exactly one nonempty, source-preserving extraction. The conservative unindented single-line ATX/Setext heading subset retains hierarchy; fences, tables, multiline Setext titles and complex/container syntax remain protected raw spans with warnings. Known-signature checks do not claim universal executable/polyglot detection; no source code or content link is executed. Planned PDF/Office/code/media entries cannot dispatch even if an upstream converter is installed.

Reviewed defaults are 1 MiB, 4,096 elements and a shared 2,000 ms cooperative deadline. These synchronous checks do not provide process isolation or preempt a blocked dependency. Safe failures and operational metadata omit content and raw filenames. Chunking and ingestion must consume the verified immutable result without a second MIME classifier; workspace resolution, version publication and public format advertisement remain consuming-workflow responsibilities.

### Internal chunking contract

The [chunking policy decision](../../../docs-website/docs/architecture/content-aware-chunking-strategy.md#token-budgeted-chunking-policy) owns profile/counter/resource identity, protected span handling and the ingestion handoff. The pure resolver lives in `chunking_profiles.py`; `chunking.py` orchestrates the reviewed Haystack/tokenizer adapter. Source text cannot select an executable strategy. Markdown headings and protected spans come from the verified parser, and overlap remains within a section/prose span. Oversized protected blocks fail safely; unpaginated sources do not gain fabricated page metadata.

The baseline counter is independent of optional exact-model admission. `LocalQwenTokenCounter` qualifies the operator-configured `Qwen3-Embedding-4B` tokenizer revision and three JSON asset hashes without weights, downloads or inference. Its serialized NFC/postprocessor appends `<|endoftext|>` ID 151643, rather than guessing from config EOS 151645. This proves local counting, not served-TEI parity. `ModelTokenAdmission.embedding_input(content, heading_path=...)` composes prefix, optional per-chunk heading context, content and suffix; admission and the future embedding caller must use the same input. Configured exact overflow refuses with `MODEL_TOKEN_LIMIT_EXCEEDED`, without truncation or automatic rechunking. The separate [ingestion workflow](../../../tasks/TASK-RAG-002-ingest-text-and-markdown.md#j3-consume-prepared-chunks) publishes through the existing persistence port.

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

These are example IDs/paths; registration creates no source and performs no ingestion. It stores a relative original pointer and byte SHA256 in the existing version metadata. Exact retry is idempotent; conflicting binding, foreign/inactive/demo records and disallowed paths fail. Registration changes corpus revision and cursor validity because version metadata participates in the corpus fingerprint. No SQL migration is required.

The metadata GET returns only `name`, `can_reveal`, optional safe `reason` and correlation. A reveal POST accepts only JSON `{}`, requires an explicit allowed Origin and rechecks current scope/version, allowed-root containment, regular-file identity and byte SHA before native dispatch. Originals are limited to 512 MiB with a five-second verification deadline. UNC/device/ADS/reparse paths and network drives are refused. The browser never submits/receives the local path. See the [local originals guide](../../../docs-website/docs/architecture/local-source-reveal.md) for exact errors, deployment limits and verification.

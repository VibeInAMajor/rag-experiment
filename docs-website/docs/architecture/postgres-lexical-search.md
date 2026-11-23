---
title: PostgreSQL lexical search
description: Run the approved read-only Haystack profile over the persisted development corpus.
---

# PostgreSQL lexical search

**Created:** 2026-11-21  
**Updated:** 2026-11-22

The API executes **`postgres-fts-baseline`**, revision **`postgres-fts-baseline-r1`**, over the existing PostgreSQL development corpus. A fixed Haystack pipeline calls the application-owned persistence adapter and returns actual PostgreSQL full-text ranks. No second store, startup seed, embedding inference or generation is involved. The browser offers fixture Preview and approved Live keyword search; it never substitutes Preview after a Live failure.

The [canonical runtime contract](rag-runtime-contract.md) owns API semantics. Follow the [PostgreSQL operations guide](postgresql-foundation.md) for the pinned database, explicit migrations, seed, backup and recovery. The immutable seed is eight synthetic technical sources in workspace `development`. The separate [durable TXT/Markdown ingestion workflow](durable-text-ingestion.md) publishes into the same active-version corpus; legitimate uploads increase source/chunk counts and change corpus revision without changing this retrieval profile.

## Start and discover

After completing database setup, run from the repository root in an application-only PowerShell terminal:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
```

The API binds to `127.0.0.1:8011`. A configured connection is not an enable flag: readiness checks the actual migration/checksum, extension, restricted role, forced RLS, complete bounded active corpus, valid GIN index and allowlisted pipeline construction. No search or inference is performed on each health check.

From another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/ready
$lexicalCapabilities = Invoke-RestMethod http://127.0.0.1:8011/api/v1/capabilities
$lexicalProfile = $lexicalCapabilities.profiles | Where-Object profile_id -EQ 'postgres-fts-baseline' | Select-Object -First 1
if ($null -eq $lexicalProfile) { throw 'No approved lexical profile is ready.' }
```

Liveness is independent of storage. Readiness is 200 while at least one authorized profile qualifies; unavailable, incompatible, empty or oversized corpora produce 503 `NOT_READY` when none qualify. Discovery can still return 200 with `profiles: []`. The baseline remains the default, while the [approved profile registry](profile-registry.md) permits additional immutable lexical policies using the same FTS composition. Each policy is subject to its own bounds, workspace rollout and revision fence. The dependency's separate database status is not a substitute for execution-profile qualification.

## Read persisted metadata and search

```powershell
Invoke-RestMethod 'http://127.0.0.1:8011/api/v1/workspaces?limit=50'
$lexicalDocuments = Invoke-RestMethod 'http://127.0.0.1:8011/api/v1/workspaces/development/documents?limit=3'
$lexicalDocuments.items
$lexicalRequest = @{
    query = 'backups'
    top_k = 5
    profile_id = $lexicalProfile.profile_id
    expected_profile_revision = $lexicalProfile.profile_revision
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8011/api/v1/workspaces/development/search' -ContentType 'application/json' -Body $lexicalRequest
```

All four request fields are required. Use the advertised immutable profile revision. The server trims the query and accepts 1–4096 Unicode code points; NUL, empty values, numeric coercions and unknown fields are rejected. `top_k` is an integer from 1 to 50. There are no client SQL, graph, filter, model or provider overrides.

Search returns `mode: "live"`, `status: "success"`, profile/corpus revisions, generated run/request/trace IDs, actual duration and ranked stored passages. Each hit includes `chunk_id`, `source_id`, **`source_version_id`**, title, content, rank and `score_type: "postgres_ts_rank_cd"`. Page is omitted when provenance is absent. Render content as text, with unsafe HTML escaped. A zero-hit query returns HTTP 200 and `results: []`.

Document pages come from actual source/version/chunk records, including active version, status, chunk count and update time. Both list routes accept `limit` 1–100, default 50. When `next_cursor` is present, pass it unchanged on the same endpoint and workspace, for example:

```powershell
if ($lexicalDocuments.next_cursor) {
    $lexicalCursor = [Uri]::EscapeDataString($lexicalDocuments.next_cursor)
    Invoke-RestMethod "http://127.0.0.1:8011/api/v1/workspaces/development/documents?limit=3&cursor=$lexicalCursor"
}
```

Cursors are authenticated, opaque and scoped to the endpoint, workspace and list/corpus revision. The signing key is process-local; restart or changed list state expires prior cursors. They have no wall-clock TTL in this implementation. Invalid, tampered, foreign or expired cursors return 400 `INVALID_CURSOR`; restart from the first page. Empty lists return an empty page and a null next cursor.

## Ranking, snapshots and timing

The approved profile uses PostgreSQL's **`simple`** text-search configuration, generated `tsvector`, GIN and `plainto_tsquery`. Terms are case-folded by PostgreSQL and combined with **AND** semantics; no language-specific stemming, semantic expansion or paraphrase understanding is promised. Application normalization trims surrounding whitespace; it does not claim embedding-tokenizer or Unicode normalization parity. Results sort by descending raw `ts_rank_cd`, with `chunk_id COLLATE "C"` breaking ties before limiting. This explicit ASCII identifier ordering matches projection checks and does not depend on the database's language collation.

Raw lexical ranks are not BM25, percentages or probabilities. They are not comparable with future dense/fusion profiles. No fallback substitutes Preview results after a database error or a weak lexical match.

The adapter reads the persisted workspace manifest and ranked active-version hits in one **read-only REPEATABLE READ transaction** for a search, following [PostgreSQL snapshot semantics](https://www.postgresql.org/docs/17/transaction-iso.html). It does not enumerate or hash the active chunks to establish each search snapshot. `corpus_revision` is an opaque committed generation identity; callers compare it for equality rather than parsing it as a content hash. Documents use their own consistent snapshot; unchanged persisted state has the same revision across requests and process restarts. Changed publication or local-original registration advances the revision and expires corpus-bound cursors. Workspace filters and active-version constraints remain server-owned. See the [generation operations guide](persisted-index-generations.md) for migration, reconciliation and rollback.

Each search constructs a fresh, one-component Haystack `Pipeline` and awaits its public `run_async()` method. The component genuinely awaits the existing PostgreSQL pool; synchronous `run()` explicitly refuses execution because that pool belongs to its async event loop. Cancellation reaches the pipeline, SQL transaction and cleanup before the HTTP admission slot is released. No worker thread continues an unaccounted search.

The response has three measured stages: `corpus_load` includes pool/snapshot acquisition, schema/index checks and manifest qualification; `retrieval` measures the actual SQL query; `projection` measures conversion into the public result schema. Total monotonic server duration also includes pipeline/orchestration overhead. These are actual intervals, not inferred UI node timings. Constant-cost manifest lookup does not imply constant-cost ranking or document listing. IDs correlate operational events without promising an external tracing collector or persisted run history.

## Bounds, failures and local security

The search body is limited to **32 KiB**. The service admits at most **two concurrent searches** with a **10-second** admitted-operation deadline; the database pool retains its own shorter statement/acquisition limits. The complete corpus must fit **10,000 chunks / 50 MiB UTF-8 content**, with at most 32,768 code points per chunk. Limits are admission policy, not a measured throughput guarantee. An oversized corpus is rejected, never silently truncated.

| HTTP      | Code                                                | Action                                                           |
| --------- | --------------------------------------------------- | ---------------------------------------------------------------- |
| 400       | `INVALID_REQUEST`, `INVALID_JSON`, `INVALID_CURSOR` | Correct the request or restart pagination                        |
| 404       | `WORKSPACE_NOT_FOUND`                               | The requested scope is absent or not authorized                  |
| 409       | `PROFILE_NOT_AVAILABLE`                             | Refresh capabilities and use the advertised profile/revision     |
| 413 / 415 | `PAYLOAD_TOO_LARGE` / `UNSUPPORTED_MEDIA_TYPE`      | Respect the byte limit and JSON content type                     |
| 429       | `SEARCH_BUSY`                                       | Observe bounded `Retry-After` advice                             |
| 503       | `NOT_READY`, `DEPENDENCY_UNAVAILABLE`               | Recover the required database/schema/corpus; no fixture fallback |
| 504       | `SEARCH_TIMEOUT`                                    | A bounded operation exceeded its deadline                        |
| 500       | `INTERNAL_ERROR`                                    | Correlate the safe error by trace ID                             |

Errors retain generated request/trace metadata and `X-Request-ID`. Failures after admission also carry the allocated run ID; invalid requests/profile selections do not create a successful run. Retry creates a new run ID. Never log request text, stored passages, DSNs or exception internals.

Only the server-resolved `development` workspace is exposed. Unknown/foreign workspace IDs are refused; UI Settings and request filters cannot grant access. The listener and origin/Host checks remain loopback-only development controls, not production authentication or tenant RBAC. Haystack telemetry, content tracing and external tracing are disabled for this isolated API.

## Qualification and rollback

The integration decision is unchanged: the evaluated `pgvector-haystack` layout/implicit DDL did not preserve the migration-owned composite references and forced RLS. Reuse the existing SQL persistence adapter behind the small Haystack component; do not create an integration-owned duplicate table. See [compatibility evidence](../../../tasks/evidence/pgvector-compatibility-2026-11-21.json).

A direct local probe on 2026-11-21 returned the eight stored documents, advertised this profile and retrieved `demo-backup` for `backups`, with actual raw score `0.10000000149011612`. Document/search corpus revisions matched. This is a recorded probe, not the complete quality or restart gate.

The completed [retrieval task](../../../tasks/completed/TASK-RAG-001-postgres-lexical-readonly-slice.md) records **144 passing tests**, including **57 real PostgreSQL integration cases**. All ten labeled exact-term/identifier queries found their expected source in the top five. All three paraphrase diagnostics missed their expected source; these are non-gated lexical limitations, not semantic-search evidence. Direct SQL parity, zero hits, tie order, scope/profile failures, cancellation and outages are tested. The [real HTTP evidence](../../../tasks/evidence/postgres-lexical-http-2026-11-21.json) records unchanged documents, corpus revision, ranked IDs, scores and content hashes after both API and database restarts. Fixture Preview and synthetic vectors do not establish retrieval quality.

Application rollback disables the live profile/API integration while retaining PostgreSQL rows and its volume. Do not auto-seed on restart, delete the volume, or reinterpret the Preview BM25 node as executable for this profile. Fixture Preview and constructor validation retain their independent behavior; the approved Keyword search graph is connected to this Live API. Upload/document-management UI remains a separate task.

## Compatibility after ingestion

The additive ingestion routes do not change search request fields, native FTS scoring or active-version filtering. Atomic replacement makes only the committed new version searchable; failed processing preserves the old active version. The ingestion collector rechecks all ten canonical exact queries and three separate paraphrase diagnostics against the expanded corpus after upload and each restart. Historic [Live acceptance](../tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) retains its original eight-source/schema-0001 evidence; its fixed-corpus harness is not reused after legitimate ingestion changes. New ingestion evidence is collected separately.

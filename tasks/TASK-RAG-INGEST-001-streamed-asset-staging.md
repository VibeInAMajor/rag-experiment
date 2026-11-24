# TASK-RAG-INGEST-001 — Stream multipart input to immutable durable source staging

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-INGEST-001-streamed-asset-staging.md

## A. Title

Stream multipart input to immutable durable source staging.

## B. Context / Problem

Current RequestBoundary._upload_request creates whole-body bytearray; read_upload calls request.body() and creates another bytearray; UploadInput.content is bytes. This is a memory amplification problem before parsing, not a Qwen limit.

## C. Current Repository State

boundary.py:340-400, upload_transport.py:read_upload, ingestion.py:UploadInput, upload_policy.py. Current PDF cap 8 MiB; CONTENT-001 proposes original AssetStorePort and is not implemented.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Deliver constant-memory (per stream buffer) 100/200 MiB candidate ingestion staging, exact SHA256, tenant-scoped durable asset reference and error/cleanup safety.

## E. Scope

- Incremental ASGI receive and multipart callbacks
- strict existing metadata/idempotency rules
- CONTENT-001-owned AssetStorePort local implementation
- disk/quota/backpressure
- file digest and staging lifecycle
- regression tests.

## F. Non-Goals

- No PDF parsing, 202 admission, permanent public size increase, remote asset URLs or new source writer.

## G. Architecture / Boundaries

ASGI stream -> bounded multipart decoder -> provider-neutral AssetStorePort -> scoped staged asset. Do not allocate whole body or whole file in request processing. Reuse CONTENT-001 owner.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

StagedAsset{opaque_ref,workspace_id,sha256,bytes_count,media_hint,staged_at,expiry}; stage_stream, stat, open_range, commit, discard. Existing source_id and expected_active_version_id remain paired; Idempotency-Key remains bound.

## I. Repository Files / Components Impacted

EDIT apps/workbench/api/boundary.py, apps/workbench/api/upload_transport.py, apps/workbench/ingestion/upload_policy.py, apps/workbench/api/ingestion_http.py and focused apps/workbench/api/tests/ and apps/workbench/ingestion/tests/; coordinate with CONTENT-001 asset modules. MUST NOT edit framework Haystack or applied 0001/0002 migrations.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Apply total request limit to Content-Length and chunked uploads, cap header/field/part sizes and parser memory.
2. Write private no-follow scratch asset with bounded buffers, 256-bit digest and durable rename/flush semantics.
3. Enforce per-workspace bytes/files, global disk reserve, slow client, abort, process crash and orphan reaper.
4. Reuse MIME/signature and unsafe-path checks; reject malformed multipart and duplicated parts.
5. Measure peak RSS at 1/8/100/200 MiB; do not claim the target tier is qualified from a unit test alone.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Authorize workspace before allocation. Never log payload, path or credentials. Reject symlinks/path traversal and unsafe filename. Audit sanitized resource refusals and retention.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

Multipart split at any byte; missing boundary, duplicate field, MIME conflict, false Content-Length, unknown length; disk full/disconnect; 200 MiB SHA comparison, restart, two simultaneous uploads, cross-tenant denial; old synchronous regression.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] 200 MiB staged byte-for-byte, memory peak recorded and bounded
- [ ] no whole-file request allocation
- [ ] no partial accepted asset on failure
- [ ] existing capabilities unchanged.

## N. Documentation / Migration / Compatibility / Rollback

Feature flag OFF. Stage 100 MiB then 200 MiB only with downstream verification. Preserve originals on rollback.

Update affected OpenAPI, capability limits, operator docs and migration plans. New SQL schema must be additive; preserve accepted originals and prior active source generations.

## O. Mandatory Completion Checklist

- [ ] Reinspect source/SQL/tests and update Section C if changed.
- [ ] Confirm reuse of existing source/job/parser/chunker/storage owners.
- [ ] Prove workspace isolation, failure, disconnect, replay, crash and rollback paths.
- [ ] Test contracts, migration and affected regression suites.
- [ ] Record real resource and quality evidence or mark NOT TESTED/BLOCKED.
- [ ] Update docs and checked acceptance items with links to evidence.
- [ ] Record modified files, executed commands and commit.
- [ ] Mark COMPLETE only after every applicable gate passes.

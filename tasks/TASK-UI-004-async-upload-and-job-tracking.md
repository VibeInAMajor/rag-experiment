# TASK-UI-004 — Live Documents 202, upload progress and durable processing status

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-UI-004-async-upload-and-job-tracking.md

## A. Title

Live Documents 202, upload progress and durable processing status.

## B. Context / Problem

Current Live browser expects only final synchronous response, imposing 240s timeout and hardcoded 8 MiB/32 pages. Network upload progress and server parsing progress are distinct realities.

## C. Current Repository State

web/src/api/client.ts DocumentUploadRequest uses 1/8 MiB and uploadTimeoutMs=240000; web/src/api/contracts.ts PDF max_pages literal 32 and IngestionResponse status=completed; LiveDocumentsContent, DocumentUploadDialog, IngestionStatus already implement synchronous experience.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Display true browser transfer, then queued/processing job, then terminal indexed source only when persisted by backend. Support reload, reconnect, idempotent uncertain retry and runtime size capabilities.

## E. Scope

- Extend shared typed client/decoder for 202 accepted vs 201/200 complete
- backend-driven caps
- polling with backoff
- real transport bytes and measured page counters
- preserve Preview and Live small path.

## F. Non-Goals

- No fake processing percentages, separate fetch client or invented 1000-page availability.

## G. Architecture / Boundaries

Existing React Live Documents controller -> shared API -> 202 accepted -> persisted job polling -> completed version refresh. Preview fixtures remain isolated.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

Discriminated accepted/complete DTOs, job_id/status_url, version identity, optional true worker pages_completed/total_pages. Transfer percentage requires a progress-capable browser transport, not inferred request size.

## I. Repository Files / Components Impacted

EDIT apps/workbench/web/src/api/client.ts, contracts.ts, decode.ts, document controller, DocumentUploadDialog, IngestionStatus, tests and README.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Strictly decode versioned 202, 201, 200 without equating queued to indexed.
2. Advertise 100/200 MiB only from verified backend capabilities, fallback to current 8 MiB/32-page limits.
3. Poll GET job with bounded backoff and visibility-aware pause; reconnect with same scoped job/idempotency identity.
4. Separate real network byte transfer from persisted worker page/stage counters; do not invent ETA.
5. Treat cancel-before-accept differently from stop-tracking-after-accept.
6. Refresh documents/chunks/search only on authoritative completed active version.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Do not persist raw bytes in storage/logs or leak scoped job IDs across workspaces. Validate all response identities and server-origin constraints.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

DTO negative cases, 202/201/200, 409/413/429/503, response lost, reconnect/reload, simulated 200 MiB transfer, real browser API+DB qualification, npm typecheck/test/build and Preview regression.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] 202 always queued not indexed
- [ ] real measured progress only
- [ ] no double accepted job on retry
- [ ] old Live/Preview behavior passes.

## N. Documentation / Migration / Compatibility / Rollback

Gate by qualified backend capability, preserve legacy synchronous flow and track accepted jobs through UI rollback.

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

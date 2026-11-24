# TASK-RAG-INGEST-002 — Accept staged originals and durable jobs atomically before HTTP 202

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-INGEST-002-atomic-http-202-job-admission.md

## A. Title

Accept staged originals and durable jobs atomically before HTTP 202.

## B. Context / Problem

Current request waits for final publication. Jobs persist but original bytes do not, and nonterminal idempotency replays become failed. A bare background coroutine loses work after API restart.

## C. Current Repository State

ingestion_http.py:IngestionRoutes.upload awaits service.ingest and returns 201/200; postgres_ingestion.py:_reserve_row marks nonterminal replay failed, recover_ingestions sets INTERRUPTED; contracts.py has completed-only IngestionResponse.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Return 202 only after asset staging plus one committed workspace-scoped job and queue record; stable same-key replay and crash recovery.

## E. Scope

- Additive PostgreSQL queue/outbox migration
- durable stage-to-job reference
- admission limits
- new 202 acceptance DTO and status
- keep legacy terminal path gated.

## F. Non-Goals

- No worker implementation or browser UX, no distributed SQL/blob transaction, no new source registry.

## G. Architecture / Boundaries

Verified original -> SQL transaction inserts job+queue/outbox -> HTTP 202. SQL and asset store use staged/orphan reconcile semantics. PostgreSQL SKIP LOCKED is initial QueuePort adapter, not core contract.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

IngestionAccepted{job_id,workspace_id,source_id,reserved_version_id,status=queued,status_url,replayed}; 201/200 completed responses preserved. 409 for same-key/different payload; 429/503 if admission limited.

## I. Repository Files / Components Impacted

EDIT apps/workbench/api/ingestion_http.py, apps/workbench/contracts/schemas.py, apps/workbench/postgres/postgres_ingestion.py, apps/workbench/postgres/postgres.py, apps/workbench/persistence/models.py; ADD additive SQL migration under apps/workbench/postgres/migrations/ and scoped API/Postgres tests. Do not change applied migrations or duplicate ingestion_jobs identities.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Staged bytes and digest must be stable before SQL reservation.
2. Queue item and job reservation commit in same transaction; 202 cannot precede commit.
3. Same idempotency key + same fingerprint returns same job even while running; mismatch is 409.
4. Handle crash before/after SQL commit, lost HTTP response, orphaned staged assets.
5. Check source version guard and workspace quotas transactionally; version OpenAPI contracts.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Enforce FORCE RLS for queued state, scoped asset resolution, server-derived context, retention, safe codes. Idempotency is not authentication.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

DB failure/crash boundaries, 202 response loss, same-key replay, conflicting fingerprint, update-version race, wrong-tenant poll, queue overload, restart and legacy synchronous responses.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] Every 202 has durable original and one queue job
- [ ] 409 never mutates prior job
- [ ] accepted jobs survive restart
- [ ] 201/200 compatibility retained.

## N. Documentation / Migration / Compatibility / Rollback

Additive migration and disabled-by-default async admission; rollback stops new intake, preserves queue and bytes.

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

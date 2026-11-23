# TASK-RAG-INGEST-003 — Supervised leased workers with retry, fencing and per-tenant fairness

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-INGEST-003-leased-workers-and-tenant-backpressure.md

## A. Title

Supervised leased workers with retry, fencing and per-tenant fairness.

## B. Context / Problem

HTTP detached tasks cannot restart after crashes. Current request-owned parser/chunker/publisher and in-process PDF semaphore are not a cross-replica worker system.

## C. Current Repository State

ingestion.py:_execute runs parse/chunk/publish; _pure is thread executor, _owned enforces request timeout; pdf_parser.py uses process-local BoundedSemaphore(1); postgres_ingestion.py already has guarded publication.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Independent API and worker lifecycles, at-least-once processing with exactly-once guarded version activation, resource isolation and fair queue processing.

## E. Scope

- Add worker process
- QueuePort claim/heartbeat/lease expiry/retry/deadletter
- reuse IngestionService parsing/chunking and existing publication
- shared cross-process capacity accounting
- status metrics.

## F. Non-Goals

- No Celery/Kafka mandate, duplicate publishers, unlimited PDF workers or assumption that async CPU work becomes faster.

## G. Architecture / Boundaries

Postgres QueuePort -> fenced lease -> AssetStorePort verified source -> existing parser/chunker -> existing complete_ingestion_with_publication; release DB locks before expensive work.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

Lease{job_id,owner_token,lease_epoch,expires_at,attempt,stage}; claim, renew, fail_retryable, deadletter. Terminal transaction checks fenced lease, expected source/version and integrity.

## I. Repository Files / Components Impacted

EDIT ingestion.py, postgres_ingestion.py, persistence.py, worker deployment/testing; ADD minimal queue adapter and worker entrypoint. Do not replace current ingestion publisher.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Decouple request deadline from per-stage worker budgets; no late publish from canceled sync threads.
2. Lease/renew with fencing token; reclaims do not permit old owner to commit.
3. Retry transient errors with exponential backoff and finite attempts; deadletter corrupt inputs.
4. Enforce shared tenant quotas for CPU, Docling, OCR and GPU across worker replicas.
5. Persist real stage transitions and errors; terminate sandboxed children after deadline.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Source asset scoped on every open, FORCE RLS, redacted logs, trusted job context and no network escape from PDF worker. Track attempt count, queue lag and processor RSS.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

Kill before/after parse and commit, two-worker race, expired lease, missing original, poison input, database outage, 1000 queued jobs and 3-tenant fairness; verify search p95 during intake.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] All accepted jobs recover on restart, no duplicate active versions, stale lease cannot publish, worker quotas and tenant fairness measured.

## N. Documentation / Migration / Compatibility / Rollback

Start one supervised worker and scale from measured capacity. Stop intake/drain jobs without deleting originals.

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

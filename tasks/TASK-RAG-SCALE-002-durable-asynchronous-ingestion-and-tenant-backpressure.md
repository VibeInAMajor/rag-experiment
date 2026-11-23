# TASK-RAG-SCALE-002 — Enterprise durable ingestion workers, queue and tenant resource fairness

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint, no runtime claim  
**Priority:** P1  
**Dependencies:** INDEX-001, EMBED-002, SCALE-001, CONTENT-001; completed RAG-002  , [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md)
**Source reviewed:** cb7fe844084133b7e09a623e0e39767af1e0d9f1  
**Target:** tasks/TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md

## A. Title

Enterprise durable ingestion workers, queue and tenant resource fairness

## B. Context / Problem

Current bounded synchronous ingestion works for local TXT/Markdown, not thousands of PDFs requiring OCR/vision or large source connectors. A FastAPI process-local background task is not recoverable after a crash. Need staged original bytes, durable queue leases, reliable retry/backpressure, per-tenant fairness and exactly-once source publication built on existing job model.

## C. Current Repository State

[parsing.py](../apps/workbench/api/parsing.py) and [parser_registry.py](../apps/workbench/api/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/api/chunking.py), [ingestion.py](../apps/workbench/api/ingestion.py) and [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [persistence.py](../apps/workbench/api/persistence.py) and [postgres.py](../apps/workbench/api/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [contracts.py](../apps/workbench/api/contracts.py) own API/capabilities. [pdf_worker.py](../apps/workbench/api/pdf_worker.py), [pdf_models.py](../apps/workbench/api/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/api/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
Current [ingestion.py](../apps/workbench/api/ingestion.py) stages parse/chunk/publish in one request and [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) provides durable owned jobs/idempotency but not independent queued original bytes for arbitrary replay. [upload_transport.py](../apps/workbench/api/upload_transport.py) is in-memory and bounded; [pdf_parser.py](../apps/workbench/api/pdf_parser.py) has a bounded heavy-process slot.

**Verification limit:** this is a source-backed task, not proof that the proposed feature exists. Re-inspect current code at implementation start.

## D. Goal

HTTP can return 202 only after exact source bytes and job reservation are durable. Queued workers resume after restart without duplicates, obey workspace quotas, and publish only complete versioned index generations.

## E. Scope

Asset staging, jobs/leases/outbox, worker pool and processor routing, retry/deadletter, pagination/poll/status, per-workspace CPU/OCR/GPU quotas and ingestion/embedding backpressure, connectable source adapter contract with security review.

## F. Non-Goals

No mandated Kafka/Celery installation without benchmark, no missing-original-in-memory queue, no unbounded task spawn, no fake upload percent, no arbitrary internet crawling, no second writer.

## G. Architecture / Boundaries

Existing source/asset port -> durable upload outbox and QueuePort (PostgreSQL SKIP LOCKED initially if justified) -> leased worker -> current parser/chunker/EmbeddingPort -> Postgres terminal transaction and generation. DB transaction must not remain open during model calls.

## H. Contracts / Interfaces / Data Model

Job{job_id,workspace,source_version,original_asset_ref,profile_revision,status accepted|queued|leased|parsing|chunking|embedding|publishing|completed|failed|cancelled,lease_owner,lease_expiry,attempts,retry_at,checkpoint,error_code}; API 202 only after durable asset+job. Idempotent lease/replay and current source version guard. Progress from measured steps/total only, no fictional percentage.

External schema changes MUST be reviewed in Pydantic/OpenAPI/client and versioned explicitly.

## I. Repository Files / Components Impacted

REUSE [ingestion.py](../apps/workbench/api/ingestion.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py), [upload_transport.py](../apps/workbench/api/upload_transport.py), CONTENT-001 AssetStorePort. CREATE worker.py, queue module, tests/test_async_ingestion.py, reviewed additive outbox migration, operator runbook. Do not duplicate source registry.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/api/ingestion.py`](../apps/workbench/api/ingestion.py) | _execute parse/chunk/publish is synchronous |
| [`apps/workbench/api/postgres_ingestion.py`](../apps/workbench/api/postgres_ingestion.py) | durable leased/owned ingestion job and terminal atomic commit |
| [`apps/workbench/api/ingestion_http.py`](../apps/workbench/api/ingestion_http.py) | HTTP upload, jobs/status route semantics |
| [`apps/workbench/api/upload_transport.py`](../apps/workbench/api/upload_transport.py) | bounded in-memory multipart |
| [`apps/workbench/api/pdf_parser.py`](../apps/workbench/api/pdf_parser.py) | sandboxed expensive PDF stage, separate capacity |
| [`apps/workbench/api/pdf_sandbox.py`](../apps/workbench/api/pdf_sandbox.py) | CPU/memory/time quotas |
| [`apps/workbench/api/tests/test_ingestion_resilience.py`](../apps/workbench/api/tests/test_ingestion_resilience.py) | timeout and incomplete job recovery |
| [`apps/workbench/api/tests/test_ingestion_process.py`](../apps/workbench/api/tests/test_ingestion_process.py) | process crash behavior |
| [`apps/workbench/api/tests/test_ingestion_routes.py`](../apps/workbench/api/tests/test_ingestion_routes.py) | source upload HTTP contract |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/77-m39-scalable-rag-ingestion-and-serving.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/77-m39-scalable-rag-ingestion-and-serving.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## J. Implementation Requirements — ordered blueprint

1. Freeze existing synchronous API and idempotent job semantics; design explicit 202 compatibility and retention.
2. Stage exact bytes via AssetStorePort with orphan recovery, commit durable job/outbox atomically, only then acknowledge.
3. Implement worker claim/heartbeat/lease expiry, bounded retries, exactly-one guarded publication on at-least-once delivery.
4. Add quotas, fair scheduling, per-stage CPU/GPU/Docling/OCR slots, token budgets and poison job deadletter.
5. Implement real status/poll/cancel semantics with traces, and recover known job state after API/DB/worker restart.
6. Benchmark >=1000 non-sensitive tasks across multiple tenants and process crash points; report queue lag, throughput, timeouts, memory, source integrity and safe rollback.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Design asynchronous behavior while preserving current bounded synchronous upload; use durable original AssetStorePort from CONTENT-001 and explicit job/outbox migration.

**J8.** Implement acceptance transaction: exact raw source staged + committed job reservation before returning HTTP 202; SQL and blob store not atomic so define orphan/stage recovery.

**J9.** Lease tasks to one owner with expiry/heartbeat and DB constraints; use existing Postgres `_publish` for terminal source version and index generation. Do not duplicate existing job state machine.

**J10.** Add tenant-aware ready queue, priority and backpressure for parsing/OCR/TEI, and one shared TPM-001 governor across all embedding worker replicas or a central inference gateway.

**J11.** Bound memory per packet, queue bytes, token budget, batch item count, retry count and admission delay, with correct cancellation and failure states.

**J12.** Implement GET job polling only with confirmed stage counts and recovery; no fake percentage, no claimed cancellation after remote commit.

**J13.** Test 1000+ synthetic jobs, source updated during worker crash, queued original surviving API/DB restart, late paid embedding result, 3-tenant fairness and all RAG-002 source-version regressions.

**Cross-cutting constraints:** One shared capacity authority [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) enforces 0.92 desired and 0.95 hard; separate workers cannot bypass it.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

Crash before/after parse, after model inference before DB write, after DB write before ack, duplicate messages, wrong tenant, poisonous PDF, no source blob, missing model, 429/503, 1000 job load and restart. Include latency p95, jobs/s, resource usage, no duplicate source versions.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

### L.1. Task-specific reproducible test vectors

- [ ] Source bytes/job atomic acceptance and crash between them, duplicate event and idempotent commit, quota 429/backoff.
- [ ] Source job recovered after restart without data loss; runtime no memory/worker explosion, queue lag p50/p95.
- [ ] Tenant fairness and query p95 with saturation and shared 0.95 TPM hard quota; report provider usage provenance.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

## M. Acceptance Criteria

- [ ] 202 accepted requires durable staged bytes plus job
- [ ] Same source/version cannot be published twice under at-least-once retries
- [ ] Restart resumes jobs without losing source or asset links
- [ ] Expired lease and poison worker safely recover or deadletter
- [ ] Per-workspace CPU/GPU/queue quotas prevent resource monopoly
- [ ] Real stage progress and correlation IDs visible, no fabrication
- [ ] 1000-task benchmark and 3-tenant fairness measured
- [ ] Old synchronous ingestion compatibility preserved or explicitly versioned

## N. Documentation / Migration / Compatibility / Rollback

Feature-gated async pipeline, keep working small-source path during transition. New schema additive, no 0001/0002 edits. Rollback disables intake, drains/replays jobs and preserves all uploaded source assets and active versions.

## O. Mandatory Completion Checklist

- [ ] Recheck source/architecture ownership before coding.
- [ ] Reuse existing parser/chunker/source publisher and provider-neutral ports.
- [ ] Contracts, auth, bounds, versions and failure states tested.
- [ ] Measured evaluation/gold data and negative cases recorded.
- [ ] No silent fallback, wrong score or partial ready claim.
- [ ] Retry, rollback, source/asset preservation tested.
- [ ] Hatch/SQL/browser regression suites executed and outputs linked.
- [ ] Operator documentation and capability gates updated truthfully.
- [ ] Modified file paths, resulting commit and safe evidence linked.
- [ ] Task remains PROPOSED until all acceptance gates pass.

**A–O scope change rule:** if a new migration, provider or authorization boundary is needed, revise the task before implementing.

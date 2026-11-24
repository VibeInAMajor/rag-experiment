# TASK-RAG-INGEST-004 — Batch staged chunks and atomically publish verified large-document index generation

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md

## A. Title

Batch staged chunks and atomically publish verified large-document index generation.

## B. Context / Problem

Even successful 1000-page extraction may exceed active corpus 10k chunks/50 MiB, and current _Publication holds all chunks in a tuple. Simply raising PDF size moves refusal to publication.

## C. Current Repository State

postgres_ingestion.py:_MAX_CORPUS_CHUNKS=10000 and _MAX_CORPUS_BYTES=52428800, complete_ingestion_with_publication calls _publish with full chunk list; ingestion.py:_Publication.chunks tuple. INDEX-001 plans persisted generation but remains proposed.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Bounded chunk-batch staging, exact manifest/page completeness checks, atomic activation of one generation while old version stays searchable.

## E. Scope

- Add staged generation manifest and idempotent chunk batch ingest
- terminal verified activation
- configurable workspace limits from measurements
- reuse INDEX-001 source snapshot/manifest strategy.

## F. Non-Goals

- No unbounded corpus, no second lexical ranking engine, no partial active source, no unqualified embeddings.

## G. Architecture / Boundaries

Verified PDF windows -> existing chunking -> hidden persisted staged chunks in small batches -> manifest validation -> single final transaction activates source_version, job and index generation.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

StagedGeneration{workspace_id,source_id,reserved_version_id,expected_pages,completed_pages,chunk_count,byte_count,checksum,state}; bounded stage_chunks/checkpoint/finalize. Consistent corpus generation coordinated with INDEX-001.

## I. Repository Files / Components Impacted

EDIT apps/workbench/ingestion/ingestion.py, apps/workbench/postgres/postgres_ingestion.py, apps/workbench/postgres/postgres.py, apps/workbench/persistence/models.py, apps/workbench/contracts/schemas.py and retrieval profile limits; add migration under apps/workbench/postgres/migrations/ and focused tests; preserve existing ranking and applied migrations.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Keep stage batches memory/transaction bounded with deterministic ordinals and SHA values.
2. Never return staged chunks through active search or detail routes.
3. Validate complete page/chunk counts, hashes, workspace quota, expected source version before atomic switch.
4. Make replay/unchanged commit idempotent; do not advance generation twice.
5. Replace hard coded global capacity with tested plan/workspace quotas, not unlimited values.
6. Benchmark snapshot/retrieval p95 at 10k/100k chunks and coordinate O(N) snapshot removal with INDEX-001.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

FORCE RLS on staging, no visibility before active generation, disk quotas and retention; protect old source version on all errors.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

100k+ chunks in bounded batches, process kill at each batch/finalize, quota overflow, cross-workspace leakage, unchanged/replay/cursor consistency, lexical ranking and source/page parity.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] No full chunk tuple required for large source
- [ ] no partial active results
- [ ] single generation commit
- [ ] measured quota and p95 search behavior.

## N. Documentation / Migration / Compatibility / Rollback

Additive generation migration with feature flag. Rollback stops staged writes and leaves prior active index available.

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

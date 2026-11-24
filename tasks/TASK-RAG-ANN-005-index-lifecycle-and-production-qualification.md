# TASK-RAG-ANN-005 — Operate HNSW index lifecycle and qualify production rollout and recovery

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no ANN runtime tests executed  
**Priority:** P1  
**Dependencies:** [ANN-002](TASK-RAG-ANN-002-generation-fenced-hnsw-retrieval-and-exact-reranking.md), [ANN-003](TASK-RAG-ANN-003-tenant-selective-routing-and-bounded-fallback.md), [ANN-004](TASK-RAG-ANN-004-ann-qualification-shadow-evaluation-and-observability.md) qualified evidence; [OPS-002](TASK-RAG-OPS-002-index-promotion-backup-and-disaster-recovery.md) owns shared promotion and DB+asset recovery and depends on ANN-001 feasibility (coordinate in parallel; no dependency on ANN-005); [SCALE-001](TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md), [SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md), [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md), [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md), [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) required for claimed enterprise rollout.  
**Repository snapshot inspected:** ce3b331e5869d563b9bfbabc034b2158148990b3  
**Target:** tasks/TASK-RAG-ANN-005-index-lifecycle-and-production-qualification.md  
**Roadmap:** [RAG index, retrieval and enterprise plan](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md)

## A. Title

Operate HNSW index lifecycle and qualify production rollout and recovery

## B. Context / Problem

Concurrent index build/drop is not free: it can wait on transactions, consume CPU/RAM/disk/WAL, and leave invalid indexes. Production rollout must preserve active source/index generations, exact/lexical service and canonical data across failures and restores.

## C. Current Repository State

[db_migrations.migrate](../apps/workbench/postgres/db_migrations.py) owns checksum-validated transactional Alembic/SQL migrations and a separate administrator; it cannot directly execute CREATE/DROP INDEX CONCURRENTLY inside its transaction. [postgres/postgres_profiles.py](../apps/workbench/postgres/postgres_profiles.py) already owns sync/qualify/activate/retire/promote/rollback; [postgres/postgres_indexes.py](../apps/workbench/postgres/postgres_indexes.py) owns generation reconciliation. [postgres/compose.yaml](../apps/workbench/postgres/compose.yaml) pins pgvector 0.8.2 / PG17. [postgres/migrations/0005_embedding_jobs.up.sql](../apps/workbench/postgres/migrations/0005_embedding_jobs.up.sql) stores canonical immutable vectors and coverage. [OPS-002](TASK-RAG-OPS-002-index-promotion-backup-and-disaster-recovery.md) is PROPOSED and owns generic generation promotion, backup/restore of DB plus assets. [Large-document ingestion map](LARGE_DOCUMENT_ASYNC_INGESTION_PLAN_2026-11-23.md) covers large-document staging, durable 202, leases and atomic publication; currently these are proposed, not proof of production-scale support.

## D. Goal

Deliver idempotent administrator-controlled physical HNSW build/validation/retirement/repair, with measured operational headroom and a successful staged rollout/rollback/recovery drill. Enable only explicitly approved cohorts after all required enterprise gates pass.

## E. Scope

Physical index lifecycle, approved additive schema metadata, concurrent DDL with safe retries and catalog verification, operational load/restart/rebuild drills, promotion and rollback integration through OPS-002, production readiness evidence.

## F. Non-Goals

No independent generic profile promotion, backup service, second publisher, duplicate quota or identity system, unconditional exact rollback, destructive data migration, automatic all-workspace activation or claims of zero-data-loss disaster recovery without shared OPS-002 evidence.

## G. Architecture / Boundaries

PostgreSQL admin/ops adapter owns physical DDL and index build health. Existing migration runner owns transactional metadata; separate reviewed autocommit administrative action owns concurrent DDL. Existing profile/generation governance owns activation and rollback; OPS-002 owns shared atomic promotion/restore and assets. Application only consumes qualified capabilities.

## H. Contracts / Interfaces / Data Model

Physical index identity includes relation/schema, compatible expression/predicate/opclass, build revision, model/dimensions, status, observed catalog readiness/validity, and qualification link. Reuse existing profile rollout/generation records; add only missing physical lifecycle state with explicit building/ready/invalid/retired semantics. Define operator run ID, idempotent action, lock/deadline/disk headroom and audit event. Catalog validity alone is insufficient; require planner and qualification evidence.

## I. Repository Files / Components Impacted

Extend [postgres/db_migrations.py](../apps/workbench/postgres/db_migrations.py) only for additive metadata/ledger compatibility, [postgres/postgres_profiles.py](../apps/workbench/postgres/postgres_profiles.py), [postgres/postgres_indexes.py](../apps/workbench/postgres/postgres_indexes.py) and existing admin/runbook owners; add physical-index admin helper/tests under postgres only if distinct from OPS-002 shared lifecycle. Update [PostgreSQL runbook](../docs-website/docs/architecture/postgresql-foundation.md), Live Dense runbook and profile discovery docs. Preserve migration 0001–0005 and any subsequently applied revisions, main DB volumes, originals, mappings and full vectors.

## J. Implementation Requirements

1. Use approved ANN-001 layout and ANN-004 evidence. Create next sequential additive metadata migration if required, never change historical checksums. Run CREATE INDEX CONCURRENTLY / DROP INDEX CONCURRENTLY as explicit administrator outside transaction blocks; use allowlisted identifiers, scoped admin authorization, bounded lock/wait/statement budgets and idempotent reconciliation. Do not blindly trust IF NOT EXISTS or drop an unknown index; verify catalog definition, table, expression/predicate, opclass, indislive/indisready/indisvalid and actual plans.
2. Track build/rebuild progress, long transactions/locks, CPU/RAM, disk and WAL headroom and ingestion impact; enforce operator stop criteria and owned index cleanup. Test interrupted/invalid build, duplicate retry, disk exhaustion in disposable resource limits, concurrent publish, version upgrade, restart, index bloat and vacuum/reindex trade-offs. Maintain old qualified path while candidate builds where feasible.
3. Coordinate OPS-002 shared atomic promotion/rollback and verified DB+asset backup/restore; do not introduce duplicate lifecycle or restore logic. Bind physical index revision and qualified current generation to existing rollout; candidate index not executable before gate. On invalidation/recall regression retire capability, apply ANN-003 bounded fallback only when eligible; otherwise explicit unavailable. Drop old index only after rollback window and active reader safety, never delete embeddings or original assets.
4. Require SCALE-001 authenticated workspace/role isolation, SCALE-002/INGEST-001..004 durable fair ingestion, INGEST-004 measured quotas and >=100k active chunk serving qualification, TPM-001 shared real model admission under target concurrency, OPS-001 safe telemetry and OPS-002 recovery evidence before enterprise rollout. Use OPS-003 evidence for 1000-page/200 MiB PDF claims and DELTA-001 evidence for optimized delta workload claims; no synthetic SQL benchmark substitutes for either. Local/disposable lifecycle drills can precede enterprise gates.
5. Qualify selected cohorts with real >=100k active chunk ingestion/search end-to-end (including skew, mixed profiles, delta/source replacement and concurrent jobs); optional 1M only if capacity measured. Record p50/p95/p99, throughput, error/fallback/underfill, recall, queue fairness, resource headroom and recovery behavior with bounded exact and lexical regression. Do not widen quotas here; use INGEST-004's qualified envelope. Roll out opt-in by cohort: shadow -> approved canary -> explicit operator promotion; stop on failed quality/security/resource gates.
6. Exercise clean shutdown, crash/restart, failed activation, rollback and restore; prove data/hash/identity preservation against independent oracle and original evidence, no stale or cross-workspace hits, no silent fallback. Record recovery time, recovery point and limitations; no unconditional zero-RPO claim for disaster recovery. Publish reviewed runbook with ownership, detection, repair and rollback commands.

Follow [AGENTS.md](../AGENTS.md) and [engineering conventions](../docs-website/ENGINEERING.md). Reuse existing owners; names MUST describe domain behavior, never task IDs. Provider-neutral application contracts MUST NOT expose PostgreSQL SQL, pgvector operators or a specific embedding SDK. Do not modify applied migrations, overwrite canonical full vectors, weaken RLS, or add a second authoritative store. Reinspect source, tests and dependencies before implementation; amend this A–O contract before material scope changes.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, parameterized SQL, the least-privileged application role, FORCE RLS and transaction-local scope for every candidate, mapping and metadata lookup. Treat query, document and graph text as untrusted data, not SQL or instructions. No credentials, DSNs, raw vectors, private queries, document content or sensitive paths in logs/evidence. Persist only authorized safe identifiers, policy/revision hashes, counts, timings and reason codes; restrict detailed evidence access and retention under [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md). No new external egress or provider-specific core dependency. Admin DDL and promotion privileges must be separate from search/worker credentials; no RLS bypass for serving. Backup artifacts are sensitive and access/retention controlled by OPS-002.

## L. Testing / Evaluation / Runtime Verification

Disposable actual DDL/restart/recovery drills; catalog validity and mixed dimensions; build failure and repair, concurrent readers and ingestion, lock/disk pressure; shared OPS-002 restore/hash evidence; tenant authorization and stress/fallback regression; real Live capability and browser smoke. Run scoped Hatch workbench-api:check/test/types and actual disposable PostgreSQL integration tests; use repository Hatch conventions (Ruff and pytest), not system Python/pip. If web contracts change, run npm typecheck, format:check, test, build and real Live/Preview smoke. Record actual commands, exit codes, test counts/skips, runtime versions and evidence paths; no mock counts as runtime proof.

## M. Acceptance Criteria

- [ ] Concurrent DDL is outside transaction, idempotent, scoped and recoverable; no invalid index can become eligible.
- [ ] Runtime load, resource headroom, recovery and large-corpus quality/latency gates recorded for each approved cohort.
- [ ] All enterprise prerequisites have linked measured evidence before production promotion; unqualified cohorts stay disabled.
- [ ] Zero unauthorized/stale/wrong-model hits; rollback preserves canonical vectors, source/asset identity and lexical availability within qualified resource limits.
- [ ] Shared OPS-002 recovery and promotion drills pass; operator runbook, opt-in rollout and rollback window reviewed.

## N. Documentation / Migration / Compatibility / Rollback

Additive metadata migrations; separate administrator DDL; preserve exact/lexical profile revisions and current data. Rollback retires ANN capability first, uses qualified exact only under bounded fallback contract, then removes owned index after safe rollback window. Preserve originals, vectors, mappings, history, and backup manifests. Restore proof and recovery objectives belong to OPS-002.

## O. Mandatory Completion Checklist

- [ ] Reinspect repository and record source/contract changes before coding.
- [ ] Reuse existing owners; review naming, architecture and dependency direction.
- [ ] Execute applicable unit, contract, integration, failure, adversarial and regression checks.
- [ ] Link actual evidence, commands, environment, limitations and unresolved risks.
- [ ] Verify documentation, compatibility and non-destructive rollback.
- [ ] Record modified paths and implementation commit; mark COMPLETE only when the task-local gates pass.

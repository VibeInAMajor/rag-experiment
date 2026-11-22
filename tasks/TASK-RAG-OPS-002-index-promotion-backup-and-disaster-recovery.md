# TASK-RAG-OPS-002 — Search generation build, promotion, backup/restore and zero-data-loss recovery

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint, not implemented  
**Priority:** P1 before production index releases  
**Dependencies:** INDEX-001, PROFILE-001, EMBED-002, ANN-001; coordinate CONTENT-001 and SCALE-002  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-OPS-002-index-promotion-backup-and-disaster-recovery.md

## A. Title

Search generation build, promotion, backup/restore and zero-data-loss recovery

## B. Context / Problem

Production ANN builds, model version upgrades, embedding backfills and multi-workspace data require reliable generation promotion/rollback and reproducible backups for PostgreSQL plus the original asset store. An index is not itself the document source; it may be rebuilt, but original PDF/image and active source history must remain safe. Current operator runbook covers local backups, not full blue/green search generation promotion with live readers.

## C. Current Repository State

[PostgreSQL runbook](../docs-website/docs/architecture/postgresql-foundation.md) covers pinned Docker service, migrations, seed and basic persistence. [db_migrations.py](../apps/workbench/api/db_migrations.py) is checksum validated. [postgres.py](../apps/workbench/api/postgres.py) supports active source version, GIN and exact cosine; [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) makes publish+job atomic. There is no unified production semantic generation lifecycle, ANN build promotion or verified blob+SQL restore process yet.

**Evidence rule:** this source audit is not proof that the proposed new feature is working. Re-read code and tests at task start.

## D. Goal

Build a candidate search generation in shadow without affecting Live, validate coverage/recall and index health, promote it conditionally and roll back to previous qualified generation. An operator can restore SQL and original assets to an internally consistent manifest and reproduce authoritative source/version/asset evidence.

## E. Scope

SearchIndexLifecycle states, rebuild and canary commands, immutable profile/generation manifest, ANN CONCURRENTLY create/drop, recovery from stuck model jobs/migrations, SQL+AssetStore coordinated backup, RPO/RTO measurement, rollout safety checks and runbooks.

## F. Non-Goals

No automatic destructive downgrade, no force-ready flags, no deleting original assets when vector index fails, no backup upload to public repository, no covering old model/vector rows with a new revision identifier.

## G. Architecture / Boundaries

Operator-approved IndexLifecycle service -> versioned committed index generation/candidate in PostgreSQL -> qualified build artifacts and AssetStore snapshot. Read queries pin active generation transactionally; an operator compare-and-set promotion is the sole gate. Model providers and ANN physical schema are adapter details.

Provider neutrality and source/tenant ownership are mandatory. Do not create empty Manager/Factory wrappers without demonstrated need.

## H. Contracts / Interfaces / Data Model

IndexGeneration{workspace,profile_id,source_generation,embedding_profile,physical_index_name,state planned|building|validating|ready|active|failed|retiring,chunk_coverage,quality_evidence,previous_generation,created_at,promoted_at}; OperatorAction{action,expected_active_generation,actor_id,trace_id,dry_run}; BackupManifest{db_lsn,asset_snapshot_id,source_generation,schema_revision,object_hashes,verified_restore_time}. No mutable alias without compare-and-set.

## I. Repository Files / Components Impacted

CREATE apps/workbench/api/index_lifecycle.py and tests/test_index_lifecycle.py, apps/workbench/postgres/operator-index.ps1 (only if conventional) and tasks/INDEX_OPERATIONS_RUNBOOK_2026-11-23.md. MODIFY Postgres adapters/profiles only after INDEX-001/ANN-001 implementation; REUSE current [db_migrations.py](../apps/workbench/api/db_migrations.py) and [PostgresPersistence](../apps/workbench/api/postgres.py). MUST NOT rewrite 0001/0002 or remove named DB volume.

MUST NOT modify historical migration 0001/0002, framework haystack/ or unrelated Preview/validator implementations as a shortcut.

## J. Implementation Requirements — ordered blueprint

1. J1 — Document state machine, current backup process, RLS, source index and model generation ownership, and how SQL/blob backup consistency will be achieved. Identify incompatible schema changes before operator action.
2. J2 — Implement operator dry-run plan and migration/index checks, verifying real schema revision, extension, model digest, index valid/ready, generation coverage and source asset hashes without reading secrets into evidence.
3. J3 — Build shadow generation and physical HNSW/GIN where needed using safe DDL (CREATE INDEX CONCURRENTLY outside transaction when appropriate); keep old committed profile active.
4. J4 — Execute quality/latency benchmark and mandatory gates before conditional promotion; use compare-and-set expected_active_generation to prevent racing operator actions.
5. J5 — Recover from interrupted embedding job, invalid ANN, stale manifest, incomplete original asset, corrupt migration, DB restore and failed operator rollback. Never return half-built generation in capabilities.
6. J6 — Rehearse database+asset restore in isolated environment, verify original bytes and source version IDs, recorded RPO/RTO, failover/rollback and no synthetic profile substitution.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext and FORCE RLS across all source, asset and index paths. Keep private source bytes, vectors, prompts, credentials, user identifiers and arbitrary URLs out of logs and public evidence. Treat source/model text as untrusted data. Enforce bounded CPU/GPU/DB/network requests, cancellation, timeout, retention, auditing and safe error codes with trace/job/run IDs. Test cross-workspace and provider outage negative cases.

## L. Testing / Evaluation / Runtime Verification

Concurrent source publication during index build, invalid index, model digest mismatch, half-built generation, source-version race, stale compare-and-set, backup/restore source hashes, 3 workspace RLS, rollback after failed ANN promotion and storage unavailability. Repeat reproducible gold query sample and record actual outage windows/RPO/RTO.

Execute existing Hatch workbench-api:check/test/types, explicit disposable PostgreSQL integration; when UI changes run npm typecheck/test/build and Preview/validator smoke. Attach real command outcomes and mark unrun tests NOT TESTED.

## M. Acceptance Criteria

- [ ] Shadow generation does not alter current qualified Live search
- [ ] Promotion requires verified index health/coverage and compare-and-set
- [ ] No query sees mixed committed source/model generation
- [ ] Invalid/partial ANN fails closed while last good profile stays available
- [ ] SQL+asset restore proves byte hashes and version identity
- [ ] Recovery keeps idempotent jobs/version activation consistent
- [ ] Real RPO/RTO and rollback evidence reported
- [ ] No destructive migration/reset or original asset deletion

## N. Documentation / Migration / Compatibility / Rollback

Release management via additive state, rollback active pointer/feature capability and preserve prior index plus original bytes. Rebuild physical indexes later with tested DDL; do not force source reuploads. Document backups, retention, operator role and incident procedures.

## O. Mandatory Completion Checklist

- [ ] Reinspect current source and completed tasks.
- [ ] Confirm API/schema/architecture owners and no duplicated services.
- [ ] Error/status/authorization contracts validated and documented.
- [ ] Original source/version and all relevant profiles preserved.
- [ ] Negative, stress/restart/recovery and security tests actually executed.
- [ ] Real metrics/cost/quality or source-evidence fidelity recorded.
- [ ] CI/Hatch/frontend regression gates passed with logs.
- [ ] New capabilities reflect true current readiness, not planned behavior.
- [ ] Safe non-destructive rollback and operator actions documented.
- [ ] Mark COMPLETE only with linked evidence proving acceptance criteria.

---
title: Persisted corpus generations
description: Transactional workspace manifests, consistent lexical snapshots and explicit reconciliation.
---

# Persisted corpus generations

**Updated:** 2026-11-23

The PostgreSQL corpus remains authoritative. A workspace manifest records the committed corpus revision and active counts so that search can qualify one generation without loading or hashing every active chunk. The [implementation task](../../../tasks/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md) records executed checks and the remaining release gates. The [runtime contract](rag-runtime-contract.md) owns HTTP behavior.

Migration `0003` adds three tables in the existing `workbench` schema: `corpus_index_state` stores the current workspace manifest, `corpus_source_state` stores each active source's contribution, and append-only `index_generations` stores committed history. The manifest includes active source/chunk counts, UTF-8 content bytes, a source-manifest hash, generation/previous-generation IDs, commit/event identity and lexical index revision. Source contributions use SHA-256 hashes combined through a commutative XOR aggregate; changed publication replaces only the affected source's contribution. The aggregate is an incremental integrity identity, not a proof of semantic quality or an authorization credential.

## Publication and search

Changed source publication, source-version activation and manifest advancement share the existing database transaction. Ingestion commits its terminal job in that transaction as well. The workspace lock serializes publications; a failed transaction exposes neither a new active version nor a new generation. Unchanged ingestion and terminal idempotency replay preserve the committed generation. A changed local-original registration continues to invalidate the corpus revision and pagination cursors.

Search reads its manifest and active-version hits in one read-only REPEATABLE READ transaction. `corpus_revision` remains an opaque identifier: callers compare it for equality and must not parse its format or treat it as a content hash. Separate document-listing requests may materialize source metadata; neither document listing nor actual full-text ranking is claimed to take constant time.

Generation readiness applies to the lexical profile only. A lexical generation does not attest embedding coverage, model identity, dense readiness or an ANN index. Future semantic generations must bind their own immutable model/profile identity and coverage to the source generation. Server-resolved workspace scope and forced row-level security remain required; the current development resolver is not production authentication.

Capabilities uses the manifest's actual persisted `corpus_id` in the existing profile field. Uploaded corpora are not labeled with a fixture corpus identity. Public request/response fields and score meanings are unchanged; `PersistencePort.current_index_generation()` and `corpus_summary()` are internal persistence contracts, not new HTTP endpoints.

## Rollout and recovery

`ApiSettings.corpus_snapshot_mode` defaults to `persisted`. Normal startup reads the trusted operator environment variable `WORKBENCH_CORPUS_SNAPSHOT_MODE`, accepting only `persisted` or `legacy`; it is never a request parameter. Persisted mode requires migration `0003`. An older schema does not silently fall back to full enumeration.

Current public profile execution additionally uses the [profile registry governance](profile-registry.md) introduced by migration `0004`. The corpus read switch selects snapshot implementation only; it does not bypass revision/rollout qualification or make missing governance tables executable. The `0003` generation contract and its recorded qualification below remain unchanged.

Keep the existing database volume and credentials. Back up the selected database using the [PostgreSQL runbook](postgresql-foundation.md), stop old application writers before changing the generation contract, and run:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
```

Startup never migrates or reseeds. Migration `0003` locks corpus tables while backfilling existing workspaces once, preserving source, version, chunk and vector identities and the checksums of applied `0001`/`0002` migrations. Empty workspaces start at generation 0; populated active corpora receive a backfill generation 1. Start the upgraded API with application credentials and inspect readiness/capabilities before resuming writes. Migration and snapshot-mode changes require restarting application processes; existing browser cursors must restart from the first page.

Run offline reconciliation with the separate migration administrator after migration, after restoring a backup and when drift is suspected:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:python -m apps.workbench.postgres.postgres_indexes --workspace-id development
```

The command reads `WORKBENCH_DB_ADMIN_DSN`, locks the selected workspace, compares actual active source projections and counts with the current manifest and ledger, then reports safe IDs/counts and `consistent`. Check-only does not repair or advance the generation. Reconciliation may scan the corpus and has a 120-second statement ceiling and five-second lock ceiling; it must not run on every HTTP request. For a reviewed mismatch, preserve the check output and explicitly request repair:

```powershell
hatch run workbench-api:python -m apps.workbench.postgres.postgres_indexes --workspace-id development --repair
hatch run workbench-api:python -m apps.workbench.postgres.postgres_indexes --workspace-id development
```

Repair rebuilds source contributions and commits one new reconciliation generation; it does not change source/version/chunk/vector data. `consistent:false,repaired:true` describes a successfully repaired mismatch; the following check must report `consistent:true`. Repair on an already consistent corpus is a no-op. Missing/incompatible schema, unknown workspace, app-role credentials or a failed transaction refuse safely. Do not force a ready flag or change counts by hand.

Dirty-marking triggers invalidate the manifest after unmanaged changes to active sources, versions or chunks. Snapshot qualification checks forced RLS, enabled protection triggers, equality with the immutable ledger and that no newer committed generation exists; an older valid ledger row cannot masquerade as current state. Missing protection refuses qualification even if counters happen to match, and offline repair refuses an incompatible schema. Application credentials have read-only access to manifest/history tables. Administrator operations such as disabling triggers, `TRUNCATE`, or restore can bypass ordinary mutation protection: keep the API stopped and reconcile before resuming it. Count the safe structured `corpus_manifest_unavailable` event by workspace/code to monitor manifest qualification failures, separately from ordinary corpus-size admission refusals. Reconciliation's `consistent`/`repaired` output supplements those event counts. Collection, persistence and alerting belong to deployment monitoring; no persistent metrics dashboard or automated repair is installed.

For an explicit read-path rollback, stop the API and start the current compatible binary with application credentials and the legacy operator setting:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
$env:WORKBENCH_CORPUS_SNAPSHOT_MODE = 'legacy'
hatch run workbench-api:serve
```

Legacy mode deliberately rechecks and fingerprints the actual full bounded corpus. It can read `0001`/`0002` without the manifest; on `0003`, current application writes still maintain generations, and a dirty manifest continues to block writes. Legacy mode changes the opaque revision format and invalidates corpus-bound cursors. It does not repair a manifest or permit an old application writer to bypass the new publication contract. To return to the persisted path, reconcile first, stop the API and restart with `WORKBENCH_CORPUS_SNAPSHOT_MODE=persisted`.

Rollback preserves source rows, original metadata, vectors and the volume. Deploy code compatible with the applied schema and prefer forward repair. A disposable-test downgrade is not a production recovery procedure. Reverting the application does not reverse a database migration. Errors must not silently return fixtures or a stale cached generation.

## Qualification evidence

Use the dedicated Hatch environment from the repository root:

```powershell
hatch --version
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test
```

Database tests create disposable databases. Missing test DSNs produce skips, not database evidence. Compare publication/replay/failure behavior, cross-workspace denial, stale cursors, independently queried hit identities and scores, concurrent publication/read snapshots, and generation persistence after application and database restart.

The benchmark must separate metadata qualification from ranking, record actual query plans/rows and p50/p95 over declared sample counts, and compare the old full fingerprint with the new manifest on 8, 10k and 100k synthetic chunks. The approved Live profile retains its 10,000-chunk / 50 MiB admission ceiling. Measurements on larger disposable corpora qualify the manifest design, not a larger public profile or production throughput. Link the actual commands and measured output in the task before marking it complete.

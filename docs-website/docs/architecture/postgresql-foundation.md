---
title: PostgreSQL foundation operations
description: Local PostgreSQL and pgvector setup, explicit migrations, development seed and recovery boundaries.
---

# PostgreSQL foundation operations

**Created:** 2026-11-21  
**Updated:** 2026-11-23

The Workbench persistence foundation stores workspace, source, version and chunk records in PostgreSQL. The browser supports fixture Preview and the approved Live keyword graph; upload UI remains separate. The application now also exposes the separately qualified [PostgreSQL lexical profile](postgres-lexical-search.md), using these same records through Haystack. Storage connectivity alone does not establish execution readiness; follow the [runtime contract](rag-runtime-contract.md) for profile semantics.

## Pinned components and ownership

The [Compose configuration](../../../apps/workbench/postgres/compose.yaml) runs only this application's database, bound to `127.0.0.1:55432`, with a named `postgres_data` volume. Its image is `pgvector/pgvector:0.8.2-pg17-bookworm@sha256:feb68f4f15446397d8cac7f4fe48fe4586de83160d1fc48b46283312d1a33966`: PostgreSQL **17.10**, pgvector **0.8.2**. Do not reuse another application's database or credentials.

The root [Hatch configuration](../../../pyproject.toml) pins Alembic **1.20.1**, SQLAlchemy **2.1.9**, psycopg **3.3.9**, psycopg-pool **3.3.3**, and the pgvector Python codec **0.5.1** for the detached `workbench-api` environment. The image digest and migration checksum are compatibility inputs, not performance evidence.

Application-owned [migrations](../../../apps/workbench/api/migrations/) create one `workbench` schema. The [persistence port](../../../apps/workbench/api/persistence.py) is independent of SQL drivers; [PostgresPersistence](../../../apps/workbench/api/postgres.py) owns parameterized SQL and connection lifecycle. There is no duplicate integration-owned document table.

Haystack **3.5.0** with `pgvector-haystack` **8.2.1** was evaluated separately: genuine keyword and synthetic-vector operations worked, while automatic initialization was refused for the restricted application role. Its flat document layout and implicit DDL do not preserve the required composite foreign keys, version publication and forced row-level security. The selected adapter therefore uses the same PostgreSQL corpus directly. See the [recorded compatibility probe](../../../tasks/evidence/pgvector-compatibility-2026-11-21.json); it records no real embedding inference.

The isolated evaluation command is `hatch -e workbench-db-compat run python scripts/workbench_pgvector_compatibility.py`, using explicitly configured test administrator/application DSNs. It creates a disposable test database; the integration is not imported by the application persistence port.

## First setup

Run these PowerShell commands from the repository root. Docker Desktop must be running; Hatch must be available.

```powershell
hatch --version
& ./apps/workbench/postgres/create-dev-env.ps1
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml up -d --wait
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-bootstrap
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
hatch run workbench-api:db-seed
hatch run workbench-api:db-seed
```

`create-dev-env.ps1` generates separate administrator and application credentials in the ignored `apps/workbench/postgres/.env`; it refuses to overwrite an existing file. Preserve that file with its existing volume. Changing an initialization password in an environment file does not rotate a role inside an existing PostgreSQL volume. Treat the file as a local secret and restrict access to it.

`db-bootstrap` provisions `workbench_app` using the separate administrator connection. `db-migrate` applies explicit, transactional Alembic migrations; startup never applies migrations. The migration head is `0004`, adding immutable profile definitions and workspace rollout/audit state after `0003` persisted corpus generations. Current public profile execution requires `0004`. Explicit `WORKBENCH_CORPUS_SNAPSHOT_MODE=legacy` selects the older bounded corpus read implementation; it does not bypass profile governance. Status reports the actually applied revision, tool `alembic-1.20.1`, vector extension `0.8.2`, and a matching SHA-256 checksum over the reviewed up/down SQL. CRLF/LF checkout differences are normalized; actual SQL changes still invalidate the checksum. An unknown head, checksum drift, missing extension, disabled generation/profile protection, or unprotected scoped table makes the schema incompatible; do not edit an applied migration to repair it.

The seed is explicit and atomic. It inserts eight synthetic, non-sensitive technical sources into workspace `development`, each with deterministic source/version/chunk identity. The first command reports eight inserted sources; an unchanged repeat reports zero. Existing non-demo records or changed seed identities/content cause refusal rather than replacement. Startup never re-seeds. These passages are development data, not uploaded user documents.

Seed records persist for the lifetime of this development volume; there is no automatic expiry or cleanup endpoint. Retiring seed data requires an explicitly reviewed operation against the identified development workspace, with a backup when other records coexist. Do not use the seed command to reset data or delete records by their display title.

## Upgrade an existing populated volume

Applied migrations `0001`–`0003` remain immutable. Apply the additive `0004` profile governance migration explicitly using existing credentials and volume; earlier installations migrate through preceding revisions in order. Stop old application writers first:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
```

Do not bootstrap or reseed as a recovery shortcut. Per-revision ledger/checksums validate applied migrations, including populated upgrades and no-op reruns. `0002` adds workspace-scoped jobs, immutable terminal state, unique idempotency reservations and fenced advisory-lock ownership. `0003` backfills workspace manifests and generation history; source/version/chunk publication, manifest advancement and job completion share one transaction. `0004` adds profile revision and rollout governance without rewriting source/vector data or the preceding generation history. Original upload bytes are not persisted. See the [generation operations guide](persisted-index-generations.md) for reconciliation and read-path rollback, [profile guide](profile-registry.md) for lifecycle/compatibility, and [ingestion runbook](durable-text-ingestion.md) for upload behavior.

Startup and GET job inspection recover an interrupted job only after its owner lock is absent; lazy lookup handles database restart without relabeling another live API's work. The previous active version remains searchable on failed replacement. A migration upgrade is not reversed by reverting code: deploy an API compatible with the applied revision, retain the volume and use a reviewed forward repair where required.

## Start and inspect the API

Use a separate PowerShell terminal, loading only the application connection:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
```

From another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/live
Invoke-RestMethod http://127.0.0.1:8011/api/v1/capabilities
curl.exe -i http://127.0.0.1:8011/api/v1/health/ready
```

Liveness returns 200 while the API runs. Capabilities separately reports database status, the actually certified schema revision and committed counts. Readiness is 200 and `postgres-fts-baseline` is advertised only after schema, role, valid lexical index, complete bounded corpus and the real pipeline qualify. Otherwise readiness is 503 `NOT_READY`, profiles are empty and document/search features false. An unset connection reports `unconfigured`; unavailable, empty or incompatible storage cannot acquire executable capabilities. See the lexical guide for search/document routes and examples.

The default pool has one to four connections, at most 16 waiting acquisitions, a three-second acquisition timeout and three-second statement/lock timeouts. API dependency checks are also bounded. Each data transaction checks the unprivileged role and sets its server-resolved workspace context with transaction-local `set_config`; pooled connections cannot retain that context after transaction completion. Close the API with Ctrl+C to release its pool.

## Data, isolation and vector policy

`workspaces`, `sources`, `source_versions` and `chunks` enforce composite workspace-scoped references. A partial unique index permits one active version per source. Publication stages a complete version and switches activation in the same transaction; failed writes roll back without publishing partial chunks. Source identity does not depend on a title or path.

The original four scoped tables, plus `ingestion_jobs` at revision `0002`, use row-level security with `FORCE ROW LEVEL SECURITY`, tied to `current_setting('workbench.workspace_id', true)`. The application role is neither a superuser nor table owner, has no RLS bypass or schema creation privileges, and cannot modify migration or embedding-profile registries. The separate administrator is for explicit operations only. Server-resolved development scope and RLS are defense in depth; this local single-workspace setup is not production authentication or multi-tenant authorization.

Chunk `search_vector` is generated with PostgreSQL's **`simple`** text-search configuration and indexed with GIN. The persistence adapter uses `plainto_tsquery('simple', ...)` and actual `ts_rank_cd`, reported as **`postgres_ts_rank_cd`**. It is not BM25, cosine similarity or a probability. `simple` avoids language-specific stemming; qualify identifiers and non-English vocabulary needed by the real corpus. The separately implemented lexical endpoint reuses this adapter and does not introduce another store.

Embedding columns are nullable for lexical-only records. A dimensionless `vector` column is paired with `embedding_profile_id` and `dimensions`; a composite profile foreign key and `vector_dims` check reject mismatches. Only the explicitly synthetic `synthetic-test-v1` profile, dimension **3**, is initially enabled. Application writes validate profile enablement, dimension and finite values. Exact cosine-distance test operations are available in the adapter; no HNSW or IVFFlat index is created.

Synthetic 2560-dimensional integration tests prove storage arithmetic only. They do not qualify Qwen, TEI, normalization, tokenization or model output. No semantic execution capability is advertised; a real embedding profile needs the separate runtime probes and versioned registry decision in the canonical contract.

## Restart and recovery

Stopping the API does not alter rows. Stop/restart PostgreSQL without removing its volume:

```powershell
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml stop postgres
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml up -d --wait
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-status
```

Restart the API and inspect dependency state without running the seed again. Compare persisted IDs, content and lexical results using the integration/restart checks recorded in the implementation task. A database failure must remain an unavailable dependency; there is no in-memory fixture fallback.

Do not delete the volume or use `down -v` as an application rollback. Reverting code does not reverse durable schema changes. Add a reviewed forward migration for repair. The downgrade CLI requires both `--confirm-disposable` and a database name beginning `rag_test_`, `workbench_test_` or `workbench_disposable_`; it refuses the main `workbench` database. It is only for throwaway migration tests and drops application tables there.

After explicitly pointing `WORKBENCH_DB_ADMIN_DSN` at an owned disposable test database, its rollback entrypoint is `hatch -e workbench-api run python -m apps.workbench.api.db_admin downgrade --confirm-disposable`. Never repoint this command at customer data or rename a database to bypass its guard.

## Backups

The following creates a PostgreSQL custom-format dump inside the container, then copies its bytes into the ignored local backup directory. It avoids PowerShell text redirection of binary dump output. Use an administrator terminal with the local environment loaded.

```powershell
$dbBackupName = "workbench-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump"
New-Item -ItemType Directory -Force -Path apps/workbench/postgres/backups | Out-Null
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml exec -T postgres pg_dump -U workbench_admin -d workbench -Fc -f "/tmp/$dbBackupName"
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml cp "postgres:/tmp/$dbBackupName" "apps/workbench/postgres/backups/$dbBackupName"
```

Verify a dump before depending on it. Database dumps contain document content; the ignored directory is not encryption or an access policy. The deployment owner must define access, retention, deletion and an off-machine backup destination. Credentials and global roles are not a substitute for a database backup; provision the restricted application role separately when restoring elsewhere.

Restore only after reviewing the selected dump and choosing a **new disposable database**. For example, after explicitly copying the chosen dump to `/tmp/workbench-reviewed.dump` in this container:

```powershell
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml exec -T postgres createdb -U workbench_admin workbench_disposable_restore_review
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml exec -T postgres pg_restore -U workbench_admin -d workbench_disposable_restore_review --exit-on-error --single-transaction /tmp/workbench-reviewed.dump
```

`createdb` fails if that database already exists. Do not add `--clean`, restore over the running database, or treat an untested restore as recovery evidence. Compare migration status, committed identities, lexical results and role isolation in the restored disposable database before planning any production recovery.

## Checks and evidence

From an administrator terminal, direct container-backed tests to explicitly disposable databases:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test
```

Without test DSNs, container-backed tests skip; a passing unit-only run is not database evidence. Fixtures create their own disposable database names. The migration suite was independently executed on 2026-11-21: **five tests passed**, covering fresh/repeated migration, disposable rollback/reapply, unknown head, extension removal, checksum drift and restricted application privileges. See the [implementation task](../../../tasks/completed/TASK-DB-001-postgresql-pgvector-foundation.md) for the final integration, restart and backup evidence rather than inferring those results from these commands.

Structured diagnostics record operation names, correlation/workspace IDs, outcomes and elapsed time. They omit DSNs, credentials, text, vectors and raw database exceptions. Default diagnostics are process-local console output; persistent log capture, retention and access remain deployment responsibilities.

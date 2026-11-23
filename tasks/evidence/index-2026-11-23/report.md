# Persisted corpus generation qualification — 2026-11-23

Base commit: `44866bb7e7dc01993bbaefefdec1ab1985951cc7`, with uncommitted task changes. Scope is the local PostgreSQL lexical generation foundation. No production deployment, semantic inference, ANN, expanded Live corpus limit or production multi-tenancy is certified.

## Measured metadata establishment

[The benchmark artifact](benchmark.json) records real PostgreSQL 17.10 / pgvector 0.8.2 measurements on disposable synthetic corpora, 30 samples per size. It includes the actual SQL and guarded-query SHA-256, migration `0003` checksum, plans, counts/bytes parity checks and generation identities.

| Chunks | Reconstructed legacy p50 / p95 (ms) | Full guarded generation runtime p50 / p95 (ms) | Legacy metadata rows / manifest rows |
| ---: | ---: | ---: | ---: |
| 8 | 1.7445 / 2.4802 | 9.4963 / 15.4113 | 10 / 1 |
| 10,000 | 100.5303 / 117.8429 | 9.2706 / 14.6148 | 10,002 / 1 |
| 100,000 | 716.6820 / 776.1418 | 9.0743 / 15.1887 | 100,002 / 1 |

The legacy comparator reconstructs the original count/chunk-hash queries and Python fingerprint with a simplified document projection. Its old 10k admission cap is omitted so that the scan can be measured at 100k. It is not a byte-for-byte replay of the full historical HTTP path. The guarded runtime measures `current_index_generation()` through its transaction, role/schema/index/catalog/ledger checks and database round trips. Those checks cost more than the reconstructed raw scan on the eight-chunk corpus; the benefit appears as the corpus grows.

The local metadata gate is one manifest row with constant query shape, and 100k guarded-runtime p95 no greater than twice the eight-chunk guarded-runtime p95. **PASS:** `15.1887 <= 2 × 15.4113 = 30.8226 ms`; the measured ratio is `0.9856`. This is a measured local gate, not a production SLO. The full-text ranking query and document listing are outside this metadata benchmark. Live retains its existing 10,000-chunk / 50 MiB limit.

For comparison only, the isolated direct manifest SELECT p95 values were 0.6711 / 1.4444 / 4.1523 ms. The actual guarded SQL server plan execution times were 0.226 / 0.186 / 0.144 ms, returning one manifest row. Neither set is substituted for the full guarded runtime above. The 100k reconstructed chunk-hash plan returned 100,000 rows and used temporary sort I/O; the guarded query does not read the active chunk corpus.

Reproduce from the repository root after setting the explicit test DSNs from the existing administrator/application environment:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
hatch run workbench-api:python -m scripts.workbench_index_benchmark
```

## Isolation, publication and recovery

The [13-test INDEX result](index-tests.xml) covers atomic and failed publication, unchanged/idempotent replay, concurrent writers, MVCC snapshot consistency, RLS, restricted manifest privileges, one-time populated backfill, stale/malformed generation selection, staged-only changes and state corruption. An unmanaged write to another source was independently observed waiting on a database lock; after its commit the workspace remained dirty rather than having the drift hidden by a concurrent publication.

The separate reconciliation suite passed nine focused real-database tests. Check-only leaves a dirty generation untouched; explicit repair commits once, preserves actual hit identities/scores and becomes a no-op on repeat. Dirty state disables HTTP search/readiness/capabilities, and failed publication cannot clear it. App credentials cannot repair, disabled protections refuse reads/repair, old valid ledger pointers cannot become current, history cannot be edited accidentally, and explicit legacy reads continue to maintain generations for new writes. The final full-suite artifact records these cases with the remaining regression tests.

[The restart artifact](restart.json) records actual API shutdown/relaunch and isolated PostgreSQL container restart. Corpus revision `corpus-4be469660ec02e9dccff152fcf4932d1cf89c9debad5b48ea39ce1eb4c82386b`, generation 1, `restart-source` / `restart-version` / `restart-chunk` and raw `postgres_ts_rank_cd` score `0.10000000149011612` remained unchanged. Safe trace IDs were independently generated before and after each restart. The UUID-owned pinned-image container and loopback API processes were cleaned up; shared services and main development data were untouched.

```powershell
hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_index_generations.py
hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_index_reconciliation.py
hatch run workbench-api:python -m scripts.workbench_index_restart
```

## Changes and operational limits

The additive migration and new persistence helper own the workspace manifest, per-source contributions and immutable ledger. Existing publication/job transactions, workspace locks, RLS, migration checksums, async PostgreSQL pool, lexical Haystack execution and projection are reused. Default `persisted` requires `0003`; explicit trusted `legacy` selects the old bounded read path for rollout/rollback. Public field shapes, API/profile revisions and raw lexical scoring are preserved; `corpus_revision` is opaque, and capabilities uses the actual persisted corpus identity. Local-original registration advances the generation atomically, with exact retry unchanged.

Review found and fixed lost cursor invalidation for local registration, stale pointers to older valid ledger rows, disabled-protection repair and an unmanaged-write race. The CLI uses the established administrator environment name. Direct administrator restore/`TRUNCATE`/disabled-trigger operations require a stopped API and reconciliation before resuming service. Safe `corpus_manifest_unavailable` events support external drift counting; no persistent monitoring or automatic repair is installed.

Updated surfaces include the generation SQL/Alembic migration and helper, persistence and ingest/search composition/configuration, corresponding tests/harnesses, canonical contract/runbooks, API README, sidebar, release note, task and this reviewed evidence allowlist. Applied migrations `0001`/`0002`, source/vector data, ranking SQL, frontend code and public DTO/OpenAPI schema are preserved. Browser/frontend checks are not applicable because browser code is unchanged.

## Final regression and quality result

```powershell
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test --tb=short --junitxml=tasks/evidence/index-2026-11-23/full-tests.xml
```

[Final whole-suite JUnit](full-tests.xml): **930 passed, 16 skipped, 0 failures, 0 errors** in 237.53 seconds, after the explicit test DSN setup above. Every PostgreSQL, INDEX and reconciliation test executed. All 16 skips are native Qwen tokenizer provisioning/counting cases requiring absent `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; no model qualification is implied. The JUnit `lexical_evaluation` property records 10/10 labeled exact targets in top five and the same three known paraphrase misses, preserving the established FTS quality boundary. Existing HTTP 400/404/409/429/503/504, cancellation, SQL parity, source-version and safe-error regression cases passed.

[Quality output](quality-checks.txt): Ruff check/format passed across 95 files and mypy reported no issues in 95 source files. Documentation relative-link targets and the new sidebar ID resolved; `node --check docs-website/sidebars.js`, strict UTF-8/newline checks, `git diff --check` and the release-note backticks check passed. Broken historical links encountered in touched guides/project map were corrected to their verified `tasks/completed/` locations.

Docusaurus full build was not run because `docs-website/node_modules` is absent; no dependencies were downloaded. Its package defines no separate Markdown format command. Frontend/browser and Haystack core checks were not run because their code was unchanged. These omissions do not claim a documentation production build or browser deployment.

Result: **COMPLETE for the scoped persisted lexical generation task**. The [operator guide](../../../docs-website/docs/architecture/persisted-index-generations.md) records rollout, explicit legacy rollback and reconciliation. The task remains separate from real model admission, dense retrieval and ANN qualification.

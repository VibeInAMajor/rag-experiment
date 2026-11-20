# Workbench API and PostgreSQL foundation

An optional, independent FastAPI process for liveness, readiness and capability discovery, with an application-owned PostgreSQL persistence adapter. The HTTP API does not execute pipelines or search documents. The [canonical RAG runtime contract](../../../docs-website/docs/architecture/rag-runtime-contract.md) defines the later execution boundary; the [PostgreSQL operations runbook](../../../docs-website/docs/architecture/postgresql-foundation.md) covers database setup, migrations, backup and recovery.

## Start

Run from the repository root with Hatch:

```powershell
hatch --version
hatch run workbench-api:serve
```

The detached `workbench-api` Hatch environment gets its pinned API, PostgreSQL and migration dependencies from the root [pyproject.toml](../../../pyproject.toml). It does not install Haystack, model SDKs or the broad library test environment. Without database configuration, health/discovery still starts and reports the dependency as `unconfigured`. The development listener is `http://127.0.0.1:8011`. Stop it with Ctrl+C.

This is separate from the constructor validator at `127.0.0.1:8010`. The existing frontend does not call this API bootstrap. Starting or stopping it has no effect on offline editing, JSON import/export or fixture Preview.

### Optional persistent development database

From the repository root, with Docker Desktop running:

```powershell
& ./apps/workbench/postgres/create-dev-env.ps1
docker compose --env-file apps/workbench/postgres/.env -f apps/workbench/postgres/compose.yaml up -d --wait
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-bootstrap
hatch run workbench-api:db-migrate
hatch run workbench-api:db-status
hatch run workbench-api:db-seed
```

The ignored local environment contains separate administrator and application credentials; generation refuses to overwrite it. PostgreSQL 17.10 + pgvector 0.8.2 are pinned by image digest and bound to `127.0.0.1:55432`. Explicit seed inserts eight synthetic sources; an unchanged repeat inserts zero. Startup never migrates or seeds. Preserve both credentials and the named volume; see the operations runbook before backup, rollback or repair.

Start the API in a separate terminal with only application credentials:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:serve
```

## Routes and readiness

| Route                      | Default result                                           | Meaning                                                         |
| -------------------------- | -------------------------------------------------------- | --------------------------------------------------------------- |
| `GET /api/v1/health/live`  | HTTP 200                                                 | The API process is running                                      |
| `GET /api/v1/health/ready` | HTTP 503, `NOT_READY`                                    | No execution profile is implemented and ready                   |
| `GET /api/v1/capabilities` | HTTP 200, `profiles: []`, document/search features false | Discovery is working; no executable capabilities are advertised |

A running process and a ready database are not a ready retrieval API. The 503 response remains intentional: no HTTP execution profile is implemented. Configured persistence verifies the application role, exact schema/checksum/extension, forced workspace RLS and actual committed active corpus. Capabilities exposes this separately as `dependencies.database.status`, with `ready`, `unconfigured`, `unavailable`, `incompatible` or `empty` status. A ready database does not enable an execution profile.

Capabilities uses `contract_revision: "rag-api-v1.0"`, `deployment_mode: "single_workspace_dev"`, a lifecycle `service_state`, `profiles: []` and `features: {"documents": false, "search": false}`. A storage-ready dependency also reports schema/workspace identity and committed counts. `backend_revision` identifies this deployed application configuration; it is separate from the constructor validator's capability revision. All responses carry generated `request_id` and `trace_id` values and the `X-Request-ID` header. Readiness failure uses the same metadata and a nested `error` containing `code`, a safe `message`, `retryable` and `http_status`.

Inspect the typed response schemas in the checked-in [OpenAPI artifact](openapi.json), generated from `create_app(settings=ApiSettings()).openapi()`. A contract test verifies that it matches the application. The service exposes only the three routes above; OpenAPI is published as a repository artifact. Stable, user-safe errors carry correlation metadata; unknown routes and unexpected failures do not expose internal exception details. The canonical contract owns detailed API semantics rather than this runbook.

Manual probes from another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/live
curl.exe -i http://127.0.0.1:8011/api/v1/health/ready
Invoke-RestMethod http://127.0.0.1:8011/api/v1/capabilities
```

The first and third requests should succeed; the second should visibly return 503. These are verification instructions, not a claim that retrieval or model inference has been tested.

## Configuration

Settings are parsed before startup; malformed or nonlocal configuration fails instead of silently widening access.

| Environment variable             | Default                                                             | Constraint                                                                                   |
| -------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `WORKBENCH_API_HOST`             | `127.0.0.1`                                                         | `127.0.0.1`, `localhost` or `::1`; no public bind                                            |
| `WORKBENCH_API_PORT`             | `8011`                                                              | Integer from 1 to 65535                                                                      |
| `WORKBENCH_API_BACKEND_REVISION` | `workbench-api-bootstrap-v1`                                        | Opaque ASCII identifier, 1–128 characters                                                    |
| `WORKBENCH_API_ALLOWED_ORIGINS`  | HTTP origins for `localhost` and `127.0.0.1` on ports 5173 and 4173 | Comma-separated exact loopback origins; no wildcard, credentials, paths or duplicate entries |
| `WORKBENCH_DB_DSN`               | Unset                                                               | Secret local PostgreSQL URI for the restricted application role; loaded by `use-dev-env.ps1` |

Administrator-only commands use `WORKBENCH_DB_ADMIN_DSN` and `WORKBENCH_DB_APP_PASSWORD`, loaded with `-IncludeAdmin`. Keep those out of the API terminal. There is no feature-enable environment switch. Setting a revision, database connection or CORS origin does not make HTTP search ready.

The default persistence pool uses one to four connections, at most 16 waiters, a three-second acquisition timeout and three-second statement/lock timeouts. Queries and writes use parameterized SQL, server-resolved workspace context and transactions; active-version publication is atomic. PostgreSQL `simple` FTS + GIN and `ts_rank_cd` are storage primitives, with score type `postgres_ts_rank_cd`, not BM25. Nullable vector storage initially enables only a three-dimensional synthetic test profile; synthetic 2560-dimensional tests are not TEI/model qualification. No ANN index or semantic capability is enabled.

## Local security and diagnostics

This service is local development infrastructure, not authenticated production access or tenant isolation. CORS uses an explicit loopback origin allowlist rather than wildcard credential access. Future remote deployment requires its own authentication, TLS, origin policy and operational limits.

Operational diagnostics go to process stdout and contain only bounded correlation IDs, status/error codes and timing metadata. Query/graph/document bodies, credentials, provider identifiers and exception internals must not be logged or returned. No application-managed payload retention or external tracing is enabled. The deployment owner controls stdout capture and must define access, retention and deletion before persisting those logs.

## Checks

Run the focused application checks from the repository root:

```powershell
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
```

The tests cover health/discovery, configuration, CORS/error contracts and persistence boundaries. Container-backed tests require explicitly configured `WORKBENCH_TEST_ADMIN_DSN` and `WORKBENCH_TEST_APP_DSN`; otherwise they skip. The [operations runbook](../../../docs-website/docs/architecture/postgresql-foundation.md#checks-and-evidence) gives the environment-loading commands. Record actual results; unit-only success is not storage or model evidence.

## Implemented versus planned

- **API:** typed health/discovery routes, environment settings, lifecycle/composition seam, correlation metadata and safe errors.
- **Persistence:** pinned PostgreSQL + pgvector infrastructure, explicit checksummed Alembic migrations, forced workspace RLS, bounded pool, transactional publication, explicit eight-source seed, native lexical and exact synthetic-vector adapter operations. These are not public search routes.
- **Existing independent validator:** real Haystack construction/connectivity checks, without execution; see [validator documentation](../validator/README.md).
- **Existing UI:** fixture-only document/run displays and Preview; see [Workbench documentation](../web/README.md).
- **Planned:** approved HTTP retrieval profile, frontend API integration, ingestion, qualified model embeddings, dense/hybrid retrieval and generation. They must pass their own readiness and capability gates before advertisement.

The initial database migration is explicit; no Haystack public API changes are introduced. Application rollback is stopping the optional API while preserving its database volume. Destructive schema rollback is restricted to explicitly confirmed disposable databases; the constructor validator and standalone UI remain independent.

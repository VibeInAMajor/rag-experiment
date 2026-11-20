# Workbench API bootstrap

An optional, independent FastAPI process for liveness, readiness and capability discovery. This bootstrap does not execute pipelines or search documents. The [canonical RAG runtime contract](../../../docs-website/docs/architecture/rag-runtime-contract.md) defines the later execution boundary.

## Start

Run from the repository root with Hatch:

```powershell
hatch --version
hatch run workbench-api:serve
```

The detached `workbench-api` Hatch environment gets its pinned dependencies from the root [pyproject.toml](../../../pyproject.toml), the single dependency owner for this application. It does not install or import Haystack, optional model/vector SDKs, or the broad library test environment. No database, model service or credentials are needed. The development listener is `http://127.0.0.1:8011`. Stop it with Ctrl+C.

This is separate from the constructor validator at `127.0.0.1:8010`. The existing frontend does not call this API bootstrap. Starting or stopping it has no effect on offline editing, JSON import/export or fixture Preview.

## Routes and readiness

| Route                      | Default result                                           | Meaning                                                         |
| -------------------------- | -------------------------------------------------------- | --------------------------------------------------------------- |
| `GET /api/v1/health/live`  | HTTP 200                                                 | The API process is running                                      |
| `GET /api/v1/health/ready` | HTTP 503, `NOT_READY`                                    | No execution profile is implemented and ready                   |
| `GET /api/v1/capabilities` | HTTP 200, `profiles: []`, document/search features false | Discovery is working; no executable capabilities are advertised |

A running process is not a ready retrieval system. The default 503 readiness response is intentional: there is no database access, authorized corpus, BM25 execution, embedding, ingestion or persistence in this bootstrap. `bm25-v1` remains the first **planned** live search profile, not an enabled capability.

Capabilities uses `contract_revision: "rag-api-v1.0"`, `deployment_mode: "single_workspace_dev"`, a lifecycle `service_state`, `profiles: []` and `features: {"documents": false, "search": false}` in the default running bootstrap. `backend_revision` identifies this deployed application configuration; it is separate from the constructor validator's capability revision. All responses carry generated `request_id` and `trace_id` correlation values and the `X-Request-ID` header. Readiness failure uses the same metadata and a nested `error` containing `code`, a safe `message`, `retryable` and `http_status`.

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

There is no feature-enable environment switch or sample credential in this bootstrap. Setting a revision or CORS origin does not make search ready. A future executable capability must come from a qualified application service at the composition boundary, not a configuration flag that bypasses its readiness checks.

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

The targeted tests cover health/readiness, discovery schemas, configuration failures, origin handling and error envelopes. These commands do not validate future database or inference adapters. Record their actual output in the implementation task; this README does not substitute inspection for executed tests.

## Implemented versus planned

- **Bootstrap:** typed health/discovery routes, environment settings, lifecycle/composition seam, correlation metadata and safe errors.
- **Existing independent validator:** real Haystack construction/connectivity checks, without execution; see [validator documentation](../validator/README.md).
- **Existing UI:** fixture-only document/run displays and Preview; see [Workbench documentation](../web/README.md).
- **Planned:** PostgreSQL registry/corpus loading, the qualified BM25 profile, frontend API integration, ingestion, dense/hybrid retrieval, TEI and generation. They must pass their own readiness and capability gates before being advertised.

No data migration or Haystack public API change is introduced. Rollback is stopping the optional API process; the constructor validator and standalone UI remain independent.

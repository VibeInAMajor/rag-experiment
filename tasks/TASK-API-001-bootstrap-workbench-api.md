# TASK-API-001-bootstrap-workbench-api

**Created:** 2026-11-20  
**Updated:** 2026-11-20  
**Status:** COMPLETE  
**Priority:** P0 · integration  
**Dependencies:** TASK-ARCH-001  
**Repository snapshot reviewed:** `5e7086364f62d4f15b7370e55767a8f84ed4dc14`

## A. Title

Bootstrap a thin Workbench API with readiness and capability discovery

## B. Context / Problem

The Workbench already has a validation-only API client and a separate loopback constructor validator. It has no RAG execution API or executable profile discovery. A distinct bootstrap boundary with truthful liveness/readiness is needed before live search can be integrated. The [canonical runtime/API contract](../docs-website/docs/architecture/rag-runtime-contract.md) owns the v1 schema; the constructor validator's revision and capabilities must not be repurposed as execution readiness.

## C. Current Repository State

Implementation starting point, rechecked in the working tree on 2026-11-20:
- `apps/workbench/validator/server.py` already exposes `/health`, `/api/pipelines/capabilities` and `/api/pipelines/validate` using a standard-library HTTP server on loopback port 8010. Its capabilities describe reviewed constructor mappings, not live execution profiles.
- `apps/workbench/web/src/domain/validation.ts` already calls the validation API. `App.tsx` still owns demonstration documents, runs and settings in React memory; preview never performs retrieval.
- `apps/workbench/web/README.md` documents optional validator startup and planned execution integration. The earlier blanket claims of “no backend” and “no API clients” are obsolete.
- At task start, `apps/workbench/api/` and `/api/v1/health/live`, `/api/v1/health/ready`, `/api/v1/capabilities` implementations did not exist. The architecture contract already specified their response/error/revision semantics.
- `pyproject.toml` owns Hatch tooling; isolated `workbench-api` dependencies and commands will be added there without adding web-server dependencies to the Haystack library distribution. No database, model SDK, Compose deployment or search implementation belongs in this task.

## D. Goal

Start a locally runnable, independent API process exposing truthful liveness, readiness, and a versioned capability payload; provide reliable failure semantics for the future UI client.

## E. Scope

1. Create a small backend app package under `apps/workbench/api/` without moving or rewriting `haystack/`.
2. Implement liveness, readiness and `/api/v1/capabilities` with a response describing only operations actually ready.
3. Configure loopback development CORS origin, environment-based settings, process lifecycle, dependency injection points and structured request IDs.
4. Document a reproducible startup command and typed API response/error schemas.
5. Add unit tests for ready/unready and malformed configuration.

## F. Non-Goals

No actual retrieval, file upload, persistence, inference, multi-workspace auth, production deployment, scheduler, or arbitrary pipeline compiler in this task. Do not return `ready=true` for features not implemented yet.

## G. Architecture / Boundaries

Affected: HTTP boundary/application composition, Port/contract, Security and Observability, Infrastructure/dev runbook and Documentation. Domain and `haystack/` remain unchanged. API imports backend services through an explicit composition seam; business policy remains independent of FastAPI request objects where that boundary is useful.

## H. Contracts / Interfaces / Data Model

Follow `rag-api-v1.0` from the canonical contract. All API responses include `contract_revision`, generated `request_id`, `trace_id`, and an `X-Request-ID` header. `GET /api/v1/health/live` returns 200 while active. `GET /api/v1/health/ready` returns 200 only for an approved executable profile, otherwise 503 with `NOT_READY`; the initial bootstrap has no profiles and must stay unready. `GET /api/v1/capabilities` returns typed profile definitions, backend revision, local-development deployment mode and additive service/feature availability fields. Default `profiles: []` must not advertise BM25. Errors use the canonical nested envelope with `code`, user-safe `message`, `retryable` and matching `http_status`; no raw exceptions or caller IDs are trusted. There is no ready-enabling configuration flag. Readiness has an explicit test/composition seam for future adapters, not an arbitrary graph executor.

## I. Repository Files / Components Impacted

Create `apps/workbench/api/` (application module, configuration, contracts, tests and README), with equivalent explicit application dependency configuration in a detached `workbench-api` Hatch environment in root `pyproject.toml`. Update `apps/workbench/web/README.md` with opt-in startup, the canonical contract's implementation-status statements, and the project routing documents that describe API availability. Include a release note. Do not change `haystack/`, `App.tsx`, `graph.ts`, fixture documents, the validator's contract or unrelated docs.

## J. Implementation Requirements

MUST use typed FastAPI/Pydantic models and explicit error handling. MUST distinguish liveness from readiness. MUST not import optional model/vector database SDKs into API bootstrap. MUST bind the development listener to loopback by default. MUST make CORS an allowlist, never blanket wildcard with credentials. MUST preserve neutral adapter seams without speculative factories. MUST use no secrets in source, logs or documentation.

## K. Security / Governance / Observability

No authentication shortcut can be presented as tenant isolation. Initial API is local/dev only and must say so in documentation and capability payload. Set stable request/trace IDs and redact exception internals in client-facing errors. Log state changes without tokens/document bodies, retain only operational metadata under an explicit default policy.

## L. Testing / Evaluation / Runtime Verification

Python: use the detached Hatch environment and actual app paths: `hatch run workbench-api:test`, `hatch run workbench-api:check`, `hatch run workbench-api:types`. These isolate FastAPI dependencies from the library/test environments. Add FastAPI TestClient checks for ready/unready composition, invalid configuration, CORS denial, lifecycle, stable error envelopes, generated correlation IDs and published OpenAPI schema compatibility. Run the documented server command and capture real HTTP liveness, default unready and empty-capability evidence. Record actual commands/results; no retrieval/database/model result may be inferred from bootstrap tests.

## M. Acceptance Criteria

- [x] A documented local command launches the API and a request to `/api/v1/health/live` returns 200.
- [x] `/api/v1/health/ready` is 503 if mandatory dependencies are unready; never false-positive 200.
- [x] `/api/v1/capabilities` validates against a published schema and does not advertise BM25 until enabled.
- [x] No secrets/model IDs or raw stack traces appear in HTTP errors/logs.
- [x] New API unit/contract tests and lint pass with attached evidence.

## N. Documentation / Migration / Compatibility / Rollback

New isolated application; no data migration or API compatibility break. API v1 contract starts here and must be versioned. Rollback: stop/uninstall the app; standalone UI remains fully functional in preview mode. No change to existing Haystack package public APIs.

## O. Mandatory Completion Checklist

- [x] Source/config tests and startup docs written.
- [x] Live health and unready-path evidence captured.
- [x] Security/CORS and response schema checks pass.
- [x] No out-of-scope framework modifications.
- [x] API version/docs match implementation.
- [x] Only mark COMPLETE with recorded test commands, outputs and limitations.

### Completion evidence — 2026-11-20

Implemented files:
- `apps/workbench/api/application.py`: typed discovery-only FastAPI composition and lifespan. Default readiness stays 503; the neutral async readiness seam is bounded and rechecks lifecycle after awaiting a snapshot.
- `apps/workbench/api/config.py`: explicit loopback settings and exact local CORS origins; there is no feature/readiness enable flag.
- `apps/workbench/api/contracts.py`, `services.py`, `boundary.py`, `__init__.py`, `__main__.py`: provider-neutral capability schemas, app exports, process startup, server-generated IDs, Host/Origin policy, safe errors and operational-only logging.
- [Published OpenAPI artifact](../apps/workbench/api/openapi.json), generated from `create_app(settings=ApiSettings()).openapi()`; a focused contract test prevents drift. The bootstrap has three routes and does not expose an additional HTTP schema endpoint.
- `apps/workbench/api/tests/test_configuration.py`, `test_http_contract.py`: configuration, lifecycle, readiness/failure/timeout, late completion after shutdown, duplicate/security headers, request body rejection, error sanitization, schema compatibility and correlation tests.
- Root `pyproject.toml`: detached `workbench-api` environment with explicit pinned runtime dependencies and `serve`, `test`, `check`, `types` scripts. No web-server dependency was added to the Haystack library distribution.
- [API README](../apps/workbench/api/README.md), [Workbench README](../apps/workbench/web/README.md), canonical contract, dated plan current-status table, project map and engineering guide: bootstrap is distinguished from execution and the separate validator. Historical architecture remains archived.
- `releasenotes/notes/workbench-api-bootstrap-6c3c7dc4e9e306b7.yaml`: optional startup and truthful empty readiness/capabilities.

Existing logic and boundaries reused: the canonical `rag-api-v1.0` metadata/error/capability semantics, repository Hatch/Ruff/mypy conventions and existing optional-service runbook structure. The validator's constructor mappings and frontend graph/domain structures remain their existing owners; they are not copied into a second execution interpreter. The API imports neither Haystack nor provider/model/vector SDKs.

Executed checks:

| Command / verification | Actual result |
| --- | --- |
| `hatch --version` | `Hatch, version 1.18.2` |
| `hatch env create workbench-api` | Isolated environment created; runtime versions resolved to FastAPI 0.165.0, Starlette 1.10.0, Uvicorn 0.54.0 and Pydantic 2.14.4 |
| `hatch run workbench-api:check` | All checks passed; 9 files already formatted |
| `hatch run workbench-api:types` | Success: no issues found in 9 source files |
| `hatch run workbench-api:test -q -o log_cli=false` | 55 tests passed; one upstream Starlette warning about its httpx TestClient transport |
| `hatch run workbench-api:serve` | Real listener started on `http://127.0.0.1:8011` |
| Real HTTP liveness/readiness/capabilities | 200 / 503 `NOT_READY` / 200 with `profiles: []` and both feature flags false; payloads validated against the published schema |
| Real HTTP denied Origin / unknown route / unsupported method | 403 `FORBIDDEN` / 404 `ENDPOINT_NOT_FOUND` / 405 `METHOD_NOT_ALLOWED`; generated IDs match response headers |
| Startup with `WORKBENCH_API_PORT=invalid-port` | Exit 1 with only `Invalid Workbench API configuration.`; no value or traceback exposed |
| Documentation / release note | MDX/GFM compilation for 8 Markdown files, 47 local links and six typed/JSON fenced examples passed; both READMEs passed Prettier; Git whitespace check and release-note YAML parsing passed |

The temporary HTTP probe ran through `hatch run workbench-api:python` and recorded six actual responses in [the HTTP evidence](evidence/workbench-api-bootstrap-2026-11-20.json). Its helper script is outside the repository in the operating-system temporary directory; no verification dependency was added to application-core contracts.

Independent review covered HTTP/source correctness, canonical compatibility, documentation links and the absence of fabricated capabilities. Issues found and corrected before completion: readiness dependency failures initially returned 500 instead of truthful 503; profile probing now has a cooperative timeout and post-shutdown guard; published schema consistency is tested; GET bodies are rejected before parsing; test arguments keep the isolated app test scope; OpenAPI documentation correctly links the artifact rather than a nonexistent HTTP route.

Not run: full upstream Haystack tests, browser/UI runtime scenarios or the full Docusaurus build. UI components and Haystack core were not changed; site dependencies are not installed. No database, Docker, embedding, inference, retrieval or production tenancy test was performed. Those are explicitly outside this bootstrap.

Remaining limits: loopback-only development with no authentication/tenant isolation; no executable profiles or data routes; readiness seam assumes cooperative async probes. TestClient emits a non-failing dependency deprecation warning. Structured application logs go to stdout without payloads or persistence; deployment owners must set retention/access/deletion policy before capturing them. No migration or graph format change is required; stopping the API leaves the standalone preview and constructor validator independent.

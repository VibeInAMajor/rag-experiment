# TASK-RAG-SCALE-001 — Enterprise multi-workspace identity, permissions and data isolation

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint, no runtime claim  
**Priority:** P0 before non-local access  
**Dependencies:** completed DB-001/API-001/RAG-002; INDEX-001, PROFILE-001 and CONTENT-001  
**Source reviewed:** cb7fe844084133b7e09a623e0e39767af1e0d9f1  
**Target:** tasks/TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md

## A. Title

Enterprise multi-workspace identity, permissions and data isolation

## B. Context / Problem

Current single-workspace development access is not a multi-tenant security architecture. Server chooses development workspace and SQL enforces RLS; enterprise must authenticate principals and check membership/roles before allowing source, asset, embeddings, index profiles and model calls. One tenant must not read or influence another tenant's search results or index resource quotas.

## C. Current Repository State

[parsing.py](../apps/workbench/api/parsing.py) and [parser_registry.py](../apps/workbench/api/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/api/chunking.py), [ingestion.py](../apps/workbench/api/ingestion.py) and [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [persistence.py](../apps/workbench/api/persistence.py) and [postgres.py](../apps/workbench/api/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [contracts.py](../apps/workbench/api/contracts.py) own API/capabilities. [pdf_worker.py](../apps/workbench/api/pdf_worker.py), [pdf_models.py](../apps/workbench/api/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/api/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
[resolve_development_workspace](../apps/workbench/api/persistence.py) authorizes one explicit workspace. [postgres.py](../apps/workbench/api/postgres.py) sets transaction-local workbench.workspace_id, RLS is FORCE enabled by schema 0001/0002, [config.py](../apps/workbench/api/config.py) and [boundary.py](../apps/workbench/api/boundary.py) are loopback-focused. [local_sources.py](../apps/workbench/api/local_sources.py) reveals local files in Explorer and must not be exposed to remote users.

**Verification limit:** this is a source-backed task, not proof that the proposed feature exists. Re-inspect current code at implementation start.

## D. Goal

Authenticated users and service workers can access multiple authorized workspaces through server membership checks with explicit roles, while cross-tenant queries, downloads and vector/ANN candidates return zero unauthorized data. Local dev mode remains safe and backwards compatible.

## E. Scope

AuthContext and identity adapter, workspace/membership/permission registry, JWT/OIDC verification, RLS role and compound keys, asset/embedding/index ownership checks, separate admin and tenant quotas, browser workspace discovery/state invalidation and audit.

## F. Non-Goals

No anonymous remote API, no caller-authorized roles, no global vector cache crossing tenant boundaries, no BypassRLS app role, no enabling arbitrary local Windows Explorer reveal for remote users.

## G. Architecture / Boundaries

IdentityPort -> trusted identity adapter -> server WorkspaceAuthorizationPolicy -> WorkspaceContext -> existing PersistencePort and AssetStorePort; RLS defense in depth. Browser receives only authorized IDs; workers get scoped service identity, never blanket admin privileges.

## H. Contracts / Interfaces / Data Model

Principal{issuer,subject,expires_at,principal_id}; WorkspaceMembership{workspace_id,role viewer/editor/operator/admin,permissions}; ResourceAccess{workspace,source/version/asset/index_generation,action,allow/deny}; QuotaProfile{sources,bytes,tokens,concurrency,worker_jobs}. All auth decisions server-only; safe missing/forbidden resource error policy prevents enumeration.

External schema changes MUST be reviewed in Pydantic/OpenAPI/client and versioned explicitly.

## I. Repository Files / Components Impacted

MODIFY [persistence.py](../apps/workbench/api/persistence.py), [application.py](../apps/workbench/api/application.py), [boundary.py](../apps/workbench/api/boundary.py), [config.py](../apps/workbench/api/config.py), [postgres.py](../apps/workbench/api/postgres.py) and web workspace selector; CREATE identity.py, workspace_policy.py, additive migration and tests/test_workspace_authorization.py. No historical migrations or unauthorized local source revelation.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

## J. Implementation Requirements — ordered blueprint

1. Inventory API, original evidence, query, model and worker entrypoints; freeze least-privilege matrix and security baselines.
2. Define provider-neutral AuthContext and validate a reviewed token provider (issuer/audience/signature, expiry/rotation); a workspace claim is insufficient without membership.
3. Add workspace and membership tables and compound FK/RLS enforcement for existing and future content/asset/vector/job/index records; test pooled connection no scope leakage.
4. Require server-selected workspace for every read/write; add scoped UI listing and cancellation/clear history on switching.
5. Enforce tenant quotas and resource usage, including HNSW filtered recall, embedding reuse and worker process queues.
6. Harden remote deployment HTTPS, CORS, secret retrieval, audit; block local Explorer/open-file feature outside local mode. Run 2-workspace/3-role penetration-like tests before enabling remote listener.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

JWT wrong audience/issuer/tampered/expired, forged workspace, same resource IDs in two tenants, connection pool RLS, tenant data over vector/ANN/evidence/embedding jobs, source update, forced cross-tenant cache read, UI switching, admin role escalation and worker quota. Measure zero leaked rows and original bytes.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

## M. Acceptance Criteria

- [ ] Remote mode never uses development-only anonymous resolver
- [ ] All API/worker permissions checked against trusted identity
- [ ] FORCE RLS and compound FK preserve workspace scope
- [ ] 0 tenant data leakage across source/vector/asset/job negative matrix
- [ ] Browser workspace switch discards stale results and downloads
- [ ] Multiworkspace quotas and audit enabled
- [ ] Local Explorer reveal unavailable remotely
- [ ] Backwards compatible local mode and real security evidence

## N. Documentation / Migration / Compatibility / Rollback

Additive role schema with staged remote mode. On auth incident disable remote listener/affected capability, never RLS. Preserve source versions and assets. Rotate credentials and document token revocation, audit retention and non-destructive rollback.

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

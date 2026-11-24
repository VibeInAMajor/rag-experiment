# TASK-RAG-SCALE-001 — Enterprise multi-workspace identity, permissions and data isolation

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
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

[parsing.py](../apps/workbench/parsing/parsing.py) and [parser_registry.py](../apps/workbench/parsing/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/chunking/chunking.py), [ingestion.py](../apps/workbench/ingestion/ingestion.py) and [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [models.py](../apps/workbench/persistence/models.py) and [postgres.py](../apps/workbench/postgres/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [schemas.py](../apps/workbench/contracts/schemas.py) own API/capabilities. [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py), [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
[resolve_development_workspace](../apps/workbench/persistence/models.py) authorizes one explicit workspace. [postgres.py](../apps/workbench/postgres/postgres.py) sets transaction-local workbench.workspace_id, RLS is FORCE enabled by schema 0001/0002, [config.py](../apps/workbench/configuration/config.py) and [boundary.py](../apps/workbench/api/boundary.py) are loopback-focused. [local_sources.py](../apps/workbench/sources/local_sources.py) reveals local files in Explorer and must not be exposed to remote users.

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

MODIFY [models.py](../apps/workbench/persistence/models.py), [application.py](../apps/workbench/api/application.py), [boundary.py](../apps/workbench/api/boundary.py), [config.py](../apps/workbench/configuration/config.py), [postgres.py](../apps/workbench/postgres/postgres.py) and web workspace selector; CREATE apps/workbench/security/identity.py, apps/workbench/security/workspace_policy.py, an additive migration under apps/workbench/postgres/migrations/ and apps/workbench/api/tests/test_workspace_authorization.py. No historical migrations or unauthorized local source revelation.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) | resolve_development_workspace server boundary and WorkspaceContext |
| [`apps/workbench/postgres/postgres.py`](../apps/workbench/postgres/postgres.py) | SET LOCAL workspace scope in transactions, no BYPASSRLS |
| [`apps/workbench/postgres/migrations/0001_initial.up.sql`](../apps/workbench/postgres/migrations/0001_initial.up.sql) | FORCE RLS workspaces/source_versions/chunks |
| [`apps/workbench/postgres/migrations/0002_ingestion_jobs.up.sql`](../apps/workbench/postgres/migrations/0002_ingestion_jobs.up.sql) | FORCE RLS and job identity |
| [`apps/workbench/api/boundary.py`](../apps/workbench/api/boundary.py) | host/CORS security and API errors |
| [`apps/workbench/configuration/config.py`](../apps/workbench/configuration/config.py) | local-mode host and secrets |
| [`apps/workbench/sources/local_sources.py`](../apps/workbench/sources/local_sources.py) | local Windows Explorer reveal, must remain disabled for remote users |
| [`apps/workbench/postgres/tests/test_postgres_persistence.py`](../apps/workbench/postgres/tests/test_postgres_persistence.py) | RLS/role tests |
| [`apps/workbench/web/src/hooks/useBackendDiscovery.ts`](../apps/workbench/web/src/hooks/useBackendDiscovery.ts) | current authorized workspace capability handling |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/independent-multi-workspace-rag-service.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/independent-multi-workspace-rag-service.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## J. Implementation Requirements — ordered blueprint

1. Inventory API, original evidence, query, model and worker entrypoints; freeze least-privilege matrix and security baselines.
2. Define provider-neutral AuthContext and validate a reviewed token provider (issuer/audience/signature, expiry/rotation); a workspace claim is insufficient without membership.
3. Add workspace and membership tables and compound FK/RLS enforcement for existing and future content/asset/vector/job/index records; test pooled connection no scope leakage.
4. Require server-selected workspace for every read/write; add scoped UI listing and cancellation/clear history on switching.
5. Enforce tenant quotas and resource usage, including HNSW filtered recall, embedding reuse and worker process queues.
6. Harden remote deployment HTTPS, CORS, secret retrieval, audit; block local Explorer/open-file feature outside local mode. Run 2-workspace/3-role penetration-like tests before enabling remote listener.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Map every API route including source browse/reveal, ingestion, live SQL, Dense/ANN/asset evidence and admin operations; explicitly distinguish current single-local development from future remote auth.

**J8.** Implement verified identity adapter (OIDC/JWT/mTLS after operator choice) and server membership/permissions check before accepting workspace_id from path; limit scope list to authorized only.

**J9.** Add additive membership/quota schema and compound scope for all existing source/version/chunk/job and future assets/generations, keep app DB role non-owner non-superuser.

**J10.** Test PostgreSQL pooled transaction reuse with A then B: no RLS residual scope, no BYPASSRLS. Security tests should prevent both data return and existence probing through 404.

**J11.** Separate local source file reveal from remote evidence serving; deny remote Explorer access, untrusted path traversal and symlink/UNC.

**J12.** Enforce model/GPU/TPM per-tenant quota and fair share with SCALE-002 and TPM-001 global model quota; no tenant may override 0.95 global guard.

**J13.** Update UI selector and session state: switch workspace cancels in-flight query, clears private result/asset caches, revalidates profile and generation before next Live call.

**Cross-cutting constraints:** Do not import model/converter/cloud or queue SDK into core, and do not change existing PostgreSQL authoritative source.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

JWT wrong audience/issuer/tampered/expired, forged workspace, same resource IDs in two tenants, connection pool RLS, tenant data over vector/ANN/evidence/embedding jobs, source update, forced cross-tenant cache read, UI switching, admin role escalation and worker quota. Measure zero leaked rows and original bytes.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

### L.1. Task-specific reproducible test vectors

- [ ] Two tenants 3+ roles, forged workspace/path/source ID, wrong JWT issuer/audience/expiry, SQL RLS owner/role tests and read-after-switch.
- [ ] Asset/evidence/vector/ANN/cached embedding scope, administrative role escalation, worker scope and local file reveal remote denial.
- [ ] Quota fairness and no unwanted model calls for forbidden workspace.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

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

# TASK-RAG-ANN-003 — Implement tenant-selective retrieval policy and bounded exact fallback

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no ANN runtime tests executed  
**Priority:** P1  
**Dependencies:** [ANN-001](TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md) cohort evidence and [ANN-002](TASK-RAG-ANN-002-generation-fenced-hnsw-retrieval-and-exact-reranking.md) internal execution; [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) owns measured corpus quotas (required before large-corpus application qualification); [SCALE-001](TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md) for production tenant authority; coordinate [SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md) and [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md).  
**Repository snapshot inspected:** ce3b331e5869d563b9bfbabc034b2158148990b3  
**Target:** tasks/TASK-RAG-ANN-003-tenant-selective-routing-and-bounded-fallback.md  
**Roadmap:** [RAG index, retrieval and enterprise plan](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md)

## A. Title

Implement tenant-selective retrieval policy and bounded exact fallback

## B. Context / Problem

Approximate post-filtering can underfill rare workspaces. An unconditional exact retry during overload can create a fallback storm. Exact, ANN and lexical profiles already have bounded HTTP contracts; they must not be silently substituted.

## C. Current Repository State

[retrieval/profile_registry.py](../apps/workbench/retrieval/profile_registry.py) bounds workspace corpus to 10k chunks/50 MiB, max_concurrent to 2, timeout to 10s, top_k to 50 and candidate_k to 1000. [postgres/postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) also enforces 10k/50 MiB publication caps. [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) explicitly owns measured workspace limits, retrieval limit changes and bounded staged publication; current caps remain valid until that task proves changes. [api/application.py](../apps/workbench/api/application.py) has global/per-profile admission, HTTP deadline, 429 SEARCH_BUSY and 504 SEARCH_TIMEOUT; [api/projection.py](../apps/workbench/api/projection.py) checks profile identity/hash. [retrieval/dense.py](../apps/workbench/retrieval/dense.py) shares the governed QueryEmbedder. [SCALE-001](TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md) is proposed; local development workspace resolution is not enterprise authorization.

## D. Goal

Select only qualified tenant/corpus/filter strategies; make one bounded exact fallback possible only where explicitly permitted and cost-qualified, otherwise produce a truthful typed retryable failure. Keep tail latency/resource usage bounded in failure storms.

## E. Scope

Deterministic strategy policy, budget propagation, shared search admission/backpressure, bounded fallback and circuit breaker, requested/executed strategy provenance, API compatibility and qualification of routing at measured limits.

## F. Non-Goals

No duplicate ingestion, quota or embedding governor; no blanket limit raise; no per-query oracle for recall; no automatic lexical/Preview/model fallback; no arbitrary client-controlled HNSW parameters or routing decisions. No multi-tenant authentication implementation here.

## G. Architecture / Boundaries

Application owns strategy/fallback policy, trusted profile identity and admission; persistence adapter owns statement/scan budgets and execution. Reuse existing search route admission and governor rather than introducing another uncoordinated limiter. INGEST-004 owns the unified publication/serving capacity envelope; SCALE-001/002 own identity and cross-worker fairness.

## H. Contracts / Interfaces / Data Model

Extend existing approved immutable profile/policy with qualified cohort range, exact eligibility and deadline/capacity budget. Preserve four-field SearchRequest and requested profile identity. If fallback within one approved policy is supported, return additive executed_strategy and bounded reason (and executed profile revision if a separate profile is explicitly permitted and validated); otherwise require explicit selection of the separately approved exact profile. Keep expected_profile/policy hash checks; fail closed on mismatch. Define typed capacity/unavailable/timeout outcomes compatible with 429/503/504 and existing 409 policy/generation conflicts.

## I. Repository Files / Components Impacted

Reuse [retrieval/dense.py](../apps/workbench/retrieval/dense.py), [retrieval/profiles.py](../apps/workbench/retrieval/profiles.py), [retrieval/services.py](../apps/workbench/retrieval/services.py), [retrieval/profile_registry.py](../apps/workbench/retrieval/profile_registry.py), [api/application.py](../apps/workbench/api/application.py), [api/projection.py](../apps/workbench/api/projection.py), [contracts/schemas.py](../apps/workbench/contracts/schemas.py) and existing Postgres timeout/pool controls; update published OpenAPI and web decoding only if additive execution metadata needs it. Coordinate retrieval limits with INGEST-004; do not edit ingestion pipeline or duplicate its quota ownership.

## J. Implementation Requirements

1. Select strategy by immutable qualification cohort: authorized workspace, compatible embedding fingerprint, eligible active chunk count, measured selectivity/fan-out and physical index coverage/health. Use bounded existing manifest/statistics, not an unbounded COUNT/digest per request. Unknown or stale estimates must not justify an unsafe fallback. Small workspaces may use exact directly if approved; no universal HNSW default or unmeasured crossover threshold.
2. Define one end-to-end deadline and remaining stage budget including embedding/admission, ANN, rerank and fallback. Use existing HTTP cancellation and transaction-local statement timeout; no fresh timeout on fallback. Retry at most once, reuse query embedding only if same compatible profile/generation, and reacquire/verify scope and fences if new transaction required. Never fallback on authorization, incompatible model, stale profile/generation, caller cancellation, or invariant failures.
3. Before exact execution require explicit profile permission, qualified exact corpus count/bytes and measured worst-case cost bound, remaining time and globally/per-tenant available search/fallback admission. Reuse existing active search accounting; bound extra SQL work, queue and attempts; account for concurrent requests/replicas via existing ownership or block scaled rollout until qualified. No bypass of INGEST-004 quota or exact's separately measured ceiling.
4. Detect index invalidity, candidate exhaustion/underfill and timeout using typed runtime signals. Do not infer recall from top-k count. Add bounded breaker with explicit cooldown, probe/recovery criteria and operator visibility; failing ANN cohort does not disable healthy lexical search. ANN-004 owns shadow oracle and qualification decisions.
5. Preserve requested policy provenance; expose actual strategy in existing result/trace contract, no misleading score, no silent cross-profile switch. If no safe fallback is available return explicit retryable 429/503/504 as appropriate; maintain 409 for stale policy. Do not serve partial ANN as complete or substitute fixtures.
6. Integrate the measured INGEST-004 workspace quota contract and existing INGEST-001/002/003/SCALE-002 backpressure interfaces when available. Test publication and search using the same limit source; test exact and ANN limits independently. Large-corpus SQL benchmark does not authorize raising application limits. Record behavior at 10k and >=100k active chunks through supported ingestion when the prerequisite passes; otherwise mark that scope blocked.

Follow [AGENTS.md](../AGENTS.md) and [engineering conventions](../docs-website/ENGINEERING.md). Reuse existing owners; names MUST describe domain behavior, never task IDs. Provider-neutral application contracts MUST NOT expose PostgreSQL SQL, pgvector operators or a specific embedding SDK. Do not modify applied migrations, overwrite canonical full vectors, weaken RLS, or add a second authoritative store. Reinspect source, tests and dependencies before implementation; amend this A–O contract before material scope changes.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, parameterized SQL, the least-privileged application role, FORCE RLS and transaction-local scope for every candidate, mapping and metadata lookup. Treat query, document and graph text as untrusted data, not SQL or instructions. No credentials, DSNs, raw vectors, private queries, document content or sensitive paths in logs/evidence. Persist only authorized safe identifiers, policy/revision hashes, counts, timings and reason codes; restrict detailed evidence access and retention under [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md). No new external egress or provider-specific core dependency. Log requested/executed strategy, eligibility decision, reason, remaining deadline and admission outcome without sensitive content; ensure one tenant cannot consume all fallback capacity. No retry on security errors.

## L. Testing / Evaluation / Runtime Verification

Table-driven routing and budget tests; exact threshold/unknown estimate, tiny tenant, index invalidity, underfill, cancellation, stale generation, timeout and 429; concurrency storm with index loss, simultaneous ingestion and pool contention; prove bounded attempts and no over-admission; verify existing HTTP/Live contracts. Large-corpus E2E depends on INGEST-004. Run scoped Hatch workbench-api:check/test/types and actual disposable PostgreSQL integration tests; use repository Hatch conventions (Ruff and pytest), not system Python/pip. If web contracts change, run npm typecheck, format:check, test, build and real Live/Preview smoke. Record actual commands, exit codes, test counts/skips, runtime versions and evidence paths; no mock counts as runtime proof.

## M. Acceptance Criteria

- [ ] Each route requires an approved compatible cohort; unsupported/unknown cases cannot silently succeed.
- [ ] At most one bounded exact retry, zero unbounded retries, zero silent cross-profile/fixture fallback, no fallback after canceled/security/stale fence failure.
- [ ] Deadline and admission limits verified under storm and concurrent ingestion; exact availability and lexical independence preserved within qualified bounds.
- [ ] Requested and executed provenance are truthful; API and browser regressions pass if changed.
- [ ] Publication and retrieval quotas reconcile through INGEST-004; any unqualified large-corpus cohort stays disabled and is explicitly reported.

## N. Documentation / Migration / Compatibility / Rollback

Additive policy revision and response metadata only; old requests remain valid. Rollback disables ANN routing and exact fallback policy without changing baseline profile or ingestion data. Document operator-configured budgets and retryable outcomes; production activation stays disabled.

## O. Mandatory Completion Checklist

- [ ] Reinspect repository and record source/contract changes before coding.
- [ ] Reuse existing owners; review naming, architecture and dependency direction.
- [ ] Execute applicable unit, contract, integration, failure, adversarial and regression checks.
- [ ] Link actual evidence, commands, environment, limitations and unresolved risks.
- [ ] Verify documentation, compatibility and non-destructive rollback.
- [ ] Record modified paths and implementation commit; mark COMPLETE only when the task-local gates pass.

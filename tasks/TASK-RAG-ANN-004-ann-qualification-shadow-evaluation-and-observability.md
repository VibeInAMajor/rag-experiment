# TASK-RAG-ANN-004 — Qualify ANN profiles with bounded shadow evaluation and operational evidence

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no ANN runtime tests executed  
**Priority:** P1  
**Dependencies:** [ANN-001](TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md) GO, [ANN-002](TASK-RAG-ANN-002-generation-fenced-hnsw-retrieval-and-exact-reranking.md) execution, [ANN-003](TASK-RAG-ANN-003-tenant-selective-routing-and-bounded-fallback.md) routing; coordinate [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) (shared telemetry/evaluation owner), [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) for large-corpus serving and [DELTA-001](TASK-RAG-DELTA-001-incremental-reindexing-and-embedding-vector-reuse.md) for reuse regression coverage.  
**Repository snapshot inspected:** ce3b331e5869d563b9bfbabc034b2158148990b3  
**Target:** tasks/TASK-RAG-ANN-004-ann-qualification-shadow-evaluation-and-observability.md  
**Roadmap:** [RAG index, retrieval and enterprise plan](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md)

## A. Title

Qualify ANN profiles with bounded shadow evaluation and operational evidence

## B. Context / Problem

Actual index existence or a full top-k does not prove recall. Production readiness must bind held-out exact-oracle quality and resource evidence to a specific physical index, tenant cohort and profile/generation; a sampled shadow mechanism must not overload the database.

## C. Current Repository State

[postgres/migrations/0004_profile_registry.up.sql](../apps/workbench/postgres/migrations/0004_profile_registry.up.sql) defines immutable revisions, scoped rollouts, qualified_generation_id and rollout audit events. [transition_profile / promote_profile / read_profile_rollouts](../apps/workbench/postgres/postgres_profiles.py) owns qualification lifecycle; [commit_source_generation / reconcile_index](../apps/workbench/postgres/postgres_indexes.py) owns persisted manifests. [api/application.py](../apps/workbench/api/application.py) already logs safe search timing/provenance; [DENSE-001 runtime evidence](evidence/dense-2026-11-24/report.md) records real exact SQL/model/browser evidence, with synthetic labels and no-answer limitations. [retrieval/dense.py](../apps/workbench/retrieval/dense.py) requires current complete coverage and active rollout. No ANN quality evidence or online shadow evaluator exists in inspected snapshot.

## D. Goal

Define and enforce a reproducible generation-bound ANN qualification decision; measure drift with budgeted independent shadow oracle and expose safe diagnostic evidence. A failed or missing gate cannot advertise ANN readiness.

## E. Scope

Qualification evidence contract, per-cohort release gates, shadow sampling and invalidation, existing profile lifecycle integration and safe operator/user-facing execution diagnostics. No production promotion or general observability platform.

## F. Non-Goals

No all-requests exact shadow, fabricated online recall, new telemetry stack, new profile registry, new DDL lifecycle, answer-generation quality claims or unqualified activation.

## G. Architecture / Boundaries

Application/evaluation owns gate policy and sampled oracle decisions; existing persistence/profile rollout owner records approval and audit state. OPS-001 owns common tracing/dashboard/retention; reuse rather than build competing infrastructure. ANN-005 owns deployment and activation.

## H. Contracts / Interfaces / Data Model

Bind evidence to physical index identity/definition and build revision, embedding fingerprint/dimensions, retrieval profile revision/policy hash, workspace/cohort/eligible population range, corpus generation and fixture/query manifest, tested runtime/limits, timestamps and review outcome. Store in existing rollout/evidence contract or minimal additive evidence record, not duplicate profile state. Distinguish offline recall, sampled shadow recall, no-sample/unknown and operational proxies. Persist bounded reason codes and qualification expiry/drift triggers.

## I. Repository Files / Components Impacted

Extend [postgres/postgres_profiles.py](../apps/workbench/postgres/postgres_profiles.py), [retrieval/profile_registry.py](../apps/workbench/retrieval/profile_registry.py), [retrieval/profiles.py](../apps/workbench/retrieval/profiles.py), [retrieval/dense.py](../apps/workbench/retrieval/dense.py), [api/application.py](../apps/workbench/api/application.py), existing evaluation tests/scripts and OPS-001 shared observability as required. Update discovery/OpenAPI/web approved graph and execution displays only behind qualified capability; no change to Preview/validator authority. Add focused tests/evidence under existing owners. No second rollout or index-generation registry.

## J. Implementation Requirements

1. Reuse ANN-001 benchmark manifest and independent float32 oracle; repeat held-out cohort gates against ANN-002/003 actual execution, including candidate mapping and fallback. Report ANN-only and served/fallback metrics separately; fallback successes cannot inflate ANN recall. Preserve >=0.97 mean recall@10 per qualified cohort, zero unexpected underfill and unauthorized/stale/wrong-model hits, predeclared lower-tail gate, and >25% p95 retrieval gain for >=100k eligible cohort; report end-to-end quality/latency without inventing a gain.
2. Record p50/p95/p99, throughput/errors, fallback frequency, timeouts, candidate/vector/mapping counts, CPU/RAM/I/O/WAL, index size and concurrent ingestion impact with sample counts. Compare semantic relevance, primary evidence and MRR against labels separately; no-answer forced-neighbor behavior is not calibrated confidence. Agree on acceptable relevance and error/latency budgets before final holdout.
3. Use bounded opt-in shadow evaluation, initially disabled; choose sample rate, max concurrent exact probes, deadline and queue/drop policy from measured spare capacity. Reuse ANN-003 exact admission (including tenant fairness); shadow must never delay the user path, extend its deadline or expose cross-tenant results. Compare same authorized immutable snapshot and query vector; discard/mark inconclusive if generation/policy changes. Skip when load/health denies probe; log sampling coverage/denominator, not zero recall or success for skipped probes.
4. Invalidate or withhold qualification on model/profile/index/schema/generation drift, insufficient evidence, underfill/recall regression, invalid index or expired qualification. Define conservative requalification for changed generations with explicit measured coverage and reviewed reuse of evidence only when allowed by policy; never silently mark an untested generation qualified. Persist audited gate verdict via existing profile transitions; coordinate breaker behavior with ANN-003.
5. Expose actual executed strategy, candidate/rerank durations, requested policy, generation/fingerprint, fallback reason, remaining budget, qualification/health and sample-only recall through existing logs/traces. Avoid unbounded metric labels (workspace IDs in restricted traces, not unrestricted metrics). Do not fabricate SQL planner usage per query; use verified plan samples. Discovery/Live graph must reject unqualified capability and preserve strict request, score semantics, source/asset provenance and no Preview fallback.
6. Test full supported ingestion-to-query path at >=100k active chunks only after INGEST-004 measured quota/publication evidence; exercise incremental/delta reuse, old/staged versions, model drift, concurrent workers and tenant skew. Require DELTA-001 evidence before claiming its optimized path, not before basic local qualification.

Follow [AGENTS.md](../AGENTS.md) and [engineering conventions](../docs-website/ENGINEERING.md). Reuse existing owners; names MUST describe domain behavior, never task IDs. Provider-neutral application contracts MUST NOT expose PostgreSQL SQL, pgvector operators or a specific embedding SDK. Do not modify applied migrations, overwrite canonical full vectors, weaken RLS, or add a second authoritative store. Reinspect source, tests and dependencies before implementation; amend this A–O contract before material scope changes.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, parameterized SQL, the least-privileged application role, FORCE RLS and transaction-local scope for every candidate, mapping and metadata lookup. Treat query, document and graph text as untrusted data, not SQL or instructions. No credentials, DSNs, raw vectors, private queries, document content or sensitive paths in logs/evidence. Persist only authorized safe identifiers, policy/revision hashes, counts, timings and reason codes; restrict detailed evidence access and retention under [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md). No new external egress or provider-specific core dependency. Sampling uses same authorization as original request; no raw query/vector retention in telemetry. Restricted benchmark artifacts may use public/synthetic labels; tenant access audit and evidence expiry must follow OPS-001.

## L. Testing / Evaluation / Runtime Verification

Qualification state/contract tests, stale/expired/mismatched evidence, failure and no-sample cases, sampled oracle budget exhaustion, changed snapshot, tenant isolation, route/projection and actual Live discovery/Preview/validator regressions; held-out real PG quality/load evidence and large-corpus end-to-end when prerequisites pass. Run scoped Hatch workbench-api:check/test/types and actual disposable PostgreSQL integration tests; use repository Hatch conventions (Ruff and pytest), not system Python/pip. If web contracts change, run npm typecheck, format:check, test, build and real Live/Preview smoke. Record actual commands, exit codes, test counts/skips, runtime versions and evidence paths; no mock counts as runtime proof.

## M. Acceptance Criteria

- [ ] Each qualified cohort passes predeclared recall, underfill, safety and performance gates or remains unqualified.
- [ ] Evidence bound to exact profile/model/index/generation and verified by existing rollout logic; no fabricated recall.
- [ ] Shadow probes obey bounded admission and leave user latency independent; skips/inconclusive samples visible.
- [ ] Safe telemetry and requested/executed strategy observable; no sensitive content or unbounded labels.
- [ ] Unqualified ANN cannot be advertised/executed as Live; qualified candidate capability and browser contract tested in disposable environment.

## N. Documentation / Migration / Compatibility / Rollback

Document evidence schema, sampling limits, thresholds, requalification and alert routing; retire or disable ANN on failed gates using existing governance. No deletion of data or production promotion. Keep exact baseline and lexical independence.

## O. Mandatory Completion Checklist

- [ ] Reinspect repository and record source/contract changes before coding.
- [ ] Reuse existing owners; review naming, architecture and dependency direction.
- [ ] Execute applicable unit, contract, integration, failure, adversarial and regression checks.
- [ ] Link actual evidence, commands, environment, limitations and unresolved risks.
- [ ] Verify documentation, compatibility and non-destructive rollback.
- [ ] Record modified paths and implementation commit; mark COMPLETE only when the task-local gates pass.

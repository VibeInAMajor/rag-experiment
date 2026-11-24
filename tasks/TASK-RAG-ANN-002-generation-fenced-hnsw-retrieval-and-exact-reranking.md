# TASK-RAG-ANN-002 — Implement generation-fenced HNSW candidate retrieval and full-precision reranking

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no ANN runtime tests executed  
**Priority:** P1  
**Dependencies:** [ANN-001](TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md) GO for selected layout; [DENSE-001](completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md), [EMBED-002](completed/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md), [PROFILE-001](completed/TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md), [INDEX-001](completed/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md). Small/local and disposable SQL integration may proceed before [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md); >10k/50 MiB supported application corpus requires its measured quota contract.  
**Repository snapshot inspected:** ce3b331e5869d563b9bfbabc034b2158148990b3  
**Target:** tasks/TASK-RAG-ANN-002-generation-fenced-hnsw-retrieval-and-exact-reranking.md  
**Roadmap:** [RAG index, retrieval and enterprise plan](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md)

## A. Title

Implement generation-fenced HNSW candidate retrieval and full-precision reranking

## B. Context / Problem

Physical HNSW feasibility does not implement Live Dense. The canonical full vectors and versioned chunk mappings must be resolved correctly even when the index yields unique cached vectors, stale cache rows or several chunks per vector.

## C. Current Repository State

[DenseService / QueryEmbedder / PostgresDenseRetriever](../apps/workbench/retrieval/dense.py) owns qualified exact Haystack execution, embedding admission reuse and snapshot verification. [vector_search_snapshot](../apps/workbench/postgres/postgres.py) validates query/profile, checks rollout/coverage/source generation and joins authoritative migration-0005 mappings to full vectors in repeatable read. [postgres/postgres_dense.py](../apps/workbench/postgres/postgres_dense.py) validates finite normalized query vectors. [retrieval/profile_registry.py](../apps/workbench/retrieval/profile_registry.py) already accepts hnsw_dense, but [validate_dense_policy and execution_profile](../apps/workbench/retrieval/profiles.py), [Composite service routing](../apps/workbench/retrieval/services.py) and [project_search](../apps/workbench/api/projection.py) recognize exact only; merely enabling the enum would misroute or mislabel results. [postgres/migrations/0004_profile_registry.up.sql](../apps/workbench/postgres/migrations/0004_profile_registry.up.sql) persists profile revisions/rollouts. ANN-001 layout/parameters are not yet measured.

## D. Goal

Implement the selected bounded ANN execution path behind existing persistence and dense orchestration, yielding deterministic final full-precision cosine scores and correct chunk identities, without exposing it as an approved Live capability yet.

## E. Scope

Candidate query and full-vector rerank; reuse existing embedding and snapshot logic; physical index prerequisite metadata/contract; explicit internal execution path with real integration tests; extend existing profile validation/dispatch only as needed for internal execution.

## F. Non-Goals

No auto fallback, tenant crossover policy, online shadow jobs, production index lifecycle or public activation; no new embedding worker, vector store, profile registry, or model-specific core interface. No lowering existing exact guarantees.

## G. Architecture / Boundaries

Application chooses approved immutable retrieval policy; persistence adapter owns HNSW SQL and candidate/rerank stages. Existing QueryEmbedder, DensePersistencePort/PersistencePort and VectorSearchSnapshot remain owners; extend only if necessary. Any measured derived index layout remains non-authoritative and uses existing publisher/fences; no second publication authority.

## H. Contracts / Interfaces / Data Model

Use existing ProfileDefinition/rollout/policy hash, embedding fingerprint and generation identity. Add only missing bounded physical index reference/qualification prerequisites and executed strategy/stage metadata. Distinguish physical index identity/revision from corpus generation and profile revision. Candidate budget and returned top-k count chunk occurrences explicitly; document vector candidate cap, mapping fan-out cap and insufficient-candidate signal. Score remains full vector cosine_distance (lower is better), never float16 score or calibrated confidence.

## I. Repository Files / Components Impacted

Modify existing [postgres/postgres.py](../apps/workbench/postgres/postgres.py), [postgres/postgres_dense.py](../apps/workbench/postgres/postgres_dense.py), [persistence/models.py](../apps/workbench/persistence/models.py), [retrieval/dense.py](../apps/workbench/retrieval/dense.py), [retrieval/profiles.py](../apps/workbench/retrieval/profiles.py), [retrieval/profile_registry.py](../apps/workbench/retrieval/profile_registry.py), [retrieval/services.py](../apps/workbench/retrieval/services.py) only as needed. Extend owner tests under postgres/retrieval and existing shared test support. Add only necessary additive metadata migration after current head; no historical migration edits. Public API/graph activation and fallback changes belong to ANN-003/004. Do not rewrite Haystack framework internals.

## J. Implementation Requirements

1. Use ANN-001 signed-off layout/params, check dimensional/model compatibility and index validity. Reuse existing query embedding and input validation; no second model request.
2. Refactor shared exact/ANN fence validation only where it removes duplication. Reuse repeatable-read transaction, tenant-local RLS, current source generation, active version, fingerprint, processing digest, input hash and expected content hash checks. Reject stale/missing profile, incomplete coverage and mismatched physical index identity. No HNSW query against nullable legacy chunks.embedding.
3. Execute bounded candidate retrieval with index-matching halfvec cosine expression; do not apply exact path's enable_indexscan=off to ANN. Resolve candidates to distinct authorized active chunk identities; preserve separate occurrences, deterministic final order, and enforce explicit bounded expansion. Recompute full float32 distance from canonical vector rows for every final candidate; stable distance/chunk-ID tie-break. Never call a rerank exact global search.
4. Use transaction-local validated hnsw settings and existing statement/cancellation budgets. Report underfill or scan exhaustion explicitly; do not pad, silently widen filters, hide as successful complete search or fall back inside the SQL adapter. A legitimately small corpus is not underfill.
5. Keep exact dense behavior and existing lexical contracts intact. Explicitly reject unsupported compositions before dispatch, never send hnsw_dense to lexical by default. Retain profile fence checks and typed execution result; no public capability until ANN-004 qualification and ANN-005 rollout.
6. Test against independently computed exact chunk oracle with real PG and a mixed-dimension cache, duplicate mapping, stale rows, concurrent source swap, index invalidation and cancellation. Record candidate/rerank timing and provenance; prove index use under actual app SQL.

Follow [AGENTS.md](../AGENTS.md) and [engineering conventions](../docs-website/ENGINEERING.md). Reuse existing owners; names MUST describe domain behavior, never task IDs. Provider-neutral application contracts MUST NOT expose PostgreSQL SQL, pgvector operators or a specific embedding SDK. Do not modify applied migrations, overwrite canonical full vectors, weaken RLS, or add a second authoritative store. Reinspect source, tests and dependencies before implementation; amend this A–O contract before material scope changes.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, parameterized SQL, the least-privileged application role, FORCE RLS and transaction-local scope for every candidate, mapping and metadata lookup. Treat query, document and graph text as untrusted data, not SQL or instructions. No credentials, DSNs, raw vectors, private queries, document content or sensitive paths in logs/evidence. Persist only authorized safe identifiers, policy/revision hashes, counts, timings and reason codes; restrict detailed evidence access and retention under [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md). No new external egress or provider-specific core dependency. All scope and identity decisions are server controlled. A physical index is not an authorization boundary. Bind settings locally so pooled connections cannot leak prior request state.

## L. Testing / Evaluation / Runtime Verification

Unit and contract tests for query/profile, bounds and score semantics; real PostgreSQL candidate plans, mixed model/dimension, duplicate/reused inputs, active/historic/staged version, generation drift, invalid index, zero/tiny/underfilled outcomes, canceled SQL and pooled settings isolation; exact/lexical regression. Run scoped Hatch workbench-api:check/test/types and actual disposable PostgreSQL integration tests; use repository Hatch conventions (Ruff and pytest), not system Python/pip. If web contracts change, run npm typecheck, format:check, test, build and real Live/Preview smoke. Record actual commands, exit codes, test counts/skips, runtime versions and evidence paths; no mock counts as runtime proof.

## M. Acceptance Criteria

- [ ] ANN-001 approved layout used; actual application-role query plan proves index use.
- [ ] Full precision final scores and deterministic chunk occurrence identities independently verified.
- [ ] Zero unauthorized, stale-version, wrong-profile or wrong-generation hits in adversarial tests.
- [ ] Candidate and mapping bounds enforced; underfill explicit; no hidden exact fallback or second embedding.
- [ ] Existing exact/lexical tests pass; ANN is not advertised or enabled as production capability.

## N. Documentation / Migration / Compatibility / Rollback

Additive internal contract/metadata only if necessary; coordinate physical DDL with ANN-005 (disposable setup allowed here). Preserve old profile behavior and migration history. Disable unqualified internal path, retain authoritative vectors and lexical retrieval. Document exact score vs approximate candidate semantics.

## O. Mandatory Completion Checklist

- [ ] Reinspect repository and record source/contract changes before coding.
- [ ] Reuse existing owners; review naming, architecture and dependency direction.
- [ ] Execute applicable unit, contract, integration, failure, adversarial and regression checks.
- [ ] Link actual evidence, commands, environment, limitations and unresolved risks.
- [ ] Verify documentation, compatibility and non-destructive rollback.
- [ ] Record modified paths and implementation commit; mark COMPLETE only when the task-local gates pass.

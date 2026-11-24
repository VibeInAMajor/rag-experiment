# TASK-RAG-ANN-001 — Qualify halfvec HNSW physical index, quantization and tenant recall

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no ANN runtime tests executed  
**Priority:** P1  
**Dependencies:** [INDEX-001](completed/TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md), [PROFILE-001](completed/TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md), [EMBED-002](completed/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md), [DENSE-001](completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md) (completed local baselines). Coordinate [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) and [SCALE-001](TASK-RAG-SCALE-001-multiworkspace-identity-authorization-and-tenanted-retrieval.md) policy; neither blocks isolated SQL feasibility. [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) owns real embedding admission.  
**Repository snapshot inspected:** ce3b331e5869d563b9bfbabc034b2158148990b3  
**Target:** tasks/TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md  
**Roadmap:** [RAG index, retrieval and enterprise plan](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md)

## A. Title

Qualify halfvec HNSW physical index, quantization and tenant recall

## B. Context / Problem

The former monolithic ANN specification is replaced by five independently gated tasks. This task alone owns the physical-index experiment and a reproducible GO/NO-GO decision. Full 2560-dimensional Qwen embeddings are already qualified locally. Native vector HNSW cannot index 2560 dimensions in pinned pgvector; halfvec can, but quantization, post-filtering and reuse of a vector by multiple chunk occurrences can reduce final recall. No production change is authorized by this experiment.

## C. Current Repository State

- [0005 migration](../apps/workbench/postgres/migrations/0005_embedding_jobs.up.sql) defines authoritative immutable `embedding_vectors.vector` (variable-dimension public.vector), keyed by workspace/profile fingerprint/processing digest/input hash; `chunk_embeddings` maps distinct chunk occurrences to cached vectors and `embedding_generations` certifies coverage. Historic vectors can outlive active mappings. The older nullable `chunks.embedding` in migration 0001 is NOT the Live Dense authority.
- [PostgresPersistence.vector_search_snapshot](../apps/workbench/postgres/postgres.py) performs full-vector cosine with active source versions, expected content hash, workspace, profile and generation fences in repeatable read; exact path disables indexscan locally and sorts by distance then chunk ID.
- [Compose](../apps/workbench/postgres/compose.yaml) pins pgvector 0.8.2 / PG17; [ProfileDefinition](../apps/workbench/retrieval/profile_registry.py) already declares hnsw_dense, halfvec and ann_index capability, but caps workspace chunks at 10,000 / content at 50 MiB. [Publisher](../apps/workbench/postgres/postgres_ingestion.py) also caps active corpus at those values. [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) explicitly owns measured quotas and retrieval limit changes.
- [DENSE-001 runtime evidence](evidence/dense-2026-11-24/report.md): 102 active real vectors, 52 queries, vector-search p95 32 ms, HTTP p95 1157 ms; local synthetic labels only, not large-scale evidence. [Exact oracle tests](../apps/workbench/postgres/tests/test_dense_persistence.py) already cover independent SQL, profile/source drift and RLS. No HNSW runtime exists in inspected code.

## D. Goal

Produce a measured physical layout and immutable benchmark decision, or a documented NO-GO that leaves ANN disabled. Establish what fraction of loss comes from float16, HNSW traversal, filtering and candidate fan-out separately.

## E. Scope

Disposable PostgreSQL benchmark, expression-index eligibility, resource/recall matrix, independent full precision oracle, exact half precision comparison, indexed candidate and final chunk ranking, physical layout trade-off and parameter selection.

## F. Non-Goals

No production DDL, profile activation, runtime routing, new production table, quota increase, model truncation, hybrid execution, new ingestion engine or GPU throughput claim. No mandatory partition-per-workspace.

## G. Architecture / Boundaries

Persistence adapter owns SQL and physical index choices; evaluation consumes the same chunk identity and authorized filters as current persistence. Application and model contracts remain unchanged. A derived candidate structure may be recommended only if measured direct indexing fails; it must be rebuildable and non-authoritative, with separate design approval in ANN-002.

## H. Contracts / Interfaces / Data Model

Benchmark manifest records PostgreSQL/extension version, hardware CPU/RAM/disk, model fingerprint/dimensions, seed and corpus/query hashes, physical vector rows vs mapped active chunks, eligible counts, per-tenant selectivity, layout, build/query parameters, policy hash, time/resource budgets, measured outcomes and GO/NO-GO. Distinguish approximate candidate distance from full precision cosine distance. The result is evidence, not a new runtime registry.

## I. Repository Files / Components Impacted

Reuse [postgres/postgres.py](../apps/workbench/postgres/postgres.py), [postgres/postgres_dense.py](../apps/workbench/postgres/postgres_dense.py), [postgres/tests/test_dense_persistence.py](../apps/workbench/postgres/tests/test_dense_persistence.py), [retrieval/tests/test_dense_evaluation.py](../apps/workbench/retrieval/tests/test_dense_evaluation.py) and existing `scripts/workbench_dense_evaluate.py` conventions. Add focused disposable benchmark/test code under the PostgreSQL/evaluation owners after reinspection and a report under `tasks/evidence/`. Do not edit applied migrations, main DB, embedding model, profile ceilings or web contracts.

## J. Implementation Requirements

1. Verify pinned extension and actual dimension/fingerprint. Use expression HNSW on authoritative `embedding_vectors.vector::halfvec(2560)` with cosine operator, partial predicate protecting mixed dimensions (and compatible profile where beneficial). Verify prepared generic/custom SQL plans imply the partial predicate; never coerce incompatible dimensions or mix model spaces. Compare existing exact plan and alternative partial/partitioned layout only when evidence warrants.
2. Use identical frozen query vectors and eligible snapshots for full float32 exact (independent oracle), halfvec exact without ANN, halfvec HNSW and HNSW with float32 reranking. Materialize index candidate selection with raw ascending cosine-distance operator plus LIMIT; deterministic chunk tie-break after full rerank. Prove the oracle cannot use ANN; inspect actual application-role query plans rather than forcing planner settings for claimed speedups.
3. Use total physical sizes 10k and >=100k vectors, optional 1M if resources permit; separately track active eligible chunks, cached/stale rows and duplicate occurrences. Test large workspace, 50%/10%/1%/0.1% eligible cohorts, empty/tiny (<k), inactive/staged versions, wrong fingerprint/dimension, repeated input and high mapping fan-out. Synthetic unit vectors are useful for mechanical tests; include representative actual embedding geometry and held-out EN/RU/UK/code queries for quality. Reuse precomputed vectors or governed model dispatch; label synthetic vs actual clearly.
4. Staged tuning, not exhaustive Cartesian sweep: m 16/32, ef_construction 64/128/256 (valid pairs), ef_search 40/100/200/400, candidate limits 50/100/200, iterative_scan off/strict_order/relaxed_order, max_scan_tuples 5k/20k/50k, scan_mem_multiplier 1/2/4; record selected bounds, warm/cold and memory trade-offs. Relaxed ordering requires final deterministic sort.
5. Compute ANN recall@k = intersection of final and independent exact chunk-ID sets divided by min(k, eligible count); exclude zero-eligible queries from mean and separately assert no result. Candidate recall uses mapped eligible candidate chunk IDs before rerank; measure underfill, per-cohort mean, lower-tail/worst-query recall and tie behavior. Use exact stable tie order and report cutoff ties. Track labeled semantic recall/MRR/primary evidence separately; ANN agreement is not answer accuracy.
6. Predeclare cohort/query counts (at least 100 held-out nonempty queries per required cohort, plus negative tests), seed, repeats, acceptable lower-tail regression, fixed load and resource envelope before tuning; report held-out confidence intervals and query counts. Require mean recall@10 >=0.97 in every qualified cohort and zero underfill where sufficient chunks exist; target >25% retrieval p95 improvement vs optimized exact on >=100k qualified eligible chunks, including candidate mapping, rerank and guard costs. Report p50/p95/p99, throughput, failures, build time, index/heap size, CPU/RAM/I/O/WAL and plan buffers. If the target cannot be proven for a cohort, that cohort is not approved. No speed claim from a physical 100k index with only a tiny eligible tenant.
7. Use isolated fixture seeding, clearly distinguish SQL feasibility from real ingestion/E2E. [INGEST-004](TASK-RAG-INGEST-004-incremental-index-and-atomic-publication.md) owns replacing 10k/50 MiB caps and verified bounded publication; no bypass in the serving path. Output reproducible parameter/layout decision with failure modes, estimated build headroom and recommended crossover ranges; leave unqualified layouts disabled.

Follow [AGENTS.md](../AGENTS.md) and [engineering conventions](../docs-website/ENGINEERING.md). Reuse existing owners; names MUST describe domain behavior, never task IDs. Provider-neutral application contracts MUST NOT expose PostgreSQL SQL, pgvector operators or a specific embedding SDK. Do not modify applied migrations, overwrite canonical full vectors, weaken RLS, or add a second authoritative store. Reinspect source, tests and dependencies before implementation; amend this A–O contract before material scope changes.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, parameterized SQL, the least-privileged application role, FORCE RLS and transaction-local scope for every candidate, mapping and metadata lookup. Treat query, document and graph text as untrusted data, not SQL or instructions. No credentials, DSNs, raw vectors, private queries, document content or sensitive paths in logs/evidence. Persist only authorized safe identifiers, policy/revision hashes, counts, timings and reason codes; restrict detailed evidence access and retention under [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md). No new external egress or provider-specific core dependency. Benchmarks run only in an owned disposable database using safe fixture data and scoped application-role queries. Administrative DDL is isolated. Enforce disk/RAM/time and cleanup bounds; measure CPU/system RAM, not VRAM as HNSW capacity.

## L. Testing / Evaluation / Runtime Verification

Independent SQL oracle; expression/partial-plan test under actual prepared statements; mixed dimensions; RLS cross-tenant negative; duplicate fan-out/history; zero/tiny cohort; recall harness and deterministic seed; warm/cold and repeated paired performance tests. Test index build/drop outside transactions and invalid-index cleanup in disposable environment. Run scoped Hatch workbench-api:check/test/types and actual disposable PostgreSQL integration tests; use repository Hatch conventions (Ruff and pytest), not system Python/pip. If web contracts change, run npm typecheck, format:check, test, build and real Live/Preview smoke. Record actual commands, exit codes, test counts/skips, runtime versions and evidence paths; no mock counts as runtime proof.

## M. Acceptance Criteria

- [ ] Independent float32 oracle, quantization-only and indexed results recorded at chunk level.
- [ ] >=100k physical vector feasibility tested; per-cohort eligible counts, held-out recall, underfill and latency/resource evidence recorded, or explicit resource blocker/NO-GO with ANN disabled.
- [ ] Every GO cohort meets >=0.97 mean recall@10, zero unauthorized/stale/wrong-profile hits, zero unexpected underfill and predeclared lower-tail threshold; >=100k eligible serving cohort must prove >25% p95 improvement to be approved.
- [ ] Actual plans use the intended compatible index for ANN and not for exact oracle; no mixed dimensions.
- [ ] Reproducible GO/NO-GO report identifies allowed layout, parameters and limits; no claim of production readiness.

## N. Documentation / Migration / Compatibility / Rollback

Only benchmark scripts/tests/evidence and operator design notes. Keep old filename intentionally to preserve repository links while replacing its scope. No permanent migration. Dispose only owned benchmark databases; production vectors and lexical path unchanged. A negative decision is valid task completion when documented and prevents dependent ANN runtime delivery until requalified.

## O. Mandatory Completion Checklist

- [ ] Reinspect repository and record source/contract changes before coding.
- [ ] Reuse existing owners; review naming, architecture and dependency direction.
- [ ] Execute applicable unit, contract, integration, failure, adversarial and regression checks.
- [ ] Link actual evidence, commands, environment, limitations and unresolved risks.
- [ ] Verify documentation, compatibility and non-destructive rollback.
- [ ] Record modified paths and implementation commit; mark COMPLETE only when the task-local gates pass.

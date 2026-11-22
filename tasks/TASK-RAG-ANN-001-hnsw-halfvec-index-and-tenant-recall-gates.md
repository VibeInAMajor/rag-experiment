# TASK-RAG-ANN-001 — Production HNSW ANN index with 2560-dimensional halfvec and per-tenant recall controls

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation specification only, no runtime tests executed  
**Priority:** P1  
**Dependencies:** EMBED-002, DENSE-001, INDEX-001, SCALE-001 policy design; coordinate OPS-002  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-ANN-001-hnsw-halfvec-index-and-tenant-recall-gates.md

## A. Title

Production HNSW ANN index with 2560-dimensional halfvec and per-tenant recall controls

## B. Context / Problem

The Qwen3-Embedding-4B model card allows full 2560-dimensional output, but pgvector HNSW on the standard vector type indexes only up to 2000 dimensions; halfvec supports 4000. The current Postgres vector_search does exact cosine on vector values, which remains the oracle. Production ANN should reduce latency on a sufficiently large corpus but must not erode rare-workspace recall or bypass active version filtering.

## C. Current Repository State

**Actual code inspected:** [postgres.py](../apps/workbench/api/postgres.py) contains vector_search() that uses exact cosine distance on existing nullable chunk.embedding; lexical_search_snapshot() executes PostgreSQL plainto_tsquery('simple') + ts_rank_cd with active source versions. [lexical.py](../apps/workbench/api/lexical.py) contains a fixed allowlisted Haystack Pipeline with PostgresLexicalRetriever. [profiles.py](../apps/workbench/api/profiles.py) exposes only postgres-fts-baseline-r1. [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py) and [projection.py](../apps/workbench/api/projection.py) enforce the current four-field search request and truthful metadata. [0001 migration](../apps/workbench/api/migrations/0001_initial.up.sql) created GIN/tsvector and pgvector storage but no HNSW/IVFFlat ANN index. [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) specifies future local TEI/Qwen 2560, not an existing real dense API.
Existing index chunks_search_vector is GIN for PostgreSQL FTS, not vector ANN. The current vector_search orders c.embedding <=> query and filters workspace_id, active source_version, embedding_profile_id. The pinned container uses PostgreSQL 17.10/pgvector 0.8.2 as recorded in [database runbook](../docs-website/docs/architecture/postgresql-foundation.md). pgvector official docs explicitly warn that approximate index filtering happens after candidate selection and may return too few tenant hits without iterative scans/partition strategy.

## D. Goal

An opt-in HNSW-based dense execution plan at the verified embedding dimension meets a measured recall/latency envelope versus exact cosine while retaining workspace isolation and active-version constraints. Inability to meet gates falls back by an explicit **approved** profile selector to exact dense, never silently returns incomplete ANN as accurate.

## E. Scope

Benchmark ANN index layouts (halfvec(2560) expression HNSW cosine, optionally partition/partial), index creation CONCURRENTLY outside transaction, per-profile operator settings, filter/iterative scan tuning, statement plans, capacity/upgrade/rollback runbook, qualification at >=100k synthetic-compatible vectors where feasible.

## F. Non-Goals

No automatic 2000-dimension truncation, no vector model training, no changing existing embedding profile in-place, no guarantee ANN is faster for small corpora, no generic partition-per-workspace without budget, no reranking/LLM semantics.

## G. Architecture / Boundaries

ANN is a physical index/SQL execution strategy behind the same PersistencePort and dense retrieval profile. Deployment schema migrator owns DDL; application chooses a qualified exact or approximate plan. Keep full 2560-dimensional vector storage for exact rerank, where using halfvec approximation verify expression and distance operator match the index. Never promote without tenant-filter recall evidence.

## H. Contracts / Interfaces / Data Model

AnnIndexProfile{index_profile_id,embedding_profile_id,dimensions=2560,index_kind=hnsw,expression=embedding::halfvec(2560),distance=cosine,half_precision=true,m,ef_construction,ef_search,iterative_scan,max_scan_tuples,active_generation,covered_workspace_ids,build_status,version}; return actual distance semantics when reranking full-precision. Recording ANN index existence is not proof planner uses it. Distinguish approximate candidate order from exact rerank.

## I. Repository Files / Components Impacted

CREATE next sequential additive SQL migration for ANN metadata and offline admin index DDL task, scripts under apps/workbench/postgres/ or reviewed ops folder, tests/test_ann_indexes.py; MODIFY postgres.py vector query adapter and profiles.py/profile registry, operator docs. REUSE migration guard in db_migrations.py. MUST NOT create 2560-dim HNSW on vector_cosine_ops, modify applied migrations or lie in SearchResult.score_type.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Reconfirm actual model dims and vector normalization; benchmark exact SQL on 10k, 100k, and up to 1M seeded synthetic distributions (subject available hardware) with different workspace sizes. Record EXPLAIN ANALYZE, read I/O and memory.
2. J2 — Evaluate full vector(2560) retained + HNSW on halfvec(2560) cast; compare index size/recall versus optional 1536-dim MRL profile only as a different model profile (never silent truncate). Keep HNSW DDL migration reviewed and build CONCURRENTLY where possible.
3. J3 — Partitioning/filter experiments: tenant A dominant, tenant B 1% and tenant C tiny; measure recall@10 vs exact under RLS and post-filtering. Test hnsw.iterative_scan strict_order, ef_search and max_scan_tuples; optimize p95 with measured tuning.
4. J4 — Store ANN build state and qualified generation; ensure no search activation while index invalid/half-built. Validate actual pg_catalog index valid/ready, planner path and operator classes; new index must match compatible dimension and profile.
5. J5 — Add runtime planned strategy exact versus hnsw controlled by profile, not user SQL parameter. If ANN fails recall gate for tenant/size, use qualified exact profile or partition plan explicitly and log selection.
6. J6 — Stress concurrent ingestion/index build/reindex, slow queries, backups and restart; provide CONCURRENTLY drop/rebuild repair playbook and rollback without dropping vector data.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

SQL negative unsupported index dimension, exact oracle hit comparison with 100+ labeled queries and 3 tenant sizes, active/historic version, profile dimension drift, ef_search sweep, partial recall, bloat, planner index usage, restart/reindex and DB lock contention. Record memory/disk size and p50/p95/p99; target suggested recall@10 >=0.97 on gated corpora and >25% p95 gain for >=100k case, but thresholds must be ratified from measured hardware baseline before approval.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

## M. Acceptance Criteria

- [ ] No unsupported vector(2560) HNSW on native vector operator; index expression and dimensions verified
- [ ] Every ANN result remains scoped to authorized workspace and active source version
- [ ] Approximate recall@10 versus exact >=97% on pre-agreed test sets or ANN remains disabled
- [ ] ANN candidate completeness and tenant imbalance measured and visible
- [ ] p95 improvement and index size/maintenance reported for at least 100k vector set, no unmeasured production claim
- [ ] Planner actually uses intended valid/ready index on qualified test
- [ ] Failure/rollback preserves exact dense vector storage and lexical availability
- [ ] Index generation and profile revision encode ANN version

## N. Documentation / Migration / Compatibility / Rollback

Deploy additive index/profile in shadow/read-only mode; compare exact oracle before activation. On recall regression mark ANN generation unqualified and route explicitly to exact dense. Drop invalid ANN index CONCURRENTLY after rollback window, never drop embeddings, sources or original assets.

## O. Mandatory Completion Checklist

- [ ] Source, dependency and existing tests re-inspected; blueprint updated if runtime diverged.
- [ ] Reuse current persistence, tokenizer, API and Haystack components; no duplicate storage.
- [ ] New profile semantics, failures and capability gates match exact contracts.
- [ ] Workspace, source version and index generation constraints enforced.
- [ ] Quality, performance, adversarial and restart tests actually executed.
- [ ] No misleading BM25/vector/ANN/hybrid score or capability claims.
- [ ] Migration/rollout/rollback non-destructive and operator documented.
- [ ] Real runtime evidence, commands, benchmark inputs and safe trace IDs linked.
- [ ] Changes and compatibility issues reviewed against dependent tasks.
- [ ] Mark COMPLETE only with proof of every applicable acceptance check.

**Documentation convention:** no feature is marked qualified merely because a test is described; amend A–O before any material scope expansion.

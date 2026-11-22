# TASK-RAG-BM25-001 — Decision and benchmark: genuine BM25 versus PostgreSQL native FTS

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation specification only, no runtime tests executed  
**Priority:** P1 decision task; start now, migrate only if data proves value  
**Dependencies:** Completed RAG-001 and EVAL-001; INDEX-001 and PROFILE-001 desired for exact versioned A/B  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md

## A. Title

Decision and benchmark: genuine BM25 versus PostgreSQL native FTS

## B. Context / Problem

It is tempting to replace current PostgreSQL FTS because the UI says "BM25", but PostgreSQL ts_rank_cd is not BM25 and installing a new extension has operational, licensing, migration, scaling and correctness implications. A genuine BM25 may materially improve long-document lexical ranking, yet current exact-term queries on eight synthetic sources cannot justify a production migration. The right immediate task is to benchmark *without changing the current Live search* and produce a go/no-go decision.

## C. Current Repository State

**Actual code inspected:** [postgres.py](../apps/workbench/api/postgres.py) contains vector_search() that uses exact cosine distance on existing nullable chunk.embedding; lexical_search_snapshot() executes PostgreSQL plainto_tsquery('simple') + ts_rank_cd with active source versions. [lexical.py](../apps/workbench/api/lexical.py) contains a fixed allowlisted Haystack Pipeline with PostgresLexicalRetriever. [profiles.py](../apps/workbench/api/profiles.py) exposes only postgres-fts-baseline-r1. [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py) and [projection.py](../apps/workbench/api/projection.py) enforce the current four-field search request and truthful metadata. [0001 migration](../apps/workbench/api/migrations/0001_initial.up.sql) created GIN/tsvector and pgvector storage but no HNSW/IVFFlat ANN index. [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) specifies future local TEI/Qwen 2560, not an existing real dense API.
Existing PostgreSQL generated tsvector uses simple dictionary with GIN; score_type postgres_ts_rank_cd. Haystack InMemoryBM25Retriever requires an InMemoryDocumentStore and is **not** a viable Live replacement. The pg_search (ParadeDB) Postgres extension offers BM25 and currently lists AGPL 3 licensing on PGXN; packaging and license/commercial implications require approval. Alternative PostgreSQL BM25 options must be researched in the implementation phase; do not invent an installed extension.

## D. Goal

Choose whether BM25 merits another SQL adapter using a reproducible, format-stratified query/evidence set, explicit extension+license review, measured index size/ingestion latency, ranking quality and multiworkspace filtering correctness. A NO-GO is a legitimate complete result and leaves Postgres FTS unchanged.

## E. Scope

Review pg_search and viable alternatives, evaluate license/runtime/container architecture, sample enterprise-like documents and query sets, build isolated disposable benchmark (native FTS baseline vs real BM25), measure quality/cost and tenant isolation, document decision record and conditional activation criteria for BM25-002.

## F. Non-Goals

No immediate change to production lexical profile or UI node, no mixing of mock BM25 with real SQL, no AGPL extension deployed by default, no additional search service, no unchecked "BM25 is always better" claim.

## G. Architecture / Boundaries

Potential BM25 remains a second approved lexical retrieval adapter under existing SearchPort/PersistencePort, separately versioned; database extension is optional deployment capability. Native FTS remains stable and an explicit rollback target. Query/tenant FKs and active versions must be enforced by source-owner SQL for either algorithm.

## H. Contracts / Interfaces / Data Model

BenchmarkExperiment{corpus_generation,query_labels,expected_relevant_source_or_chunk,profile_id,config,raw_score,metric,latency,plan,index_bytes,license_assessment,db_image_revision}; candidates native_postgres_fts, pg_search_bm25 and supported alternatives. Require per-query top-k/source IDs and human-reviewed evidence labels; compare document/segment exact, paraphrase, long-form and multilingual. Publish Decision{go/no-go,conditions,measured_gains,operational_costs,legal_approval,failures}. No public BM25 score_type until a real BM25 query is measured.

## I. Repository Files / Components Impacted

READ [0001 migration](../apps/workbench/api/migrations/0001_initial.up.sql), [postgres.py](../apps/workbench/api/postgres.py), [lexical.py](../apps/workbench/api/lexical.py), [lexical gold fixture](../apps/workbench/api/fixtures/lexical-evaluation.json), [evaluation guide](../docs-website/docs/architecture/postgres-lexical-search.md); CREATE benchmark design/tools in tests/benchmarks/ or apps/workbench/api/tests/benchmark_bm25.py, and tasks/BM25_DECISION_REPORT.md with Created/Updated; do not change live SQL or public API.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Freeze current lexical quality and EXPLAIN/latency from actual corpus. Expand to >=1000 non-sensitive representative chunks across 3+ format families and >=100 labeled query/evidence pairs with exact, long-tail, paraphrase and code identifiers.
2. J2 — Research pg_search exact current version, PostgreSQL 17 compatibility, host image constraints, AGPL-3 obligations, extension upgrade/backup and support costs. Present at least native FTS and one genuine BM25 candidate; legal sign-off required before product shipment.
3. J3 — Deploy BM25 extension **only** into disposable isolated database, not the pinned operator volume, with correct workspace/active version filters. Build audited index and verify scores truly BM25, not ts_rank_cd relabeled.
4. J4 — Compare Recall@5/10, MRR@10, nDCG@10 where graded labels exist, source/citation correctness, p50/p95 latency, indexing time, disk and memory, query analyzer behavior EN/RU/UK, update workload and tenant skew.
5. J5 — Write Go/No-Go with pass thresholds proposed pre-analysis: >=5 percentage point source-hit improvement on weak-query subset OR comparable overall quality with materially better latency/cost, no critical tenant regression; require stakeholders to agree on gates before looking at results.
6. J6 — If GO: authorize BM25-002 as conditional implementation; if NO-GO: keep native FTS, preserve benchmark/evidence, reassess only when corpus/query workload changes.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

Reproduce signed corpus/query manifest, stable sample query labels, multiple runs cold/warm, one tenant 1% of rows, source version switch, query tokenization, extension outage, index build pressure, 100+ queries and 1000+ chunks. Record all unsuccessful queries; no leakage of confidential documents; compare raw scores only within their algorithms.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

## M. Acceptance Criteria

- [ ] Current native FTS quality/performance frozen and repeatable
- [ ] At least one real BM25 candidate tested in isolated PostgreSQL, not mocked or in-memory
- [ ] 100+ labeled queries and >=1000 chunks yield paired metrics with all failures retained
- [ ] Index size, write throughput, p95 and tenant filtering reported
- [ ] Legal/license/commercial approval assessed and documented
- [ ] Decision Go/No-Go with measurable gates and query examples published
- [ ] Public baseline keeps postgres_ts_rank_cd throughout decision task
- [ ] BM25-002 stays blocked until explicit Go decision

## N. Documentation / Migration / Compatibility / Rollback

No live schema/API changes by design. Benchmark databases disposable and segregated; preserve current PostgreSQL baseline and all source/embedding records. No forced license acceptance; decision can remain NO-GO without delaying dense/hybrid.

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

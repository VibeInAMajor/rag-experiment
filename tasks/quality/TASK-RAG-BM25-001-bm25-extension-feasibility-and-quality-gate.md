# TASK-RAG-BM25-001 — Decision and benchmark: genuine BM25 versus PostgreSQL native FTS

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — implementation specification only, no runtime tests executed  
**Priority:** P1 decision task; start now, migrate only if data proves value  
**Dependencies:** completed RAG-001/EVAL-001/INDEX-001/PROFILE-001; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md) reviewed tuning data, [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md) lexical baseline; compare [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) when available.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md

## A. Title

Decision and benchmark: genuine BM25 versus PostgreSQL native FTS

## B. Context / Problem

It is tempting to replace current PostgreSQL FTS because the UI says "BM25", but PostgreSQL ts_rank_cd is not BM25 and installing a new extension has operational, licensing, migration, scaling and correctness implications. A genuine BM25 may materially improve long-document lexical ranking, yet current exact-term queries on eight synthetic sources cannot justify a production migration. The right immediate task is to benchmark *without changing the current Live search* and produce a go/no-go decision.

## C. Current Repository State

[PostgresPersistence](../../apps/workbench/postgres/postgres.py) now owns lexical_search_snapshot and real vector_search_snapshot over migration 0005's immutable embedding_vectors and chunk_embeddings, not nullable legacy chunks.embedding. [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py) executes qualified exact Dense; [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py) already defines rrf/bm25 but they are not executable merely by schema. [profiles.py](../../apps/workbench/retrieval/profiles.py), [retrieval routing](../../apps/workbench/retrieval/services.py), [projection](../../apps/workbench/api/projection.py) and [API contracts](../../apps/workbench/contracts/schemas.py) own qualification and score provenance. [actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md) records 102 real vectors, 52 queries and independently checked exact SQL; no independent quality holdout, BM25 or Hybrid runtime claim. Current local corpus cap 10k/50 MiB remains. Native PostgreSQL simple FTS/GIN uses ts_rank_cd, not BM25. No deployed BM25 extension; review actual extension license and runtime before isolated trial.

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

READ [0001 migration](../../apps/workbench/postgres/migrations/0001_initial.up.sql), [postgres.py](../../apps/workbench/postgres/postgres.py), [lexical.py](../../apps/workbench/retrieval/lexical.py), [lexical gold fixture](../../apps/workbench/retrieval/fixtures/lexical-evaluation.json), [evaluation guide](../../docs-website/docs/architecture/postgres-lexical-search.md); CREATE benchmark design/tools in apps/workbench/retrieval/tests/benchmarks/ or apps/workbench/retrieval/tests/benchmark_bm25.py, and tasks/BM25_DECISION_REPORT.md with Created/Updated; do not change live SQL or public API.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/postgres/postgres.py`](../../apps/workbench/postgres/postgres.py) | true baseline plainto_tsquery('simple') + ts_rank_cd + active version filter |
| [`apps/workbench/postgres/migrations/0001_initial.up.sql`](../../apps/workbench/postgres/migrations/0001_initial.up.sql) | generated tsvector and GIN index |
| [`apps/workbench/retrieval/lexical.py`](../../apps/workbench/retrieval/lexical.py) | read-only Haystack FTS baseline |
| [`apps/workbench/retrieval/fixtures/lexical-evaluation.json`](../../apps/workbench/retrieval/fixtures/lexical-evaluation.json) | 10 exact, 3 paraphrase cases, insufficient for BM25 decision |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../../apps/workbench/api/tests/test_lexical_routes.py) | rank and provenance oracle |
| [`docs-website/docs/architecture/postgres-lexical-search.md`](../../docs-website/docs/architecture/postgres-lexical-search.md) | current lexical runbook/results |
| [`haystack/components/retrievers/in_memory/bm25_retriever.py`](../../haystack/components/retrievers/in_memory/bm25_retriever.py) | in-memory implementation NOT a pgvector adapter |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/22-implementation-step-05-sparse-and-symbol-retrieval.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/22-implementation-step-05-sparse-and-symbol-retrieval.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

**Quality-track boundary:** [implementation order](IMPLEMENTATION_ORDER.md). Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion. Use DATASET-001 reviewed tuning data and common evidence facets, equal final context token budget, predeclared paired metrics and explicit no-go. The independent final holdout is reserved for QUALITY-002; prior synthetic query counts remain minimum regression tests, not final quality qualification. No production activation based on benchmark alone.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Freeze current lexical quality and EXPLAIN/latency from actual corpus. Expand to >=1000 non-sensitive representative chunks across 3+ format families and >=100 labeled query/evidence pairs with exact, long-tail, paraphrase and code identifiers.
2. J2 — Research pg_search exact current version, PostgreSQL 17 compatibility, host image constraints, AGPL-3 obligations, extension upgrade/backup and support costs. Present at least native FTS and one genuine BM25 candidate; legal sign-off required before product shipment.
3. J3 — Deploy BM25 extension **only** into disposable isolated database, not the pinned operator volume, with correct workspace/active version filters. Build audited index and verify scores truly BM25, not ts_rank_cd relabeled.
4. J4 — Compare Recall@5/10, MRR@10, nDCG@10 where graded labels exist, source/citation correctness, p50/p95 latency, indexing time, disk and memory, query analyzer behavior EN/RU/UK, update workload and tenant skew.
5. J5 — Write Go/No-Go with pass thresholds proposed pre-analysis: >=5 percentage point source-hit improvement on weak-query subset OR comparable overall quality with materially better latency/cost, no critical tenant regression; require stakeholders to agree on gates before looking at results.
6. J6 — If GO: authorize BM25-002 as conditional implementation; if NO-GO: keep native FTS, preserve benchmark/evidence, reassess only when corpus/query workload changes.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Freeze current FTS exact SQL/GIN/profile and score_type before evaluating any BM25 extension; record baseline source IDs and quality of full 10+3 set.

**J8.** Define ≥1000 non-sensitive chunks across code/TXT/Markdown/real parsed PDF, 100+ manually labeled exact/error-code/multilingual/long-document queries; avoid skewing benchmark to eight seed rows.

**J9.** Investigate current pg_search/ParadeDB extension version, Postgres 17 binary compatibility, licensing AGPL/commercial obligations and maintenance. Document explicit GO conditions approved by owner before running results.

**J10.** Deploy extension only to disposable Postgres clone with correct RLS/workspace and active version filter; do not change current GIN index or production connection.

**J11.** Run pairwise Recall@5, MRR@10, false source/page citation, query p95, index write/update time, index size, memory and query analyzer behavior; include real no-match/remote mode negative.

**J12.** Compare with current FTS and evaluate whether source-dense RRF is a better quality investment than BM25 migration; record no-go as valid success.

**J13.** Publish signed markdown decision and rollback/operator impact. Only if GO unblocks BM25-002; no test should claim source model embeddings helped lexical BM25 quality.

**Cross-cutting constraints:** BM25 is a measured GO/NO-GO; the production path must not relabel ts_rank_cd as bm25_raw.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

Reproduce signed corpus/query manifest, stable sample query labels, multiple runs cold/warm, one tenant 1% of rows, source version switch, query tokenization, extension outage, index build pressure, 100+ queries and 1000+ chunks. Record all unsuccessful queries; no leakage of confidential documents; compare raw scores only within their algorithms.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

### L.1. Task-specific reproducible test vectors

- [ ] A/B paired >100 queries, >=1000 chunks; exact/identifier RU/UK/EN, document text length strata.
- [ ] Workspace skew, deleted/updated active version and stale data, no cross-tenant search.
- [ ] Extension unload/restart/upgrade, FTS unaffected, no transient InMemoryDocumentStore Live fallback.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

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

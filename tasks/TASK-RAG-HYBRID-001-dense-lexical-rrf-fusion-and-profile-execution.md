# TASK-RAG-HYBRID-001 — Live hybrid retrieval combining genuine lexical and dense ranks with explicit RRF

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation specification only, no runtime tests executed  
**Priority:** P1  
**Dependencies:** DENSE-001, PROFILE-001, INDEX-001; BM25-002 optional and not a prerequisite  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md

## A. Title

Live hybrid retrieval combining genuine lexical and dense ranks with explicit RRF

## B. Context / Problem

Dense semantic retrieval and lexical exact term recall have complementary failure cases. We need a bounded, testable combined profile that invokes both sources against a consistent workspace/index generation and uses Reciprocal Rank Fusion rather than mixing incomparable raw ts_rank_cd and cosine distance. Existing Haystack has DocumentJoiner with RRF support but its default join mode is concatenate; configuring the wrong default would silently change ranking.

## C. Current Repository State

**Actual code inspected:** [postgres.py](../apps/workbench/api/postgres.py) contains vector_search() that uses exact cosine distance on existing nullable chunk.embedding; lexical_search_snapshot() executes PostgreSQL plainto_tsquery('simple') + ts_rank_cd with active source versions. [lexical.py](../apps/workbench/api/lexical.py) contains a fixed allowlisted Haystack Pipeline with PostgresLexicalRetriever. [profiles.py](../apps/workbench/api/profiles.py) exposes only postgres-fts-baseline-r1. [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py) and [projection.py](../apps/workbench/api/projection.py) enforce the current four-field search request and truthful metadata. [0001 migration](../apps/workbench/api/migrations/0001_initial.up.sql) created GIN/tsvector and pgvector storage but no HNSW/IVFFlat ANN index. [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) specifies future local TEI/Qwen 2560, not an existing real dense API.
The source library has [DocumentJoiner](../haystack/components/joiners/document_joiner.py) with RRF mode, and a query-dependent lexical Haystack pipeline. No cross-retriever profile/execution exists in the application. Current source-aware identities and active version constraints must be shared by both retrievers.

## D. Goal

A qualified hybrid Live API returns one merged ranked result set with deterministic RRF scores and traceable component ranks, source/version/chunk provenance, no duplication and correct partial-failure policy. The profile does not claim BM25 unless BM25-002 has actually qualified.

## E. Scope

Haystack composed lexical + dense retrievers and explicitly configured RRF joiner, normalized document ID key, bounded candidate_k/top_k/rrf_k, cancellation/deadlines, stale generation rejection, selectable profile and UI, per-arm/stage timing and benchmark, consistent source/asset provenance.

## F. Non-Goals

No naive weighted summation of raw FTS scores and cosine distances, no automatic BM25 migration, no arbitrary joiner mode from UI, no global rewrite of corpus, no reranker in first gate unless independently approved.

## G. Architecture / Boundaries

FastAPI approved hybrid profile -> parallel bounded lexical/dense Haystack components -> explicit RRF (reuse Haystack DocumentJoiner with verified join_mode) -> server-side final projection. Both search arms obtain one compatible index manifest; workspace authorization remains SQL-side and local vectors not exposed to browser.

## H. Contracts / Interfaces / Data Model

HybridProfile{profile_id,profile_revision,index_generation,lexical_profile_id,dense_profile_id,embedding_revision,candidate_k_lexical,candidate_k_dense,rrf_k default 60 configurable approved,top_k,require_both_arms,timeout,score_type="rrf_score"}. RRF for unique stable chunk ID: sum_{retriever containing chunk}(1/(k+rank_i)); rank_i is 1-based. Output component_ranks with arm, rank and raw score_type, not full vectors. Define deterministic tie: fusion score desc then chunk_id asc. Default fail-closed if one required arm fails; optional explicit degraded profile must be separate and transparently labeled.

## I. Repository Files / Components Impacted

CREATE apps/workbench/api/hybrid.py, tests/test_hybrid_retrieval.py, tests/test_hybrid_routes.py; MODIFY profiles.py/registry, services.py, application.py, contracts.py, projection.py and shared UI approved matcher/template; REUSE lexical.py, dense.py, PostgresPersistence, Haystack DocumentJoiner. MUST NOT silently change existing keyword flow, DocumentJoiner defaults or raw score labels.

## J. Implementation Requirements — ordered executable blueprint

1. J1 — Inspect actual Haystack DocumentJoiner RRF mode and its score semantics in current library; verify joiner input socket map, Document.id provenance and rank output with controlled two-arm fixture including duplicate source/versions.
2. J2 — Build bounded Haystack Pipeline whose lexical and dense retrieval stage requests target same authorized workspace and compatible source/index generation. Snapshot inconsistency causes re-resolve or 409, never cross-version fusion.
3. J3 — Configure joiner explicitly for RRF (not concatenate) or use smallest pure, tested fusion helper if DocumentJoiner loses required provenance; document why. Deduplicate by source_version_id+chunk_id rather than by similar text/title.
4. J4 — Integrate provider/profile capabilities, normalized request and component-specific stage/timing; attach source link/evidence from CONTENT-005 when ready without making image processing a prerequisite for text hybrid.
5. J5 — Add browser approved hybrid template and test 400 bad graph, 409 stale profile, 503 missing vectors, 429 busy, 504 timeout/cancellation. Do not execute existing demo Hybrid canvas until server validates the exact supported graph.
6. J6 — Compare 30+ labeled lexical, paraphrase, source code and multi-part queries at fixed context-token budget. Record hybrid Recall@5/10 and MRR versus each arm and per-workspace p95; prioritize no material regression.

## K. Security / Governance / Observability

WorkspaceContext and RLS are required for every candidate and metadata lookup. No credentials, raw document text, vectors or private model responses in logs; only safe IDs, profile/generation revision, bounded counts, trace_id, stage duration and error codes. Incoming graph/config/doc text is untrusted. No outbound cloud connections or unreviewed license burden; cap memory, candidate counts and provider timeouts. Apply adversarial tests to source-version, workspace and ranking result integrity.

## L. Testing / Evaluation / Runtime Verification

Unit RRF score numeric examples, duplicate chunks, ties, missing arms, empty results, reversed score direction, source/version disambiguation, timeout, concurrent query, partial embedding coverage, 10+ classic lexical and 30+ semantic queries, UI Preview/Live distinctness and full HTTP/SQL output parity. Check RRF k monotonic and no arbitrary graph execution.

Run scoped Hatch workbench-api:check/test/types, PostgreSQL container integration tests and (if UI touched) web typecheck/test/build and existing Preview/validator smoke. Use disposable benchmark database; real measurements must be labeled separately from mocks.

## M. Acceptance Criteria

- [ ] Hybrid uses explicit RRF rather than concatenation or raw-score mixing
- [ ] Both retrieval arms operate on compatible qualified generation and same server-authorized workspace
- [ ] Fusion output has deterministic stable ranks/IDs, proper provenance and score_type rrf_score
- [ ] Missing required arm causes clearly unavailable profile, no silent FTS-only fallback
- [ ] 30+ labeled queries compare hybrid and both arms at equal evidence budget
- [ ] Corpus version and component ranks/timings recorded with every Live run
- [ ] No duplicate chunks and no mixed source versions
- [ ] Existing lexical and dense regression suites remain green

## N. Documentation / Migration / Compatibility / Rollback

Enable hybrid only as a new immutable profile, leave current lexical and exact dense paths unchanged. Disable hybrid on quality regression; preserve original scores/vectors and their generation. Future reranker is another profile stage, not a reinterpretation of RRF score.

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

# TASK-RAG-LEXICAL-001 — Qualify natural-language lexical retrieval before hybrid fusion

**Created:** 2026-11-26  
**Updated:** 2026-11-26  
**Status:** PROPOSED — local benchmark and conditional policy implementation; no tests executed  
**Priority:** P0  
**Dependencies:** [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md) failure report; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md) local OPEN data; existing approved PostgreSQL lexical profile.  
**Target:** tasks/quality/TASK-RAG-LEXICAL-001-natural-language-query-policy.md  
**Repository snapshot inspected:** `458349c280bc2409ecbe2b573d8e973b52e0c64c`  
**Reference:** [Quality and content-understanding plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md)

## A. Title

Qualify a useful bounded natural-language lexical policy without changing the existing literal FTS baseline.

## B. Context / Problem

[DATASET-001 actual report](../evidence/dataset-2026-11-24/report.md) records zero FTS hits on 306 natural-language queries, despite 10/10 native literal controls passing. Adding an empty lexical arm to RRF will not supply missing evidence. Distinguish overly restrictive AND policy from vocabulary/morphology, representation and indexing failures. Do not infer that BM25 or a new store will fix query formation.

## C. Current Repository State

- [postgres.py](../../apps/workbench/postgres/postgres.py), blob `3fd5ebbeb8a39440beda2c7afbe9b0815cbbb0f1`: `lexical_search_snapshot` uses parameterized `plainto_tsquery('simple', %s)`, `search_vector @@ q.query`, `ts_rank_cd`, active-version workspace join and deterministic score/chunk-ID order. All tokenized terms are conjoined. The literal control demonstrates the current path is functional, not suitable for full natural-language queries on this corpus.
- [lexical.py](../../apps/workbench/retrieval/lexical.py), blob `fb33476b5056f0b564ed04880f147182ffa82d7f`: `PostgresLexicalRetriever.run_async` delegates to `PersistencePort.lexical_search_snapshot`; `LexicalService` and existing composition table own approved profiles and readiness.
- [profile_registry.py](../../apps/workbench/retrieval/profile_registry.py), [profiles.py](../../apps/workbench/retrieval/profiles.py), [lexical architecture](../../docs-website/docs/architecture/postgres-lexical-search.md) define immutable profile revisions and validated bounds. Reinspect current policy types, migrations, tests and SQL plans before modifying.
- [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md) already mandates native query diagnostic probes, not a new lexical profile. [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) owns fusion; [BM25-001](TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md) owns conditional extension feasibility. Neither should duplicate this lexical policy experiment.
- Local case-level predictions and mapping data are under the existing ignored evaluation directory; not inspected by this repository-only audit. Final eight-arm results not yet published at snapshot time.

## D. Goal

Select and qualify a minimal versioned lexical query policy that contributes meaningful source-grounded evidence for natural-language questions, or record a measured NO-GO before hybrid qualification. Preserve the existing FTS profile and literal behavior.

## E. Scope

Native token analysis; bounded query policy candidates; matched OPEN evaluation with existing dataset/scorer; conditional integration into existing lexical profile/SQL ownership if GO; exact-identifier, language, negative, provenance and latency regressions.

## F. Non-Goals

No new vector store, ANN, external LLM query rewriting, separate domain pipelines, BM25 extension installation, RRF integration, generation or answerability. No tuning on Retrieval-R2/ANSWER. No enterprise infrastructure, reviewer identities or manual approvals.

## G. Architecture / Boundaries

- [ ] Domain / core — no Haystack core changes.
- [x] Application / orchestration — approved query policy and existing lexical service.
- [x] Port / interface / contract — extend existing profile definition only if necessary.
- [ ] Provider adapter — no new provider; existing PostgreSQL adapter owns SQL mapping.
- [x] Persistence / vector store — parameterized bounded FTS policy, no new store.
- [x] Retrieval / RAG — lexical candidate quality.
- [ ] Agent runtime — no new runtime.
- [x] Security / governance — preserve scope, active generation and input bounds.
- [x] Observability / evidence — existing per-case and timing artifacts.
- [ ] Infrastructure / CI/CD — no new service or pipeline.
- [x] Documentation — approved profile semantics and measured decision.

Use semantic names and existing port/composition; no task-ID identifiers.

## H. Contracts / Interfaces / Data Model

Existing query/top_k/profile revision and typed lexical result unchanged unless a compatible addition is justified. Any selected policy has explicit policy revision, term bounds, language behavior, phrase/identifier handling, deterministic tie policy, empty-query behavior and score semantics (`postgres_ts_rank_cd` when unchanged). Never return arbitrary SQL or user-selected tsquery expressions. Candidate metadata records native token count, effective query policy, matched count, ranks, scope and timing; sensitive query text only in local evaluation artifacts.

## I. Repository Files / Components Impacted

Reuse existing local evaluation adapters, `scripts/workbench_embedding_evaluate.py` and actual lexical HTTP path, `apps/workbench/retrieval/lexical.py`, `apps/workbench/postgres/postgres.py`, `apps/workbench/persistence/models.py`, profile registry and existing lexical/persistence/API tests. Change only the existing owner if necessary for a qualified new policy. Update lexical architecture doc if behavior changes. Preserve baseline profile/revision, GIN schema unless separately scoped, existing fixture, dense path, corpus originals and UI/API contracts. Amend this specification before any migration or broader work.

## J. Implementation Requirements

1. Finish QUALITY-001 and reuse its diagnostics. Freeze OPEN originals/query families, source mapping and candidate/context budgets; use the same source revision and authorized scope for baseline and variants. Record native `ts_debug` / equivalent tokenization, query terms, stored vector lexemes and why selected failures returned no hits.
2. Compare current full AND, bounded meaningful-term AND, bounded OR over safely derived native lexemes and a conservative mixed exact-identifier/phrase policy. Use language-aware native dictionaries only if availability, matching index representation and EN/RU/UK compatibility are demonstrated; do not claim stemming or transliteration unsupported by actual configuration. Preserve negation, code identifiers, versions, names, numbers and units. Empty/no usable terms produce explicit empty lexical results, not an unbounded scan. Construct tsquery via safe parameterized native functions/operators and bounded validated lexemes; no raw user tsquery concatenation.
3. Run actual PostgreSQL/HTTP where supported and retain paired raw ranks, first-primary and any-fact hit@1/5/10, all-facets@5/10, candidate coverage, nonempty result count, exact-term hits, hard-negative admission, no-answer raw hits and p50/p95/p99. Report sparse qrel judgment coverage; do not invent recall/nDCG or abstention rates. Include Art/Literature/Kubernetes and languages. Use dense-only and lexical-only comparisons to identify incremental evidence absent from dense top-k.
4. Predeclare local GO criterion before comparison: preserve 10/10 literal controls and all existing lexical regressions, nonzero useful source-supported results on OPEN, measurable complementary fact/primary contribution to the dense pool (report counts and apply the proposed five-case minimum in the measured next-experiment amendment), no forbidden scope/version results and bounded cost. Prefer the smallest policy that helps difficult queries; a nonempty but irrelevant list is NO-GO. Report proposed p95 budget and paired cost; no automatic activation solely from nonempty count.
5. If GO, add/qualify a separate immutable lexical policy using existing registry and SQL owner; preserve the original baseline. Verify actual HTTP behavior and compatibility. If NO-GO, document why and route to BM25 feasibility or a dense-only rerank experiment; do not present empty-arm fusion as meaningful hybrid improvement.
6. Use existing local corpus limits (10,000 active chunks, 50 MiB) and no holdout inspection. Reuse actual tests and local evaluation reports; record commands, exit codes and failures.

### Measured next experiment after Markdown cleanup — 2026-11-26

Use the latest [QUALITY-001 completion](../evidence/quality-2026-11-25/report.md#завершение-quality-001-dense-fts-и-парное-сравнение-чанкинга--2026-11-26) rather than repeating its completed native diagnostics: four corpora, 1224 diagnostic sets, all natural AND queries empty, all native literal controls 1224/1224 successful, zero stored-vector mismatches. Per corpus 252 questions contain absent lexemes; for 54 all words exist but never together in one chunk. Reuse captured lexemes/OR probes; compare meaningful term subsets, bounded OR and mixed phrase/exact-term policies with the new canonical-LF post-cleanup corpus, preserving 306/306 native literal controls on that corpus and the original profile. Freeze useful contribution criterion before testing: proposed >=5 additional distinct answerable OPEN cases with known evidence absent from matched dense top-10 at equal total candidate budget, no scope/version errors, and show actual hard-negative/cost trade-off; if smaller gain, report NO-GO or evidence-backed limited experimental result without promotion. Use same 306 query IDs and report language/domain results; cross-language mismatch is not solved by OR alone. Run new functional acceptance through existing local UI/Workbench, not a new evaluation service. No need to wait for DATASET-002 to measure known-facet coverage; use its distinct primary/pooled judgments when ready.

## K. Security / Governance / Observability

Keep server-derived WorkspaceContext, RLS, active version, profile fences, parameterized SQL, query length/time/term limits and existing cancellation semantics. No arbitrary operator syntax, credentials, raw content or vectors in normal logs. No external data egress. Retain local benchmark artifacts and safe aggregate report under existing evidence policy.

## L. Testing / Evaluation / Runtime Verification

Focused unit/contract tests for Unicode, punctuation, exact identifiers, numbers, negation, empty terms, operator-like injection, term caps, deterministic output and wrong revision. Real disposable PostgreSQL positive/negative, scope/version, SQL plan, HTTP, cancellation/timeouts and existing literal regressions. Test EN/RU/UK and mismatched vocabulary; report no-answer as raw retrieval only. Run `hatch --version` then configured workbench-api check/test/types and applicable lint/static checks; use repository Hatch commands rather than direct Python/pip. Browser checks only if touched. Record actual artifact paths and skips.

## M. Acceptance Criteria

- [ ] Native token and source evidence explains zero-hit cases or records unknown causes.
- [ ] Same OPEN queries compared across bounded candidates with paired evidence and latency; no holdout opened.
- [ ] Literal control and existing profile unchanged; all relevant regressions and safety checks pass.
- [ ] GO/NO-GO justified by measured useful lexical contribution, not hit count alone.
- [ ] If GO, separate immutable profile tested through actual API and ready for HYBRID-001; if NO-GO, explicit alternative route.

- [ ] Native cause reused, useful lexical contribution and hard-negative trade-off measured against matched cleaned Dense baseline; no empty fusion or artificial metric pass.

## N. Documentation / Migration / Compatibility / Rollback

Version new policy separately, document native ranking and limits. Disable new profile and retain existing FTS baseline for rollback. No schema migration assumed. Preserve immutable prior evidence and reports.

## O. Mandatory Completion Checklist

- [ ] Reinspect existing owners and actual QUALITY-001 failure handoff.
- [ ] Run bounded local lexical comparisons and source-grounded checks.
- [ ] Run applicable configured tests, preserve baseline and record actual evidence.
- [ ] Document GO/NO-GO, scope, affected paths and commit; mark complete only after evidence. No reviewer or external approval prerequisite.

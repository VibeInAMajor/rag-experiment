# TASK-RAG-DATASET-002 — Complete local ranking judgments and metric eligibility

**Created:** 2026-11-26  
**Updated:** 2026-11-26  
**Status:** PROPOSED — local evaluation correction; no new runtime tests executed  
**Priority:** P0  
**Dependencies:** DATASET-001 local delivery; QUALITY-001 completed diagnostic evidence  
**Repository snapshot inspected:** `472f550e8d91658228eb3ceeb1dfd2a79e2dbb47`

## A. Title

Make Primary Evidence Hit, MRR, precision, recall and graded nDCG measurable without confusing them with source-fact coverage.

## B. Context / Problem

QUALITY-001 found that historical OPEN fields named primary@k actually measure any complete known required fact. Separate judged primary evidence is absent, and sparse relevance labels cannot support exhaustive Recall or nDCG. The existing release thresholds therefore cannot be honestly evaluated. A better ranker alone cannot fix this measurement gap.

## C. Current Repository State

[QUALITY-001 actual report](../evidence/quality-2026-11-25/report.md) records 261 answerable and 45 no-answer OPEN cases, 87/15 correlated families, and a matched post-cleanup baseline of 194/261 any-fact@1, 255/261 any-fact@5, 237/261 all-facts@5 and 240/261 all-facts in 2048 source-content tokens. Separate primary hit and full Recall/nDCG are NOT_EVALUABLE_SPARSE_QRELS. Existing local source-span oracle and EvidenceCoverage are under `.local/evaluation-holdout/quality-check/`; raw captures are not in Git. The [legacy scorer](../../scripts/workbench_embedding_evaluate.py), blob b559aa6ca0b045fb9721a19521ad0b159c4d93bb, uses relevance.get(id, 0), appropriate for its fully judged fixed synthetic fixture, not sparse OPEN labels. Keep legacy behavior intact. DATASET-001's original delivery remains immutable.

## D. Goal

The coding agent produces a versioned, source-first judgment extension, explicitly defines metric eligibility and independently recomputes the existing baseline where possible. Make final evaluation possible without inventing negatives or changing questions to fit predictions.

## E. Scope

Agent-verified primary/support/explicit-negative judgments, original occurrence and alternative evidence mappings, bounded judgment pooling on OPEN, metric semantics, regression tests and frozen local holdout rubric.

## F. Non-Goals

No reviewer recruitment, special credentials/storage, new model/DB, production evaluation service, exhaustive corpus claim from a pooled sample, or retriever optimization. Do not open R2/ANSWER for tuning.

## G. Architecture / Boundaries

Reuse existing local EvidenceCoverage and evaluator owners; additive evaluation-only data and metric adapter. Runtime receives only questions and authorized sources; gold labels never influence ranking/context selection.

## H. Contracts / Interfaces / Data Model

Versioned query/family ID, source/version/hash, exact original locator or alternative set, grade (3 primary, 1 supporting, 0 explicitly judged negative; unknown separate), rationale, assessment status, mapped candidate occurrence, projection revision. A primary judgment is query-specific direct evidence, not any required facet by default. Define separate primary hit (at least one judged primary unit), primary recall (fraction of primary units), first-primary MRR, any-complete-fact and all-facts coverage. Multi-span evidence is measured as a union separately from singleton hit. Report judgment coverage, duplicate occurrence handling, denominators and metric scope.

## I. Repository Files / Components Impacted

Existing local dataset delivery, local ranking/coverage adapters and tests; sanitized evidence under tasks/evidence/. Existing synthetic evaluator/fixture and frozen historical reports must not change. No runtime API/UI or schema change.

## J. Implementation Requirements

1. Reuse preserved OPEN post-cleanup original sources, frozen queries, labels, chunk mappings and top-50 predictions. Define a source-first rubric before judging: direct primary, supporting, explicit negative, unknown. Verify complete facts, negation, version, code, numerical/attribution qualifiers and acceptable alternatives. Keep source-first labels independent of candidate rank; blind the agent to rank and arm where practical.
2. Build a bounded pooled set from existing judged anchors and unique returned occurrences across available baseline and subsequent approved tuning arms; judge all candidates at the reported cutoff for pooled ranking metrics. Map across rechunking using original locators; never assume a new chunk ID is negative. Deduplicate overlap/alternative evidence without erasing distinct occurrences. Record uncertain cases and stop rather than fabricate labels. If newly returned unjudged candidates appear, report incompleteness and assess them under the same frozen rubric before claiming comparable metrics.
3. Report standard graded nDCG/Recall only if the relevant universe and ideal ranking are justified; otherwise explicitly named pooled nDCG/pooled recall with pool definition, judged coverage, and limitations; do not pass exhaustive release gates with proxies. For source-level/facet recall, use the fixed known evidence universe with alternative sets; never count all translated variants as independent. Report primary Hit@1/5/10 and first-primary MRR where primary units are verified. Separate no-answer and service errors. Verify formulas against hand-computed examples.
4. Freeze new revision/digest, preserve all historical scores and labels; recompute post-cleanup baseline from saved predictions (no new full matrix). Compare old and new metrics by explicit name, not by overwriting historical primary fields. Use only OPEN for development. Prepare or apply the same rubric to the local R2 set only during final evaluation, after candidate freeze; no tuning on its judgments, questions or detailed outcomes. If the relevant universe remains incomplete, keep affected gate NOT_EVALUABLE.
5. Coordinate with QUALITY-001 pending source-fidelity diagnostic; use existing artifacts rather than duplicating the check. Agent performs all work autonomously; no new infrastructure. Record actual counts, uncertainty, unresolved judgments and remaining gate limitations.

## K. Security / Governance / Observability

Existing workspace/version/profile fences and local label exclusion apply. No credentials/raw vectors/source text in normal logs. Keep detailed judgments local; publish aggregate results and artifact pointers.

## L. Testing / Evaluation / Runtime Verification

Known ranking fixtures: primary vs support, unknown vs explicit negative, duplicate/alternative, multi-span, missing primary, no-answer, stale version, insufficient pool, cutoff and denominator. Independently verify arithmetic and unchanged legacy score. Run configured Hatch checks after hatch --version; reuse existing local UI evidence path for any new functional ingestion/retrieval if needed, do not repeat historical matrix. Record exact checks and outcomes.

## M. Acceptance Criteria

- [ ] OPEN judgment revision and coverage manifest exist; source references verified by the agent.
- [ ] Primary hit, primary recall, MRR and any-fact/all-facts metrics are explicitly separate; unknown is never silently grade zero.
- [ ] Pooled metrics and exhaustive metrics are distinguished; no unqualified release pass.
- [ ] Post-cleanup baseline rescored where supported and linked, legacy fixture unchanged; R2/ANSWER untouched during tuning.
- [ ] Existing scorer reused or extended compatibly and actual verification recorded.

## N. Documentation / Migration / Compatibility / Rollback

Additive local revision; retain prior oracle and reports. No runtime migration. Revert to old diagnostic metric names/scope if new judgment set fails validation, not a fake pass.

## O. Mandatory Completion Checklist

- [ ] Reinspect existing evaluator and local artifacts.
- [ ] Create, verify and freeze judgments and metric definitions.
- [ ] Run arithmetic/contract/regression checks and record evidence.
- [ ] Report unknowns, actual counts and handoff to QUALITY-002.

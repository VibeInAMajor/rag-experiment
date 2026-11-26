# TASK-RAG-DATASET-002 — Complete local ranking judgments and metric eligibility

**Created:** 2026-11-26  
**Updated:** 2026-11-26  
**Status:** COMPLETE — all 87 answerable OPEN families (261 queries), including the remaining 69, and all 15 no-answer families (45 queries) assessed; all 1241 baseline top-10 pooled occurrences judged, 0 UNKNOWN; 409 checks passed through UI. Current evidence: [full report](../evidence/dataset-ranking-full-open-2026-11-26/report.md), [full metrics](../evidence/dataset-ranking-full-open-2026-11-26/metrics.json). Historical partial evidence is preserved separately.
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

**Historical subset declaration (2026-11-26, before initial judgments; superseded below):** reuse the 18 unique answerable families selected by the completed source-fidelity diagnostic (three per domain), expanded to all their EN/RU/UK variants, plus the first three sorted OPEN no-answer families. This is a purposive diagnostic subset, not a representative population sample. Pool the unique original occurrences in the saved post-cleanup baseline top five for every included question, plus occurrences completing source-first primary anchors; future approved arms must extend/refreeze this pool before comparison. Verify source-first unit roles against original alternatives before showing candidate order. Hide rank/distance/arm in judgment UI; prior exposure during QUALITY-001 is disclosed, so independent blinding is not claimed. Grade every pooled occurrence explicitly or retain UNKNOWN; never fill missing labels with zero. Report pooled ranking metrics at @1/@5 only where the complete declared pool supports the ideal ranking; primary Hit/MRR @10 may be incomplete when positions 6–10 remain unjudged. Map verified original primary units across all saved top-50 candidates for separately named known-primary union/singleton coverage. Keep unsupported full-corpus gates NOT_EVALUABLE. New adapter, rubric, judgments, tests and raw evidence remain in the existing ignored local quality directory; publish sanitized aggregates under tasks/evidence/. No new production API/UI, model, DB or full matrix run.

**Full-OPEN continuation declaration (2026-11-26, before additional judgments):** the earlier 21-family declaration above is historical and does not close this task. Cover every one of the 87 answerable families, including the remaining 69, and retain all 15 OPEN no-answer families. Verify all three translations and source alternatives before candidate inspection. Preserve the earlier revision unchanged; inherit its verified roles/occurrences by exact identities only. Extend the pool to unique baseline top-10 occurrences for all 306 OPEN questions plus source-first primary anchors, so @1/@5/@10 judgments and eligibility are complete for this baseline. Source-relative known-unit recall and pooled ranking metrics remain explicitly different from exhaustive corpus relevance. Use the same rubric, original sources, unchanged saved predictions and local UI; no R2/ANSWER tuning, production service or new retrieval run. Completion requires full family/query coverage and no unassessed returned occurrence at any reported cutoff; ambiguous judgments remain explicit blockers, never manufactured negatives.

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

- [x] Full OPEN revision and coverage manifest: all 87 answerable / 15 no-answer families, 306 queries, 209 primary units, 1241 assessed occurrences, 0 UNKNOWN; all baseline top-10 positions judged.
- [x] Primary hit, primary recall, MRR and any-fact/all-facts metrics are explicitly separate; unknown is never silently grade zero.
- [x] Pooled metrics and exhaustive metrics are distinguished; no unqualified release pass.
- [x] Post-cleanup baseline rescored where supported and linked, legacy fixture unchanged; R2/ANSWER untouched during tuning, rubric prepared only.
- [x] Existing scorer reused behind completeness guards; 409 checks passed through UI, including independent arithmetic for all 261 answerable rankings at @1/@5/@10, complete coverage and preserved parent revision.

## N. Documentation / Migration / Compatibility / Rollback

Additive local revision; retain prior oracle and reports. No runtime migration. Revert to old diagnostic metric names/scope if new judgment set fails validation, not a fake pass.

## O. Mandatory Completion Checklist

- [x] Reinspect existing evaluator and local artifacts.
- [x] Create, verify and freeze judgments and metric definitions.
- [x] Run arithmetic/contract/regression checks and record evidence.
- [x] Report unknowns, actual counts and handoff to QUALITY-002.

## QUALITY-001 source-fidelity handoff — 2026-11-26

QUALITY-001 source-fidelity scope is complete as bounded diagnosis: 18/18 original-supported semantic units, coverage 18/219; 201 remain semantically unassessed. This is not primary/relevance gold completion, and does not turn source-span overlap into fully judged Recall/nDCG. Existing frozen labels are unchanged.

Evidence: [completed bounded source-fidelity assessment](../evidence/quality-2026-11-25/report.md); metrics.json → source_fidelity. This handoff does not implement or qualify this owner task.

## Historical partial delivery — 2026-11-26 (superseded)

The execution declaration above was recorded before new source/candidate judgments. Delivered 21 families / 63 queries (18 / 54 answerable; 3 / 9 no-answer), 45 distinct primary units, 4 support units, and 143 unique pooled occurrences: 36 primary, 39 support, 68 explicitly negative, 0 UNKNOWN within the declared pool. Source roles were verified against originals before the pool was shown; 24 labels use complete verified anchor mapping, 119 occurrences were individually inspected in rank-hidden local UI. Prior QUALITY-001 exposure is disclosed; no independent-blinding claim.

Frozen content digest: `29a8ddccdb18eca67b9558a92b809419f9e622ce24383a4d4d95daaf261f7e3b`. Raw manifests, source references, rationale, occurrence/version/hash mappings, case-level scores and `R2_RUBRIC.json` stay under the existing ignored `.local/evaluation-holdout/quality-check/runs/ranking-judgments-2026-11-26/`. The adapter and 34 new regression cases stay local as well. Only sanitized report/metrics and task/handoff documents are added to Git; no production evaluation code or new infrastructure.

On the 54 selected answerable cases: Primary Hit@1 42/54, @5 49/54; first-primary MRR@5 0.83148; pooled nDCG@5 0.78604; pooled recall@5 macro 0.78951; known-primary unit recall@5 macro 0.87037 / micro 116/135. Legacy any-fact@5 is 52/54 and all-required-facts@5 is 43/54, explicitly separate. At @10: 53 confirmed primary hits and one UNKNOWN; MRR determinable for 51 cases, not all 54. There are 231 unknown positions outside the judged pool across all 63 top-10 rankings; no pooled @10 claim. Full historical OPEN scores remain 194/261, 255/261, 237/261, 246/261, 240/261 under their original any-fact/all-fact/context definitions.

Checks: Hatch 1.18.2; **406 passed, 0 failures/errors/skips**, including independent nDCG/recall/first-primary arithmetic on every selected answerable baseline @1/@5, real multi-source union, strict grades, UNKNOWN, duplicate and stale-input refusal, unchanged dataset/legacy fixture and frozen output hashes. Tests and publication-safety audit ran through local UI. Safety audit: PASS, 2 files, 0 configured-secret/credential-URL/vector/private-field matches. Static Ruff format/F-E9 passed with `--no-cache`; full frontend/Haystack/DB/model suites were not run because runtime code did not change.

This historical partial delivery did not close the full task; the full delivery below supersedes its scope limitation. At that historical point 69 answerable families / 207 questions were not separately primary/relevance-judged. Full-corpus Recall/nDCG and affected release gates remain NOT_EVALUABLE; no-answer decisions and generation remain NOT_EVALUATED. No two-human-reviewer or separate-storage requirement was introduced.

## Completed full OPEN delivery — 2026-11-26

Completed the remaining 69 answerable families and 12 no-answer families through the existing local UI. All 102 families / 306 queries now have verified source roles; all 1241 pooled occurrences are explicitly assessed: 226 primary, 393 supporting, 622 negative, 0 UNKNOWN. Full coverage: 87/87 answerable families / 261 queries and 15/15 no-answer families / 45 queries. The declared pool covers all 3060 baseline top-10 positions. Of the labels, 143 were inherited unchanged, 102 added by complete verified primary-anchor mapping, and 996 individually judged through rank-hidden UI. Original source/version/content locators, translations, negation and material attribution were checked; no questions were rewritten to fit returned text.

Revision `source-first-ranking-open-r2-full`, digest `a87a8e7c1fef975111acb59d6579e125c2c8c2a5d7eb74c16e29f97c5827d6a4`; r2 denotes revision number, not holdout access. Current evidence: [full report](../evidence/dataset-ranking-full-open-2026-11-26/report.md), [metrics](../evidence/dataset-ranking-full-open-2026-11-26/metrics.json). Previous revision, labels and scores remain unchanged, with archived implementation hashes for historical reproducibility. Raw revision, judgments and tests remain in the existing ignored local quality directory, under `runs/ranking-judgments-full-open-2026-11-26/`; no production evaluation code was added.

Primary Hit@1 **209/261**, @5 **252/261**, @10 **257/261**; first-primary MRR@5 **0.87414**, @10 **0.87670**; pooled nDCG@5 **0.78748**, @10 **0.85343**. Pooled occurrence recall@5 **0.58477** and known-primary unit macro union recall@5 **0.94444** have different universes. All primary units recovered union@5 **243/261**, singleton@5 **237/261**. All reported cutoffs are eligible for all 261 answerable queries, with 0 unjudged returned positions. No-answer outcomes remain separate; no abstention/generation decisions are invented. Historical any-fact/all-facts/context scores remain unchanged. This rescoring measures unchanged saved predictions and does not claim a new retrieval improvement.

**409 passed, 0 failures/errors/skips, 43.41 s, exit 0**, executed through existing local code-check UI in Hatch 1.18.2 workbench-api. Independent formulas cover each actual answerable ranking @1/@5/@10; scope/position coverage, immutable parent/inherited judgments, frozen input/output hashes, UNKNOWN, stale identities, strict grades, multi-span union and legacy compatibility passed. Static Ruff format/F-E9 passed with `--no-cache`. Frontend/full Haystack/DB/model/live retrieval suites were not run because runtime code was not changed. Publication-safety audit is recorded with exact report/metrics hashes in the local audit artifact.

All requested OPEN families are complete; no remaining 69-family limitation applies. Exhaustive corpus relevance, robustness and final retrieval GO remain separate QUALITY-002 gates. R2/ANSWER were not opened; `R2_RUBRIC.json` is PREPARED_NOT_APPLIED. Future arms require additive pool assessment/refreeze, then frozen local final evaluation under the existing process. Agent subjectivity, prior exposure and shared-source family correlation remain disclosed limitations, not new user prerequisites.

### User-requested independent review — 2026-11-26

Prepared [local question-first human review](http://127.0.0.1:8018/independent-review) for all 102 OPEN families / 306 translations, with unannotated originals and randomized candidate order. Agent labels, gold answers, expected answerability, ranks and A/B identities are excluded from its responses. Reviewer answers are recorded before opening saved retrieval materials; exports remain separate from frozen gold. **PREPARED, NOT_REVIEWED**: no human assessments were entered by the agent, and prior agent completion is not retroactively called independent blind review. Prior exposure must be marked. Details and assignment manifest remain in the ignored local `runs/independent-open-review-2026-11-26/` directory.

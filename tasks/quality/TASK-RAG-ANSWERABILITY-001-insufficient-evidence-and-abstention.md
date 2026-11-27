# TASK-RAG-ANSWERABILITY-001 — Qualify insufficient-evidence detection and explicit abstention

**Created:** 2026-11-24  
**Updated:** 2026-11-28  
**Status:** PROPOSED — Phase A (offline diagnostic classification) is the immediate prerequisite for full OPEN audit reporting; Phase B (runtime policy qualification) remains gated by its existing dependencies. No implementation or runtime tests executed.  
**Priority:** P0  
**Dependencies:** Phase A: existing DATASET-002 three-family pilot and caller-side scorer; no runtime policy or new retrieval prerequisite. Phase B: [EVIDENCE-002](TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md), [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md), [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md); qualified selected exact/Hybrid/reranked path; no generation dependency.  
**Repository snapshot inspected:** `64087f2c63791d542016428a2592cb0c828909a4` (2026-11-28); earlier baseline `d6cba6580e308fbb37266b779dce5b6880309a44`  
**Target:** tasks/quality/TASK-RAG-ANSWERABILITY-001-insufficient-evidence-and-abstention.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Qualify insufficient-evidence detection and explicit abstention

## B. Context / Problem

All six baseline no-answer cases return neighbors. Cosine/reranker score is not calibrated confidence; no-answer can overlap low-score answerable queries. A system must distinguish no evidence, conflicting evidence, and retrieval failure.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md) documents forced neighbors and no-answer limitations. [API contracts](../../apps/workbench/contracts/schemas.py), [projection](../../apps/workbench/api/projection.py), [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py) expose raw ranking and typed service failures but no approved answerability decision. EVIDENCE-002 supplies bounded context pack.

## D. Goal

Implement and evaluate a bounded, provider-neutral evidence sufficiency decision before answer generation, with explicit abstention and distinct failure states.

## E. Scope

Calibrate decision on tuning data, choose minimal measurable heuristic or separately qualified local classifier if necessary, test no-answer/partial/contradictory cases and integrate typed readiness/decision.

## F. Non-Goals

No answer generator, no universal raw cosine threshold by assumption, no hidden model judge used as ground truth, no ANN or large ingestion.

## G. Architecture / Boundaries

Application policy owns decision; optional model adapter only after measured evidence and review. Existing errors remain errors, not no-answer.

## H. Contracts / Interfaces / Data Model

Phase A: separate frozen reference answerability, context sufficiency, diagnostic status, scope/coverage provenance, projection revision, operational status and reason. Phase B: local runtime support/abstention decision, reason codes, calibrated policy revision, evidence refs, separate transport failure/cancellation; no gold labels at runtime. False acceptance and false abstention apply to the actual decision under the declared rubric, not merely returned neighbors; actual generated claims are evaluated later. See the two-phase truth table in J.

## I. Repository Files / Components Impacted

Phase A: reuse the existing ignored local DATASET-002 evaluator/reporting owner and its tests; publish only additive sanitized evidence under tasks/evidence/. Phase B: reuse evaluation and retrieval contracts, existing profile governance, [API contracts](../../apps/workbench/contracts/schemas.py), [projection](../../apps/workbench/api/projection.py); add minimal decision owner and focused tests, no new global model service.

## J. Implementation Requirements

1. Freeze rubric: required evidence support and scope, partial facts, conflict handling, no-answer absence vs retrieval miss; distinguish gold answerability from actual retrieved support. Label both on reviewed tuning cases.
2. Compare empty-result and rank/score-margin baselines; assess calibrated decision with PR/ROC and separate risk by language, code, query class; use a bounded classifier only if cheaper rules fail and model is qualified. No gold labels at runtime.
3. Freeze policy and thresholds before held-out validation. Target false acceptance <=5%, false abstention <=5%, report numerator/denominator, Wilson/exact confidence intervals and trade-offs; ambiguous/conflicting cases separately. No fabricated per-query confidence.
4. Integrate explicit outcome and source refs while preserving service failure codes, no evidence fabrication. Reject stale/mismatched evidence; no automatic retries or broadened tenant access. If targets fail, report blocked and keep answer-generation gate closed.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Distribution-shift calibration — 2026-11-26

Follow [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md) section 4.6. Separate gold corpus answerability from actual selected-context sufficiency, partial facts, contradictions and transport failure; report outcome-specific denominators and false acceptance/abstention by family, language and OOD stress. Fit/calibrate only on OPEN sub-split, freeze before validation. If a genuine probability of sufficient context is available, report Brier, predeclared-bin ECE/reliability, PR/ROC and risk-coverage ID vs OOD with family-clustered uncertainty; otherwise probability metrics NOT_EVALUABLE. Raw cosine/reranker scores and model self-reported confidence are not probabilities. Do not publish invented confidence.

### Measured no-answer handoff — 2026-11-26

The [completed QUALITY-001 report](../evidence/quality-2026-11-25/report.md) confirms all 45 OPEN no-answer queries return dense neighbors, including after cleanup; no sufficiency classifier or generator was evaluated. Reuse local absence judgments, near-matches and captured ranks/distances to compare empty-result and score/margin baselines, then source-evidence sufficiency only if needed using a qualified local model. Separate corpus answerability from retrieved-context sufficiency and partial/conflicting/error outcomes. At 45 no-answer localized rows, <=5% observed false acceptance permits at most 2; at 261 answerable rows <=5% observed false abstention permits at most 13, provided all rows are evaluable and denominators match those definitions. Report family counts and uncertainty; no automatic calibration claim from correlated translations. Use final R2 only once candidate/policy frozen. No new functional runtime service or human reviewer required; use existing local UI/Workbench checks.

### Independent sufficiency labels and runtime boundary — 2026-11-27

Use the reopened [DATASET-002](TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md) and [MAF Semantic Judge](../maf/TASK-MAF-002-semantic-judge-agent.md) for offline source-scope and actual context sufficiency assessments. EXT-NA-003 is a mandatory regression: redundancy descriptions do not establish the exact EUR monthly invoice of invoice-birch-902. Distinguish corpus-level absence, candidate-level irrelevance, missing required fact, partial/conflicting evidence and operational error. No-answer gold requires independently checked original corpus scope, not a failure of retrieval to find evidence. External judge can supply evaluated labels, but may not stand in for the runtime answerability decision or be the only evidence of its correctness; calibrate and test the actual selected local decision policy, keeping existing false-acceptance/abstention gates and eligible denominators. No online MAF dependency, no threshold inferred from raw similarity, no grading transport failures as unanswerable.

### Two-phase execution and diagnostic classification — 2026-11-28

The [full-input pilot](../evidence/dataset-semantic-pilot-full-2026-11-28/report.md) reports all three Azure variants as `insufficient`, despite the [first pilot](../evidence/dataset-semantic-pilot-2026-11-27/report.md) recording a scoped absence check of all 31 eligible originals. All 12 Azure passages scored zero. Six Austen/Ruskin contexts were sufficient. The raw context verdict is correct under [the existing judge contract](../../apps/maf/SEMANTIC_JUDGE.md): an empty required-fact list cannot establish sufficiency. This is a reporting/interpretation defect, not evidence of a retrieval miss or of a prompt/schema defect.

**Phase A — execute before continuing the full OPEN audit.** Reuse the existing local DATASET-002 evaluation/report owner under `.local/evaluation-holdout/quality-check/`. Implement one deterministic projection over verified reference answerability, original-corpus scope/coverage evidence, admitted `judge_context` verdict and operational state. Do not invoke another LLM, change MAF prompts/schemas, alter original grades, invent source completeness, or write a second evaluator. Freeze projection revision and truth table before replay. Consume the preserved nine pilot packs; no new retrieval/generation call is needed. The full OPEN audit may produce the new labels after Phase A passes; Phase A MUST NOT depend on completion of that audit.

Preserve raw `reference.answerability` and `sufficiency` and distinguish corpus answerability from context support, diagnostic classification and runtime decision. Reuse existing field naming/DTO conventions. The following names define diagnostic semantics; use a single canonical representation.

| Reference/coverage | Admitted context result | Diagnostic status |
| --- | --- | --- |
| Verified answerable | sufficient | `ANSWER_SUPPORTED` |
| Verified answerable | partial | `ANSWER_PARTIALLY_SUPPORTED` |
| Verified answerable | insufficient | `RETRIEVAL_MISS` |
| Verified absence in complete eligible scope | insufficient, no independently verified answer support | `EXPECTED_NO_ANSWER` |
| Verified absence reference but independently verified scoped answer support | any | `UNEXPECTED_ANSWER_SUPPORT` — quarantine reference/evidence and investigate; do not automatically accept or rewrite gold |
| Not found in supplied excerpts only, incomplete eligible scope, or unknown answerability | insufficient | `UNKNOWN` — no corpus-wide absence inference |
| Partially answerable reference | any nonconflicting verdict | `REFERENCE_PARTIAL` — report known-fact coverage separately; never claim complete answer from only known subset |
| Any reference | conflicting | `CONFLICTING_EVIDENCE` |
| Any reference | unknown or unresolved/inconsistent combination | `UNKNOWN` |
| Not invoked / ineligible | no verdict | `NOT_EVALUATED` |
| Technical failure, invalid output, cancellation or budget rejection | no admitted verdict | `EVALUATION_ERROR` with original typed reason |

A missing/invalid verdict MUST NOT become expected absence; check operational state first. A verified no-answer reference has no required answer facts; the existing validator rejects a sufficient verdict for that state. Do not assume that `judge_context` can positively validate a novel fact absent from such a reference. Independent source-first verification is required for `UNEXPECTED_ANSWER_SUPPORT`; a conflicting/unknown verdict alone is not proof. Missing source proof, unresolved disagreement, and partial coverage remain visible. Grade-zero topical neighbors alone do not imply corpus absence. No-answer in the verified corpus is expected success for absence-of-support evaluation, not proof of a good general ranking, runtime abstention, or generated-answer quality.

Render the Azure regression as **No answer in the verified corpus / Expected no answer**, with scope and raw `insufficient` visible as technical detail. Render the six answerable pilot contexts as Answer supported. Preserve historical reports; produce an additive projected report with separate answerable/no-answer denominators and explicit UNKNOWN/error counts. Do not count translated variants as independent families. Do not publish a general release PASS from this pilot.

**Phase B — actual runtime answerability policy.** Retain existing EVIDENCE-002, corrected reference/context labels, selected retrieval profile and tuning/holdout dependencies. Runtime receives only authorized selected evidence, query, provenance and qualified local decision policy, never gold reference or expected label. It can return support/partial/no answer in supplied evidence/conflict/unknown, with abstention recommendation and separate typed failures; it cannot claim corpus-wide absence unless a distinct caller-owned complete-scope verification proves it. No external MAF dependency and no hard-coded similarity threshold. Preserve existing 5% gates, separate false acceptance of an unsupported answer-admission decision from actual generation hallucinations, and defer actual generated-answer abstention measurement to QUALITY-003.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No unsupported certainty or privileged source disclosure; prompt-injected evidence cannot authorize actions.

## L. Testing / Evaluation / Runtime Verification

Phase A: table-driven deterministic tests of every mapping and precedence rule, exact source-scope evidence, invalid/missing results, and multilingual pilot replay with preserved raw verdicts; no credentials/provider required. Record case/family denominators, report revision, commands and evidence. Phase B uses the existing runtime checks below.

No-answer, partial answer, hard negative, contradictory sources, high cosine wrong match, low cosine correct match, empty corpus, 429/503/504 and cancellation, calibration leakage and decision regression.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Phase A projection has an explicit revision and exhaustive table-driven tests, including operational error, incomplete scope, partial reference, conflict, unexpected verified support and all three Azure language variants.
- [ ] Additive pilot replay reports 6/6 answerable contexts as ANSWER_SUPPORTED and 3/3 verified Azure variants as EXPECTED_NO_ANSWER (one family); raw judge results and historical evidence remain unchanged.
- [ ] Full OPEN reporting is not started until Phase A passes; Phase B remains gated by corrected labels and EVIDENCE-002. Do not mark the overall task COMPLETE at Phase A alone.

- [ ] Real reviewed tuning evidence and fixed thresholds with error trade-off.
- [ ] Explicit insufficient/conflicting vs transport failure outcome and safe provenance.
- [ ] Target <=5% false acceptance/abstention demonstrated on tuning or blocked; final independent gate belongs QUALITY-002.

- [ ] Calibration and OOD outcomes reported with exact denominators, fixed policy, uncertainty and probability availability; existing <=5% false acceptance/abstention targets retained.

- [ ] Actual local answerability policy evaluated against eligible source-first and semantic sufficiency labels; invoice regression and unknown/error distinction verified; judge not a runtime dependency.

## N. Documentation / Migration / Compatibility / Rollback

Version decision policy; if unqualified, do not enable grounded generation. Preserve underlying retrieval capability and label raw ranks as such.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.


## QUALITY-001 failure-localization evidence

QUALITY-001 OPEN V2 handoff (2026-11-25): 45 no-answer questions / 15 translated families have original automated corpus-absence records, captured neighbors, negative-span overlap and distance margins on every arm (360 observations). No sufficiency decision executed; neighbor presence is not false acceptance, zero lexical results are not abstention. Inspect the original absence rubric and near-neighbors through an authorized UI case review; semantic sufficiency remains UNKNOWN. No cosine threshold was tuned or qualified.

Evidence: [V2 report](../evidence/quality-2026-11-25/report.md). Raw per-query IDs, locators, alternative sets and next probes remain in the ignored existing V2 run; sanitized counts are in metrics.json → failure_localization.
## QUALITY-001 UI completion evidence — 2026-11-26

Two additional matched UI phases each submit all 45 no-answer questions; forced neighbors observed on 45/45. No answerability decision or generation executed. Native FTS zeros are traced to actual lexical AND conditions and cannot serve as an abstention label. Final holdout remains unused.

Evidence: [completed UI comparison](../evidence/quality-2026-11-25/report.md); metrics.json → ui_completion. Raw case details remain ignored locally.

## QUALITY-001 source-fidelity handoff — 2026-11-26

Source-supported gold does not imply support by the actual pack: 18 semantic cases contain 15 supported, 1 partial and 2 absent. Consume context sufficiency separately from original corpus answerability. No sufficiency threshold or false-acceptance metric was measured.

Evidence: [completed bounded source-fidelity assessment](../evidence/quality-2026-11-25/report.md); metrics.json → source_fidelity. This handoff does not implement or qualify this owner task.

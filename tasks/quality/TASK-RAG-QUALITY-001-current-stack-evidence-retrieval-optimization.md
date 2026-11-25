# TASK-RAG-QUALITY-001 — Reproduce and improve primary-evidence retrieval using the qualified current stack

**Created:** 2026-11-24  
**Updated:** 2026-11-26  
**Status:** IN PROGRESS — Windows ledger reliability fix committed and verified; 152 local checks and 108 backend checks pass; patched 52-case replay passed; uniform OPEN V2 matrix running

**Priority:** P0  
**Dependencies:** [DENSE-001](../../tasks/completed/TASK-RAG-DENSE-001-live-dense-retrieval-and-exact-cosine-baseline.md), completed EMBED-001/002, INDEX-001, PROFILE-001, CHUNK-001/002, CONFIG-001, RAG-002; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md) for reviewed dataset; [TPM-001](../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) valid current local admission.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44; continuation base fde9fbe

**Implementation commits:** `9955252728b3653deb0b5e63339c6ed7c8802ccf` (instruction-bound calibration), `a44c9f9048130c7dcf8081dcbf4f91e6d9a80645` (bounded Windows atomic replacement recovery)

**Target:** tasks/quality/TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Reproduce and improve primary-evidence retrieval using the qualified current stack

## B. Context / Problem

Correct exact SQL is not sufficient evidence quality. The baseline ranks support ahead of primary evidence and misses two primary labels at top five. Optimize only existing model/input/chunk policies before introducing new components.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md): 102 active vectors, 52 queries (46 answerable and six no-answer), two relevant labels per answerable case; primary@1 31/46 (0.673913), primary@5 44/46 (0.956522), Recall@5 86/92 (0.934783), MRR@10 0.942029, nDCG@5 0.845519 (preserved embedding evidence); all six no-answer cases return neighbors. Exact SQL/HTTP agreement is demonstrated, independent production relevance is not. [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) owns score_ranking/evaluate_query and fixed-span fixtures; [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) owns real HTTP/SQL identity and latency checks but currently loads its fixed fixture. [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py) and [vector_search_snapshot](../../apps/workbench/postgres/postgres.py) now implement Live exact; [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py) supports declared future modes but only approved lexical/exact are executable. [EmbeddingProfile / prepare_embedding_request](../../apps/workbench/embedding/embedding.py), [embedding_candidate_input](../../apps/workbench/embedding/embedding_ingestion.py), [apps/workbench/document_processing.yaml](../../apps/workbench/document_processing.yaml) own input and chunk policy. Existing fixture max 100 queries and fixed chunk IDs do not support large reviewed facets/rechunking without bounded schema evolution.

**Observed OPEN V2 failures (DATASET-001 report, 2026-11-25):** [report](../evidence/dataset-2026-11-24/report.md) and [metrics](../evidence/dataset-2026-11-24/metrics.json) record 31 originals, 144 published representations, 1080 active embedded chunks, 306 queries (261 answerable, 45 no-answer), and 306/306 Dense HTTP/SQL agreements. Dense any-complete-fact@1/5/10 = 176/261, 246/261, 252/261; all-required-facts@1/5/10 = 136/261, 222/261, 232/261. Art any-fact@1 = 13/24 and all-facts@5/10 = 17/24 and 18/24; Literature = 32/60, 51/60, 54/60; Kubernetes = 37/57, 45/57, 46/57. These are source-facet coverage, NOT Primary Evidence Hit or generated-answer accuracy. FTS returned zero results for 306/306 natural queries while native literal controls passed 10/10; `apps/workbench/postgres/postgres.py` uses `plainto_tsquery('simple', query)` (all-lexeme AND). Dense returned neighbors for all 45 no-answer cases; no sufficiency decision or generation was executed. Five Markdown HTTP 413 refusals were handled by source-only TXT windows; mapping and boundary effects require case-level verification, not an assumption of parser failure. This is the prior DATASET-001 baseline, not a result of the ongoing eight-arm experiment.

## D. Goal

Recompute preserved baseline independently, then run paired exact and FTS baselines and bounded current-stack tuning on DATASET-001 approved tuning data; select minimal immutable candidate or report INSUFFICIENT_WITH_CURRENT_STACK with failure attribution. This is a diagnostic decision, not final release qualification. Before completion, establish an evidence-backed failure location for each failed OPEN case, quantify affected cohorts, and hand off concrete fixes to existing component owners. Unknown causes must remain explicit.

## E. Scope

Baseline reproduction, real parsing/chunking and governed embedding of small reviewed originals, fixed query-instruction and existing chunk policy grid, independent source-span scoring, lexical control, measured latency and regression evidence.

**Runtime reliability amendment (2026-11-25):** two actual long-chunk attempts were refused by the existing governor after 125 and 246 completed HTTP/SQL pairs. An isolated exercise of its unchanged atomic ledger writer reproduced Windows `PermissionError` / `winerror=5` at `Path.replace` (6872 and 713 writes before failure). Include a narrow, bounded retry of the same fsynced temporary-file replacement for Windows access/sharing violations in the existing capacity owner. Preserve atomic publication, charged usage, shared lease and fail-closed quarantine for permanent failure. This does not add an application/API capability or alter ranking/admission policy. Restart all scored arms together on a new v2 execution snapshot; preserve v1 artifacts as interrupted/historical evidence.

## F. Non-Goals

No Hybrid/BM25 integration, cross-encoder, ANN, answerability implementation or generation. Offline diagnostics of these downstream gaps are in scope; implementing their fixes is not. No new model or arbitrary threshold, no large-file work. No rewriting immutable baseline or original fixture.

## G. Architecture / Boundaries

Evaluation reuses existing scorer and Live evaluator; ingestion uses existing qualified parsers/chunkers/worker; retrieval uses exact and FTS ports. DATASET-001 owns source labels; QUALITY-002 owns locked final gate. CHUNK-004 owns advanced chunk strategies, not duplicated here.

## H. Contracts / Interfaces / Data Model

Versioned dataset/fixture digest, original evidence facets/grades and source locators; immutable candidate profile/input/chunk revision; run manifests, per-case ranks and latency, status PASS/FAIL/BLOCKED/NOT_EVALUABLE. Distinguish primary hit, primary recall, relevant recall, first-any vs first-primary MRR and graded nDCG; with two relevant labels Recall@1 max 0.5. No-answer metrics separate. Map rechunked outputs back to source spans, count each facet once and report unjudged results.

## I. Repository Files / Components Impacted

**Execution amendment (2026-11-25):** DATASET-001's completed local handoff is recorded in [its actual report](../evidence/dataset-2026-11-24/report.md), despite older PROPOSED headers. Reuse the existing ignored `.local/evaluation-holdout/quality-check/rag_quality/` adapters and source-coverage scorer; preserve their original artifacts. Experiment code/raw predictions remain local; only sanitized reports/metrics and this task are repository deliverables. Existing capacity benchmark ownership may receive a backward-compatible internal instruction-profile qualification parameter, because a changed query instruction must have its own measured profile-bound admission rather than a copied fingerprint. No application, public API, UI, model-provider or CI capability change is authorized by this amendment.

The reliability amendment additionally touches `apps/workbench/embedding/embedding_capacity.py` and its existing `tests/test_embedding_capacity.py`, plus a focused bugfix release note. Do not introduce a second ledger writer or delete/reset real admission state. Local exception-only diagnostics/probes remain ignored. The bounded Windows retry must be tested for successful recovery, permanent failure with preserved old ledger and quarantine, and immediate refusal of unrelated errors before the new uniform experiment snapshot starts.

[embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), [52-case fixture](../../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json), [EmbeddingProfile / prepare_embedding_request](../../apps/workbench/embedding/embedding.py), [embedding_candidate_input](../../apps/workbench/embedding/embedding_ingestion.py), [apps/workbench/document_processing.yaml](../../apps/workbench/document_processing.yaml), existing embedding/retrieval tests and qualified ingestion owners. Extend existing runner(s) without a competing scorer; preserve exact/lexical contracts and original 52-case fixture. No migrations or UI changes unless separately scoped.

**Failure-analysis amendment (2026-11-25):** reuse existing local predictions, source mappings, ingestion records, oracle bindings, score and timing artifacts in `.local/evaluation-holdout/quality-check/`. Extend the same local diagnostic runner only when evidence is missing. Do not create another evaluator, persistent telemetry service, separate reviewer workflow or production component. Detailed case evidence remains in the existing ignored local run directory; publish a sanitized Markdown report and aggregate counts under `tasks/evidence/`.

## J. Implementation Requirements

**External-domain baseline requirement:** in addition to the preserved synthetic regression and repository-specific dataset, execute the [external multidisciplinary V1 protocol](dataset/EXTERNAL_EVALUATION_PROTOCOL_V1.md) on all admitted EN/RU/UK query variants after DATASET-001 review. Use actual corpus Markdown ingestion, real governed embeddings and existing HTTP/SQL evaluator; report separately by domain, query intent, language and family, including exact formulas/numbers/code and required facets. Do not treat translations as independent samples, tune on local held-out split or index answer keys. A failure in external evaluation must be explicitly attributed; no quality claim based solely on internal project documents.


1. Independently recompute all baseline metrics from preserved reports, including primary misses checksum-en and code-digest at rank six, hard-negative and six no-answer cases. Reproduce on disposable DB with actual model and exact HTTP/SQL; preserve 52-case regression fixture.
2. Use DATASET-001 agent-verified split; use only its tuning split for iterative decisions. Frozen local holdout remains untouched until QUALITY-002. Extend bounded loader/scorer for original spans, grade 0/1/3, facets, unjudged, explicit split, no-answer and provenance; maintain legacy fixture behavior.
3. Compare same reviewed originals under actual supported parsing/chunking, FTS and exact Dense; report pre-cut candidate coverage and final fixed token budget. Test one variable at a time: Qwen generic vs bounded technical/code instructions, supported chunk lengths 384/500/768 and 0/10/15% overlap where accepted, heading inclusion. Preserve query/document input contract and re-embed/requalify if fingerprint changes; no mismatched vector reuse.
4. Record per-case failures and paired group-level relevance, primary hit, all facets, nDCG, hard negatives, first-primary MRR, p50/p95/p99 embedding/SQL/HTTP, token cost, reembedding churn; compare identical final context budget and report clustered uncertainty. Do not infer answerability from cosine threshold.
5. Target Primary Evidence Hit@1 >=0.95, Primary Evidence Hit@5 >=0.98, relevant evidence Recall@5 >=0.95, graded nDCG@5 >=0.95, All Required Facets@5 >=0.95; critical adequately sized cohorts Primary@5 >=0.95. Predeclared p95 <=1.20x identical baseline load unless an explicitly approved cost/latency trade-off is recorded. Zero observed unauthorized/stale/wrong-profile/source-hash/citation integrity violations. These are proposed point targets, not achieved results. Use existing gold regression targets 44/46 primary@1 and 46/46 primary@5 only diagnostically. Record source-verified tuning results, not release holdout scores. Route exact-term failures to HYBRID/BM25, ranking failures to RERANK, evidence-selection errors to EVIDENCE-002, no-answer to ANSWERABILITY, structural errors to CHUNK-004. A measured NO-GO is valid task outcome; final gate remains blocked if insufficient.

### J.1 Mandatory per-query failure localization (after the existing eight-arm matrix)

Do not restart, expand or change the predeclared matrix solely for this amendment. Finish and preserve the comparable V2 runs; reuse captured predictions for offline analysis. If a targeted probe needs real model/HTTP/SQL execution, run only the missing evidence on the same pinned configuration and record it separately from scored arms. No ANSWER or Retrieval-R2 holdout access. No label-aware runtime changes.

1. For all 306 OPEN query IDs on every completed arm, automatically record execution status and known-facet/primary coverage at raw candidate @1/5/10 and after the fixed context selection. Preserve explicit unknowns for incomplete qrels. Compare baseline and selected candidate case by case (improved, unchanged, regressed, not evaluable). Investigate all baseline or selected-candidate failures, including all 45 no-answer cases; group related EN/RU/UK variants for inspection but keep individual outcomes.
2. Trace each missing mandatory fact or primary label from original locator/hash through parsed representation, source-only view, chunk boundaries, persisted active version and embedding coverage, actual candidate ranks, and final context. Compare coverage of valid alternative evidence sets; distinguish one complete span from a fact requiring a union of spans. Reuse exact source mapping; inspect whether the union of all eligible indexed chunks can cover each missing facet and whether any single chunk can cover it. Do not treat a union requiring multiple chunks as a single-chunk ranking failure.
3. For answerable failures where indexed evidence exists but top-10 is insufficient, use a bounded targeted exact top-20/top-50 diagnostic on the same profile/corpus, with actual ranks and coverage, if the saved artifacts cannot establish rank. Preserve raw ranked candidates and selected context separately. Compute candidate ceiling at each cutoff; reranking can only improve ordering of existing candidates. If all eligible chunks cannot cover an anchor, investigate ingestion/mapping before ranking.
4. For lexical failures, verify query lexemes using native PostgreSQL tokenization, actual AND tsquery, matching source lexemes and stored search_vector. Contrast original question, literal positive control and a bounded read-only subset/OR term probe where needed; distinguish lexical mismatch, cross-language vocabulary, conjunction restriction and index/provenance defect. These are diagnostics, not a changed approved lexical profile or replacement benchmark. FTS returning no results on an unanswerable query does not establish successful abstention.
5. For no-answer cases, verify the original authorized-corpus label and inspect whether returned evidence actually supports the question. Record raw neighbor presence, misleading near-matches, score/rank margins where available, contradictions/partial evidence and overlap with answerable hard cases. Do not report false acceptance/abstention without an actual sufficiency decision. Mark answerability as NOT_IMPLEMENTED / NOT_EVALUATED and hand off to ANSWERABILITY-001. Generation is likewise NOT_EVALUATED until its own task; do not fabricate hallucination or answer accuracy measurements.
6. Report Art, Literature and Kubernetes separately (including language and source family); do not mask regressions with the aggregate or create domain-specific production routing. Test hypotheses against the actual source representation and paired arms: paragraph/section boundary losses, source-only window effects, title/heading context, entity/alias mismatch, distributed facts, ranking of near-topic passages and sparse alternative labels. Record the probe, result and affected IDs for each supported conclusion.

Use the following offline failure taxonomy. A case may have several findings; assign one earliest demonstrated actionable cause per missing facet (or UNKNOWN), preserve contributing causes, and separately report downstream gaps. These are diagnostic labels, not new production API states.

| Failure location | Evidence required | Existing owner / next action |
| --- | --- | --- |
| Source or gold label | Wrong/missing original anchor, ambiguous answer, or a source-supported alternative omitted by sparse qrels | DATASET-001; version correction separately, never rewrite frozen labels to improve a score |
| Parser / source representation | Original evidence exists but is absent or changed in parsed/source-only representation; demonstrate offset or text mismatch | Existing parsing/ingestion owner |
| Chunk structure | Evidence preserved in representation but omitted or split across chunks; show boundaries, overlap and attainable union/single-chunk coverage | Existing chunk policy; CHUNK-004 for advanced structure |
| Index / embedding coverage | Eligible chunk absent, stale, wrong profile/version or missing embedding; verify persisted identity and coverage | Existing ingestion/index/embedding owner |
| Candidate retrieval | Eligible indexed evidence exists but is outside the bounded candidate pool; show actual rank or bounded search result | Existing retrieval owner; HYBRID-001/BM25 feasibility where applicable |
| Ranking | Primary evidence or complete fact is in the pool but below target rank; show competing results and grades where judged | RERANK-001; qualified integration only after GO |
| Lexical query policy | Native token/control evidence shows restrictive query or term mismatch rather than broken storage | Existing lexical owner / HYBRID-001; benchmark lexical policy before fusion; BM25 only if justified |
| Context selection | Raw candidates cover required evidence but final token-budget selection loses it; show discarded ranges and token cost | EVIDENCE-002 |
| Answerability gap | No sufficient evidence, but raw neighbors present; no qualified decision in this experiment | ANSWERABILITY-001; not an observed false acceptance without a decision |
| Generation gap | No actual generation or claim evaluation in this experiment | GENERATION-001 / QUALITY-003; NOT_EVALUATED |
| Operational / unknown | Actual execution error, missing artifact or inconclusive trace | Existing failing component; record error or missing evidence and smallest next probe |

For every investigated failure record query/family/domain/language, arm and profile revision, missing fact IDs, original source locators, attainable indexed coverage, ranks/coverage by cutoff, context coverage, failure category, confidence in attribution (confirmed/inconclusive/not evaluated), evidence pointer, and next owner. Keep raw source/question content in local artifacts, not ordinary application logs.

Deliver a local `FAILURE_ANALYSIS.md` (and existing machine-readable diagnostic artifacts if needed), plus a sanitized repository summary in the uniform V2 report: reconciled counts by failure category, arm, domain and language; distinct affected queries and facts; paired improvements/regressions; explicit unknown and not-evaluated counts; priority and recommended experiment for each existing owner. Separate candidate misses, ranking misses and context losses; overlapping diagnostic categories must not be summed as distinct cases. Report Primary Evidence Hit only where supported by judged primary labels, separately from any-complete-fact and all-required-facts coverage. Preserve the original eight-arm budgets and targets; do not claim sparse coverage metrics establish exhaustive Recall/nDCG.

Completion is a measured decision: select a justified current-stack candidate or report INSUFFICIENT_WITH_CURRENT_STACK with concrete handoff. Do not require all downstream failures to be fixed inside this task, and do not mark the task complete with aggregate percentages alone.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Source-fidelity diagnostic (Faithfulness-Plus extraction half) — 2026-11-26

Apply section 4.2 of the [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md) to the existing J.1 failure inventory: distinguish exact source/locator integrity, semantic qualifier loss, missing facets and unknown judgments. Report verified source-supported evidence units / assessed units, assessment coverage and invalid identity/locator counts, with examples and evidence pointers. Use the existing frozen original/representation/chunk mappings, and inspect actual context selected. No new scored arms, corpus perturbation or generation required here; answer faithfulness and NAG remain NOT_EVALUATED. Finish the current uniform matrix first.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No unreviewed tuning on final holdout; no provider change or new public capability.

## L. Testing / Evaluation / Runtime Verification

**Predeclared local comparison (2026-11-25):** OPEN V2 only (31 originals, 306 translated cases / 102 families), without reading ANSWER or Retrieval-R2 labels. Eight arms: existing 500/50 generic baseline; bounded global technical instruction; bounded global code instruction; 384/38 and 768/77 token policies; 500/0 and 500/75 overlap; existing heading-path input with equivalent native 8192-token admission. Change one semantic policy at a time; record integer overlap rounding and input/representation differences. Fixed candidate top-10 and fixed 2048 `o200k_base` source-content token prefix budget; no label-aware evidence selection. Use a fresh owned DB and real governed re-embedding per arm; new instruction fingerprints require separate fresh calibration/qualification. Baseline source/facet coverage remains sparse: unjudged results stay unknown, full graded nDCG/relevance recall are NOT_EVALUABLE unless exhaustively justified. Family-clustered uncertainty and language/domain/intent groups remain separate; no translation counted as independent sample. No candidate is promoted by this experiment.

Independent metric reference, source-span/facet mapping and unjudged semantics, profile drift, input/Unicode, wrong source/tenant/version, partial coverage, provider outage, ranking and latency regression.

The v1 scored baseline/short-chunk results are historical after the reliability fix. V2 must rerun all eight arms against identical patched owners; retain the original predeclared candidate grid, source/query split, selector and budget. Perform a real-filesystem isolated ledger stress replay before model experiments, and preserve the two pre-fix failures with exact OS category and cleanup evidence.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

Additional diagnostic checks: test the failure classifier/aggregation with known source-mapping, split-fact, missing-index, rank, context-budget, sparse-label and operational-error examples; verify no-answer rows are not counted as answerable retrieval misses. Reconcile case-level counts to the original scoring denominators; verify baseline and selected candidate comparisons are paired. Reuse existing local tests and actual artifacts; no fresh full matrix solely for report generation.

## M. Acceptance Criteria

- [ ] External V1 actual API/model/SQL baseline and paired evaluation reports linked, separately by domain/language/family; no source/answer leakage.

- [x] Original 52-case regression preserved and actual metrics independently reproduced. Independent arithmetic and a fresh actual model/HTTP/SQL replay after the writer fix completed on 2026-11-25 under `.local/evaluation-holdout/quality-check/runs/current-stack-2026-11-25-v2/`; historical V1 artifacts are preserved. Public report follows the uniform paired run.
- [ ] Reviewed tuning set, real ingestion/embedding and paired candidate reports with fixed token budget and all required metrics.
- [ ] Best candidate or explicit insufficient-current-stack verdict, per-case failures and next-owner handoff.
- [ ] No false quality/production claim; final holdout not used for tuning and all integrity gates pass.

- [ ] All completed OPEN arms have a reconciled 306-case diagnostic inventory; every baseline/selected-candidate failure is attributed with evidence or explicitly UNKNOWN and a next probe. All 45 no-answer cases have a diagnostic disposition without invented decision metrics.
- [ ] Art, Literature and Kubernetes have separate per-case failure breakdowns, paired arm comparisons and demonstrated or rejected hypotheses.
- [ ] Candidate ceiling, rank losses and final context losses are distinguished; lexical zero-result cause is verified with native token/control evidence.
- [ ] Local failure analysis and sanitized aggregate report are linked; existing owner tasks receive actionable handoff with affected counts and evidence references, without adding duplicate implementations or opening holdout.

- [ ] Source-fidelity counts and assessment coverage are reported from existing OPEN artifacts; extraction failures and context omissions are distinct; no generation claim or matrix restart.

## N. Documentation / Migration / Compatibility / Rollback

Use tasks/evidence/ for actual reports; retain pinned old profile/generation and roll back explicitly. No original evidence overwrite. Current exact Live stays available; promotion requires fresh qualified profile and subsequent release gate.

## O. Mandatory Completion Checklist

- [x] Reinspect source and dependencies; record reused owners and amended scope if needed. Scope amendments and the existing ingestion/scoring/capacity/HTTP/SQL owners are recorded above.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

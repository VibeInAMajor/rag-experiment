# TASK-RAG-QUALITY-003 — Evaluate grounded answer correctness, completeness and citation support

**Created:** 2026-11-24  
**Updated:** 2026-11-26  
**Status:** BLOCKED — grounded generation implementation required  
**Priority:** P0  
**Dependencies:** [GENERATION-001](TASK-RAG-GENERATION-001-grounded-answer-generation.md) internal implementation, [QUALITY-002](TASK-RAG-QUALITY-002-retrieval-release-gate-and-regression.md) GO, [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md); source-verified answer rubric and local holdout.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-QUALITY-003-grounded-answer-correctness-evaluation.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Evaluate grounded answer correctness, completeness and citation support

## B. Context / Problem

A correct retrieval can still produce unsupported statements, missing details or wrong citations. Retrieval recall is not answer accuracy.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md) establishes retrieval only. Existing [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) and [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) measure ranking/provenance, not generated factual claims. No independently qualified answer evaluator exists.

## D. Goal

Local development only: the coding agent prepares and verifies reference answers without human reviewers or external approval. No enterprise certification claim.

Measure grounded answer quality using reviewed original evidence and expected facts; decide whether generated answers can be released for local supported scope.

## E. Scope

Agent-verified answer rubric, claim-to-evidence support, required-facet completeness, numeric/code/version correctness, citation precision/coverage, abstention and latency; repeatability regression.

## F. Non-Goals

No LLM-as-judge as sole truth, no production SLA, no retrieval metric mislabeled answer correctness or unsupported modality.

## G. Architecture / Boundaries

Evaluation extends current evidence/run manifest owner, separate answer scorer for distinct responsibility. The coding agent verifies claims against original sources; runtime remains GENERATION-001.

## H. Contracts / Interfaces / Data Model

Per-case required facts, acceptable variants, claim support grade, citation source/version/locator, completeness and contradiction status, abstention and reviewer disagreement. Separate conditional answer correctness and unconditional end-to-end success.

## I. Repository Files / Components Impacted

Reuse reviewed dataset and source/facet contracts, existing evaluation runner/report patterns; add answer evaluation tests and restricted evidence. Do not modify ranking gold or prior reports.

## J. Implementation Requirements

**External answer-quality requirement:** after retrieval and generation prerequisites, use the [external V1 corpus/questions/expected answers](dataset/README.md) as an additional diagnostic set. Review actual answers in EN/RU/UK for source-grounded mathematical formula/numeric/code accuracy, historical attribution, literary interpretation and all required facts. Use [external protocol](dataset/EXTERNAL_EVALUATION_PROTOCOL_V1.md), separate open diagnostic from local holdout excluded from tuning; do not use answer keys as model inputs or count translations as independent. Report unsupported claims and citation/facet failures separately by domain and language.


1. Define predeclared rubric and locally held-out answer questions with verified expected facts; no tuning on answer holdout. Include multi-document, numeric, exact code, contradictory and no-answer cases.
2. Score each material claim against original evidence (supported/unsupported/contradicted), required fact coverage, citation precision and citation coverage; record all-required-facts rate and exact numeric/unit/code/version correctness. Review actual outputs, not templates. The agent rechecks high-impact claims against originals; automated judgment alone is not source evidence.
3. Proposed local targets >=95% fully correct and complete answerable cases, >=95% supported material claims, >=98% valid supporting citations, <=5% false acceptance/abstention; zero observed cross-tenant/wrong-version fabricated provenance. Report sample counts, uncertainty and critical cohort failures. Ratify before final run; failed gate stays blocked.
4. Separate retrieval misses, context omissions, answerability errors and generation hallucinations; attribute with frozen context and actual retrieved evidence. Measure end-to-end p95/p99, tokens, shared GPU resource and failure rates.
5. Publish GO/NO-GO, permanent regression checks and rollback decision; generation capability only promoted after successful local evaluation gate.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Faithfulness-Plus, claim chains and noise robustness — 2026-11-26

Execute [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md) sections 4.2/4.3/4.5/4.6. Score claim-to-context support separately from context-to-original source fidelity, complete claim-to-original evidence chains and required facts; distinguish unsupported, contradicted, unverified and omitted. Proposed >=95% valid supporting claim chains and existing >=98% valid supporting citations; zero fabricated/unauthorized locators. Run matched oracle-clean and actual-context generation at 0/10/20/30% noise by token share, fixed total budget; evidence-preserving and displacement arms separate, near-topic contradictions separate. Proposed 20% evidence-preserving noise tolerance <=10 pp fully-correct/complete accuracy drop, predeclare before evaluation. Report relative and pp changes, actual coverage and cost. If actual answer correctness probabilities exist, assess separate ID/OOD Brier/ECE and risk-coverage; no fake confidence. Agent verifies originals and deterministic values, local model judge optional diagnostic only. Keep ANSWER holdout out of tuning.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No unsafe source instructions, confidential logs or unsupported authority; labels remain evaluator-only.

## L. Testing / Evaluation / Runtime Verification

Actual model outputs, source-grounded automated verification and reference rubric tests, citation exists but unsupported negative, incomplete correct answer, numeric/code mismatch, false abstention, outage and stale evidence regression.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] External V1 actual grounded answers evaluated against reviewed localized facts, formulas and citation support; open diagnostics and unseen final holdout reported separately.

- [ ] Actual source-verified claim/fact/citation evidence and all metrics with denominator.
- [ ] Release GO or explicit NO-GO/BLOCKED, no answer-quality claim from retrieval scores.
- [ ] Regression suite and rollback preserve retrieval independently.

- [ ] Full source/claim metrics, broken links, NAG paired degradation and optional answer calibration reported separately; proposed stress thresholds frozen before final run, no unsupported pass.

## N. Documentation / Migration / Compatibility / Rollback

Version answer rubric and evaluation set; freeze reports, retain previous generation profile and disable if quality regresses.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

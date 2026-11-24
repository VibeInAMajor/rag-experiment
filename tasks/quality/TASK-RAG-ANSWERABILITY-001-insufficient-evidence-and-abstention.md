# TASK-RAG-ANSWERABILITY-001 — Qualify insufficient-evidence detection and explicit abstention

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** PROPOSED — specification only; no runtime tests executed  
**Priority:** P0  
**Dependencies:** [EVIDENCE-002](TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md), [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md), [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md); qualified selected exact/Hybrid/reranked path; no generation dependency.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
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

Decision: sufficient / insufficient / conflicting / not_evaluable (or equivalent documented existing convention), reason codes, calibrated policy revision, evidence refs; separate transport failure/cancellation. False acceptance = answerable claim on unanswerable set; false abstention = insufficient/conflicting/no-answer on answerable set under declared rubric.

## I. Repository Files / Components Impacted

Reuse evaluation and retrieval contracts, existing profile governance, [API contracts](../../apps/workbench/contracts/schemas.py), [projection](../../apps/workbench/api/projection.py); add minimal decision owner and focused tests, no new global model service.

## J. Implementation Requirements

1. Freeze rubric: required evidence support and scope, partial facts, conflict handling, no-answer absence vs retrieval miss; distinguish gold answerability from actual retrieved support. Label both on reviewed tuning cases.
2. Compare empty-result and rank/score-margin baselines; assess calibrated decision with PR/ROC and separate risk by language, code, query class; use a bounded classifier only if cheaper rules fail and model is qualified. No gold labels at runtime.
3. Freeze policy and thresholds before held-out validation. Target false acceptance <=5%, false abstention <=5%, report numerator/denominator, Wilson/exact confidence intervals and trade-offs; ambiguous/conflicting cases separately. No fabricated per-query confidence.
4. Integrate explicit outcome and source refs while preserving service failure codes, no evidence fabrication. Reject stale/mismatched evidence; no automatic retries or broadened tenant access. If targets fail, report blocked and keep answer-generation gate closed.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No unsupported certainty or privileged source disclosure; prompt-injected evidence cannot authorize actions.

## L. Testing / Evaluation / Runtime Verification

No-answer, partial answer, hard negative, contradictory sources, high cosine wrong match, low cosine correct match, empty corpus, 429/503/504 and cancellation, calibration leakage and decision regression.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Real reviewed tuning evidence and fixed thresholds with error trade-off.
- [ ] Explicit insufficient/conflicting vs transport failure outcome and safe provenance.
- [ ] Target <=5% false acceptance/abstention demonstrated on tuning or blocked; final independent gate belongs QUALITY-002.

## N. Documentation / Migration / Compatibility / Rollback

Version decision policy; if unqualified, do not enable grounded generation. Preserve underlying retrieval capability and label raw ranks as such.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

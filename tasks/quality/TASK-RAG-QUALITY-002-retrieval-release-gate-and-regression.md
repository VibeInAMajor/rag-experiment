# TASK-RAG-QUALITY-002 — Qualify end-to-end retrieval quality and establish a permanent regression gate

**Created:** 2026-11-24  
**Updated:** 2026-11-25  
**Status:** PROPOSED — specification only; no runtime tests executed  
**Priority:** P0  
**Dependencies:** [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md), [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md), [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) or documented NO-GO/approved baseline, [EVIDENCE-002](TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md), [ANSWERABILITY-001](TASK-RAG-ANSWERABILITY-001-insufficient-evidence-and-abstention.md); [RERANK-001](TASK-RAG-RERANK-001-local-semantic-reranker-qualification.md)/[RERANK-002](TASK-RAG-RERANK-002-qualified-reranking-integration.md) and [BM25-001](TASK-RAG-BM25-001-bm25-extension-feasibility-and-quality-gate.md)/[BM25-002](TASK-RAG-BM25-002-conditional-postgresql-bm25-search-profile.md) only if GO; [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) scoped integration.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-QUALITY-002-retrieval-release-gate-and-regression.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Qualify end-to-end retrieval quality and establish a permanent regression gate

## B. Context / Problem

Correct SQL, a synthetic recall score and candidate tuning are not independent end-to-end evidence. Final quality must measure required facets in selected context and answerability, not just neighbor overlap.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md): 102 active vectors, 52 queries (46 answerable and six no-answer), two relevant labels per answerable case; primary@1 31/46 (0.673913), primary@5 44/46 (0.956522), Recall@5 86/92 (0.934783), MRR@10 0.942029, nDCG@5 0.845519 (preserved embedding evidence); all six no-answer cases return neighbors. Exact SQL/HTTP agreement is demonstrated, independent production relevance is not. [embedding evaluator](../../scripts/workbench_embedding_evaluate.py) and [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py) are existing evaluation owners. [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py) and [profiles.py](../../apps/workbench/retrieval/profiles.py) support immutable policies; no final independent quality release gate exists.

## D. Goal

Local development only: no human reviewers, external approval, independent accounts or special custody infrastructure required. The holdout is an ordinary local split, not a security boundary.

Freeze one candidate retrieval stack before opening local held-out dataset. Publish a reproducible release GO/NO-GO with cohort quality, provenance, abstention, latency and regression gates at supported small-document scale.

## E. Scope

Actual ingestion → embedding → approved retrieval → optional fusion/rerank → context → sufficiency; shared regression suite, held-out evaluation and release decision.

## F. Non-Goals

No generation quality claim, ANN, 100k ingestion, enterprise tenancy or new infrastructure. No retuning on opened final holdout.

## G. Architecture / Boundaries

Existing evaluation owner validates original source and actual API output; runtime uses existing registry and profiles. OPS-001 consumes evidence; no second evaluation framework.

## H. Contracts / Interfaces / Data Model

Run manifest with dataset/labels/corpus digest, source family split, profile/model/tokenizer/index revisions, exact commands, metrics and raw safe case-level identities, fixed token budget, verdict and automated validation results. Separate tuning/holdout/synthetic and candidate/final context metrics.

## I. Repository Files / Components Impacted

[embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), existing retrieval tests and API/browser smoke; add focused regression configuration/CI artifacts only after reinspection. Use existing profile and telemetry owners.

## J. Implementation Requirements

**External-domain regression and qualification:** [external multidisciplinary V1](dataset/README.md) must be run as a separate source-grounded cohort suite with [execution protocol](dataset/EXTERNAL_EVALUATION_PROTOCOL_V1.md), paired exact/FTS and qualified candidate comparisons, fixed context budget, source-line/facet and no-answer outcomes. The open external set is diagnostic/regression; final GO still requires a local holdout excluded from tuning and grouped uncertainty. Report external and internal results separately; no aggregate masking critical domain failures, no treating translated variants as independent gold cases.


1. Freeze candidate settings, model assets, gold manifest, allowed cohorts and predeclared gates; the evaluator loads held-out labels only for scoring after candidate settings are frozen. Verify actual supported ingestion and complete current generation. No fixed-fixture shortcut as E2E.
2. Run FTS and exact baseline plus qualified hybrid/reranked candidates as applicable with equal source scope and final context budget; retain raw arm metrics, candidate ceiling, final pack facets, no-answer and all failure cases. Do not add scores across incompatible algorithms.
3. Require Primary Evidence Hit@1 >=0.95, Primary Evidence Hit@5 >=0.98, relevant evidence Recall@5 >=0.95, graded nDCG@5 >=0.95, All Required Facets@5 >=0.95; critical adequately sized cohorts Primary@5 >=0.95. Predeclared p95 <=1.20x identical baseline load unless an explicitly approved cost/latency trade-off is recorded. Zero observed unauthorized/stale/wrong-profile/source-hash/citation integrity violations. These are proposed point targets, not achieved results. plus false acceptance/abstention <=5%. Report macro/micro distinctions, primary MRR, nDCG grades, cluster-bootstrap intervals, per-cohort sample sizes and lower-tail failures. Local phase point targets apply. Report uncertainty, sample-size limitations and incomplete source verification; do not claim enterprise qualification. Incomplete source verification blocks the affected measurement, not routine development. No-answer denominator excludes transport errors but report them and count operational failures separately.
4. Run original 52-case and lexical regression, stale/foreign/version hard negatives, restart, model outage, cancellation and actual Live browser provenance. Record p50/p95/p99 and resource costs; no hidden fallback or fake outputs.
5. Publish GO/NO-GO. If FAIL, route to owning task, create a fresh local holdout for subsequent tuning cycles; do not recycle opened holdout as blind. Keep regression suite versioned and require it for every retrieval/profile/chunker/model/ANN change. Generation starts only after retrieval GO.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No raw customer content in CI logs; keep reference answers out of training/tuning inputs.

## L. Testing / Evaluation / Runtime Verification

Actual PG/model/HTTP/browser E2E, independent metric recomputation, failure/negative tests, holdout hash and leakage validation, regression threshold checks, explicit unrun cohort state.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] External V1 diagnostic/regression suite executed with actual runtime and separate domain/language/family metrics; independent final holdout remains separate.

- [ ] Agent-verified frozen local holdout and actual end-to-end evidence; every gate has numerator/denominator and result.
- [ ] Targets met for qualified local scope or explicit NO-GO/BLOCKED with no activation.
- [ ] Regression suite and runbook reproduce results and detect injected ranking/identity failures.
- [ ] No enterprise or answer-quality claim from retrieval success.

## N. Documentation / Migration / Compatibility / Rollback

Record versioned release decision, evidence and operator rollback; retain qualified prior profiles, corpus and original labels. Fail gate on regression rather than silently reducing requirements.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

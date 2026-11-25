# TASK-RAG-EVIDENCE-002 — Select sufficient, provenance-preserving evidence within a fixed context budget

**Created:** 2026-11-24  
**Updated:** 2026-11-26  
**Status:** PROPOSED — specification only; no runtime tests executed  
**Priority:** P0  
**Dependencies:** [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md), [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) or qualified exact baseline; [RERANK-002](TASK-RAG-RERANK-002-qualified-reranking-integration.md) only if GO; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md); coordinate [CHUNK-004](../../tasks/TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md) and CONTENT-005 for richer evidence later.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Select sufficient, provenance-preserving evidence within a fixed context budget

## B. Context / Problem

Top-k ranking does not guarantee all required facets fit the final context. Overlapping chunks can waste tokens, and similar text can erase distinct source occurrences.

## C. Current Repository State

[vector_search_snapshot](../../apps/workbench/postgres/postgres.py) and [projection](../../apps/workbench/api/projection.py) preserve source/version/chunk/page; [chunk policies](../../apps/workbench/chunking/chunking_profiles.py) and native token admission exist. [API contracts](../../apps/workbench/contracts/schemas.py) returns ranked passages, not an approved generator context pack. CHUNK-004 plans hierarchy and evidence expansion; CONTENT-005 owns future original asset resolution. No final context selector is qualified.

## D. Goal

Produce bounded evidence context with exact source locators, transparent omissions and measurable all-required-facet coverage, without introducing a generator.

## E. Scope

Candidate deduplication by occurrence/overlap, context token accounting, deterministic selection/diversity policy, provenance and per-facet evaluation; optional already-supported bounded neighbor expansion only if tested.

## F. Non-Goals

No gold labels as runtime inputs; no generation, OCR, invented page/citation, arbitrary multi-hop agent, new asset resolver or hierarchy implementation owned by CHUNK-004.

## G. Architecture / Boundaries

Application context-selection policy consumes existing typed ranked results; token estimator and source lookup reuse owners; original source version remains authority.

## H. Contracts / Interfaces / Data Model

Context pack carries selected ordered evidence IDs, original source/version/chunk/span/page, token count with declared tokenizer, policy revision, dropped IDs/reasons and generation. Offline evaluator maps pack to gold required facets. No claim runtime knows all gold facets.

## I. Repository Files / Components Impacted

Extend retrieval orchestration and evaluation owners, [API contracts](../../apps/workbench/contracts/schemas.py) only if explicitly required; reuse current token counter/seams and source provenance. No new ingestion store.

## J. Implementation Requirements

1. Define fixed final context budget independent of top-k; count actual serialized payload including separators and evidence labels. Pin tokenizer or explicitly label proxy until generation tokenizer exists.
2. Compare rank-order baseline vs bounded redundancy suppression/diversity and supported neighboring chunks. Preserve distinct source occurrences, version scope, exact identifiers and numeric/table evidence; never merge incompatible versions or truncate across required source anchors silently.
3. Evaluate candidate recall vs selected-context recall, all-required-facets, primary hit, duplication ratio, token utilization, source provenance and latency at equal budget; use tuning labels only. Select minimal policy with measured benefit; report missing/omitted evidence.
4. Define typed insufficient/empty pack result for ANSWERABILITY; selection alone does not certify sufficiency or answerability. Retain stable locators for GENERATION-001.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Source chain and noise accounting — 2026-11-26

Implement context-to-original chain validation using existing source/version/locator metadata; no new asset resolver here. Report verified source-support/locator coverage, duplicate and irrelevant assessed token share, candidate ceiling vs selected pack, broken links and missing facts. Preserve actual serialized pack and hash locally for later NAG tests; label unjudged content unknown, not irrelevant. Compare bounded original paragraph/section neighbor expansion only where existing ownership permits and source integrity holds. [Quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md) sections 4.2/4.3/4.5 define metrics; final answer-chain links belong to QUALITY-003.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No user-visible unsupported original asset links; no label leakage or prompt instructions from source.

## L. Testing / Evaluation / Runtime Verification

Token boundary, duplicate occurrences, repeated overlapping spans, multi-document facets, contradictory active evidence, empty result, stale/cross-workspace expansion, deterministic budget and source parity.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Context pack never exceeds declared budget and retains source/version locators.
- [ ] Paired equal-budget facet coverage and omission analysis, no integrity regressions.
- [ ] Explicit empty/insufficient candidates; no runtime gold-label dependence.

- [ ] Selected-pack source chain and assessed noise share are measured; context artifacts permit reproducible later NAG experiments; no gold-aware runtime selection.

## N. Documentation / Migration / Compatibility / Rollback

Version selection policy and preserve raw retrieval output; disable policy to use approved rank-order baseline.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.


## QUALITY-001 failure-localization evidence

QUALITY-001 OPEN V2 handoff (2026-11-25): the captured fixed 2048-token ranked prefix loses an otherwise available candidate facet on 12 baseline and 12 selected questions. All required facts survive the final context for 225/228 of 261 answerable cases. These overlap candidate/structural/ranking losses and must not be added as disjoint failure totals. Use captured selected_chunk_ids, source ranges and token costs to benchmark a bounded selector without label-aware runtime selection.

Evidence: [V2 report](../evidence/quality-2026-11-25/report.md). Raw per-query IDs, locators, alternative sets and next probes remain in the ignored existing V2 run; sanitized counts are in metrics.json → failure_localization.
## QUALITY-001 UI completion evidence — 2026-11-26

Matched UI pair fixed 2048-token ranked source-content prefix: all facets retained on 226 → 240/261; complete top10 but incomplete final context on 6 → 6. Preserve actual chunk sizes/projection provenance and paired regressions. This is source coverage, not semantic sufficiency, and does not authorize label-aware runtime selection.

Evidence: [completed UI comparison](../evidence/quality-2026-11-25/report.md); metrics.json → ui_completion. Raw case details remain ignored locally.

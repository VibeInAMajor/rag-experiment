# TASK-RAG-RERANK-001 — Qualify a bounded local semantic reranker against exact and hybrid candidates

**Created:** 2026-11-24  
**Updated:** 2026-11-27  
**Status:** PROPOSED — conditional quality experiment; no model qualified  
**Priority:** P0  
**Dependencies:** [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md), [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) for hybrid arm; [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md); valid [TPM-001](../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) admission for embedding queries.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-RERANK-001-local-semantic-reranker-qualification.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Qualify a bounded local semantic reranker against exact and hybrid candidates

## B. Context / Problem

Float32 exact ranking already exists; reranking must improve semantic relevance, not repeat ANN distance. Supporting evidence and hard negatives currently outrank primary evidence.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md): 102 active vectors, 52 queries (46 answerable and six no-answer), two relevant labels per answerable case; primary@1 31/46 (0.673913), primary@5 44/46 (0.956522), Recall@5 86/92 (0.934783), MRR@10 0.942029, nDCG@5 0.845519 (preserved embedding evidence); all six no-answer cases return neighbors. Exact SQL/HTTP agreement is demonstrated, independent production relevance is not. [DocumentJoiner](../../haystack/components/joiners/document_joiner.py) has RRF; core rankers include [MaxSim](../../haystack/components/rankers/max_sim.py) and [LLM ranker](../../haystack/components/rankers/llm_ranker.py) but neither proves a qualified local cross-encoder. No executable Workbench reranking profile or measured reranker capacity observed.

## D. Goal

Measure whether one compatible local cross-encoder (candidate Qwen3-Reranker family, smaller variant if suitable) improves primary/facet ranking at equal candidate and context budget. Produce GO/NO-GO and model/resource evidence.

## E. Scope

Review model card, license and local runtime availability; isolated comparative reranking on frozen candidates from exact and RRF, multilingual and code cases; truncation and GPU/CPU resource envelope.

## F. Non-Goals

No production adapter/activation, no embedding replacement, cloud model, generative judge as gold, ANN or assumed 4090 capacity.

## G. Architecture / Boundaries

Evaluation invokes reviewed candidate model through a narrow provider adapter; model choice stays outside core; existing retrieval candidates and gold scorer remain authoritative.

## H. Contracts / Interfaces / Data Model

Record model artifact digest/license/tokenizer, pair input format, maximum pair tokens, truncation policy, candidate limit, score semantics, timeout/batching and measured CPU/RAM/VRAM. Scores are ranking signals not probabilities.

## I. Repository Files / Components Impacted

Reuse [embedding evaluator](../../scripts/workbench_embedding_evaluate.py), [Live Dense evaluator](../../scripts/workbench_dense_evaluate.py), [DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py), [DocumentJoiner](../../haystack/components/joiners/document_joiner.py); inspect actual installed ranker integrations before adding a narrow experimental adapter; no upstream Haystack change.

## J. Implementation Requirements

1. Freeze QUALITY-001 tuning baseline and HYBRID candidate ranks; compare exact, RRF, exact+reranker and RRF+reranker with same corpus, candidate sizes (e.g. 20/50) and final token budget. Record candidate oracle ceiling: reranker cannot recover absent evidence.
2. Verify model licensing, artifact identity, tokenization, instruction/pair formatting, language/code support, max tokens; no silent truncation of primary evidence. Evaluate bounded batch/concurrency and actual shared RTX 4090 resource headroom with TEI; use CPU or smaller candidate if necessary. No inference outside approved budget.
3. Report primary@1/5, facets, recall, nDCG, hard negatives, pair latency, end-to-end p95/p99, throughput, VRAM/RAM, failures; paired tuning comparisons and uncertainty. Predeclare minimum material gain and no critical cohort regression before runs; Primary Evidence Hit@1 >=0.95, Primary Evidence Hit@5 >=0.98, relevant evidence Recall@5 >=0.95, graded nDCG@5 >=0.95, All Required Facets@5 >=0.95; critical adequately sized cohorts Primary@5 >=0.95. Predeclared p95 <=1.20x identical baseline load unless an explicitly approved cost/latency trade-off is recorded. Zero observed unauthorized/stale/wrong-profile/source-hash/citation integrity violations. These are proposed point targets, not achieved results. are final program targets, not required to force a reranker.
4. Decide GO only if gain justifies measured cost and safety, otherwise NO-GO with retained best non-reranked profile. Do not inspect final holdout or activate anything.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

### Hard-negative and cohort robustness — 2026-11-26

Use QUALITY-001 failure handoff and compare raw candidate ceiling vs reordered top-k. Dense-only qualification may proceed if lexical NO-GO; add hybrid arm only when useful lexical/hybrid profile qualifies. On OPEN compare hard-negative@1, known-facet/primary hits and all-required-facets at equal budget, including Art/Literature/Kubernetes, multilingual and close contradictory passages. Follow [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md); do not infer answerability from ranker score or claim exhaustive recall/nDCG with sparse qrels.

### Activate dense-only qualification from measured ranking gap — 2026-11-26

The historical selected code-query had 63 cases with a complete singleton fact below rank one within top ten; 15 had no complete singleton in the known indexed representation and 3 had one outside top ten. Targeted top-50 replay recovered 44/50 missing facet observations, 25 by rank 20; these are historical, not the cleaned corpus. Use [latest matched Markdown baseline](../evidence/quality-2026-11-25/report.md) and preserved current top-50 captures; run a dense-only reranker experiment now without waiting for lexical GO. Start with one compatible small local cross-encoder (Qwen3-Reranker-0.6B candidate if qualified); compare raw Dense vs reranked top-10/20/50, same candidate pool and final budget, source singleton feasibility and oracle ceiling. Proposed component GO: >=5 pp paired any-complete-fact@1 gain on OPEN and no reduction in all-facts@5 or fixed-budget all-facts, disclose clustered uncertainty, domain/language regressions, actual shared GPU/latency cost; freeze criterion before running. If ceiling below final targets, route to CHUNK-004 or candidate retrieval; never inflate ranks by gold. DATASET-002 provides distinct primary/relevance labels; do not misname any-fact scores. Use existing UI/local quality evidence path for new functional acceptance; no production integration until qualified RERANK-002.

### Judge-separated ranking qualification — 2026-11-27

The [standalone reranker](../../apps/workbench/reranking/README.md) deployment at commit d31eb5ca283523f90584a61c80ca6a90d6fccfe9 does not itself qualify ranking. The prior full OPEN grade revision is provisional pending reopened [DATASET-002](TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md). Reuse [MAF-002](../maf/TASK-MAF-002-semantic-judge-agent.md) only through the external evaluation runner to judge previously unseen candidate occurrences and audit direct/partial/support/related/wrong-scope/contradictory results. The judge never sees candidate score/rank/arm or old grade during assessment; use the same frozen rubric/profile and common eligible pool for comparisons. In addition to rank gain and required facts, report strict precision@1/5/10, irrelevant and wrong-scope rates, and paired regressions on EXT-LIT-001, EXT-NA-003 and EXT-ART-003 plus multilingual cohorts. A reranker must not grade its own output; no automatic promotion from its similarity scores. Capturing experimental rankings may proceed before audit completion, but final semantic GO requires eligible revised judgments. Existing exact-source metrics remain separately diagnostic. No MAF imports or external API calls in the reranking application.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No external content egress; model assets and pair inputs must be reviewed.

## L. Testing / Evaluation / Runtime Verification

Golden rank ordering, invalid/NaN scores, oversized pair, cancellation, OOM, multilingual and exact identifier/hard-negative samples; actual model smoke and paired resource measurements.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Actual pinned local model and resource tests recorded or explicit blocker.
- [ ] Reproducible paired quality/cost evidence and candidate ceiling analysis.
- [ ] GO/NO-GO with measured bounds, no production claim; conditional RERANK-002 handoff.

- [ ] Paired hard-negative and cohort results, candidate ceiling, cost and material gain/no-go are reported; unavailable hybrid arm explicitly not evaluated.

- [ ] Dense-only candidate qualification executed or measured NO-GO, with equal-budget ceiling and paired gains against cleaned baseline; hybrid arm added only if qualified.

- [ ] Paired ranking evaluation uses eligible independent judge judgments and reports strict precision/irrelevance and three regression families; deployment/readiness not confused with qualified ranking.

## N. Documentation / Migration / Compatibility / Rollback

Preserve original candidate ranks and exact profiles. Keep experiment isolated; remove only owned temporary assets if required.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.


## QUALITY-001 failure-localization evidence

QUALITY-001 OPEN V2 handoff (2026-11-25): earliest ranking attribution affects 70 baseline / 68 selected queries; individual-facet top-five ordering losses affect 14/16. Full required-fact union is present in top ten for 232/238 of 261 answerable questions, an upper bound rather than proof of fitting five chunks or 2048 tokens. Review captured ranks and singleton-vs-multi-chunk feasibility; a reranker cannot add missing candidates. No reranker was implemented or qualified by this diagnosis.

Evidence: [V2 report](../evidence/quality-2026-11-25/report.md). Raw per-query IDs, locators, alternative sets and next probes remain in the ignored existing V2 run; sanitized counts are in metrics.json → failure_localization.
## QUALITY-001 UI completion evidence — 2026-11-26

Matched original-only before/after pair: all-facts candidates available at 50 but missing at 10 affect 23/9 answerable queries; complete at 10 but missing at 5 affect 10/9. These are observed ranking losses, not proof that five whole chunks can cover every facet. Original frozen targeted ranks are also captured through 50; no reranker implemented or promoted.

Evidence: [completed UI comparison](../evidence/quality-2026-11-25/report.md); metrics.json → ui_completion. Raw case details remain ignored locally.

## QUALITY-001 source-fidelity handoff — 2026-11-26

Original-span/selected-pack source chains are valid in the captured scope, while known facts remain absent from candidate/context cutoffs. Reorder only the available pool; Bingley actor/income near-matches are a concrete risk, not a measured generated-answer error.

Evidence: [completed bounded source-fidelity assessment](../evidence/quality-2026-11-25/report.md); metrics.json → source_fidelity. This handoff does not implement or qualify this owner task.

# TASK-RAG-RERANK-001 — Qualify a bounded local semantic reranker against exact and hybrid candidates

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
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

## N. Documentation / Migration / Compatibility / Rollback

Preserve original candidate ranks and exact profiles. Keep experiment isolated; remove only owned temporary assets if required.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

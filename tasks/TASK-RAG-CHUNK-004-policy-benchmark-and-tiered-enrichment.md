# TASK-RAG-CHUNK-004 — Cohort-based chunking evaluation, hierarchy and optional enrichment

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** PROPOSED — evaluation and rollout blueprint; not an implemented agent  
**Priority:** P2 — optimize only after baselines are actually indexed  
**Dependencies:** TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-EVAL-001, TASK-RAG-PARSE-001; advanced cohorts depend on their qualified format tasks  
**Repository snapshot reviewed:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target:** `tasks/TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md`  
**Architecture:** [Content-aware format/policy decision](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Build a reproducible, **cohort-specific** benchmark and safe policy promotion mechanism comparing recursive, structure-aware, hierarchy/parent expansion and embedding-based semantic chunking; evaluate high-value LLM/agentic enrichment only behind a separate explicit gate.

## B. Context / Problem

The supplied decision tree says static single-fact should use agentic chunking, periodic updates semantic, and high overlap for exact phrases. These are plausible hypotheses but not guaranteed policies; ingestion strategies are chosen before unknown future queries, while query complexity can vary per request. Product decisions must be based on measured retrieval, structural citation and operational cost rather than a categorical rule. Preserve the first PostgreSQL lexical baseline and immutability of active source versions while evaluating alternatives.

## C. Current Repository State

| Existing source | What is already there | Gap |
| --- | --- | --- |
| [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../haystack/components/preprocessors/embedding_based_document_splitter.py) `EmbeddingBasedDocumentSplitter` | Cosine distance between sentence-group embeddings; supports percentile, min/max length and language. | Already implemented in Haystack; not connected to a qualified TEI/Qwen service or benchmark. Do **not** reimplement. |
| [`haystack/components/preprocessors/hierarchical_document_splitter.py`](../haystack/components/preprocessors/hierarchical_document_splitter.py) | Parent/child chunk metadata. | Parent expansion/query-time service and durable parent relationship not app-qualified. |
| [`haystack/components/preprocessors/recursive_splitter.py`](../haystack/components/preprocessors/recursive_splitter.py) | Reusable recursive baseline. | Word/token units must be honest; default tiktoken != Qwen tokenizer. |
| [`apps/workbench/api/fixtures/lexical-evaluation.json`](../apps/workbench/api/fixtures/lexical-evaluation.json) | 10 exact keyword + 3 diagnostic paraphrase labeled queries. | Good for first lexical baseline, **not** broad evidence for agentic/semantic or format cohorts. |
| [`apps/workbench/api/lexical.py`](../apps/workbench/api/lexical.py) | Genuine PostgreSQL `ts_rank_cd` retrieval. | Cannot claim semantic/multi-hop answer evaluation without a separately qualified retrieval/generation runtime. |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | Source/version/chunk identities; `Chunk.metadata` for fingerprints. | No currently persisted alternate parent-child index with run-time expansion guarantees. |
| [Parser/strategy architecture](../docs-website/docs/architecture/content-aware-chunking-strategy.md) | Explicit candidates for prose, code, page/table, transcript and structured data. | Need real performance and indexing costs before policy promotion. |

## D. Goal

Given a fixed gold corpus and a set of revisioned candidate chunking profiles, produce inspectable paired evaluation reports showing metrics, costs and confidence intervals by document format, update frequency and query cohort. A higher-cost profile is adopted only when an explicit acceptance gate and security/cost limits pass; otherwise the default remains unchanged.

## E. Scope

- Build reproducible snapshots of source documents, parser outputs, normalized chunk manifests and gold label spans; pin tokenizer/model/retriever versions where applicable.
- Compare: recursive baseline at explicit units; heading/page/table/AST; hierarchical with retrieval-time parent expansion; semantic via existing Haystack splitter only after provider qualification.
- Separate source-format cohorts, update-frequency classes (`static`, `periodic`, `near_real_time`) and query classes (`fact`, `exact_phrase`, `paraphrase`, `multi_hop`, `table_lookup`, `code_symbol`, `speaker_time`).
- Record retrieval/structure/cost/latency metrics, sample counts, uncertainty, negative safety and behavior after partial updates.
- Optional experimental **LLM/agentic enrichment** for a specifically approved high-value corpus with strict content privacy, token budget, output validation and deterministic cache; not enabled by default.
- Provide a reviewable policy-approval artifact before switching a production profile, not automatic reinforcement/agent orchestration.

## F. Non-Goals

No arbitrary query-time re-chunking of live documents, no uncontrolled agent running on customer data, no paraphrase metrics from pure lexical search reported as generative accuracy, no fabricated Recall lift, no editing core Haystack, no automatic DB reindex of prior production versions or vendor-coupled application policy.

## G. Architecture / Boundaries

`immutable gold corpus → fixed parser output → candidate policy split → isolated index build → fixed retrieval profile → gold label metrics + cost → human-approved promotion`.

Evaluation engine is provider-neutral: select model capabilities/adapters separately. Query-time `parent expansion` belongs to retrieval service and is versioned independently from ingest policy. Different chunk indices must use isolated evaluation workspaces/versions, never the same active customer corpus.

## H. Contracts / Interfaces / Data Model

`EvaluationProfile`: parser_revision, chunker_revision, token_unit/revision, embedding profile, retriever/ranker revision, scoring rubric, corpus hash. `QueryCase`: document/source/element truth spans, query class, expected source/chunk IDs, relevance labels. `EvaluationReport`: size, Recall@K/MRR/nDCG, token-span IoU, citation fidelity, lost-content rate, duplicate-token ratio, stored bytes, ingest/embedding costs, update churn, p50/p95 latency, confidence interval, failure list. `PolicyPromotion`: evidence_path, from_profile, to_profile, cohort, signed decision, explicit rollback. No raw source text or credentials in shared logs. No profile chosen solely by a task ID.

## I. Repository Files / Components Impacted

- CREATE `apps/workbench/api/evaluation/chunking.py` or the existing evaluation package's cohesive location; avoid second score calculation if present.
- ADD versioned curated cohort fixtures under `apps/workbench/api/fixtures/` (non-sensitive, properly licensed) and exact labels.
- ADD `apps/workbench/api/tests/test_chunking_evaluation.py` and separate integration benchmark command under app-specific Hatch environment.
- EXTEND only approved retrieval parent-expansion adapter after reviewing source/version parent metadata contract; possible **separate** migration.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and per-cohort result `.md` summaries, not core Haystack.

## J. Implementation Requirements

### J1. Baseline reproducibility

Pin one immutable corpus and a stratified gold set. Preserve original source/provenance and Qwen tokenizer qualification state. Reuse existing lexical evaluation fixtures as a **sanity** baseline only, not as broad document-type accuracy. No Qwen/TEI call unless it is genuinely available/validated.

### J2. Experimental grid

For prose test 384/512/768 **model tokens only if qualified**, otherwise explicitly named word baselines; 0/10/15% overlap. For PDF test page/section; Markdown heading/recursive; code AST/recursive; tables row group vs flattened; chat turn/topic when parser is enabled. Keep one parser and retrieval configuration fixed while comparing chunkers; split parser comparison into separate experiment.

### J3. Hierarchical retrieval-time expansion

Prove parent-child metadata store/lookup before enabling small-to-big. Build a limited retrieval adapter that expands selected matched child results to only authorized active parents with stable provenance, bounded context length and no workspace leak. If existing JSONB cannot satisfy reliable parent access, propose an additive relational migration **before coding**.

### J4. Semantic and optional agentic research

Reuse `EmbeddingBasedDocumentSplitter` with a qualified embedding provider; no new semantic similarity algorithm unless measured deficiency. Agentic enrichment is a separately approved opt-in experiment: explicit consent, max tokens/cost, no remote model by default, schema-validated output, prompt-injection resistance, deterministic caching by content+model+policy revision, fallback to safe baseline on validation failure with visible reason (never a hidden fallback in Live execution).

### J5. Analysis and promotion

Report metric definitions and denominators, per-cohort paired bootstrap confidence intervals, bad-case examples without private data, index cost, delta update churn, p95 query changes. Proposed admission gate: +3 points Recall@5 or +0.03 MRR with <=20% index cost increase (or separately justified tradeoff); safety remains absolute. Publish a reversible versioned decision before changing any default.

## K. Security / Governance / Observability

Use only approved/test corpora and opt-in privacy policy for model-based enrichment. Untrusted documents may contain prompt injection; no assistant/code tools operate on them, no private material sent to an unapproved provider. Test cross-workspace isolation for parent expansion; user query does not change authorization scope. Attribute cost and tokens per workspace/corpus without logging prompt/document raw text. Retention and deletion of evaluation copies need explicit policy.

## L. Testing / Evaluation / Runtime Verification

- Unit metric identities, ranking ties, missing truth, confidence interval implementation and candidate selection invariants.
- Integration exact SQL/HTTP parity, immutable source versions, isolation of alternate evaluation indexes and parent expansion.
- Golden spans for headers, PDFs/table rows, code line/symbol, chat turns/timestamps and multilingual data.
- Negative prompt-injection and schema-invalid LLM output, timeout, quota, offline TEI, cross-tenant parent request, no parser.
- Regression preservation of `postgres_ts_rank_cd` and basic TXT/Markdown reference results.
- Run focused Hatch checks and materialize benchmark JSON/MD evidence with environment/corpus hashes and PASS/FAIL/SKIP.

## M. Acceptance Criteria

- [ ] Every compared profile has identical fixed corpus/labels and clearly pinned parser/tokenizer/retriever configuration.
- [ ] Report includes Recall@5/10, MRR/nDCG, citation fidelity, duplicate ratio, indexing cost and latency with sample counts/uncertainty by cohort.
- [ ] Zero unapproved model invocation or silent semantic/agentic fallback; unavailable embeddings remain explicit.
- [ ] Parent expansion returns only authorized active parent and respects bounded context; zero cross-workspace leaks.
- [ ] No default strategy is promoted solely by the supplied decision tree; documented gate, evidence and rollback must exist.

## N. Documentation / Migration / Compatibility / Rollback

Evaluation runs may use dedicated disposable data/index spaces; never overwrite production active versions. If parent-child provenance needs relational indexes, create a separate full A–O migration task. Keep parser/chunking profiles immutable and versioned; promotion changes a pointer/config profile, not already indexed source IDs. Rollback restores prior approved profile and reindex plan without deleting PostgreSQL data. Research-only agentic experiments remain disabled without a subsequent reviewed enablement task.

## O. Mandatory Completion Checklist

- [ ] Existing Haystack semantic/hierarchical components reused where applicable.
- [ ] Each corpus and query cohort gold set versioned with provenance.
- [ ] Evaluation/policy promotion reports and negatives executed, not simulated.
- [ ] Privacy/cost and tenant isolation gates passed; no hidden model use.
- [ ] Compatibility, rollback and documented strategy decision updated.
- [ ] All A–O criteria resolved before marking COMPLETE.

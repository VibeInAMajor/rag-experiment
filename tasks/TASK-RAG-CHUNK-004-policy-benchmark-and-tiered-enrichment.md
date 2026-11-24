# TASK-RAG-CHUNK-004 — Cohort-based chunking evaluation, hierarchy and optional enrichment

**Created:** 2026-11-21  
**Updated:** 2026-11-24  
**Status:** PROPOSED — evaluation and rollout blueprint; not an implemented agent  
**Priority:** P2 — optimize only after baselines are actually indexed  
**Dependencies:** completed TASK-RAG-CHUNK-001, TASK-RAG-CHUNK-002, TASK-RAG-002, TASK-EVAL-001, TASK-RAG-PARSE-001; qualified text-layer PDF via TASK-RAG-CHUNK-003; original-evidence and multimodal cohorts additionally require implemented TASK-RAG-CONTENT-001/002/003/004/005 as applicable. Experimental cohorts may be reported NOT_EVALUABLE until their producer is qualified.  
**Repository snapshot reviewed:** historical `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`; refreshed source inspection `a32b0a7a666f8bdef0eeb01d00dbb04a159fcd2f` (2026-11-23)  
**Target:** `tasks/TASK-RAG-CHUNK-004-policy-benchmark-and-tiered-enrichment.md`  
**Architecture:** [Content-aware format/policy decision](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Build a reproducible, **cohort-specific** benchmark and safe policy promotion mechanism comparing recursive, structure-aware, hierarchy/parent expansion and embedding-based semantic chunking; evaluate high-value LLM/agentic enrichment only behind a separate explicit gate.

## B. Context / Problem

**2026-11-23 architecture correction:** the earlier benchmark scope optimized the ratio of retrieved **text chunks** to cost. With [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) and [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md), our target is **Document -> Structured Elements -> Multiple Representations -> Searchable Chunks + Original Evidence**. Consequently, chunking quality cannot be evaluated solely by text Recall@K: the benchmark must also test whether found evidence maps to the correct immutable source/version, original asset/page/table/graph relation and the appropriate confidence/trust state. A VLM paraphrase retrieved at rank 1 is **not** a correct result if it invents an arrow, numeric value, or citation. An OCR-only label list is **not** a successful diagram-understanding result.

This remains a **benchmark and promotion task**, not an implementation task for new OCR, Mermaid parsers, asset storage or visual inference. Specialized producers must be delivered by their own A–O tasks; missing producers are recorded as NOT_EVALUABLE, never fake quality measurements or silently converted to text-only scoring.



The supplied decision tree says static single-fact should use agentic chunking, periodic updates semantic, and high overlap for exact phrases. These are plausible hypotheses but not guaranteed policies; ingestion strategies are chosen before unknown future queries, while query complexity can vary per request. Product decisions must be based on measured retrieval, structural citation and operational cost rather than a categorical rule. Preserve the first PostgreSQL lexical baseline and immutability of active source versions while evaluating alternatives.

## C. Current Repository State

### Refreshed implementation evidence (2026-11-23) — authoritative over older initial observations

| Inspected path / state | Actual current behavior | Impact on the benchmark |
| --- | --- | --- |
| [chunking_profiles.py](../apps/workbench/chunking/chunking_profiles.py) | `ChunkingProfile` has actual token unit and `text-token-r1/r2` revisions; `PythonChunkingProfile` measures **effective lines**; `PdfChunkingProfile` supports approved 512/64, 768/0, 768/64 token child configurations. | Benchmark by **actual declared unit**, not assumed 500 Qwen tokens or words. No converting effective lines to tokens by guess. |
| [document_processing.py](../apps/workbench/configuration/document_processing.py) | `DocumentProcessingSettings.to_profile()` supplies the configured `text-token-r2` profile with sentence/language restrictions and guarded resources. | Pin actual resolved YAML, language policy and tokenizer identity/revision; never claim `o200k_base` equals a qualified Qwen tokenizer. |
| [chunking.py](../apps/workbench/chunking/chunking.py) | `prepare_chunks`, `PreparedChunk.metadata()`, `resolve_chunking` and optional `ModelTokenAdmission` already produce deterministic fingerprints, source spans, headings and parent structural IDs. | **Reuse** production manifests and fingerprints instead of a second splitter implementation. |
| [chunking_adapters.py](../apps/workbench/chunking/chunking_adapters.py) | Existing recursive/Markdown splitting and protected structural boundaries. | Compare policy variants using real split behavior, not reconstructed counts from fixture strings. |
| [parser_registry.py](../apps/workbench/parsing/parser_registry.py) | TXT, Markdown, Python AST and PDF registry are qualified, subject to runtime assets. | Do not call these missing or implement another format detector. |
| [pdf_chunk_preparation.py](../apps/workbench/chunking/pdf/pdf_chunk_preparation.py) | Real PDF child metadata contains `page_number`, `bbox`, `source_span_basis`, `original_excerpt`, `retrieval_sha256`, and `visual_processing_status`. | Page/table provenance tests can run **now**; original asset bytes and diagram semantics cannot be inferred from these metadata fields. |
| [test_pdf_ingestion.py](../apps/workbench/api/tests/test_pdf_ingestion.py) | PDF upload/real SQL tests, negative scanned PDF and a mixed figure fixture that reports `visual_processing_status="incomplete"`. | Reuse baseline and add a false-completeness regression; do not treat figure detection as vision understanding. |
| [test_chunking.py](../apps/workbench/chunking/tests/test_chunking.py), [test_python_chunking.py](../apps/workbench/chunking/tests/test_python_chunking.py), [test_pdf_chunking.py](../apps/workbench/chunking/pdf/tests/test_pdf_chunking.py) and [chunking fixture manifest](../apps/workbench/chunking/tests/fixtures/chunking/manifest.json) | Existing real splitter/format fixtures and regressions. | Reuse and extend labelled cohorts rather than making duplicate baselines. |
| [completed CHUNK-001](completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md), [completed CHUNK-002](completed/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md), [completed EVAL-001](completed/TASK-EVAL-001-prove-vertical-slice.md) | Repository task status is complete for routing, Python AST and baseline lexical UI/SQL evaluation. | The benchmark adds format-specific **paired comparative evidence**, not replacement implementations. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md), [CONTENT-002](TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md), [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md), [CONTENT-004](TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md), [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) | These are detailed **PROPOSED** producer/evidence tasks, not currently implemented proof of original asset or multimodal search. | Benchmark prerequisites for specific visual/OCR/Mermaid metrics; missing capability must be marked NOT_EVALUABLE. |
| [content-aware architecture](../docs-website/docs/architecture/content-aware-chunking-strategy.md) | Source matrix now calls PDF text-layer qualified but reports scan/OCR and original evidence as unavailable. | Preserve this capability truth in the benchmark report and policy promotion decision. |

No application-owned cohort evaluation runner was identified under `apps/workbench/evaluation/` in the inspected tree. Existing tests are correctness baselines, **not** an already completed multi-profile paired benchmark. The older source table below documents the original plan; this refreshed evidence controls implementation decisions.



| Existing source | What is already there | Gap |
| --- | --- | --- |
| [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../haystack/components/preprocessors/embedding_based_document_splitter.py) `EmbeddingBasedDocumentSplitter` | Cosine distance between sentence-group embeddings; supports percentile, min/max length and language. | Already implemented in Haystack; not connected to a qualified TEI/Qwen service or benchmark. Do **not** reimplement. |
| [`haystack/components/preprocessors/hierarchical_document_splitter.py`](../haystack/components/preprocessors/hierarchical_document_splitter.py) | Parent/child chunk metadata. | Parent expansion/query-time service and durable parent relationship not app-qualified. |
| [`haystack/components/preprocessors/recursive_splitter.py`](../haystack/components/preprocessors/recursive_splitter.py) | Reusable recursive baseline. | Word/token units must be honest; default tiktoken != Qwen tokenizer. |
| [`apps/workbench/retrieval/fixtures/lexical-evaluation.json`](../apps/workbench/retrieval/fixtures/lexical-evaluation.json) | 10 exact keyword + 3 diagnostic paraphrase labeled queries. | Good for first lexical baseline, **not** broad evidence for agentic/semantic or format cohorts. |
| [`apps/workbench/retrieval/lexical.py`](../apps/workbench/retrieval/lexical.py) | Genuine PostgreSQL `ts_rank_cd` retrieval. | Cannot claim semantic/multi-hop answer evaluation without a separately qualified retrieval/generation runtime. |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) | Source/version/chunk identities; `Chunk.metadata` for fingerprints. | No currently persisted alternate parent-child index with run-time expansion guarantees. |
| [Parser/strategy architecture](../docs-website/docs/architecture/content-aware-chunking-strategy.md) | Explicit candidates for prose, code, page/table, transcript and structured data. | Need real performance and indexing costs before policy promotion. |

## D. Goal

**Expanded observable outcome:** select a winning **per-cohort ingest policy and retrieval-time evidence expansion policy** only when independent evaluation demonstrates not just retrieval quality but also original evidence correctness, trust-status fidelity, full-content coverage, tenant isolation and acceptable operation cost. Publish separate `SUPPORTED`, `FAILED`, `NOT_EVALUABLE` or `NOT_TESTED` outcomes by format and modality. A global weighted headline score must never hide a severe citation/diagram numeric error in an individual cohort.



Given a fixed gold corpus and a set of revisioned candidate chunking profiles, produce inspectable paired evaluation reports showing metrics, costs and confidence intervals by document format, update frequency and query cohort. A higher-cost profile is adopted only when an explicit acceptance gate and security/cost limits pass; otherwise the default remains unchanged.

## E. Scope

**Explicit modality-aware additions:**

- Test already implemented cohorts immediately: prose/Markdown, Python AST, PDF text pages/tables, standard lexical retrieval and fixed query sets. Include actual visual-coverage warnings from mixed PDFs; do not grade a missing visual asset as a successfully understood diagram.
- Add **conditional** cohorts when producer tasks are genuinely operational: scanned/mixed PDF OCR (CONTENT-002), visual diagrams/flowchart edges and charts (CONTENT-003), Mermaid relation/order/cardinality (CONTENT-004), original-asset evidence resolution (CONTENT-001/005). Producer tasks own extraction accuracy; this task measures end-to-end *chunking, retrieval and evidence utility* while reusing their qualified gold fixtures.
- Support multiple representations from one element: direct source, OCR observation, structured graph, model description and retrieval projection. Evaluate duplicate-indexing risk, child-to-parent expansion and exact source-version linkage rather than treating five representations as five independent documents.
- Ensure all compared profiles have the same accessible source corpus and eligible evidence under each tested modality. Do not unfairly compare a text-only baseline that cannot access images to a vision policy and attribute the difference solely to chunk length.
- Track the cost of **full processing**, including PDF parser/OCR/VLM requests, asset storage, chunk preparation, model-token admission, embedding/indexing and retrieval-time expansion/asset resolution.
- Require explicit per-cohort policy promotion gates, provenance completeness and correct inference trust labels; semantic/agentic enrichment stays opt-in experimental and may **never** override original facts.



- Build reproducible snapshots of source documents, parser outputs, normalized chunk manifests and gold label spans; pin tokenizer/model/retriever versions where applicable.
- Compare: recursive baseline at explicit units; heading/page/table/AST; hierarchical with retrieval-time parent expansion; semantic via existing Haystack splitter only after provider qualification.
- Separate source-format cohorts, update-frequency classes (`static`, `periodic`, `near_real_time`) and query classes (`fact`, `exact_phrase`, `paraphrase`, `multi_hop`, `table_lookup`, `code_symbol`, `speaker_time`).
- Record retrieval/structure/cost/latency metrics, sample counts, uncertainty, negative safety and behavior after partial updates.
- Optional experimental **LLM/agentic enrichment** for a specifically approved high-value corpus with strict content privacy, token budget, output validation and deterministic cache; not enabled by default.
- Provide a reviewable policy-approval artifact before switching a production profile, not automatic reinforcement/agent orchestration.

## F. Non-Goals

**Additional exclusions:** no OCR implementation, new visual model/diagram parser, Mermaid grammar, evidence asset store, new provider, automatic query/answer generation or cross-tenant corpus sharing. Their dedicated CONTENT tasks are prerequisites for a *qualified metric*, not work to be absorbed into the benchmark. No assertion that a SHA256 check proves a VLM inference semantically true. No mutation of the current production active corpus just to compare candidates.



No arbitrary query-time re-chunking of live documents, no uncontrolled agent running on customer data, no paraphrase metrics from pure lexical search reported as generative accuracy, no fabricated Recall lift, no editing core Haystack, no automatic DB reindex of prior production versions or vendor-coupled application policy.

## G. Architecture / Boundaries

**Refined evaluation architecture:**

```text
Authorized immutable source + original asset (when qualified)
   -> verified parser elements / source-version spans
   -> fixed element/representation availability snapshot
   -> candidate chunking policy (same input and parser revision)
   -> isolated candidate index and candidate parent/element links
   -> fixed retrieval/rerank runtime, bounded top-k AND context-token budget
   -> optional authorized evidence expansion (CONTENT-005 when ready)
   -> gold evidence labels: source/span/page/table cell/graph edge/number
   -> separate quality + cost + completeness + security metrics
   -> human-reviewed cohort-scoped policy decision
```

**Ownership:** extraction trust belongs to parser/OCR/vision/Mermaid adapters; immutable element/representation/asset identity to CONTENT-001; evidence resolver and allowed citation payloads to CONTENT-005; this evaluation task only reads them. It must not implement another source store, parser, RAG API, AST grammar or graph verifier. Query-time expansion must use server-resolved workspace and exact source version; no implicit "latest" redirection. Evaluation indexes and asset reads are isolated and bounded, never provided direct public object URLs.



`immutable gold corpus → fixed parser output → candidate policy split → isolated index build → fixed retrieval profile → gold label metrics + cost → human-approved promotion`.

Evaluation engine is provider-neutral: select model capabilities/adapters separately. Query-time `parent expansion` belongs to retrieval service and is versioned independently from ingest policy. Different chunk indices must use isolated evaluation workspaces/versions, never the same active customer corpus.

## H. Contracts / Interfaces / Data Model

### H1. Mandatory evaluation identity

Define `CohortManifest` with `manifest_revision`, corpus fixture/reference hash, workspace/test isolation ID, source_version IDs, exact input asset hashes if available, parser + splitter + tokenizer/model revisions, document modality (text/markdown/code/pdf_table/pdf_scan/pdf_diagram/chart/mermaid), evidence availability flags and disjoint TRAIN/DEV/EVAL labels where optimization occurs.

Define `CandidateRun` with `candidate_id`, processing fingerprint, parser revision, splitter strategy/params/units, embedding service/model and native guard revision if available, retrieval profile/score_type, rerank/parent-expansion revision, evidence-resolver revision, `corpus_revision`, case IDs, sample size, cold/warm status, execution durations and error/skip reasons. Keep SQL lexical `postgres_ts_rank_cd` different from any BM25, cosine or reranking score.

Define `ElementGoldLabel` (existing source id/version + source span/line/page and optional bbox/table row/column, Mermaid edge/message/ER cardinality or visual graph direction/condition), with `evidence_kind`, reference `representation_id?`, original `asset_hash?`, human-audited gold relation/value and unit. Unknown or unjudged source references are **not negative labels**.

Define `EvaluationCase`: query ID, intent class, required evidence elements and facets, source eligibility, expected full evidence set where judged, forbidden false relations/values, and separate expected score classes (exact recall, answerability, multimodal provenance). A multi-hop question may need **two or more** evidence elements; measuring only one retrieved source hit is insufficient.

Define `CaseOutcome`: `run_status` = `PASS|FAIL|NOT_EVALUABLE|NOT_TESTED|ERROR`, retrieved child IDs, expanded parent/evidence IDs, exact citation locators, trust-state labels, evidence coverage, unsupported/inferred assertions, processing warnings and redacted trace IDs. A missing qualified parser/model/asset/resolver yields `NOT_EVALUABLE` with reason code, never a fabricated zero or mock success.

Define `PromotionDecision`: format+intent cohort, incumbent vs challenger fingerprints, paired effect sizes/confidence bounds, integrity/security gates, context budget, cost ratio, eligible sample count, decision/approver, fallback, staged rollout and rollback evidence. No automatic agent decides the policy.

### H2. Metric definitions and integrity gates

- **Source hit@K / MRR@K:** fraction/reciprocal rank of manually relevant source IDs; include all failed eligible queries in denominator. Keep separate from Chroma's token excerpt recall and from answer quality.
- **Evidence recall/coverage@K:** fraction of *all required* manually labeled element/span/table-cell/graph-edge references found in the authorized top-K child results or bounded resolved parent context. Distinguish retrieved-but-not-resolved from original actually available.
- **Citation fidelity:** percentage of returned locators whose (workspace, source, version, page/bbox or line) and SHA256 match gold. Add false-citation and wrong-version counts. `asset_hash_ok` is a byte integrity check, **not** semantic verification.
- **Provenance trust fidelity:** do not classify `model_inferred` as `direct_source` or `human_verified`. Report `unsupported_claim_rate` and `false_verified_rate` separately; require zero false promotion in crafted negative tests.
- **Structure-specific:** Python qualified-symbol first hit and correct line range; PDF row/column/header and page citation; scanned PDF CER/WER/read-order when OCR available; graph node/edge/direction/YES-NO condition; chart axis/scale/unit/value accuracy; Mermaid message ordering/branch conditions/ER cardinality. Missing producer = `NOT_EVALUABLE`.
- **Coverage:** number of original structural elements, protected blocks, source bytes and representations eligible for retrieval versus silently lost; explicit `visual_processing_status=incomplete` counts as known *incomplete*, not a successful fully understood PDF.
- **Efficiency:** actual tokens including heading/enrichment, duplicated context tokens, bytes/asset storage, child/parent expansion inflation, OCR/VLM calls/tokens, parse/ingest p50/p95, search p50/p95, resolver p50/p95, timeouts and failure rate. Report cold/warm and separate ingestion vs retrieval.
- **Comparability:** compare within fixed parser, corpus, embedding/retriever/rerank profile, K and **total context token budget**. Parser/model/VLM changes are separate experiments. Use paired source/query bootstrap CI where sample size permits, and report n and uncertainty.



`EvaluationProfile`: parser_revision, chunker_revision, token_unit/revision, embedding profile, retriever/ranker revision, scoring rubric, corpus hash. `QueryCase`: document/source/element truth spans, query class, expected source/chunk IDs, relevance labels. `EvaluationReport`: size, Recall@K/MRR/nDCG, token-span IoU, citation fidelity, lost-content rate, duplicate-token ratio, stored bytes, ingest/embedding costs, update churn, p50/p95 latency, confidence interval, failure list. `PolicyPromotion`: evidence_path, from_profile, to_profile, cohort, signed decision, explicit rollback. No raw source text or credentials in shared logs. No profile chosen solely by a task ID.

## I. Repository Files / Components Impacted

**Verified existing owners and intended touch points:**

| Path | Impact |
| --- | --- |
| [chunking.py](../apps/workbench/chunking/chunking.py), [chunking_profiles.py](../apps/workbench/chunking/chunking_profiles.py), [chunking_adapters.py](../apps/workbench/chunking/chunking_adapters.py) | READ/reuse real `PreparedChunk`, fingerprints, actual token units, profile revisions and splitters; avoid changing production code just to win a benchmark. |
| [document_processing.py](../apps/workbench/configuration/document_processing.py) | READ current configured r2 sentence/tokenizer policy; snapshot effective config; do not expose private YAML to reports. |
| [pdf_chunk_preparation.py](../apps/workbench/chunking/pdf/pdf_chunk_preparation.py), [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py), [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py) | READ page/table/visual-incomplete provenance and approved PDF policy choices. |
| [tests/test_pdf_ingestion.py](../apps/workbench/api/tests/test_pdf_ingestion.py), [tests/test_chunking.py](../apps/workbench/chunking/tests/test_chunking.py), [tests/test_python_chunking.py](../apps/workbench/chunking/tests/test_python_chunking.py) | REUSE existing fixtures/tests as regression controls; add gold labels, not duplicate splitter implementations. |
| `apps/workbench/evaluation/chunking.py`, `apps/workbench/evaluation/metrics.py`, `apps/workbench/evaluation/cohorts.py` | CREATE **minimal** evaluation modules after inspecting actual app package; avoid parallel search/persistence stacks. |
| `apps/workbench/api/tests/test_chunking_evaluation.py`, `tests/test_chunking_evidence.py`, `tests/test_chunking_promotion.py` | CREATE unit/integration/evidence and policy-promotion tests using test-only corpora. |
| `apps/workbench/api/fixtures/chunking-evaluation/` | CREATE labeled fixtures/manifests for new cohorts with non-sensitive source and original evidence. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md), [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) | READ provider-neutral element/asset/representation and evidence resolver once implemented; no duplicate ContentRepresentation or EvidenceReference models. |
| [CONTENT-002](TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md), [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md), [CONTENT-004](TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) | Import their actual approved gold source/quality fixtures only after capabilities pass; do not implement visual/semantic adapters in the benchmark. |
| `docs-website/docs/architecture/content-aware-chunking-strategy.md` | UPDATE with measured results, cohort decisions and **real** modality availability; no blanket claims. |
| `docs-website/docs/tasks/chunking-benchmark-results.md` (new) | CREATE human-readable benchmark/evidence summary and runbook; record NOT_EVALUABLE cohorts and rationale. |

**MUST NOT change:** `haystack/` splitter implementations, completed task evidence, applied DB migrations, production source/version rows or active content, public search score semantics, authentication, Preview fixtures or CONTENT task provider adapters. Any necessary new relational parent/evidence index is a **separate A–O migration approval**, not a benchmark side effect.



- CREATE `apps/workbench/evaluation/chunking.py` or the existing evaluation package's cohesive location; avoid second score calculation if present.
- ADD versioned curated cohort fixtures under `apps/workbench/api/fixtures/` (non-sensitive, properly licensed) and exact labels.
- ADD `apps/workbench/api/tests/test_chunking_evaluation.py` and separate integration benchmark command under app-specific Hatch environment.
- EXTEND only approved retrieval parent-expansion adapter after reviewing source/version parent metadata contract; possible **separate** migration.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and per-cohort result `.md` summaries, not core Haystack.

### I.1. Source-level reuse matrix — refreshed 2026-11-23

**Recipient code anchors (real files, inspected):**

| Repository file | Existing owner; exact integration role |
| --- | --- |
| [`apps/workbench/chunking/chunking.py`](../apps/workbench/chunking/chunking.py) | current approved recursive/heading-aware prepared chunk policies |
| [`apps/workbench/chunking/chunking_adapters.py`](../apps/workbench/chunking/chunking_adapters.py) | semantic element-aware part building; avoid second chunker |
| [`apps/workbench/chunking/chunking_profiles.py`](../apps/workbench/chunking/chunking_profiles.py) | token/section/policy revisions and PDF profile parameters |
| [`apps/workbench/parsing/parsing.py`](../apps/workbench/parsing/parsing.py) | typed ParsedElement/SourceSpan |
| [`apps/workbench/api/python_code.py`](../apps/workbench/api/python_code.py) | PythonCodeSplitter integration and symbol metadata |
| [`apps/workbench/chunking/pdf/pdf_chunking_adapter.py`](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) | Docling HybridChunker for PDF page/table chunks |
| [`apps/workbench/chunking/tests/test_chunking.py`](../apps/workbench/chunking/tests/test_chunking.py) | current invariant/golden tests |
| [`apps/workbench/chunking/pdf/tests/test_pdf_chunking.py`](../apps/workbench/chunking/pdf/tests/test_pdf_chunking.py) | current page/cell/heading regressions |

**Pinned previous-project candidates (do NOT copy unlicensed code or Qdrant/SQLite infrastructure):** donor commit `955fd049949d3fc462d555be14774e4b255aa15c`.

| Pinned previous-project source | Targeted symbol/behavior |
| --- | --- |
| [`src/enterprise_ai_pipeline/rag/chunking.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/chunking.py) | StructuralChunker: element-aware, stable chunk occurrence, parent/child and span metadata |
| [`src/enterprise_ai_pipeline/rag/json_structural_chunking.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/json_structural_chunking.py) | bounded JSON object/list boundaries, no silent truncation |
| [`src/enterprise_ai_pipeline/rag/diagnostic_structural_chunking.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/diagnostic_structural_chunking.py) | diagnostic structural boundary measurements |
| [`tests/pipeline/test_parsing_and_chunking.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_parsing_and_chunking.py) | baseline structural and parent/path regression scenarios |
| [`tests/pipeline/test_json_structural_chunking.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_json_structural_chunking.py) | numeric/array/object JSON fidelity cases |
| [`src/enterprise_ai_pipeline/rag/chunk_delta.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/chunk_delta.py) | partial/full chunk hash stability across versions |
| [`LICENSE.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) | reuse rights; do not blindly transplant another app's parser |

**Reuse decision gate:** compare current component to donor behavior, list reusable algorithm/contract, incompatibilities and the exact owner of PostgreSQL/model/tokenizer state. Code copying requires permission under [donor LICENSE](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md); otherwise independently implement compatible behavior and port test **scenarios**. Existing completed Workbench components must not be replaced without a measurable reason.

## J. Implementation Requirements

**Extended executable blueprint (preserve the original J1–J5 gates below):**

### J0. Reconcile completed components and capability gates

Re-read the actual inspected source paths and current active task states. Mark completed parser/ingestion/UI lexical work as implemented, qualified PDF/text data where test-proven, and CONTENT-001..005 as PROPOSED until checked runtime evidence exists. Build a capability matrix `cohort -> parser -> source element -> representation -> original asset -> resolver -> search profile`. For every missing link, set `NOT_EVALUABLE` with a concrete reason; do not schedule an unqualified multimodal evaluation as though it had already run. Freeze original/source hashes before any evaluation indexing.

### J0a. Define labelled evidence cohorts before tuning

Reuse `lexical-evaluation.json` for exact-term sanity checks. Curate separate gold fixtures per family: at least 20 meaningful TXT/Markdown queries, 20 Python symbol/line queries, 20 text-PDF/table/page queries, plus >=20 per qualified advanced modality (scanned OCR, diagram edges/conditions, chart numeric/units, Mermaid relations/order). Source/element/asset versions and complete gold evidence sets must be labelled by reviewer. Record unknown/unjudged relevance explicitly; do not assume every non-gold chunk is irrelevant. Deduplicate near-identical paraphrases across train/dev/eval partitions so tuned thresholds do not leak.

### J0b. Execute an isolated per-cohort candidate grid

Use identical normalized **source bytes and parser projection** for policies under comparison. For prose test 384/0, 500/50, 512/64, 768/96 in *verified units*; for Markdown heading-first vs recursive; for Python AST vs generic; for PDF page/section vs table-row children and exact page locators. Pin `text-token-r2` config and actual tiktoken counter when that is the experimental unit; do not advertise as native Qwen units. Test no-overlap controls. For each candidate create a distinct disposable evaluation index/snapshot, run identical actual authorized retrieval calls, collect child ranks/raw scores and source-version IDs, and never copy mock Preview responses into metric computation. Use one fixed K **and** one fixed context-token budget to prevent longer chunks from gaining free evidence capacity.

### J0c. Integrate original evidence **only after** source producers are ready

CONTENT-001/005 supply exact asset and evidence references. Evaluate small-to-big parent expansion against the actual authorized element/representation graph: child -> parent (same workspace/source/version) -> original asset -> checksum + provenance check. Record false missing/incorrect page/line/crop/graph reference. A retrieved model description cannot be counted as `human_verified`. Model-inferred diagram edges or chart numbers without corresponding gold observation must count as unsupported; no figure category can pass on figure-detector metadata alone.

### J0d. Add OCR, visual and Mermaid cohorts conditionally

For CONTENT-002 scans: measure CER/WER, page-level OCR completeness, reading order, duplicate hidden text and bounding-box citation; only if a real OCR adapter is qualified. For CONTENT-003: evaluate edge direction, condition labels, chart axis scale/unit and numerical claims against manual source-image gold, and count false verified assertions; only if VLM/crop producer exists. For CONTENT-004: test deterministic Mermaid graph source spans, flowchart YES/NO, sequence message ordering and ER cardinality by supported family; unsupported family must not score "correct" from raw text alone. Keep retrieval/evidence metric reporting separate from the producers' extraction quality metrics; do not reimplement the producers.

### J0e. Optional enrichment and trustworthy parent expansion

Use the existing Haystack EmbeddingBasedDocumentSplitter only with a **qualified** embeddings adapter; do not run an unsolicited model just because experimental semantic splitting exists. Compare semantic splitting and model-based contextual descriptions against deterministic structural baselines. Enrichment outputs are `derived` or `model_inferred` representations, cannot overwrite original evidence, and must have bounded token/cost, source hash, processor revision and safe schema validation. Parent expansion is query-time, bounded, version-scoped and authorized; do not join to another workspace or historical version by fuzzy title matching. Keep agentic processing a separate opt-in **research** gate even if it wins a trial.

### J0f. Analyze failures and decide promotion safely

For every run publish evidence coverage, ranked hit/citation outcomes, incomplete/unsupported cases, paired uncertainty, processing cost and retrieval latency; compute change at the **cohort level**. Preserve the original J5 proposed +3 percentage points/+0.03 MRR/<=20% cost threshold as **a candidate discussion guardrail**, not an unconditional universal winner criterion. Hard gates override metric gains: zero verified-false claims in crafted negatives, no cross-workspace leakage, no silent visual loss, no missing-original citations and no corruption of previous active versions. Promotion requires a human-reviewed rollback plan, staged cohort pointer activation and demonstrated recoverability. Other cohorts keep their previous profile.



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

### J7–J14. Detailed, source-grounded implementation handoff — 2026-11-23

**Step J7 —** Before adding new code, compare current `PreparedChunk`/Haystack parser to donor StructuralChunker on same JSON, Markdown, fenced code and AST Python fixtures. Produce a **gap table**: elements lost, headings/parents detached, occurrence ID drift and ingestion speed. If current engine already covers a case, reuse it.

**Step J8 —** Treat donor StructuralChunker as a source of structural boundary and parent/child **invariants**, not as a replacement for current `ChunkingPolicyResolver`. Current profile identity and tokenizer unit must remain authoritative; do not reset existing committed source versions for benchmark runs.

**Step J9 —** Add source-safe JSON/YAML/CSV structural cohorts only if an authorized parser registry supports format; compare donor json_structural_chunking's duplicate key, nesting depth, unknown scalar, oversized array and record chunk handling. Do not silently import donor runtime classes.

**Step J10 —** Define normalized map `(workspace,source,version,element_id,source_span,heading_path,structural_parent,processing_revision)` across both strategies; verify read source offsets and preserved tables/method signatures, especially in mixed documents.

**Step J11 —** Run equal-token-budget evaluation across 384/0, 500/50, 512/64 and 768/96 for prose, headings, JSON records and 100–350-token AST units. Distinguish native Qwen guard versus `o200k_base` chunk sizing, and compare under same model/index generation.

**Step J12 —** Port donor parsing/JSON test fixtures **as independent small cases**, not tests coupled to Qdrant/Root/SQLite. Add human-labelled source/line/table/parent citation accuracy, plus no-loss checks.

**Step J13 —** Decision gate: if donor semantics improve per-format recall/structural fidelity without unacceptable parse/embedding overhead, extend current strategy adapter via small code change and new profile revision; otherwise record NO-GO and retain current splitter.

**Step J14 —** With DELTA-001 coordinate embedding-input hash changes; even if split text stays unchanged, new representation prefix/parent policy may require reembedding. Record cache invalidation and cross-workspace isolation.

**Mandatory dependency handshake:** Current [CHUNK-001](completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) is COMPLETE; treat source donor chunker as a measured policy candidate, not already integrated.

## K. Security / Governance / Observability

**Multimodal trust and retention requirements:** untrusted PDF images, Markdown Mermaid code, OCR labels and VLM descriptions must never be executed or used to choose a model/provider. For benchmark gold/evidence files, use non-sensitive or explicitly approved content with license and retention recorded; do not persist original customer scans in public evaluation fixtures. Evaluate using a server-resolved test workspace, protected original asset reads and forced RLS; all child-parent-evidence joins must enforce the *same* workspace/source/version. Treat SHA256 as byte-integrity only, not proof of diagram semantics. Distinguish direct_source, deterministic_parse, observed_OCR and model_inferred in metrics and logs; never promote inferred relation to verified merely because a model provides a confidence number. Redact raw file bytes, OCR transcripts, images, prompts, personal data and credentials from logs/reports. Account separately for OCR/VLM token/image costs, staging/retention of original assets and deletion of evaluation copies. No automatic use of remote models or hidden fallback that changes test population.



Use only approved/test corpora and opt-in privacy policy for model-based enrichment. Untrusted documents may contain prompt injection; no assistant/code tools operate on them, no private material sent to an unapproved provider. Test cross-workspace isolation for parent expansion; user query does not change authorization scope. Attribute cost and tokens per workspace/corpus without logging prompt/document raw text. Retention and deletion of evaluation copies need explicit policy.

## L. Testing / Evaluation / Runtime Verification

**Expanded test matrix and runbook:**

| Test family | Required verification | Expected outcome |
| --- | --- | --- |
| Metric unit | Known hit@K, reciprocal rank, evidence coverage with 2 required elements, ties, excluded/errored cases and paired CI | All metrics preserve denominators and show NOT_EVALUABLE separately; no silent drop of failed eligible cases. |
| Replay determinism | Same corpus and profiles in two isolated evaluation indexes | Same processed manifest, source references and deterministic candidate IDs; report measured runtime variance separately. |
| Existing lexical baseline | Reuse `test_chunking.py`, `test_python_chunking.py`, `test_pdf_chunking.py`, `test_pdf_ingestion.py`, `lexical-evaluation.json` | No changes to SQL `postgres_ts_rank_cd` or active source publication. |
| Parent/context expansion | Same active source/version with bounded context budget; foreign workspace; old version | Only authorized matching-version parent; refusal on guessed/fuzzy/stale matches. |
| PDF text+figure | Existing mixed-figure fixture `visual_processing_status=incomplete` | Text retrieval may succeed; diagram semantic/evidence metrics are NOT_EVALUABLE until producers qualify. |
| OCR conditional | Scanned and mixed native/OCR + page/box gold | CER/WER and wrong-page count only when OCR producer exists; otherwise explicit NOT_EVALUABLE. |
| Visual conditional | Arrow direction/YES-NO, chart numerical axis/units | False verified rate and evidence support counted; missing VLM never masquerades as success. |
| Mermaid conditional | Source-code flowchart, sequence message order, class/ER supported families | Every relation cites original line span; unsupported grammar reported separately. |
| Cost/performance | Cold/warm parse/split/embedding/OCR/VLM/asset/resolve/retrieval | Separate stage p50/p95, invocation counts, asset bytes, duplicates, timeouts and source count. |
| Security/integrity | Asset tamper, wrong content hash, foreign scope, no original, model-inferred claim | Zero leaked bytes, zero fabricated verified relation, no silent unsupported evidence resolution. |
| Deployment policy | candidate fails integrity gate despite better source hit@5 | Promotion rejected, old profile stays active and rollback is proven. |

Run the repository's actual app targets from root: `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`. Use disposable PostgreSQL and isolated asset roots; compare source snapshots by immutable hashes and explicitly distinguish `PASS`, `FAIL`, `SKIP`, `NOT_EVALUABLE`, `NOT_TESTED`. Never claim a browser/SQL/GPU benchmark ran merely because this document specifies it. Add test evidence under `tasks/evidence/` and a human-readable **Markdown** results report, with every command and revision captured.



- Unit metric identities, ranking ties, missing truth, confidence interval implementation and candidate selection invariants.
- Integration exact SQL/HTTP parity, immutable source versions, isolation of alternate evaluation indexes and parent expansion.
- Golden spans for headers, PDFs/table rows, code line/symbol, chat turns/timestamps and multilingual data.
- Negative prompt-injection and schema-invalid LLM output, timeout, quota, offline TEI, cross-tenant parent request, no parser.
- Regression preservation of `postgres_ts_rank_cd` and basic TXT/Markdown reference results.
- Run focused Hatch checks and materialize benchmark JSON/MD evidence with environment/corpus hashes and PASS/FAIL/SKIP.

### L.1. Reuse-specific test migration and verification

- [ ] At least 20 per-cohort source/evidence queries, absolute source-span coverage, parent/child correctness, repeated identical text occurrences, JSON nested structures/duplicate keys, Markdown Mermaid fences, table headers, AST method bounds and no blank chunks.
- [ ] Compare current and donor-derived policy in isolated disposable profiles, never training/eval leakage; use same retrieval top-k and max evidence token budget.
- [ ] Record processing cost, embedding calls by profile, Recall@5/MRR/nDCG (only with labels) and no-indexed-original claims for unsupported PDF/OCR/visual cases.

**Proof requirements:** record donor behavior source commit, recipient code and exact executed test commands. Donor unit tests **do not** demonstrate recipient functionality; recipient CI evidence must exercise the actual PostgreSQL/TEI/client paths. Capture a fixture-vs-runtime result matrix, error correlation and no-secrets logs.

## M. Acceptance Criteria

**Additional must-pass gates for the expanded content/evidence architecture:**

- [ ] Cohort manifests and evaluation pipeline use existing parser/processing profiles, actual source versions and retained original asset hashes where available; no duplicate search engine/indexing policy.
- [ ] TXT/Markdown, Python and text-PDF/page/table tests run on the qualified current implementation; unavailable OCR/VLM/Mermaid producer cohorts are explicitly `NOT_EVALUABLE` rather than scored as successful.
- [ ] For every qualified evidence cohort, report source hit@K **and** all-required-element coverage, true citation/source-version correctness and trust-status fidelity; no single global metric hides modality failures.
- [ ] Parent expansion uses only authorized matching source/version and a fixed context token budget; wrong-workspace/wrong-version returns zero unauthorized parents or assets.
- [ ] Existing mixed-PDF visual incomplete state is preserved; no benchmark assumes figures have been interpreted just because page text was indexed.
- [ ] Once CONTENT-001/005 are operational, original-asset hash/locator check, evidence read/404/503 tests and no-false-trust negative tests pass before a representation can enter verified search claims.
- [ ] Conditionally enabled OCR reports page/CER/WER/read-order; Mermaid reports graph relation/order; visual reports edge/condition and chart unit/number faithfulness with denominators and failure cases.
- [ ] Source/reference score semantics are truthful: PostgreSQL FTS not renamed BM25, generic tiktoken not renamed Qwen native tokens, SHA hash not presented as semantic grounding.
- [ ] Candidate policy changes are a reviewed cohort-scoped decision with paired evidence, quality **and** cost, explicit known failures and rollback; no automatic promotion or customer corpus mutation.
- [ ] Old parsing, chunking, ingestion, PDF, lexical/API and security regressions pass with actual logs, and report filenames are Markdown for human documentation.



- [ ] Every compared profile has identical fixed corpus/labels and clearly pinned parser/tokenizer/retriever configuration.
- [ ] Report includes Recall@5/10, MRR/nDCG, citation fidelity, duplicate ratio, indexing cost and latency with sample counts/uncertainty by cohort.
- [ ] Zero unapproved model invocation or silent semantic/agentic fallback; unavailable embeddings remain explicit.
- [ ] Parent expansion returns only authorized active parent and respects bounded context; zero cross-workspace leaks.
- [ ] No default strategy is promoted solely by the supplied decision tree; documented gate, evidence and rollback must exist.

- [ ] Donor StructuralChunker and json_structural_chunking reuse or rejection decision is explicitly justified against existing Haystack adapters
- [ ] Donor parsing/JSON golden scenarios are integrated as independent source-format tests
- [ ] No duplicate chunker or new data store introduced when current structured logic already covers a case

## N. Documentation / Migration / Compatibility / Rollback

**Compatibility with multimodal roadmap:** CONTENT-001 owns structural element/asset/representation persistence, CONTENT-002/003/004 own OCR/vision/Mermaid producer qualification, CONTENT-005 owns evidence resolution. This task must NOT add substitute SQL tables or publish an inferred asset as original. The current `parent_structural_id` and JSONB metadata support initial experiments, but an authorization-safe durable parent/evidence index requires explicit inspected source and possibly a separately approved migration. Report `NOT_EVALUABLE` while unavailable; never retroactively rewrite original PDF/Markdown, embeddings or archived benchmark records. Rollback a promoted cohort to its previous immutable profile/processing revision with a documented reindex/corpus snapshot; leave other cohorts and current source versions untouched. Docs must distinguish measured results from planned capabilities and explain why a lexically high-ranked description can still fail original-evidence correctness.



Evaluation runs may use dedicated disposable data/index spaces; never overwrite production active versions. If parent-child provenance needs relational indexes, create a separate full A–O migration task. Keep parser/chunking profiles immutable and versioned; promotion changes a pointer/config profile, not already indexed source IDs. Rollback restores prior approved profile and reindex plan without deleting PostgreSQL data. Research-only agentic experiments remain disabled without a subsequent reviewed enablement task.

## O. Mandatory Completion Checklist

- [ ] Current qualified PDF/Python/TXT/Markdown source and completed task states re-inspected; no obsolete missing-component assumptions retained.
- [ ] CONTENT-001..005 dependencies and NOT_EVALUABLE semantics explicitly enforced per advanced cohort.
- [ ] Original source/evidence provenance, multi-representation trust, visual and OCR/graph-specific metrics implemented only when producers exist.
- [ ] Per-cohort query labels, corpus/version hashes, token unit and source-identity controls verified.
- [ ] Parent expansion and evidence authorization tested at source **and** version granularity.
- [ ] Cost includes ingestion, OCR/VLM/model inference, assets and evidence resolution where applicable, not only embedding cost.
- [ ] Human review rejects candidates violating citation/scope/trust correctness despite improved Recall.
- [ ] Measured results/commands in Markdown and raw permitted test artifacts linked; missing tests clearly marked.
- [ ] Previous completed routing/AST/PDF/lexical tests retained as regressions.
- [ ] No task is marked COMPLETE based on document creation or synthetic performance claims.



- [ ] Existing Haystack semantic/hierarchical components reused where applicable.
- [ ] Each corpus and query cohort gold set versioned with provenance.
- [ ] Evaluation/policy promotion reports and negatives executed, not simulated.
- [ ] Privacy/cost and tenant isolation gates passed; no hidden model use.
- [ ] Compatibility, rollback and documented strategy decision updated.
- [ ] All A–O criteria resolved before marking COMPLETE.

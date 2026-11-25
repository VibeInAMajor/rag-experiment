# TASK-RAG-CONTENT-003 — Visual diagrams, flowcharts, and chart understanding

**Created:** 2026-11-23  
**Updated:** 2026-11-26  
**Status:** PROPOSED — implementation blueprint; no qualified visual inference service exists  
**Priority:** P1 — visual evidence after content assets and PDF layout  
**Dependencies:** TASK-RAG-CONTENT-001, TASK-RAG-CHUNK-003; OCR-dependent scanned cases also require TASK-RAG-CONTENT-002  
**Repository snapshot inspected:** 522c2cb38aff746e65a8f04ea48d88d3695fc5a9  
**Target:** tasks/TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md

## A. Title

Detect graphical elements in PDFs, preserve authorized exact image evidence, derive bounded visual descriptions and typed graph/chart representations using a provider-neutral capability, and publish only verifiable search projections without treating model inferences as original facts.

## B. Context / Problem

Text extraction can return all labels of a flowchart while losing arrow direction, decision branches and conditional edge labels. Charts are more dangerous: describing a trend does not establish correct axis scales or numerical data. A text-search pipeline that indexes a fabricated visual description can confidently answer the wrong question. Conversely, a visual diagram may occupy only a bounded region on a page and can be retained as exact image evidence. We need representation plurality: source crop, observed labels, candidate relations, confidence/verification and retrieval text, all linked to source and version. Do not use plain OCR as a graph parser.

## C. Current Repository State

### C0. Source and parser-family status reconciliation

**Source reinspection 2026-11-23:** the current PDF parser has qualified text-layer/page/table mechanics and explicitly incomplete visual semantics; [parser_registry.py](../apps/workbench/parsing/parser_registry.py) reports no OCR/visual understanding despite Docling availability. [PARSE-002](TASK-RAG-PARSE-002-office-and-web-document-parsers.md) and [PARSE-003](TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md) remain proposed and **do not** qualify embedded slide/workbook charts today. No approved VLM or graph representation exists.

| Exact repository source | Verified state and gap |
| --- | --- |
| [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py) | PdfBlock.kind accepts only text, heading, caption and table. PdfBox is validated and page-qualified; no diagram/chart, nodes/edges, axis or numeric series yet. |
| [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py) | Quota-limited Docling worker extracts bounded text/layout/table blocks, disables network. The worker is NOT a trusted source of visual graph semantics. |
| [pdf_parser.py](../apps/workbench/parsing/pdf/pdf_parser.py), [pdf_sandbox.py](../apps/workbench/parsing/pdf/pdf_sandbox.py) | A bounded subprocess execution and one-slot parser gate exist; reusing a child boundary is required for untrusted PDF rasterization. |
| [pdf_assets.py](../apps/workbench/parsing/pdf/pdf_assets.py), [pdf_asset_manifest.json](../apps/workbench/parsing/pdf/pdf_asset_manifest.json) | Reviewed layout/table models; no approved picture understanding or visual LLM asset set. |
| [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) | Distinguishes original_excerpt from retrieval content and retains tables; not a diagram parser. |
| [parsing.py](../apps/workbench/parsing/parsing.py), [parser_registry.py](../apps/workbench/parsing/parser_registry.py) | App-owned verified format/element contracts, but ElementKind lacks chart/diagram qualified outputs. |
| [chunking.py](../apps/workbench/chunking/chunking.py), [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) | Proven versioned prepared chunks and atomic publication; use them for searchable descriptions. |
| [models.py](../apps/workbench/persistence/models.py), [postgres.py](../apps/workbench/postgres/postgres.py) | Chunk metadata and PostgreSQL FTS exist; no trusted original image storage or graph relation registry. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | Defines document assets/elements/multiple representations and authorization; must be implemented before publishing derived graphics. |
| [Docling pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/) | Picture classification/description are optional configurable capabilities, NOT proof those models are installed in the app. |

The local Qwen3-Embedding-4B target is a text embedding model, **not** an automatically available vision-language model. This task must not assume a GPU model exists or install remote APIs silently. Current repo has no application-owned image crop/evidence lookup or structured graph schema. These are design gaps, not already observed hallucinations.

## D. Goal

For an authorized, bounded document containing a detectable visual diagram or chart, persist an exact source image/crop with page/bbox, register typed visual elements and independent observed/inferred representations, and optionally call an explicitly qualified vision adapter to extract graph/chart structure. A caller can retrieve a searchable description and the **original** evidence, distinguish verified from guessed relationships, and see an explicit unverified/error outcome when confidence is inadequate. No silent numeric invention or arrow reversal may be accepted as verified data.

## E. Scope

- Bounded figure/chart/diagram detection and cropping from verified PDF page geometry, with exact source version identity and image SHA256.
- An application-owned VisualUnderstandingPort separating provider-neutral capabilities: picture_classification, diagram_relation_extraction, chart_structure_extraction and optional text_description.
- A reviewed local/offline VLM adapter only when available and qualified; deterministic observed-text/layout paths can work without it.
- Typed DiagramNode/DiagramEdge/DecisionCondition and ChartAxis/Series/Point with original visual locator and provenance_state (observed, model_inferred, human_verified); use null for unknown labels/values.
- Representation lifecycle: original asset -> observed OCR labels -> unverified graph/chart candidate -> validated retrieval text; no loss of the original.
- Verify graph consistency and numeric parsing (axes, units, series, legend), record reviewer/quality status, fail or downgrade if unreliable.
- Extend chunking projection and current PostgreSQL publication with source/version/element references, plus quality evaluation and negative security tests.

## F. Non-Goals

No OCR engine implementation (CONTENT-002), no Mermaid source parsing (CONTENT-004), no auto-generated image editing, no general chat reasoning model, no universal vector-image embeddings, no training/finetuning a VLM, no default remote image uploads, no full digital-twin graph database, and no reproduction of charts by guessing unobserved values. PNG/JPEG uploads outside an authorized PDF/source are deferred unless separately added to parser registry and contracts. Do not claim support for chart data extraction on all chart families based on successful detection.

## G. Architecture / Boundaries

### G0. Explicit PARSE/CONTENT ownership contract — no duplicate parsing/persistence

- **Source parsing is NOT here:** format-specific [PARSE-002](TASK-RAG-PARSE-002-office-and-web-document-parsers.md) extracts slides/embedded-media placeholders; [PARSE-003](TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md) extracts sheets/tables; existing [PDF CHUNK-003](TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) extracts page blocks. They provide `ParsedElement` and verified image/crop/page/slide/row hints where genuinely available, not VLM content.
- **This task uniquely owns interpretation:** versioned `VisualUnderstandingPort` and typed candidate diagram nodes/edges/conditions plus chart axes/series/numeric uncertainty. It receives **already detected/cropped** visual source elements through one shared element/asset contract. No new DOCX/XLSX/PDF parser, blob store, or source writer.
- **Supported input gates:** first PDF images after [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md); Office slide and workbook chart adapters are **future per-format extensions** requiring the PARSE input family qualification and an explicit source-coordinate policy. Do not mark these formats visually supported merely because a common VLM port exists.
- **Not Mermaid:** [CONTENT-004](TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) parses original Mermaid grammar deterministically rather than analyzing a rendered picture. [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) owns evidence resolution, not model inference.

[x] application visual element projection, [x] provider-neutral inference port, [x] bounded adapter, [x] evidence assets, [x] existing ingestion + PostgreSQL, [x] retrieval provenance, [x] security, [x] observations/tests; [ ] arbitrary agent runtime. Dependency graph:

    PDF/verified page -> bounded crop/figure detector -> OriginalAsset
       -> optional OCR labels (observed)
       -> VisualUnderstandingPort (candidate nodes/edges/chart series)
       -> deterministic schema/geometry/numeric validator
       -> ContentRepresentation(provenance=model_inferred or human_verified)
       -> safe retrieval-text projection via existing chunking and publisher
       -> secured evidence resolution (CONTENT-005)

Providers must be selected by registered capability/version, not model vendor strings scattered through application core. The inference model may propose; only deterministic checks/human review can promote facts to reviewed. Model confidence cannot be blindly treated as calibrated probability.

## H. Contracts / Interfaces / Data Model

**VisualElement**: workspace/source/version/element IDs, kind diagram/chart/figure, page (1-based verified), PdfBox or equivalent normalized geometry and explicit coordinate frame, image asset ID/hash, detected_caption?, detector/revision and extraction/verification state.

**DiagramGraph**: graph_id, schema_revision, directed/undirected, nodes[{node_id,label?,shape?,observed_text_ref?,bbox?}], edges[{edge_id,from,to,label?,condition?,direction?,observed_arrow_ref?}], groups/subgraphs?, ordering if relevant, source_element_id, provenance. A graph with ambiguous arrow heads MUST record unknown direction and must not fabricate YES/NO relationships. Duplicate IDs/dangling edges/cycles outside declared flow semantics fail typed validation.

**ChartData**: chart_id, chart_type? (bar,line,scatter,pie,etc.), title?, axis labels and units with unit provenance, legend/series, points[{x?,y?,value?,unit?,bbox?,evidence_ref?,certainty}], scale type (linear/log/unknown) and digitization_method. Numeric values parsed from pixels without verified scales are **estimates** and may NOT be published as exact observations. Confidence alone does not authorize financial/engineering numeric answers.

**RepresentationEnvelope**: type/source version/asset; kind observed_label_text | structured_graph | chart_data_candidate | model_description | retrieval_projection; processor_id/revision, schema_revision, input_hash, warning codes, verification_state, evidence_refs. Store retrieved text separately from original excerpt. A derived description must not include unsupported relations stated as facts; uncertain relations are skipped or explicitly marked uncertain.

**VisualUnderstandingPort**: describe_image(ImageRequest, profile) / extract_diagram / extract_chart (only supported methods) -> typed bounded result + processor metadata. Capability negotiation includes vision, diagram_edges, chart_axes, max_pixels, max_output_nodes/edges, local/offline eligibility, deadline, supported language and model revision. Do not create a default fake provider in Live.

**Error cases**: FIGURE_UNDETECTED, IMAGE_ASSET_MISSING, VISION_UNAVAILABLE, VISUAL_STRUCTURE_UNCERTAIN, ARROW_DIRECTION_AMBIGUOUS, AXIS_SCALE_UNKNOWN, CHART_NUMERIC_UNVERIFIED, RESOURCE_LIMIT, UNTRUSTED_OUTPUT. Map only through current safe API ErrorResponse; no stack/raw image bytes in logs. Partial searchable caption can remain available while graph-specific capability reports unavailable.

## I. Repository Files / Components Impacted

Expected new app-owned visual_models.py, visual_processing.py, visual_adapter.py, tests/test_visual_processing.py, tests/test_visual_knowledge_integrity.py and synthetic fixtures (small source-safe PNG crops with known arrow/numerical gold labels). Extend pdf_models.py and pdf_worker.py only to **observe** picture/figure regions and verified page crops, not to unconditionally invoke a VLM. Reuse pdf_parser.py/pdf_sandbox.py for safe source handling; CONTENT-001 asset store/representation contracts for storage; ingestion.py/postgres_ingestion.py for atomic searchable projections. Extend parser_registry.py only when capability tests pass; add operator profile config and docs under docs-website/docs/architecture/. Modify contracts.py/openapi.json only for approved new evidence features. MUST NOT change haystack/ library, 0001/0002 migrations, current text FTS ranking, validator semantics, Preview fixtures or upstream Docling class internals.

## J. Implementation Requirements

### J1 — evidence and taxonomy first
Inventory actual Docling picture, table and caption output in the pinned runtime, including which objects expose reliable page/bbox. Build at least 20 diagram fixtures and 10 chart fixtures with manually audited source images, gold nodes/edges/axes/labels. Store immutable test image hashes and expected provenance; no production documents in fixtures. Document which figure types can be detected without inference.

### J2 — capture exact images safely
Add bounded raster/crop extraction in the existing PDF process, reusing its no-network, quota, timeout and PDF catalog preflight. Validate page dimensions, crop containment and pixel allocations; protect against image decompression bombs. Store original source/page/figure crop via CONTENT-001 in a staged, hashed asset. Never substitute a model-rendered image for source evidence; cropped visual must remain associated with original PDF page and version.

### J3 — implement typed graph/chart extraction
Create schema validators independent of model APIs and a narrow VisualUnderstandingPort. Integrate a qualified offline adapter only after documenting model revision, availability, output type, performance and license. A VLM can return candidate JSON; decode as untrusted, reject unknown fields, overlong strings, edges referencing nonexistent nodes and chart values unsupported by observed axes. Bind all output to source visual element and parent evidence. Unavailable model should preserve the original figure and expose unprocessed state, not a fabricated summary.

### J4 — semantic reconciliation without hallucination
Associate OCR labels and detected arrow regions where available. Require explicit evidence for direction, edge labels and YES/NO conditions. For charts, require readable axes/scales/units/legend before publishing exact series values; compare OCR numeric glyphs against parsed output. Retain alternative ambiguous candidates for review without indexing them as indisputable facts. Never let model output override source evidence bytes; keep model_inferred and human_verified states separate.

### J5 — retrieval projection and API handoff
Generate bounded human-readable retrieval text from **approved** graph facts and verified captions/labels, including element/source/version/evidence IDs in provenance, not raw image bytes or base64. Large diagrams become several child subgraph projections linked to one full graph parent. Use same chunking profile/fingerprint and idempotent SQL publication as existing ingestion. Preserve original excerpt field distinct from context-enriched summary. Publish capabilities for figure search, structural graph extraction and exact numeric chart retrieval **separately** when each has tests; no vector-image claim unless a genuine multimodal embedder is later qualified.

### J6 — quality/regression gate
On 20+ diagrams, measure node label hit rate, correctly oriented edges, decision-condition exact accuracy, unsupported-edge false positive rate, evidence/source citation accuracy and retrieval hit@5. On 10+ chart fixtures, measure axis/scale correctness, table/point agreement and numeric-answer unsupported rate. Test one corrupted arrow label, ambiguous arrow crossing, log-axis chart, unreadable value and PDF with picture-only page; require explicit uncertain states. Verify cross-workspace denial, asset hash tamper, missing VLM, timeout, restart, idempotent reingestion and old source version preservation. Report p50/p95 time and model invocation count separately; do not call the service "accurate" based on one example.

### Microsoft visual sample adaptations and source fidelity — 2026-11-26

Use pinned [visual document notebook](https://github.com/Azure-Samples/azure-ai-search-with-content-understanding-python/blob/82ade360894b5b7959ef546cbfe96f0ff9e1cc81/notebooks/search_with_visual_document.ipynb) and chart analyzer schema as reference. Adapt bounded figure cropping and structured fields (title/type/axes/series/units/values/footnotes) within existing PDF worker, validating coordinate frame, rotation, page and multi-region bounds. Do not insert descriptions into original Markdown or reuse invalidated original offsets. Keep unknown values null; exact chart data requires source support. Evaluate original image/region fidelity, field precision/coverage, invalid numbers/units/edges, known-facet retrieval and original evidence chain per [quality/content plan](quality/RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md). Agent verifies gold against actual images; no external reviewer or Azure dependency. Missing local VLM is explicit not evaluated, not a fabricated description.

## K. Security / Governance / Observability

Treat graphics, OCR labels, Markdown, model responses and extracted text as untrusted data; never execute displayed code or follow image/link URLs. No arbitrary provider URLs or prompt/body selected by source document. Verify image hashes, bounded crop geometry, allowed content types and per-workspace byte access. Model prompts and output schemas must be versioned, and should instruct extraction not obedience to embedded text; enforce by post-validation, not prompts alone. Keep token/image and VLM invocation budgets explicit; no covert remote exfiltration. Logs retain only trace/job/source/asset/processor IDs, latency, safe failure counts and review state; redact raw image, text, VLM output, keys and customer data. Subject asset deletion/retention to CONTENT-001 policy.

## L. Testing / Evaluation / Runtime Verification

Run workbench-api Hatch test/types, then focused synthetic visual tests in app test environment and disposable PostgreSQL with temporary asset root. Required unit tests for Pydantic/typed graph contracts, dangling/duplicate nodes, invalid bbox, unknown axes, numeric mismatch and confidence handling. Integration: PDF extractor -> crop asset -> candidate representation -> bounded chunk -> PostgreSQL -> source/evidence lookup; test with and without a fake/stub vision provider and with one **real** qualified provider only as an explicit optional smoke. Negative: VLM hallucinated extra edge, reversed arrow, mislabeled axis, dangerous markup, oversized image, expired review, foreign workspace, missing original asset, crash recovery and no-network. Capture real artifact IDs and test outputs; no mock benchmark disguised as real VLM quality.

## M. Acceptance Criteria

- [ ] Detect and hash at least 20 known diagram regions and 10 chart regions with verified page/crop evidence and stable source IDs; record misses.
- [ ] No visual representation becomes "observed" merely by VLM output; observed/model_inferred/human_verified remain distinct in persisted records and API.
- [ ] No hallucinated edge, fabricated axis or numeric point is published as a verified relation in adversarial gold cases.
- [ ] Full diagram graph and smaller retrieval children link to the **same** immutable original image asset, source version and page.
- [ ] A diagram question retrieves correct element/representation and original evidence, with source and page attribution.
- [ ] Unavailable VLM and unclear chart/arrow produce safe, explicit incomplete states rather than invented answers.
- [ ] Diagram edge/condition and chart scale/value metrics are recorded with denominators and real candidate provenance; no universal accuracy claim.
- [ ] Workspace isolation, process isolation, storage tampering and restart negative tests pass.
- [ ] Existing PDF table/heading, TXT/Markdown/Python, SQL and search regression suites remain green.
- [ ] API capability flags distinguish visual description, graph extraction and chart numeric extraction exactly.

- [ ] Actual crop/field source-fidelity and retrieval comparisons with validated locators, null unknowns, zero falsely verified values/edges; no original offset mutation.

## N. Documentation / Migration / Compatibility / Rollback

Build on CONTENT-001 storage migration, not a second image store. Do not modify historical source/version hashes on reprocessing: new inference and chunk representation revisions get new immutable provenance/fingerprints. Document model/resource qualifications, types supported, visual errors, human-review path and numeric chart limitations. Roll out asset detection first (no VLM), optional VLM candidate next, verified graph search last. Roll back by disabling visual inference and maintaining original assets and earlier text chunks; never delete source files because VLM is unavailable. Image vector embeddings, advanced multimodal reranking, chart arithmetic and UI overlay tools are deferred scoped features.

## O. Mandatory Completion Checklist

- [ ] Current PDF extraction code, Docling capabilities and source models re-inspected.
- [ ] Exact source crop storage implemented through CONTENT-001 (no duplicate blob store).
- [ ] Diagram/chart typed schemas and verified versus inferred state tested.
- [ ] Provider-neutral visual inference seam used; no unsafe remote/default inference.
- [ ] Every candidate graph/chart numerical claim traceable to original evidence or explicitly unverified.
- [ ] Search projection, parent relation, score semantics and tenant checks verified.
- [ ] Quality, negative/security, crash/restart and legacy regressions actually executed.
- [ ] Metrics, model versions, failure samples, latency and resource cost published.
- [ ] Capabilities and documentation show only measured enabled features.
- [ ] Mark COMPLETE only after real evidence is recorded.

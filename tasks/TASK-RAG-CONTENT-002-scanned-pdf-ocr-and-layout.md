# TASK-RAG-CONTENT-002 — Scanned and mixed PDF OCR with page-accurate provenance

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — implementation blueprint; scanned-PDF support not qualified  
**Priority:** P1 — after evidence storage and existing PDF parser qualification  
**Dependencies:** TASK-RAG-CONTENT-001; coordinate with active TASK-RAG-CHUNK-003 and completed TASK-RAG-PARSE-001/TASK-RAG-002  
**Repository snapshot inspected:** 522c2cb38aff746e65a8f04ea48d88d3695fc5a9  
**Target:** tasks/TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md

## A. Title

Implement bounded, offline-capable **page-by-page OCR** and layout recovery for scanned or mixed-content PDFs using the existing PDF sandbox/parser pipeline, preserving exact original page evidence and explicitly distinguishing extracted text from inferred interpretation.

## B. Context / Problem

Scanned PDF pages contain image pixels rather than a reliable text layer. Existing text PDF parsing must NOT report success when scanned pages produce no searchable text. Mixed PDFs are more difficult: some pages may have selectable text, others scans; some contain both a poor hidden OCR layer and visible images. A single blanket OCR pass either loses legible text, duplicates it, or corrupts reading order. Neither OCR nor page segmentation understands arrows, graph data or causal relationships; that belongs to CONTENT-003. We need page-level inspection and a separately qualified OCR route that can be measured and safely disabled.

## C. Current Repository State

### C0. Source and parser-family status reconciliation

**Source reinspection 2026-11-23:** [parser_registry.py](../apps/workbench/parsing/parser_registry.py) now sets PDF descriptor `qualified=true` and gates actual `available` on pinned runtime asset discovery; [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py) and [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) implement text-layer/page/table processing. The current [PDF task](TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) reports **Gate A locally qualified** and **original evidence/OCR/vision unavailable**. Older rows in this task describing all PDF as unqualified are historical. Scanned-page OCR remains a new, separate producer.

| Inspected source | Current behavior and reuse |
| --- | --- |
| [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py) | PdfLimits defaults: 8 MiB, 32 pages, 180 seconds, bounded blocks/cells/memory; PdfPage, PdfBox, PdfBlock and PdfDocument represent verified page geometry and text/table blocks. No OCR-layer provenance or detected-scanned status is modeled yet. |
| [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py) | Isolated Docling worker preflights PDF text, forbids embedded JavaScript/actions/attachments, enforces no network, and builds text/heading/caption/table projections. Existing OCR capability is NOT enabled by virtue of installing Docling. |
| [pdf_parser.py](../apps/workbench/parsing/pdf/pdf_parser.py) | extract_pdf runs quota-limited subprocess; guarded runtime availability and a single parser concurrency slot. |
| [pdf_assets.py](../apps/workbench/parsing/pdf/pdf_assets.py), [pdf_asset_manifest.json](../apps/workbench/parsing/pdf/pdf_asset_manifest.json) | Pin Docling layout/table artifacts; no approved OCR language model assets or OCR engine configuration in current manifest. |
| [pdf_sandbox.py](../apps/workbench/parsing/pdf/pdf_sandbox.py) | OS child process budget, useful for an OCR child extension without spawning unbounded subprocesses. |
| [parser_registry.py](../apps/workbench/parsing/parser_registry.py) | FormatId.PDF and error taxonomy exist, PDF remains unqualified in this registry; NO_EXTRACTABLE_TEXT is already available. |
| [parsing.py](../apps/workbench/parsing/parsing.py) | ParsedElement/ParsedDocument typed projections and bounded inspection; TXT/MD/Python currently registered. |
| [chunking.py](../apps/workbench/chunking/chunking.py), [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) | Existing unit-honest prepared chunks and PDF page/table adapter; should consume verified OCR observations, not re-OCR text. |
| [ingestion.py](../apps/workbench/ingestion/ingestion.py), [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) | Durable jobs and version publication; use same upload/commit transaction. |
| [TASK-RAG-CHUNK-003](TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) | Active text-layer PDF parser/chunking qualification; scanned pages intentionally excluded and must remain unsupported until this task passes. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | New original asset and observed-versus-derived representation contracts; this task depends on those contracts being implemented. |

The existence of Docling packages and PDF model weights does not prove that Tesseract/EasyOCR/RapidOCR engines or required Cyrillic language models are installed. Current application documentation describes parser entries separately from public supported-upload capabilities. All new OCR capability flags must therefore begin false.

## D. Goal

Given an authorized, bounded PDF, classify each page by quality of its text layer, OCR only the pages/regions that need it, preserve page and bounding-box provenance and a stable link to the original bytes, then publish search text through the shared policy and PostgreSQL workflow. A page with uncertain text or reading order is flagged; no synthetic page numbers or fabricated diagram interpretation. Encrypted, corrupt, timeout, resource-exhausted and unsupported-language documents fail safely without replacing an active source version.

## E. Scope

- Define a per-page text-layer inspection result and deterministic OCR selection policy: native_text, OCR_REQUIRED, OCR_APPLIED, OCR_LOW_CONFIDENCE, empty/unsupported, with reason codes and extractor revision.
- Qualify one fully local OCR adapter through a provider-neutral OcrProvider port. Compare at least one candidate for en and Cyrillic scripts; do not enable ru/uk without real language model tests.
- Extend the existing PDF subprocess safety boundary for OCR, with pinned engine/asset versions, no silent downloads and memory/CPU/page/time budgets.
- Preserve page rasters or exact source-PDF reference via CONTENT-001 AssetStorePort; OCR-derived text remains a typed observed representation with image-space source coordinates.
- Reconcile OCR words/lines with native text to avoid duplicate searchable passages and preserve reading order; expose deterministic warnings when unable.
- Feed verified OCR text plus structural page/table blocks into the existing PDF chunking policy and atomic ingestion, with capability/status gates and regression tests.
- Establish benchmarks of text accuracy, page/box attribution, retrieved evidence and indexing cost.

## F. Non-Goals

No extraction of arrow semantics, chart numerical series, graph node/edge inference, Mermaid parsing, visual question answering, remote OCR APIs, generic image uploads, handwriting recognition without a qualified engine, unbounded OCR, production multi-user RBAC, or raw PDF execution. CONTENT-003 owns diagram understanding. Do not classify an image-only diagram as search-complete merely because labels were OCR'ed.

## G. Architecture / Boundaries

### G0. Explicit PARSE/CONTENT ownership contract — no duplicate parsing/persistence

- **Already implemented owner:** [CHUNK-003](TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md) and its existing Docling sandbox own safe PDF text-layer parse, page geometry, table-aware chunking and source-version publication. **Do not write another PDF parser or upload API.**
- **This task alone owns PDF OCR:** native-vs-scan classification, bounded OCR provider, extracted words/lines/confidence and deterministic reconciliation; emits verified OCR observations through existing `PdfPage/PdfBox/ParsedElement`, then [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) persists representations/assets when ready.
- **Other parsers:** [PARSE-002](TASK-RAG-PARSE-002-office-and-web-document-parsers.md) covers DOCX/PPTX/HTML text. Office embedded-image OCR is **not** implicitly supported by this PDF-only task; a follow-on approved adapter could reuse this `OcrProvider` without duplicating it. [PARSE-003](TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md) covers spreadsheets without OCR.
- **Visual meaning:** [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) alone owns arrow/graph/chart inference; text extracted by OCR must never be advertised as a verified relationship graph. [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) owns secure original evidence reads.

[x] parsing/OCR adapter, [x] application policy, [x] provider-neutral OcrProvider contract, [x] content representations, [x] existing Postgres ingestion, [x] security and audit, [x] evaluation; [ ] agent runtime. Flow:

    PDF preflight -> page text-layer quality -> selected OCR regions
      -> bounded offline OCR provider -> OCR text/boxes/confidence
      -> reconcile with observed PDF text -> typed elements/representations
      -> PAGE_LAYOUT chunker -> existing job-coupled publication
      -> existing PostgreSQL lexical retrieval + secured original asset reference

OCR engine SDKs must remain in the worker/adapter, not in the domain, persistence or React UI. The local parser's PDF safety scan MUST run before rasterization or model inference.

## H. Contracts / Interfaces / Data Model

**PageInspection**: source_version, page number (1-based, verified), page_dimensions, rotation/crop transform, observed native text count/quality metrics, scanned_likelihood_reason, decision (native_text, ocr_required, ocr_allowed, rejected), content-free errors and inspection revision.

**OcrRequest**: authorized source/page asset handle, trusted pixel buffer/region bbox, language profile IDs and revision, maximum pixels/words/time, signal/deadline. No remote URL or client-selected executable path.

**OcrResult**: observed lines/words with text, confidence if engine exposes it (never fabricated), page, bounding box with explicit coordinate frame and transform into PdfBox, reading_order_index, engine ID/revision, model asset digest and warning codes. OCR observations are **not** verified diagram interpretations; representation provenance is observed_from_pixels. Unsupported/no confidence is null, not 1.0.

**Reconciliation**: choose native text when quality is adequate; OCR when absent/broken and authorized; compare overlap and duplicates, never merge contradictory strings without a recorded decision. For mixed pages, retain both raw observations and selected index projection with their separate hashes.

**Output**: append page and OCR representation IDs through CONTENT-001 to existing SourceVersion/Chunk; Chunk.page must reference actual PDF page; boxes must fit page bounds. Parent page asset remains retrievable after restart. Existing table integrity checks still apply; if OCR destroys row alignment, TABLE_STRUCTURE_UNCERTAIN is emitted.

**Errors/capabilities**: reuse safe ParsingError and current ErrorResponse envelope. Extend with stable codes OCR_ENGINE_UNAVAILABLE, OCR_LANGUAGE_UNSUPPORTED, OCR_LOW_CONFIDENCE, OCR_RESOURCE_LIMIT, OCR_LAYOUT_UNCERTAIN only after contract review. feature OCR must remain false until engine + models + sandbox + correct UI/API data path are verified. Do not change SearchResponse score_type.

## I. Repository Files / Components Impacted

REVIEW/EXTEND pdf_worker.py, pdf_parser.py, pdf_models.py, pdf_assets.py, pdf_asset_manifest.json and pdf_sandbox.py; add narrowly scoped ocr_adapter.py and ocr_profiles.py if not already provided by another approved task. Extend parser_registry.py and parsing.py only with qualified OCR element descriptors, not a second file detector. Reuse chunking.py, pdf_chunking_adapter.py, ingestion.py, ingestion_http.py, postgres_ingestion.py, CONTENT-001 contracts, existing Chunk metadata. Add tests/test_pdf_ocr.py, tests/test_pdf_ocr_ingestion.py, synthetic tests/fixtures/pdf_ocr/ and docs for OCR operator assets/resources. Do NOT modify upstream haystack/, applied migrations 0001/0002, page table index semantics, lexical scorer, validator registry or Preview fixtures. Schema changes belong to CONTENT-001 unless a documented new requirement forces an additional task revision.

## J. Implementation Requirements

### J1 — qualify readiness and inspect source behavior
Reinspect the actual Docling worker conversion path and current parser availability; compare PDF output for text-only, scanned-only and mixed pages. Confirm no OCR engine is quietly downloaded or enabled by default. Specify one approved offline OCR engine and pinned resource digests, necessary language packs, page pixel cap, image DPI and minimum confidence rules based on experiments rather than arbitrary assertions. Create a preflight capability probe that cannot be spoofed by caller metadata.

### J2 — detect text-layer quality per page
Inspect page text coverage, empty/garbled Unicode, invisible text, rotation, reading order and duplicate-image overlays. Establish testable deterministic reasons for OCR_REQUIRED versus native text. Do not automatically replace valid native text with OCR. For documents with 10 pages, OCR may process only 2 and must record which. Native and OCR outputs remain separately traceable.

### J3 — implement isolated OCR extraction
Run OCR inside the existing quota-limited child or a demonstrably equivalent isolated subprocess. Reuse PDF safety catalog checks. Enforce page count, raster pixel, decompression, memory, CPU, wall time and language limits before work. Transform pixel bbox to PDF page-space with documented rotation/crop mapping. Preserve confidence only when measured. Do not accept raw outbound network, arbitrary engine commands, shell evaluation or caller-chosen model paths.

### J4 — reconcile, project and chunk
Create DocumentElement for page/line/paragraph/table where observed. Store OCR text representation tied to original page asset and crop/bbox. Reconcile native/OCR duplicate lines and preserve uncertain alternatives without inflating indexed text. Use the existing page-layout/table splitter and keep section headers/rows. A scan with only diagrams and no verified text remains OCR_INCOMPLETE or needs CONTENT-003, not falsely search-complete. Exact Word/token units follow existing approved chunking profiles.

### J5 — integrate job and capability lifecycle
Feed prepared chunks into the existing authorized upload/version transaction; no side database. A failed page with required OCR cannot turn the whole upload success unless an explicit partial-result contract and coverage threshold are reviewed; default fail closed. Store per-page processing decisions and warnings. Report OCR availability separately from PDF text-layer availability, and preserve old source version on OCR timeout/engine failure.

### J6 — run quality/security benchmarks
At least 12 synthetic/non-sensitive PDFs covering 40+ page observations, mixed-native+scanned, two-column, Cyrillic, rotation, low contrast, tables, empty diagrams, encrypted/corrupt, resource exhaustion and duplicate hidden text. Audit >30 labelled OCR/search cases. Compare CER/WER where ground truth is available, wrong-page citation rate, reading-order errors, duplicate text ratio, token cost and per-page p50/p95; report per-language separately. Repeat API/DB/asset store restart test and cross-workspace denial.

## K. Security / Governance / Observability

Pages can contain confidential data and adversarial prompt text. OCR content is data only; never use it as instructions or HTML. No external OCR call without explicit future capability. Constrain untrusted PDF rasterization, filesystem, process count, CPU/memory, DPI and asset storage. Workspace scoping applies to every asset/representation/word record and derived crop, not just source ID. Redact image/word content and personal file paths from logs; log only trace/job IDs, page count, engine revision, OCR decisions, failure code, time and confidence distribution. Define retention and access of intermediate page rasters; do not leak them as publicly routable files.

## L. Testing / Evaluation / Runtime Verification

Commands from repo root: hatch run workbench-api:check; hatch run workbench-api:test; hatch run workbench-api:types. Run integration suite on a disposable Postgres database and CONTENT-001 temporary asset root; verify Windows and POSIX subprocess quotas or explicitly mark unsupported OS modes unready. Required tests: missing engine/asset/language, correct native/OCR choice, duplicate suppression, corrupt PDF, encrypted PDF, mixed page, bogus bbox transform, OCR timeout/cancel, OCR-only no-layout table, failed replacement, wrong workspace, idempotent retry, restart, no outbound network and no raw-content logs. E2E: upload scanned text, GET chunk/pages/evidence, search unique term, resolve original page crop. Record actual test execution and gold evaluation—not simulation as operational proof.

## M. Acceptance Criteria

- [ ] Existing text-PDF route still behaves identically when OCR is disabled/unavailable.
- [ ] Scanned pages with qualified OCR produce actual searchable text with verified 1-based page and bbox provenance linked to original page asset.
- [ ] A mixed 10-page fixture OCRs only necessary pages and does not duplicate native and OCR text.
- [ ] OCR engine/language/model absent returns visible unsupported/error state; zero fabricated successful chunks.
- [ ] Per-language CER/WER and wrong-page/reading-order metrics for 40+ pages and 30+ gold checks recorded with sample counts and failures.
- [ ] Text/diagram distinction is explicit; graph/causal relationships are NOT claimed from OCR text alone.
- [ ] 503/timeout/invalid scope/corrupt and low-quality failures preserve previous active version; no partial indexed success or leaking raster bytes.
- [ ] Original exact PDF/page reference and OCR element remain retrievable after API/DB/asset restart; RLS and access tests pass.
- [ ] Qualifying OCR does not force any cloud network dependency; source/lexical regressions pass.
- [ ] Capability/README reflect only installed and measured OCR profiles.

## N. Documentation / Migration / Compatibility / Rollback

Extend current Docling/PDF operator runbook with per-language OCR qualification, local model assets, reviewed DPI/page/timeout limits and representation states. Existing PDF text-only publication is preserved. The storage schema is owned by CONTENT-001; this task should avoid extra migrations unless necessary and reviewed first. Rollout with OCR disabled by default, then explicit test workspace, then per-language capability. Rollback disables OCR adapter but retains all original source assets and published versions; do not delete scans or amend prior source bytes. Defer handwriting, vision graph extraction, chart digitization and remote OCR to separate scoped tasks.

## O. Mandatory Completion Checklist

- [ ] Current PDF and asset model code re-inspected; no redundant OCR implementation added.
- [ ] Page-level native/OCR classifier and provider-neutral engine contract tested.
- [ ] At least one pinned offline engine/profile with required languages genuinely qualified.
- [ ] Per-page provenance, confidence honesty, coverage and deduplication verified.
- [ ] Existing parser sandbox and source-version publication reused.
- [ ] Security/quotas/tenant/restart/cancellation negative suite actually executed.
- [ ] Page-level retrieval and original-image resolution proven with non-sensitive fixtures.
- [ ] Docs/capabilities and independent quality report linked.
- [ ] Only mark COMPLETE after all applicable checks have executed evidence.

# Parser-family vs Content-family task overlap and Live Documents contract audit

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** COMPLETE — source-level architecture/task specification audit; no new parser, multimodal runtime or Live Documents UI was implemented  
**Repository source snapshot reviewed:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Scope:** [UI-003](../TASK-UI-003-live-document-management.md), four tasks in this review folder, five CONTENT tasks, existing completed PARSE-001/RAG-002/CHUNK-001/Python and current FastAPI/web API contracts

## Executive finding

**No two task files have the same complete deliverable.** PARSE-002..005 primarily cover **format-specific parsing, verified structural elements and chunk generation**. CONTENT-001..005 cover **versioned persistence of elements/representations/original bytes, PDF-only OCR, optional inference over visual pictures, deterministic Mermaid graphs and authorized retrieval-time evidence resolution**. There are nevertheless **three dangerous interface overlaps** and **two format-coverage gaps** that would create redundant code if agents execute the original specifications literally:

1. PARSE tasks propose `ParsedElement` kinds and provenance while CONTENT-001 also proposes `DocumentElement`. These MUST be different lifecycle stages of one pipeline; do not define a second MIME/parser registry or independent element persistence per parser.
2. DOCX/PPTX/HTML and CSV/XLSX both encounter tables; a separate `table`/row storage model or second table chunker per task would duplicate shared structure. Reuse canonical `ParsedElement` and current content-aware policies; add only format-native extraction.
3. PARSE-004 handles YAML/JSON structures while CONTENT-004 handles Mermaid structures; fields containing Mermaid-looking text in JSON/YAML are **not** automatically Mermaid. Mermaid parser consumes already-identified Markdown `mermaid` fenced elements.
4. **Gap:** CONTENT-002 is scoped to scanned/mixed **PDF** OCR. PARSE-002 excludes embedded Word/PowerPoint image OCR; no task currently qualifies Office-image OCR end to end.
5. **Gap:** CONTENT-003 starts with **PDF** diagrams/charts; PARSE-002 may detect PPTX charts and PARSE-003 may detect XLSX charts, but neither auto-qualifies chart-data/arrow semantics for those source types.

**Decision:** retain all four PARSE tasks and all five CONTENT tasks; do not merge or delete them. Their boundaries and source links have been updated in place. Stage the work as Gate P (parser + bounded current PostgreSQL lexical ingestion) and Gate E (persisted original-asset/representation/evidence), with **independent, fail-closed qualifications**.

## Actual source and task status (not hypothetical)

| Current source / accepted task | Verified state and implication |
| --- | --- |
| [PARSE-001 completed](../completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md), [parser_registry.py](../../apps/workbench/api/parser_registry.py), [parsing.py](../../apps/workbench/api/parsing.py) | App-owned verified format classifier, `ParsedDocument`/`ParsedElement`/`SourceSpan`, `ElementKind`, TXT/MD/Python qualified. Additional format entries are catalogued but **not automatically qualified**. |
| [RAG-002 completed](../completed/TASK-RAG-002-ingest-text-and-markdown.md), [ingestion.py](../../apps/workbench/api/ingestion.py), [ingestion_http.py](../../apps/workbench/api/ingestion_http.py), [postgres_ingestion.py](../../apps/workbench/api/postgres_ingestion.py) | Real bounded multipart, idempotency, detail/chunks/jobs, active source/version and PostgreSQL publication are ALREADY implemented. No parser or CONTENT task may create a second HTTP family or source writer. |
| [CHUNK-001 completed](../completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md), [chunking.py](../../apps/workbench/api/chunking.py), [chunking_profiles.py](../../apps/workbench/api/chunking_profiles.py) | Source-aware chunk selection and profile fingerprints already exist. Format-specific parsers extend/adapt these, not create independent general chunking policy engines. |
| [Python AST completed](../completed/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md), [python_code.py](../../apps/workbench/api/python_code.py) | Python parsing should not be reimplemented by PARSE-004, even when the user uploads DevOps files. |
| [PDF CHUNK-003](../TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md), [pdf_worker.py](../../apps/workbench/api/pdf_worker.py), [pdf_chunking_adapter.py](../../apps/workbench/api/pdf_chunking_adapter.py) | Existing Docling source and text-layer PDF/table integration; task reports Gate A locally qualified while original assets/OCR/VLM remain separately gated. |
| [contracts.py](../../apps/workbench/api/contracts.py), [application.py](../../apps/workbench/api/application.py) | `rag-api-v1.0` now includes real `Features.upload/document_details/jobs`, `PdfIngestionCapabilities` and all ingestion/document DTOs; no missing backend upload route. |
| [web contracts.ts](../../apps/workbench/web/src/api/contracts.ts), [decode.ts](../../apps/workbench/web/src/api/decode.ts), [client.ts](../../apps/workbench/web/src/api/client.ts) | Frontend still lacks those typed flags/DTOs and multipart/201 handling; this is a **UI-003 contract implementation gap**, not a PARSE/CONTENT duplicate. |
| [UI-003 revised blueprint](../TASK-UI-003-live-document-management.md) | Updated for real server contracts and TXT/MD/Python plus conditionally qualified PDF; current [DocumentsView.tsx](../../apps/workbench/web/src/views/DocumentsView.tsx) remains fixture-only. |

## Task-by-task overlap matrix

| Parser task | Exclusive Gate P (format parser) | CONTENT intersection and gate | Verdict |
| --- | --- | --- | --- |
| [PARSE-002 Office/HTML](TASK-RAG-PARSE-002-office-and-web-document-parsers.md) | DOCX/PPTX/HTML headings, lists, slides, embedded tables, links, exact verified source order; safe OOXML/HTML extraction | CONTENT-001 stores elements and original files; CONTENT-003 may **later** analyze slide/picture diagrams; CONTENT-005 resolves exact slide/page refs; CONTENT-002 currently PDF-only | **No full duplicate.** Danger only if it builds a private `DocumentElement`/asset/vision parser. Keep slide number distinct from PDF page. |
| [PARSE-003 tabular](TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md) | CSV/TSV/XLSX parsing, sheet/cell/row/column/formula source fidelity, header-preserving row groups | CONTENT-001 persists original workbook and source element refs; CONTENT-005 resolves cell/row provenance; CONTENT-003 workbook charts require a future explicitly qualified visual adapter | **No full duplicate.** Shared table element contract with PARSE-002, format-native source-coordinate differences kept. |
| [PARSE-004 structured/DevOps](TASK-RAG-PARSE-004-structured-data-and-devops-parsers.md) | JSON/JSONL/YAML records, bounded nesting, JSON pointers, safe YAML/Kubernetes source semantics | CONTENT-001 stores elements/original bytes; CONTENT-004 deterministically interprets **Mermaid fences**, not general YAML or JSON; CONTENT-005 resolves source path/codepoint offsets | **No full duplicate.** Mermaid-looking scalar remains data. Do not create a new Markdown scanner or run YAML. |
| [PARSE-005 conversations](TASK-RAG-PARSE-005-conversations-and-transcripts.md) | EML/MSG/SRT/VTT message and cue/author/speaker/time spans; attachment metadata only | CONTENT-001 may persist email/attachment originals; CONTENT-005 authenticates original message/cue time; CONTENT-002 OCR and CONTENT-003 vision do **not** supply ASR/diarization | **No full duplicate.** Speaker/timestamps are source data, not authorization; ASR is out of scope. |

## CONTENT ownership matrix — avoid a second parser or store

| CONTENT task | Unique owner | What it MUST reuse, MUST NOT implement |
| --- | --- | --- |
| [CONTENT-001](../TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | Durable `DocumentElement`, `ContentRepresentation`, `DocumentAsset`/AssetStorePort and chunk-evidence mappings | **Consumes transient** `ParsedElement/ParsedDocument` from PARSE-001..005. Does not reimplement DOCX/XLSX/YAML/EML/PDF parsers or create a second source registry. |
| [CONTENT-002](../TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md) | Per-page scanned/mixed PDF OCR, native-vs-OCR reconciliation, OCR box/language, offline engine | Reuses existing Docling PDF worker/sandbox, PdfBox/PdfPage and CONTENT-001 assets. Does not parse Office, imply OCR of DOCX pictures, or infer flowchart arrow direction. |
| [CONTENT-003](../TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) | Optional VLM image/diagram graph and numerical chart data **candidate** plus provenance/trust checks | Consumes cropped/verified image regions from existing PDF processing and future qualified Office/XLSX adapters. No new PDF/Office/spreadsheet parsers; VLM guesses are NOT original facts. |
| [CONTENT-004](../TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) | Mermaid grammar/AST, arrow/sequence/class/ER relations and deterministic text projection | **Consumes existing Markdown `PROTECTED_RAW` fenced element**. Does not implement JSON/YAML parser, second Markdown tokenizer or OCR/VLM on rendered Mermaid. |
| [CONTENT-005](../TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) | Authorized source/version/asset/line/row/page/time/graph reference resolution and hash/claim checks | Consumes CONTENT-001 rows and PARSE-produced true source spans. Does not parse document formats, run OCR/VLM/Mermaid, or implement a second blob store. |

## Canonical contract and two-stage handoff

```text
Source bytes -> ONE verified parser registry
             -> format-specific adapter (PARSE-002/003/004/005, or existing TXT/MD/Python/PDF)
             -> ParsedDocument / ParsedElement / SourceSpan (TRANSIENT, content extraction)
             -> existing ChunkingPolicyResolver + PreparedChunk
             -> existing RAG-002 job + PostgreSQL publish
                      |                    |
                      | Gate P: lexical    +--> source/version/Chunk provenance (current)
                      v
             CONTENT-001 ElementProjection (when implemented)
             -> persisted DocumentElement + Original DocumentAsset + ContentRepresentations
             -> optional CONTENT-002 OCR / CONTENT-003 VLM / CONTENT-004 Mermaid
             -> CONTENT-005 EvidenceResolver + authorized original bytes (Gate E)
             -> UI Evidence Viewer (independent)
```

**Identity invariant:** parser element/offset is a verified *observation* of specific source bytes; persisted `DocumentElement` is a long-lived `(workspace_id,source_id,source_version_id,element_id)` projection. The projection MUST not re-parse files, reassign workspace, invent missing offsets or cross old/new source versions. Renderable summaries/OCR/VLM output are separate representations with `direct_source/deterministic_parse/observed_OCR/model_inferred/human_verified` provenance states. One trusted storage port/publisher owns committed data; format parsers cannot create their own SQL source version or private asset tables.

**Table consistency:** DOCX/PPTX/HTML and XLSX/CSV emit consistent `table/row/heading/cell` typed structures; sheet/row/column and slide/page coordinates remain distinct source-native optional fields. A table parser may repeat verified header text for retrieval context but must retain exact original cell source hashes/provenance separately. No invented page numbers.

**Feature activation:** completed API `features.upload` indicates the synchronous upload route, **not all parser catalog entries**. Candidate Office/CSV/YAML/EML families stay unsupported until their own Gate P tests and capability extension pass. Evidence features must remain false/unavailable until Gate E; parser success alone is not original asset availability. Existing PDF may qualify text layer with explicitly unavailable OCR/visual semantics.

## Duplicate-prevention validation and missing tests

- [x] Audited four PARSE tasks and five CONTENT tasks against actual repository source, not task titles.
- [x] Resolved old source-link path mistakes in all four `tasks/check/` files. Their original `../apps`, `../haystack`, `../docs-website` paths were broken from this nested folder, as were PARSE-001 references. Updated to valid repository-relative targets.
- [x] Clarified in all PARSE and CONTENT specifications which contract/source layer each task exclusively owns and the two distinct qualification gates.
- [x] Refreshed UI-003 to the actual implemented backend DTOs including `upload/document_details/jobs`, `pdf_ingestion`, multipart HTTP 201 and `replayed/reserved_version_id/error.job_id`.
- [ ] **Implementation test:** a PARSE source with structured element can be projected by CONTENT-001 without duplicating source parse, element class vocabulary or source/version writer. This is a future task acceptance gate.
- [ ] **Implementation test:** PARSE-002 embedded media warning and PARSE-003 workbook chart can be projected as evidence-unavailable before a qualified visual adapter; not a fabricated chart result.
- [ ] **Implementation test:** Mermaid-looking text in JSON/YAML stays literal unless CONTENT-004 has an explicitly approved, proven grammar/field contract.
- [ ] **Implementation test:** new PARSE adapters never register their own upload routes, durable job tables, source version publication or blob store; code-level imports and DB schema review required.
- [ ] **Implementation test:** source/asset/evidence pointers are tenant- and source-version-scoped under RLS and fail closed for unavailable originals or unsupported OCR/VLM/ASR.
- [ ] **Frontend E2E:** UI-003 must prove its own real Live Documents page; documentation audit is NOT execution evidence.

## Recommended execution order and scope of changes

1. **UI-003 now:** the current API already exposes all required document/list/upload/detail/chunk/job routes and user-visible capability flags. Its missing work is the frontend transport (FormData 201), typed DTOs, list/detail/chunk controller and real UI. No need to block UI-003 on PARSE-002..005 or CONTENT-001..005.
2. **PARSE tasks independently as format coverage:** release DOCX/PPTX/HTML, CSV/TSV/XLSX, JSON/JSONL/YAML and EML/MSG/SRT/VTT only after format-specific parsing + PostgreSQL lexical + source span + security evidence. Each may be qualified for **textual retrieval only**; never claim original asset support until Gate E.
3. **CONTENT-001 before multimodal publishing:** design one persisted element/representation/original asset model; integrate parser outputs through a single adapter and existing source-version atomic job. Existing completed parser and chunking components remain authoritative for parsing.
4. **CONTENT-002/003/004 only for their unique modality:** scanned PDF OCR, image/diagram/chart interpretation and deterministic Mermaid grammar. No duplicate PDF/Office/Spreadsheet/JSON conversion and no inferred source authority.
5. **CONTENT-005 plus UI evidence viewer last:** reference original source version and hash, secure bounded asset access and clear trust state. Additional Office-image OCR, workbook chart/ASR extensions require **separately scoped** tasks, not silent expansion of existing MIME parsers.

## Operational notes

All newly written or updated documents are Markdown and retain Created/Updated dates. The updated task files remain **PROPOSED**; this audit does not mark any unfinished parser/content implementation complete. Test paths, dependencies and active capabilities must be rechecked immediately before coding because other changes may land after the inspected source snapshot.

**Current API contract risk to track:** backend [ingestion_http.py](../../apps/workbench/api/ingestion_http.py) still contains stale upload OpenAPI prose saying “TXT or Markdown at most 1 MiB”, while server accepts Python and conditionally PDF. [UI-003](../TASK-UI-003-live-document-management.md) now specifies a docs-only correction and a schema test; actual runtime capability and parser registry remain the authoritative source of supported formats.

# TASK-RAG-PARSE-002 — DOCX, PPTX and HTML document-aware ingestion

**Created:** 2026-11-21  
**Updated:** 2026-11-23  
**Status:** PROPOSED — blueprint, not implemented  
**Priority:** P1 — common business-document coverage  
**Dependencies:** TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001; PDF belongs to TASK-RAG-CHUNK-003  
**Repository snapshot reviewed:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Target:** `tasks/check/TASK-RAG-PARSE-002-office-and-web-document-parsers.md  
**Architecture:** [Format and chunking matrix](../../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Enable **DOCX, PPTX and HTML** under the existing bounded upload/job/version pipeline, with headings, paragraphs, tables, slides and links preserved as typed elements. Qualify EPUB/ODT/ODP/RTF/DOC/PPT separately, without claiming them as implemented in this task.

## B. Context / Problem

Business corpora contain policies in Word, sales/architecture decks and knowledge articles in HTML. Flat, arbitrary 500-token text splitting loses section and slide provenance and can mix unrelated table rows. The backend already provides bounded durable TXT/Markdown/Python upload and active-version PostgreSQL search; this task extends its qualified file formats and structure extraction. Reuse those boundaries rather than adding a second HTTP path, index or importer.

## C. Current Repository State

**Source audit refreshed 2026-11-23:** the earlier “read-only API / future upload” premise is obsolete. [RAG-002](../completed/TASK-RAG-002-ingest-text-and-markdown.md) now provides real `IngestionRoutes.upload/detail/chunks/job` in [ingestion_http.py](../../apps/workbench/api/ingestion_http.py), durable jobs in [postgres_ingestion.py](../../apps/workbench/api/postgres_ingestion.py), and [PARSE-001](../completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) is complete. The catalog lists planned Office/HTML formats but they are **not qualified**. Pinned Docling PDF worker code exists in [pdf_worker.py](../../apps/workbench/api/pdf_worker.py), but installing it does not qualify Word/PowerPoint or image interpretation.

**Actual missing work:** per-format bounded Office/HTML adapter plus golden source/slide/table provenance tests and a capability update through the existing HTTP route. Do not create the new `ingestion.py` or another table/endpoint as the dated task suggests.

| Actual source | Reusable implementation | Gap / caution |
| --- | --- | --- |
| [`haystack/components/converters/docx.py`](../../haystack/components/converters/docx.py) `DOCXToDocument` | Existing document text and table conversion. | Native library converter may not reconstruct page numbers; never invent pages. |
| [`haystack/components/converters/pptx.py`](../../haystack/components/converters/pptx.py) `PPTXToDocument` | Existing deck extraction. | Qualify slide order, notes, tables and hyperlinks explicitly; do not assume every type preserved. |
| [`haystack/components/converters/html.py`](../../haystack/components/converters/html.py) `HTMLToDocument` | Existing HTML extraction with optional structured markdown. | Strip scripts/nav/ads/tracking; HTML text alone loses DOM boundaries. |
| [`haystack/components/converters/multi_file_converter.py`](../../haystack/components/converters/multi_file_converter.py) `MultiFileConverter` | Routes DOCX, PPTX, HTML among other formats. | Can be reused for simple fallback; not evidence of page/slide/table fidelity. |
| [`haystack/components/preprocessors/markdown_header_splitter.py`](../../haystack/components/preprocessors/markdown_header_splitter.py) | Existing heading splitting. | Prefer structural element boundaries from parser; secondary chunks stay under parent. |
| [`apps/workbench/api/persistence.py`](../../apps/workbench/api/persistence.py) | `Chunk.page?`, metadata JSON and source/version IDs. | `page` is **not** a slide number; store `slide` under bounded metadata unless schema changes are separately justified. |
| [`apps/workbench/api/postgres.py`](../../apps/workbench/api/postgres.py) | Atomic `_publish` and forced workspace scope. | No second writer or table. |
| [`apps/workbench/api/contracts.py`](../../apps/workbench/api/contracts.py) | v1 error/result schemas. | Format claims only after route + parser + storage qualification. |
| [`tasks/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md`](../completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) | Completed parser registry/element contract. | Declare additional adapters through its one registry. |

Pinned Docling PDF worker and model assets exist in the Workbench source; this does **not** qualify Office/HTML parsing. Optional legacy/publishing formats require additional review.

## D. Goal

A valid DOCX, PPTX or HTML file passes checked file identity, creates truthful ordered structural elements and bounded chunks, persists via the existing transactional write path, and can be found via the existing PostgreSQL lexical search. Citations identify real sections/slide numbers; malformed files or unavailable parser dependencies fail without replacing a prior active version.

## E. Scope

- Enable `.docx`, `.pptx`, `.html`, `.htm` after per-format qualification; add MIME and OOXML container checks via PARSE-001.
- Build thin, per-format element adapters using existing Haystack converters and optionally pinned Docling for structure-rich cases after validation.
- Preserve source document section hierarchy, paragraph order, lists, tables, slide title/ordinal, body text and trustworthy links/captions. Represent unsupported media with a warning, not invented descriptions.
- Reuse CHUNK-001 policy for recursive fallback **within** heading/slide/table child boundaries; no cross-slide overlap.
- Extend the single TASK-RAG-002 upload flow, source listing/detail and processing-report fields additively; keep source/version identity unchanged.
- Add per-format real golden fixtures and negative tests.

## F. Non-Goals

No `.pdf` integration (CHUNK-003), spreadsheet parsing (PARSE-003), OCR of images in decks, active macros, browser rendering of external URLs, crawling, HTML JavaScript execution, `doc/ppt/rtf/odt/odp/epub` autoenablement, custom WYSIWYG UI, embeddings, generation or authentication redesign.

## G. Architecture / Boundaries

### PARSE/CONTENT ownership contract — non-duplication gate

- **Ownership:** PARSE-002 alone qualifies DOCX/PPTX/HTML **format extraction**, source-native slide/paragraph/table order and safe HTML; it reuses existing [parser registry](../../apps/workbench/api/parser_registry.py), [ParsedElement](../../apps/workbench/api/parsing.py), [ingestion](../../apps/workbench/api/ingestion.py), and existing [chunking](../../apps/workbench/api/chunking.py). PARSE-003 owns XLSX/CSV/TSV row/sheet extraction, not PARSE-002.
- **CONTENT-001 integration:** [CONTENT-001](../TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) defines a persisted `DocumentElement` and `ContentRepresentation` for original-evidence linkage. It must **adapt from** the parser's immutable `ParsedElement`, not re-parse Office/HTML or create another registry/table/chunker. This PARSE task can qualify textual chunks independently; original assets remain `not_available` until CONTENT-001.
- **Visual boundary:** charts, images, and diagrams in slides or DOCX are **detected and warned about**, never interpreted here. [CONTENT-003](../TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) currently targets qualified PDF visual understanding; an explicit follow-up is required to support PPTX/DOCX images through its reusable `VisualUnderstandingPort`. [CONTENT-002](../TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md) is specifically scanned PDF OCR, not Office OCR.
- **Mermaid boundary:** HTML/Markdown-like Mermaid text remains untrusted text; [CONTENT-004](../TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) owns Mermaid grammar, not this generic HTML parser. Raw link/asset bytes and citations are [CONTENT-001/005](../TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) responsibilities.
- **Conversion option:** [CONVERT-001](../TASK-RAG-CONVERT-001-microsoft-markitdown-evaluation-and-safe-conversion-adapter.md) benchmarks Microsoft MarkItDown; it is a per-format adapter alternative, **not a second required extraction pipeline**. Only an approved measured format profile can select it.

**Qualification modes:** Gate P = format-specific parser/structured chunk + existing PostgreSQL lexical publication (this task); Gate E = durable byte/evidence/representation resolution (CONTENT-001/005 or specialty CONTENT adapter). Gate P may pass while Gate E is NOT_IMPLEMENTED, but Gate P must not claim original evidence or multimodal completeness. No new global parser registry, ContentRepresentation storage or EvidenceResolver is permitted in this task.

`uploaded bytes → PARSE-001 verification → qualified Office/HTML adapter → ParsedDocument(elements) → CHUNK-001 policy + bounded section/slide refinement → existing job/atomic PersistencePort → PostgreSQL → existing lexical result projection`.

- [x] Application/parser adapters: individual typed implementations, no Haystack fork.
- [x] Policy: structural elements and explicit provenance.
- [x] Security: container validation, HTML sanitizer, isolated parsing/CPU memory limits.
- [x] Persistence: reuse existing port/write job with server-resolved workspace.
- [x] Observability: parse quality/element counts and failure reasons.
- [ ] Agent/LLM runtime: N/A — no generated interpretation.

## H. Contracts / Interfaces / Data Model

Parser registry descriptors must declare `format_id`, allowed MIME/ext/container signature, parser revision, required dependencies and `required_provenance`. `ParsedElement` kinds: `section`, `heading`, `paragraph`, `list_item`, `table`, `table_row`, `slide`, `caption`, `link`; only emit a kind when actual source evidence supports it. A slide must include `slide_number >= 1`, presentation source ID; Word page number only if the parser supplies verified pagination. `processing_fingerprint` covers parser and chunking revisions; a different parser output must not silently reuse previous embeddings. HTML source URLs are **data**, not commands to fetch third-party resources.

First supported format set is exactly `.docx`, `.pptx`, `.html`, `.htm`; `.doc`, `.ppt`, `.rtf`, `.odt`, `.odp`, `.epub`, `.mhtml`, `.xhtml` stay `planned/unavailable` until separate dependency and parser tests. Typed parse warnings: `TABLE_LAYOUT_LOSS`, `MISSING_SLIDE_NOTES`, `UNVERIFIED_PAGE_NUMBER`, `UNPARSED_MEDIA`, `LINK_NORMALIZED`; no false confidence scores.

## I. Repository Files / Components Impacted

| Path | Change |
| --- | --- |
| `apps/workbench/api/parser_registry.py` | Extend reviewed descriptors; don't duplicate MIME rules. |
| `apps/workbench/api/parsing.py` or task-created `parsers/office.py`, `parsers/html.py` | Add bounded extraction adapters; choose the simplest existing structure. |
| `apps/workbench/api/ingestion.py` (created by TASK-RAG-002) | Wire approved parser via common dispatcher, not a second upload route. |
| `apps/workbench/api/contracts.py`, `openapi.json`, `application.py`, `boundary.py` | Extend supported format/capability and request-specific bounds additively, only after parser works. |
| `apps/workbench/api/tests/test_office_parsers.py`, `test_ingestion_routes.py` | Structural goldens, API+Postgres and failure cases. |
| `pyproject.toml` | App-only pinned optional Docling/Office dependencies if proven necessary. |
| `docs-website/docs/architecture/content-aware-chunking-strategy.md`, `apps/workbench/api/README.md` | Accurate support matrix and runtime constraints. |

**Must NOT change:** Haystack library implementations, applied migrations, validation-only service, PostgreSQL full-text score semantics or frontend Preview fixture objects.

## J. Implementation Requirements

### J0. Reconcile completed app owners and format-specific handoffs

1. Confirm current [parser registry](../../apps/workbench/api/parser_registry.py), [parsing.py](../../apps/workbench/api/parsing.py), [ingestion_http.py](../../apps/workbench/api/ingestion_http.py), [chunking.py](../../apps/workbench/api/chunking.py), [PostgreSQL publication](../../apps/workbench/api/postgres_ingestion.py) and [actual contracts](../../apps/workbench/api/contracts.py). The old blueprint predates completed RAG-002 and PARSE-001; do not reimplement their components.
2. Build a format/element/asset/evidence matrix and mark all unsupported extractions `NOT_QUALIFIED`; record original evidence status separately from parsed text.
3. Align this task's format-specific `ParsedElement` projection with CONTENT-001's long-lived `DocumentElement` contract **without building it here**. Confirm all source/span/line/page/time units are explicitly defined before using them as citations.

### J6. Format boundary regression and CONTENT handoff

Test a DOCX with a table and embedded image, PPTX with a slide chart, and HTML with a Mermaid code block. Verify that parser outputs real paragraphs/table/slide references and `UNPARSED_MEDIA` where appropriate; require **zero** VLM-inferred arrows, invented Word pages or original asset URLs. Original visual/evidence availability is a later independent CONTENT gate. Regression test current TXT/MD/Python/PDF ingestion and upload API.

### J1. Parser and threat qualification

Freeze converter versions, actual optional Python packages and bounded inputs; identify OOXML signatures/central-directory caps (unzip bomb/macro abuse) and HTML sanitizer behavior. Build a file family x test fixture matrix. Define explicit size, slide/page count, wall-time and memory limits before enabling a format.

### J2. Section/slide extraction

Use `DOCXToDocument`, `PPTXToDocument` and `HTMLToDocument` where structure fidelity meets gate; otherwise opt in a qualified Docling adapter. Extract typed section/slide/table units with original order, source IDs, header paths, link provenance, actual slide numbers. Reject successful but empty extraction. Never fabricate Word pagination.

### J3. Chunking and metadata

Group related text within section/slide; apply recursive subchunking only when over budget, respecting protected tables/captions. Preserve heading path and slide number for every child, with stable anchors and model/word unit declaration. Do not merge across unrelated slides or workspaces.

### J4. Shared write path

Extend approved parser capability without creating a new route or datastore. Call the existing versioned ingestion job and atomic PostgreSQL writer. Failed converter, unsupported binary, HTML sanitizer overflow or DB rollback keeps previous active version. Verify term retrieval through existing `postgres-fts-baseline` and honest `postgres_ts_rank_cd`.

### J5. Test and benchmark

Compare structural vs naive recursive chunks on a small labeled set per format: at least 10 documents each, 10 targeted queries each, section/slide attribution accuracy, table header survival, zero missing content, duplicate ratio, indexed bytes and p95 parse. Record per-cohort evidence, not a global performance claim. Keep legacy formats disabled until their own gates.

## K. Security / Governance / Observability

Untrusted OOXML ZIP/HTML may contain external relationships, embedded objects, active content and network references. Disable script, external file fetches, macros, remote images/entities. Enforce bounded parsing and resource isolation, storage ACL/RLS and source provenance. Logs contain source/job/trace IDs, parser revision, counts, duration and failure codes, not document text, user-supplied URLs, credentials or embedded objects. Retention follows uploaded source policy; no unreviewed data exfiltration via optional converter.

## L. Testing / Evaluation / Runtime Verification

- Unit goldens for headings, nested lists, tables, slide order, title/notes where supported, HTML script/nav exclusion, Unicode and whitespace.
- Format spoofing and OOXML ZIP traversal/bomb; external relationships and HTML remote assets must never be fetched.
- Missing optional dependency, malformed/empty document, over-size, oversized paragraph/table and parser timeout return controlled errors.
- Real async HTTP + disposable PostgreSQL: upload, read source/chapters, search, update, rollback, restart; compare active source/version/chunk IDs.
- Existing lexical test suite, TXT/Markdown upload and parser registry tests stay green.
- `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, plus specific parser tests.

## M. Acceptance Criteria

- [ ] `.docx`, `.pptx`, `.html`, `.htm` are advertised only after independently passing real parser+HTTP+PostgreSQL+search tests.
- [ ] 100% of enabled golden fixtures retain heading/slide source-order labels; no fabricated Word page numbers.
- [ ] 0 cross-slide/section structural merges outside explicit overflow policy, 0 silent empty-success outputs.
- [ ] At least 10 representative documents and 10 labeled queries per enabled family are benchmarked; slide/section citation correctness and cost reported.
- [ ] HTML/OOXML active content/external resources never execute or fetch; failures preserve prior active version.
- [ ] Legacy/publishing extras remain explicitly unavailable until separately qualified.

- [ ] Reuses **completed** PARSE-001/RAG-002/chunking and current API; no duplicate format registry, HTTP upload handler, persistence adapter or version publication.
- [ ] Does **not** implement CONTENT-001 original asset storage/`DocumentElement` persistence or CONTENT-005 evidence resolution; the parser exports accurate source/element spans for later adapters.
- [ ] `Office/HTML` format-specific supported/unsupported visual/attachment/graph cases are labelled truthfully; no inferred OCR/VLM/Mermaid/ASR behavior advertised from parsing.

## N. Documentation / Migration / Compatibility / Rollback

Add source-specific parser revisions/capabilities, known layout loss and upload limits to the canonical architecture and API README. No SQL migration is initially required if bounded `Chunk.metadata` covers slide/heading/table provenance; stop and add a migration task if reliable parent/child relations need indexed durable records. Keep `rag-api-v1.0` request/response shape compatible or revise it by explicit contract task before deployment. Roll back by disabling parser descriptor while retaining existing versions and DB volume; do not overwrite old profile fingerprints.

## O. Mandatory Completion Checklist

- [ ] All new source paths and GitHub-relative links verified from the actual `tasks/check/` location.
- [ ] PARSE/CONTENT ownership boundaries exercised with fixture tests; no duplicate durable element/asset model.
- [ ] Existing SQL/API/upload/source-version test gates remain passing when new parser family is enabled.


- [ ] Real format signatures and optional dependencies qualified.
- [ ] Reuse of existing converters documented; no duplicated converter or writer.
- [ ] Section/slide/table structural evidence and limits tested.
- [ ] HTTP+SQL+search tests and negative security cases executed with recorded evidence.
- [ ] Capabilities and Markdown support matrix match actual installed behavior.
- [ ] No unresolved acceptance criteria before COMPLETE.

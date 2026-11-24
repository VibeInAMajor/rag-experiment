# TASK-RAG-PARSE-003 — CSV, TSV and XLSX table-aware ingestion

**Created:** 2026-11-21  
**Updated:** 2026-11-24  
**Status:** PROPOSED — blueprint, not implemented  
**Priority:** P1 — spreadsheets and tabular business data  
**Dependencies:** TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001  
**Repository snapshot reviewed:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Target:** `tasks/TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md  
**Architecture:** [Content-aware format/strategy matrix](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Add row/header/sheet-preserving ingestion for `.csv`, `.tsv` and `.xlsx` to the shared PostgreSQL document pipeline, with exact table provenance and meaningful retrieval of identifiers/values. Keep `.xls`, `.xlsm`, `.ods` opt-in pending separate qualification.

## B. Context / Problem

Naively splitting a spreadsheet every 500 tokens detaches data rows from their header, units, worksheet and table context. Relevant questions often name a column, account, error code, product ID, or row. We need *table-aware* units and explainable citations, not generic flattened prose and invented page numbers.

## C. Current Repository State

**Source audit refreshed 2026-11-23:** [RAG-002](completed/TASK-RAG-002-ingest-text-and-markdown.md) and [PARSE-001](completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) are complete. The existing [parser_registry.py](../apps/workbench/parsing/parser_registry.py) contains a `DELIMITED_TABLE` candidate but does **not** qualify CSV/TSV/XLSX for public ingestion. The existing upload, document metadata, chunks and jobs are implemented; this task only adds approved spreadsheet/CSV format adapters and provenance. Spreadsheet parsing is NOT already implemented simply because Haystack `XLSXToDocument` or `CSVDocumentSplitter` exists upstream.

| Inspected source | Existing behavior | Boundary |
| --- | --- | --- |
| [`haystack/components/converters/csv.py`](../../haystack/components/converters/csv.py) `CSVToDocument` | CSV conversion available; encoding/row mode. | Preserve delimiter, quotes and typed text; do not misinterpret comma in quoted values. |
| [`haystack/components/preprocessors/csv_document_splitter.py`](../../haystack/components/preprocessors/csv_document_splitter.py) `CSVDocumentSplitter` | Already supports row-wise and threshold mode and source row/column start metadata. | Reuse; its pandas optional dependency and read kwargs need qualification. |
| [`haystack/components/converters/xlsx.py`](../../haystack/components/converters/xlsx.py) `XLSXToDocument` | Extracts each sheet into a tabular `Document`; supports CSV/Markdown table representation. | A flattened sheet is not a proven cell-level lineage; verify sheet/cell positions. |
| [`haystack/components/converters/multi_file_converter.py`](../../haystack/components/converters/multi_file_converter.py) | Routes CSV/XLSX using existing converters. | Reuse without reducing output to an opaque text blob. |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) `Chunk.metadata` | JSONB provenance; `page` optional. | Sheet/row/cell are separate typed metadata; do not overload `page`. |
| [`apps/workbench/postgres/postgres.py`](../apps/workbench/postgres/postgres.py) | Atomic version activation under RLS. | Reuse; no second spreadsheet DB. |
| [`apps/workbench/retrieval/lexical.py`](../apps/workbench/retrieval/lexical.py) | Native PostgreSQL `simple`/`ts_rank_cd` lexical retrieval. | Numeric/text exact matching requires actual benchmark; formula evaluation unsupported. |

The application-level upload/job/detail/chunk routes are implemented for currently qualified formats, but **no CSV/TSV/XLSX format adapter is qualified** in the current parser registry.

## D. Goal

An approved tabular file yields deterministic structured blocks containing table/sheet, header and row/cell provenance, with entire logical records maintained where possible. Every published chunk can be traced back to its sheet/table/row range and contains enough repeated header context for lexical retrieval. Malformed/oversized sheets fail safely without partial publication.

## E. Scope

- Qualified parsers for `.csv`, `.tsv` and `.xlsx`; explicit delimiter/quote/encoding/worksheet selection rules and revisioned parsing profile.
- Emit `table`, `header`, `row_group` elements with `sheet_name?`, `table_id`, `row_start/end`, `column_names`, `column_range?`, source file hash.
- Reuse existing `CSVDocumentSplitter` where it retains faithful source mapping; implement minimal bounded grouping only when existing behavior loses mandatory header/row provenance.
- Repeated header/units context for each child chunk, with row groups sized by approved word/model-token policy and protected row boundaries. Split oversized single cells only with explicit parent/offset metadata.
- Integrate with shared TASK-RAG-002 upload/jobs and PostgreSQL persistence; append capabilities after E2E evidence.
- Define mixed Excel sheets/table ranges, empty sheets, hidden sheets and formulas-as-data policy explicitly.

## F. Non-Goals

No formula execution/recalculation, spreadsheet macros, `.xlsm` automatic support, live SQL queries against workbook data, numeric aggregation with correctness guarantees, chart/OCR understanding, BI visualizations, pivot reconstruction promises, arbitrary workbook size or second data warehouse.

## G. Architecture / Boundaries

### PARSE/CONTENT ownership contract — non-duplication gate

- **Ownership:** PARSE-003 alone qualifies CSV/TSV/XLSX **sheet, cell, row, formula-text and header extraction**. PARSE-002 may extract a table physically embedded in DOCX/PPTX/HTML, but must reuse the shared typed `ParsedElement` boundary; do not create a second generic `TableElement` schema or spreadsheet-specific storage table.
- **CONTENT-001:** [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) owns durable, version-scoped `DocumentElement`/`ContentRepresentation` and exact original file/asset links. This parser exports canonical row/sheet/cell references, then a single CONTENT projection adapts them; it must not implement `AssetStorePort` or a separate evidence lookup route.
- **Visual charts:** Excel charts/pivots/images are only reported as unsupported/observed structures until qualified interpretation exists. [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) initially targets PDF figures; workbook chart support is a **coverage gap requiring a separately approved extension**, not already covered by CONTENT-003. Neither parser nor CONTENT infers numeric series from an Excel chart by guessing.
- **Evidence:** [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) resolves original sheet/row/column from stored source references. Parser does not implement a general citation service. [CONVERT-001](TASK-RAG-CONVERT-001-microsoft-markitdown-evaluation-and-safe-conversion-adapter.md) assesses Markdown as derived spreadsheet representation, not a second unconditional XLSX parser.

**Qualification modes:** Gate P = format-specific parser/structured chunk + existing PostgreSQL lexical publication (this task); Gate E = durable byte/evidence/representation resolution (CONTENT-001/005 or specialty CONTENT adapter). Gate P may pass while Gate E is NOT_IMPLEMENTED, but Gate P must not claim original evidence or multimodal completeness. No new global parser registry, ContentRepresentation storage or EvidenceResolver is permitted in this task.

`PARSE-001 verified source → CSV/TSV/XLSX adapter → structured table elements → row-group chunker (header repeated) → existing ingestion jobs/atomic PostgreSQL writer → lexical retrieval`. Parser owns *what cell/row exists*; chunking owns grouping; query runtime owns answer aggregation. Provider SDKs stay behind format adapters.

## H. Contracts / Interfaces / Data Model

`ParsedElement(kind="table_row_group", table_id, sheet?, row_start, row_end, column_names[], normalized_text, source_span?, parser_revision)` is the minimum. Row/column references are source derived, not invented post-flattening. For spreadsheet row `A12:D15`, preserve authoritative coordinate `A12:D15` if extractor can prove it; otherwise store an explicit missing-provenance flag and fail strict mode. All header repetition is distinguished from source text to prevent duplicate fact attribution. Formula source text may be recorded but **never evaluated**; cached displayed values must be labeled as cached, not recalculated. `processing_fingerprint` covers delimiter/encoding/locale/table header detection.

## I. Repository Files / Components Impacted

- CREATE `apps/workbench/parsing/tabular.py` or the existing parsing module's focused equivalent.
- EXTEND `apps/workbench/parsing/parser_registry.py` and `apps/workbench/chunking/chunking.py` (defined in PARSE-001/CHUNK-001).
- EXTEND `apps/workbench/ingestion/ingestion.py`, `apps/workbench/contracts/schemas.py`, `apps/workbench/api/application.py`, and `apps/workbench/api/openapi.json` only for approved formats; reuse shared upload/limits.
- CREATE `apps/workbench/parsing/tests/test_tabular_parsing.py`; EXTEND integration `test_ingestion_routes.py` and retrieval fixtures.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and API runbook.
- Must NOT edit applied migration, Haystack library code, PostgreSQL score label, general JSON/YAML config parsing or external file system paths.

## J. Implementation Requirements

### J0. Reconcile completed app owners and format-specific handoffs

1. Confirm current [parser registry](../apps/workbench/parsing/parser_registry.py), [parsing.py](../apps/workbench/parsing/parsing.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [chunking.py](../apps/workbench/chunking/chunking.py), [PostgreSQL publication](../apps/workbench/postgres/postgres_ingestion.py) and [actual contracts](../apps/workbench/contracts/schemas.py). The old blueprint predates completed RAG-002 and PARSE-001; do not reimplement their components.
2. Build a format/element/asset/evidence matrix and mark all unsupported extractions `NOT_QUALIFIED`; record original evidence status separately from parsed text.
3. Align this task's format-specific `ParsedElement` projection with CONTENT-001's long-lived `DocumentElement` contract **without building it here**. Confirm all source/span/line/page/time units are explicitly defined before using them as citations.

### J6. Format boundary regression and CONTENT handoff

Test an XLSX containing two sheets, merged cells, sparse rows, hidden sheet and a chart, plus CSV with quoted multiline values. Enforce exact spreadsheet coordinate/sheet provenance and no invented PDF page/crop. A chart warning is not CONTENT-003 graph inference. Preserve original spreadsheet bytes only through CONTENT-001 later, and test source/version/cursor handling with the existing PostgreSQL API.

### J1. Qualify parser paths

Confirm CSV parser behavior with UTF-8/BOM, escaped quotes, multiline cells, semicolon and tab delimiters; enforce deterministic dialect rather than unsafe guessing. Confirm XLSX converter sheet names, sparse rows, merged cells and formulas without executing. Pin pandas/openpyxl through app environment when needed.

### J2. Preserve structural metadata

Project ordered sheet/table/row groups. Group rows only inside one table and repeat verified headers/units. Deduplicate header copies from source provenance. Empty tables may produce warnings; empty output must never mark the entire file success. Source row/column references must be deterministic across repeat runs.

### J3. Bounded chunking and large-value protection

Define max rows, columns, cells, bytes, text length, sheets and parse duration; protect full logical records where possible. If one row exceeds the model budget, split fields with exact row/column references; do not silently truncate or cross workspace/source/table.

### J4. Shared ingestion/retrieval verification

Send approved formats through the same job API/atomic publication; run identifier and header+row queries against PostgreSQL FTS; verify identical source/chunk/row citations after restart and update. Do not present this as accurate numerical QA; that needs separate execution semantics.

### J5. Evidence and capability rollout

Use a minimum 10 representative datasets per format and 10 row/column/value queries per corpus; record structural coverage, citation correctness, p95 parse/chunk and index growth. Enable one format at a time. `xls/xlsm/ods` remain disabled until separate compatibility and macro security checks.

## K. Security / Governance / Observability

Spreadsheet formulas/macros are untrusted **data**. Disable evaluation, external workbook links, DDE and fetches. Enforce workbook decompression limits, maximum sheet/cell counts, no formula errors leaked, no PII in logs. All row and cell metadata remain tied to server-resolved scope, source and active version; sensitive columns follow existing source ACL. Log only format, parser/profile ID, counts, timings, warning/status codes.

## L. Testing / Evaluation / Runtime Verification

CSV quote/newline/embedded comma; TSV delimiter; Unicode; duplicate/empty headers; formulas; dates/number formats; hidden sheets; merged cells; duplicate values; blank tables; too many rows; decompression bomb; wrong MIME; malformed workbook; optional parser absent; API+DB outage and restart; rerun lexical and TXT/MD tests. Use focused `hatch run workbench-api:check`, `:test`, `:types` after necessary app deps.

## M. Acceptance Criteria

- [ ] Each enabled format passes parser, idempotent upload, PostgreSQL persistence and real lexical search E2E, with 0 fake source citations.
- [ ] Header/row/sheet provenance has 100% agreement with inspected golden fixtures (or explicit rejection in strict mode).
- [ ] Quoted CSV cells and multi-line rows are not split into incorrect columns; 0 silent dropped rows in golden matrix.
- [ ] Formulas, external links and macros are never executed or fetched.
- [ ] At least 10 files and 10 labeled queries per format evaluated; result quality and cost reported, not assumed.
- [ ] Unsupported legacy workbook formats are not advertised.

- [ ] Reuses **completed** PARSE-001/RAG-002/chunking and current API; no duplicate format registry, HTTP upload handler, persistence adapter or version publication.
- [ ] Does **not** implement CONTENT-001 original asset storage/`DocumentElement` persistence or CONTENT-005 evidence resolution; the parser exports accurate source/element spans for later adapters.
- [ ] `CSV/TSV/XLSX` format-specific supported/unsupported visual/attachment/graph cases are labelled truthfully; no inferred OCR/VLM/Mermaid/ASR behavior advertised from parsing.

## N. Documentation / Migration / Compatibility / Rollback

Register parser/profile revisions, limits and citations in one canonical architecture document; no schema change unless structured relational querying is explicitly required, which needs a separate migration task. Preserve existing v1 lexical contract and prior active source versions. Rollback disables one parser descriptor while retaining stored chunks and volume; old content remains readable under its original processing fingerprint.

## O. Mandatory Completion Checklist

- [ ] All new source paths and GitHub-relative links verified from the actual `tasks/` location.
- [ ] PARSE/CONTENT ownership boundaries exercised with fixture tests; no duplicate durable element/asset model.
- [ ] Existing SQL/API/upload/source-version test gates remain passing when new parser family is enabled.


- [ ] Source inventory and reuse verified; no duplicate table chunker introduced.
- [ ] Parsing, row/column citations, safe formula handling and size caps tested.
- [ ] Real HTTP+Postgres+retrieval regression and quality data recorded.
- [ ] Capabilities match qualified formats and docs are updated.
- [ ] All acceptance criteria and security gates met before COMPLETE.

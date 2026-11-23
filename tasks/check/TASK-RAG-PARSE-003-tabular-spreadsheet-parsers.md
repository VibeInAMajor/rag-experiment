# TASK-RAG-PARSE-003 — CSV, TSV and XLSX table-aware ingestion

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** PROPOSED — blueprint, not implemented  
**Priority:** P1 — spreadsheets and tabular business data  
**Dependencies:** TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001  
**Repository snapshot reviewed:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target:** `tasks/TASK-RAG-PARSE-003-tabular-spreadsheet-parsers.md`  
**Architecture:** [Content-aware format/strategy matrix](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Add row/header/sheet-preserving ingestion for `.csv`, `.tsv` and `.xlsx` to the shared PostgreSQL document pipeline, with exact table provenance and meaningful retrieval of identifiers/values. Keep `.xls`, `.xlsm`, `.ods` opt-in pending separate qualification.

## B. Context / Problem

Naively splitting a spreadsheet every 500 tokens detaches data rows from their header, units, worksheet and table context. Relevant questions often name a column, account, error code, product ID, or row. We need *table-aware* units and explainable citations, not generic flattened prose and invented page numbers.

## C. Current Repository State

| Inspected source | Existing behavior | Boundary |
| --- | --- | --- |
| [`haystack/components/converters/csv.py`](../haystack/components/converters/csv.py) `CSVToDocument` | CSV conversion available; encoding/row mode. | Preserve delimiter, quotes and typed text; do not misinterpret comma in quoted values. |
| [`haystack/components/preprocessors/csv_document_splitter.py`](../haystack/components/preprocessors/csv_document_splitter.py) `CSVDocumentSplitter` | Already supports row-wise and threshold mode and source row/column start metadata. | Reuse; its pandas optional dependency and read kwargs need qualification. |
| [`haystack/components/converters/xlsx.py`](../haystack/components/converters/xlsx.py) `XLSXToDocument` | Extracts each sheet into a tabular `Document`; supports CSV/Markdown table representation. | A flattened sheet is not a proven cell-level lineage; verify sheet/cell positions. |
| [`haystack/components/converters/multi_file_converter.py`](../haystack/components/converters/multi_file_converter.py) | Routes CSV/XLSX using existing converters. | Reuse without reducing output to an opaque text blob. |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) `Chunk.metadata` | JSONB provenance; `page` optional. | Sheet/row/cell are separate typed metadata; do not overload `page`. |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | Atomic version activation under RLS. | Reuse; no second spreadsheet DB. |
| [`apps/workbench/api/lexical.py`](../apps/workbench/api/lexical.py) | Native PostgreSQL `simple`/`ts_rank_cd` lexical retrieval. | Numeric/text exact matching requires actual benchmark; formula evaluation unsupported. |

No application-level spreadsheet upload route or schema-aware chunker is implemented in the inspected snapshot.

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

`PARSE-001 verified source → CSV/TSV/XLSX adapter → structured table elements → row-group chunker (header repeated) → existing ingestion jobs/atomic PostgreSQL writer → lexical retrieval`. Parser owns *what cell/row exists*; chunking owns grouping; query runtime owns answer aggregation. Provider SDKs stay behind format adapters.

## H. Contracts / Interfaces / Data Model

`ParsedElement(kind="table_row_group", table_id, sheet?, row_start, row_end, column_names[], normalized_text, source_span?, parser_revision)` is the minimum. Row/column references are source derived, not invented post-flattening. For spreadsheet row `A12:D15`, preserve authoritative coordinate `A12:D15` if extractor can prove it; otherwise store an explicit missing-provenance flag and fail strict mode. All header repetition is distinguished from source text to prevent duplicate fact attribution. Formula source text may be recorded but **never evaluated**; cached displayed values must be labeled as cached, not recalculated. `processing_fingerprint` covers delimiter/encoding/locale/table header detection.

## I. Repository Files / Components Impacted

- CREATE `apps/workbench/api/parsers/tabular.py` or the existing parsing module's focused equivalent.
- EXTEND `apps/workbench/api/parser_registry.py` and `apps/workbench/api/chunking.py` (defined in PARSE-001/CHUNK-001).
- EXTEND `apps/workbench/api/ingestion.py`, `contracts.py`, `application.py`, and `openapi.json` only for approved formats; reuse shared upload/limits.
- CREATE `apps/workbench/api/tests/test_tabular_parsing.py`; EXTEND integration `test_ingestion_routes.py` and retrieval fixtures.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and API runbook.
- Must NOT edit applied migration, Haystack library code, PostgreSQL score label, general JSON/YAML config parsing or external file system paths.

## J. Implementation Requirements

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

## N. Documentation / Migration / Compatibility / Rollback

Register parser/profile revisions, limits and citations in one canonical architecture document; no schema change unless structured relational querying is explicitly required, which needs a separate migration task. Preserve existing v1 lexical contract and prior active source versions. Rollback disables one parser descriptor while retaining stored chunks and volume; old content remains readable under its original processing fingerprint.

## O. Mandatory Completion Checklist

- [ ] Source inventory and reuse verified; no duplicate table chunker introduced.
- [ ] Parsing, row/column citations, safe formula handling and size caps tested.
- [ ] Real HTTP+Postgres+retrieval regression and quality data recorded.
- [ ] Capabilities match qualified formats and docs are updated.
- [ ] All acceptance criteria and security gates met before COMPLETE.

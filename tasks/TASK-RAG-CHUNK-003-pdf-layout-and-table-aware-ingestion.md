# TASK-RAG-CHUNK-003 — Paginated PDF layout- and table-aware ingestion

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** IN PROGRESS — source audit and bounded parser qualification  
**Priority:** P1 · specialized paginated document family  
**Dependencies:** TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001; UI support follows through an approved TASK-UI-003 extension  
**Repository snapshot reviewed:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target path:** `tasks/TASK-RAG-CHUNK-003-pdf-layout-and-table-aware-ingestion.md`  
**Canonical decision:** [Content-aware chunking strategy](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Add a qualified parser adapter and chunking policy for **text-extractable, paginated PDFs** that preserves page/section provenance, table rows, headings and captions while enforcing bounded model-aware child chunk sizes and reusing current PostgreSQL ingestion.

## B. Context / Problem

PDFs are visual layouts, not plain paragraphs. A blanket 500-word or 500-token splitter may separate numerical values from their column headers, put the page cited in the answer on the wrong segment, or merge unrelated sections. Evidence from NVIDIA's page-level RAG benchmarks favors page boundaries on average for several paginated datasets, but does not guarantee every page fits an embedding input or that page-level is optimal for analytical tasks. We need a **page-as-context / smaller-chunk-as-retrieval-unit** policy, with verified layout extraction, explicit failure/overflow and measured quality.

The current Workbench does **not** contain a qualified Docling PDF ingestion integration. The UI mentions Docling in a demonstration node, but that is only display metadata and the constructor validator marks the parser unsupported. This task integrates PDF parsing behind a reviewed app-owned adapter; it must not pretend Docling is already installed or that a scanned image PDF has usable text.

## C. Current Repository State

**Current checkout audit, 2026-11-22, before implementation:** base `a0a353d5c5ab9504b9284008fcc1f67d1b0f9809` is clean and already has durable TXT/Markdown/Python ingestion, atomic job-coupled PostgreSQL publication, native Qwen token admission and a shared upload-policy owner. `upload_transport.py` and `boundary.py` reuse `upload_policy.py`; `parsing.py`/`parser_registry.py` own byte verification and typed parser results; `chunking.py` owns policy dispatch, common `PreparedChunk` and native admission. The original discovery table below predates those features. PDF is still unqualified. No upstream Haystack, applied SQL, Python AST adapter, validator semantics or Preview fixture changes are planned.

**Superseding user decision:** install Docling and declare it in application dependencies; do not replace it merely because it was initially absent. Docling 2.151.1 / MIT is pinned in the reviewed application Hatch environment and will be the primary parser, with its HybridChunker explicitly qualified. pdfplumber 0.11.11 / MIT and pypdf 7.1.1 / BSD-3-Clause are comparison/safety tools. Parser work must run in a bounded local child process with no OCR or network resolution; model assets must be provisioned explicitly before runtime, never downloaded during upload. Resource/extraction measurements follow before enabling the format. The earlier pdfplumber-only proposal is superseded.

| Evidence | Implementation finding / necessary change |
| --- | --- |
| [`apps/workbench/web/src/domain/catalog.ts`](../apps/workbench/web/src/domain/catalog.ts) | `parser` display component is `DoclingConverter` and its `.format` option is UI data. Not an executable PDF parser binding. |
| [`apps/workbench/validator/registry.py`](../apps/workbench/validator/registry.py) | Parser mapping has no approved constructor dependency; construction validator is not an ingestion or OCR service. |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | Existing `Chunk` provides `page: int?`, title, content, JSON metadata, stable scoped source/version IDs. No dedicated table block or page parent storage exists. |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | `_publish()` stages, validates and atomically activates a version; `get_chunk()` and lexical retrieval enforce active workspace scope. |
| [`apps/workbench/api/migrations/0001_initial.up.sql`](../apps/workbench/api/migrations/0001_initial.up.sql) | Existing bounded `chunks.content`, page, RLS, search_vector. Must not edit applied revision. |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) | Approved read-only lexical API; TXT/Markdown upload is planned in TASK-RAG-002 and will supply shared upload/jobs/contracts. |
| [`haystack/components/converters/pypdf.py`](../haystack/components/converters/pypdf.py) and [`pdfminer.py`](../haystack/components/converters/pdfminer.py) | Existing generic PDF text converters, but presence of converters alone does NOT verify table/layout/page fidelity. Benchmarks needed as baseline. |
| [`haystack/components/preprocessors/recursive_splitter.py`](../haystack/components/preprocessors/recursive_splitter.py) | Recursive splitter for fallback/controls, not authoritative page/table preservation. |
| [`apps/workbench/api/config.py`](../apps/workbench/api/config.py) | API app configuration currently local-only; no reviewed Docling runtime/inference dependency. |
| [Docling chunking docs](https://docling-project.github.io/docling/concepts/chunking/) | `HierarchicalChunker`, `HybridChunker`, table header repetition are available in Docling ecosystem, **not yet qualified in this Workbench runtime**. |
| [`tasks/TASK-RAG-002-ingest-text-and-markdown.md`](TASK-RAG-002-ingest-text-and-markdown.md) | Initial allowlist is TXT/Markdown and a 1 MiB request cap. PDF requires new explicit file/body bounds and testing; no silent extension. |

**Known risk:** PDF may have no text layer, oversized table cells or page/column order ambiguity. A parser that returns empty text while reporting success produces a silent search false-negative. No run of a Docling PDF parser has been executed for this task; no benchmark is claimed.

## D. Goal

A multi-page, text-extractable PDF with sections and a table can be uploaded using the authorized ingestion job workflow. The backend extracts trustworthy page/heading/table units, produces bounded chunks that retain source and real page provenance, atomically publishes them to PostgreSQL, and returns lexical hits from the expected table/page with correct citations. Unsupported encrypted/scanned/ambiguous PDFs fail safely with actionable bounded diagnostics, keeping prior source versions searchable.

## E. Scope

1. Approve an application-local PDF parser adapter, preferably Docling after measured extraction quality and dependency/runtime review; prove exact parser version and resource bounds.
2. Add PDF-only trusted MIME/signature and multipart limits, explicitly distinct from current TXT/Markdown limits where necessary; no extension-only trust.
3. Extract typed page/section/table units from layout; keep captions, reading order, page range and parse warnings.
4. Implement `page_layout` strategy plus `table_aware` overlay in the shared resolver from TASK-RAG-CHUNK-001. Use Docling `HybridChunker` or an equivalent explicitly qualified adapter; verify supplied tokenizer identity and output behavior, do not assume defaults.
5. Keep pages as context/parent units and publish bounded retrievable children; oversized pages/tables get bounded structure-aware refinement and truthful warning codes.
6. Persist actual `page`, `heading_path`, `table_id?`, row/header/caption and parent ID metadata using existing `Chunk`/`SourceVersion` and job-coupled atomic publication.
7. Add table, numeric QA and page-citation evaluation and a negative security/recovery matrix.

## F. Non-Goals

No scanned-document OCR in this task, no PDF visual question answering, image embedding, handwriting recognition, DOCX/Excel parsing, web crawling, tree-sitter, semantic LLM chunker, arbitrarily large PDFs, external page retrieval, UI image viewer, automatic migration to a second vector store, or general-purpose arbitrary Haystack graph execution. OCR and DOCX require separate qualification; never call scanned PDF `Indexed` after empty extraction.

## G. Architecture / Boundaries

- [x] Application parsing adapter (Docling behind an app-owned bounded interface after qualification).
- [x] Application chunking policy (shared resolver; do not create a second router).
- [x] Provider isolation: parser implementation outside core; no Docling-specific types in persistence contract.
- [x] Persistence and RAG: existing Postgres `Chunk`/atomic version publication; existing FTS for smoke; embeddings deferred until qualified.
- [x] Security: untrusted PDFs and oversized decompression, encrypted content and malicious layouts controlled by resource limits.
- [x] Observability: stage times, parser pages/tables/warnings, no raw document text in logs.
- [x] Testing/evaluation and docs.
- [ ] Agent execution: N/A — no LLM agent controls PDF processing.

Desired flow:

```text
Shared authenticated/authorized upload + bounded PDF bytes
     -> PDF signature/safety checker
     -> app parser adapter -> typed Page/Section/Table elements
     -> shared ChunkingPolicyResolver -> page_layout + table-aware overlay
     -> structure-aware child split/token verifier
     -> PreparedChunk (real page references, heading/table metadata)
     -> existing ingestion job / atomic PostgresPersistence publication
     -> PostgreSQL lexical search + source-aware UI citations
```

## H. Contracts / Interfaces / Data Model

- PDF is a **separate** document class and only advertised after qualified parser installed and transport gates tested. Validate `%PDF-` signature, MIME allowlist, source basename, size and page count. Signature alone is not full security validation.
- Parser result must carry `source_id`, verified pages with **1-based** page numbers, extraction warnings, ordered text blocks, headings, and table blocks with column headers/row order/caption. If a property cannot be extracted reliably, it is missing plus a warning, not invented.
- Policy `page_layout` selects trustworthy page boundaries and applies per-page child splitting as needed. Optional `table_aware` overlay can repeat table heading/caption text for retrieval; maintain original excerpt separately from repeated context.
- `parent_structural_id` links children to a source/page/section context; whether this stays only JSON metadata or uses a relational parent table is an explicit measured decision. Do not invent a duplicate document-store schema.
- `Chunk.page` must be sourced from real extractor page metadata; a child spanning pages records verified page range metadata or is split at page boundary. No unqualified `page=1` default.
- `Chunk.content` <=32,768 characters; actual model-token cap enforced only when tokenizer qualified. An oversized indivisible table row causes bounded failure or a named overflow policy with sufficient header/key context; never silently drop cells.
- `processing_profile_id`/revision, `parser_revision`, `tokenizer_ref`, `heading_path`, `table_id`, `table_header_repeated` and `parse_warning_codes` are persisted in bounded metadata. For public search, use existing source/version identifiers and raw truthful `postgres_ts_rank_cd` until dense/hybrid profile separately approved.
- Jobs / status / upload and chunk GET APIs from TASK-RAG-002 are reused, not reimplemented. PDF-specific error codes include `PDF_ENCRYPTED`, `NO_EXTRACTABLE_TEXT`, `PDF_TOO_LARGE`, `PDF_PARSE_TIMEOUT`, `PDF_LAYOUT_UNCERTAIN`, `TABLE_OVERFLOW`, as appropriate after confirming existing error vocabulary.

## I. Repository Files / Components Impacted

| Path | Action / purpose |
| --- | --- |
| `apps/workbench/api/chunking.py` | Extend existing strategy registry with `page_layout` and table overlay, avoid duplicate rules. |
| `apps/workbench/api/parsing.py` or actual TASK-RAG-002 parsing owner | Add only a bounded PDF parser adapter; isolate Docling-specific imports/version from domain. |
| `apps/workbench/api/ingestion.py` or actual TASK-RAG-002 ingestion module | Extend verified format dispatcher and shared jobs; no second HTTP endpoint. |
| `apps/workbench/api/config.py` | App-only parser resource limits/capabilities; keep loopback and credentials contract intact. |
| `apps/workbench/api/boundary.py`; `application.py` | Exact PDF upload size/content-type and response allowances; no broad CORS bypass. |
| `apps/workbench/api/contracts.py` and `openapi.json` | Only additive declared PDF support/parse metadata after runtime tests. |
| `apps/workbench/api/tests/test_pdf_chunking.py` | CREATE typed layout/table/page golden and negative fixtures. |
| `apps/workbench/api/tests/test_ingestion_routes.py` or task-created equivalent | Extend upload/rollback/real retrieval and signed page metadata checks. |
| `apps/workbench/api/tests/fixtures/pdf/` | CREATE small non-sensitive, reproducible text/tables/multipage/corrupt/scanned PDF fixtures; no personal data. |
| `pyproject.toml` | Add pinned **application-only** optional parser dependency with reviewed license/security and tested environment. |
| `docs-website/docs/architecture/content-aware-chunking-strategy.md`, `apps/workbench/api/README.md` | Update supported status, parser version, constraints, runtime warnings and quality evidence. |

**Must NOT change:** `haystack/` core, applied migration `0001`, existing version publication semantics, unrelated vector index, code AST component, preview fixtures, or Python validator semantics. If true parent/page FK/indexes are needed, write a separate additive migration task before changing schema.

## J. Implementation Requirements — ordered executable blueprint

### J1. Parser qualification and threat/resource bounds

1. Inspect current parser libraries and Docling availability/license/runtime. Pin approved parser revision and characterize CPU/RAM/time on small PDF test inputs in app-isolated Hatch environment.
2. Build a corpus of text PDFs (1/5/20 pages), two-column text, table with caption, table spanning pages, encrypted document, malformed PDF, scanned PDF without text and a PDF with extreme layout/large decompression potential. All fixtures are non-sensitive.
3. Explicitly choose development-only maximum raw bytes/pages, parser deadline and memory budget through tests. The existing 1 MiB TXT/Markdown cap must not be silently widened for all files; require a separate checked PDF allowance.
4. If parser crashes, times out, returns zero text or cannot identify pages, return an explicit failed job. Never publish zero chunks or mark a PDF indexed from filename alone.

**J1 gate:** parser bounded, version/license known, supported/unsupported fixture cases enumerated with exact outputs and failure reasons.

### J2. Extract trustworthy structural blocks

1. Normalize parsed PDF to application-owned typed `Page`, `Section`, `TextBlock`, `Table` projections rather than persisting Docling classes or binary objects.
2. Preserve exact reading order as extracted and flag uncertainty in multi-column layouts. Verify captions, page number, table row headers, row/cell order and section nesting against manually checked ground truth.
3. Never use text-only extraction as proof of accurate table reconstruction. When a table cannot be reconstructed reliably, mark `TABLE_STRUCTURE_UNCERTAIN` and use an explicit approved safe fallback or fail based on quality gate.
4. Preserve source text/excerpts for citation and enrich retrieval representation only through a documented bounded header/caption prefix, not by rewriting facts.

**J2 gate:** manual golden comparison for page, heading and table extraction; zero silent lost numerical rows in gated fixtures.

### J3. Implement bounded page/layout chunking

1. Use shared resolver from TASK-RAG-CHUNK-001; a verified paginated PDF chooses `page_layout` with optional `table_aware` overlay. A PDF with no usable layout cannot claim page-level success.
2. Preserve page as parent context; split a large page into coherent child blocks. Compare initial 512/64 and 768/0 or 768/64 child policies against page-alone controls at consistent **retrieval token budget**.
3. Use Docling `HybridChunker` where qualified, with explicitly selected tokenizer; verify splitting/merging and `repeat_table_header` behavior on long tables. No mixing unrelated tables and no hidden half-row truncation.
4. Overlap must remain within coherent parent section/page; crossing page boundary is permitted only if a manually verified element truly spans it and resulting provenance represents both pages.
5. If a table is longer than the child cap, partition by full rows with repeated column header and caption, keep row order and table identity; oversized single row follows explicit overflow error or a documented line/column-safe policy.
6. Encode real source/page/section/table metadata, model count unit, profile fingerprint and parse warnings into PreparedChunk; preserve semantic identity and stable ID generation used by TASK-RAG-002.

**J3 gate:** every stored PDF child maps to a real source and page range; no unexpected page/row/cell loss or false token-budget claim.

### J4. Integrate shared ingestion, jobs and existing PostgreSQL

1. Extend TASK-RAG-002 shared multipart route and document type allowlist only after parser qualification. Do not create an independent PDF store, job table, or document writer.
2. Persist child chunks through the same scoped `Chunk`/`SourceVersion`/atomic `_publish()` transaction; preserve prior active version on failed parser/table/DB operation.
3. Expose documented parse warning codes in the existing job/detail response and actual chunk/page provenance in existing GET chunks; no fictional `pages` value in UI.
4. Search for a unique table header/numeric identifier using existing lexical `postgres-fts-baseline` profile; results must reference actual PDF source and real page. Distinguish lexical proof from numerical QA/semantic proof.
5. UI support (if required) consumes these authoritative metadata fields; do not put Docling SDK or layout parsing in React.

**J4 gate:** real PDF upload -> durable active version -> real chunk GET -> exact term lexical search -> correct page citation, including API/DB restart.

### J5. Benchmark alternative policies and negative paths

1. Curate ≥10 representative text PDFs with ≥20 audited evidence queries covering exact values, table cross-row questions, figure/table caption, section queries and cross-page analytical evidence.
2. Compare page child/section-aware versus plain recursive baseline, under identical model/retriever configuration. Report evidence Recall@5/10, page citation correctness, row/column integrity, token IoU/duplicate share, child count, parser failures, parse+split p95 and query latency.
3. Validate corpus changes and version update leave only one active version; parser failures, encrypted/scanned PDF, overlarge pages and DB outages do not corrupt previous search results.
4. Test concurrent uploads, idempotency key replay, signed pagination cursor expiry after new version, request-size violations, path traversal, malicious PDF content that resembles policy instructions and cross-workspace authorization.
5. Record parser runtime stability and resource use, no raw PDF text in logs, no unapproved outbound requests, and explicit no-OCR limitation.

**J5 gate:** benchmark and all negative tests pass; evidence demonstrates PDF page/table quality relative to baseline, not universal superiority.

## K. Security / Governance / Observability

Uploaded PDFs are untrusted potentially hostile binary inputs. Parse only under bounded CPU/RAM/page/time quotas; never use unrestricted shell commands, extract embedded programs, follow external PDF links, or resolve paths outside protected temp areas. Isolate Docling runtime behind a dependency boundary with pinned/verified versions and license/security review. Enforce local-development scope, app-role forced RLS and existing source/version ownership. Log only stage, selected profile, page/table counts, warning codes, elapsed time, resource measures and correlation IDs; do NOT log raw text, vector payloads, credentials, binary pages or parser tracebacks. Do not silently enable OCR or ship scanned PDFs to a remote service. Published chunks remain subject to original source retention and access decisions.

## L. Testing / Evaluation / Runtime Verification

```text
hatch --version
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
```

Use existing `httpx.AsyncClient` + app lifespan test patterns in `apps/workbench/api/tests/test_lexical_routes.py`. Container tests require **disposable** PostgreSQL setup and must record real PASS/SKIP separately. Add parser-only goldens and a PDF ingestion HTTP smoke with actual small non-sensitive file. If runtime dependency is optional, test absence produces an `UNSUPPORTED_FORMAT`/`PARSER_UNAVAILABLE` error and does not advertise PDF capability. Regression-test existing TXT/Markdown, lexical, auth, validator and UI flows when shared code changes. Record extraction page/table truth labels and associated metric definitions in reusable `.md` evidence summaries, not a success story from mock data.

## M. Acceptance Criteria

- [ ] Versioned qualified PDF parser is installed only in the reviewed application environment and fails safely when unavailable.
- [ ] All PDF chunks have real source/version provenance; where reliable pages exist, `Chunk.page` and page-range metadata match manually audited input.
- [ ] No PDF with missing text/OCR requirement is marked indexed or publishes an empty chunk set.
- [ ] Table header/caption/row labels are preserved in retrieved child context; data cells are not silently dropped or spliced across unrelated rows.
- [ ] A PDF page larger than child token target is split within bounded structure without claiming a false model-token count.
- [ ] Explicit upload → persistent job/active version → chunk inspection → lexical retrieval works on actual PostgreSQL, including restart and source update.
- [ ] Failed/incompatible/corrupt/encrypted PDF leaves previously published version and search intact, with sanitized diagnostic code.
- [ ] At least 10 representative PDFs and 20 evidence queries produce a recorded page/section/plain-recursive comparison with source/page citation accuracy and resource cost.
- [ ] New format support is not advertised before parser/route/capabilities checks pass; UI displays only authoritative available metadata.
- [ ] No alternate document store, upstream Haystack fork, unreviewed OCR/network calls or destructive migration is added.

## N. Documentation / Migration / Compatibility / Rollback

Document parser revision, accepted PDFs, page/table limitations, exact byte/page/time caps, layout confidence handling, tokenizer/profile identity and measured benchmark outcomes in architecture/operations docs. Existing TXT/Markdown upload shape and lexical `postgres_ts_rank_cd` semantics remain stable. **DB migration is not initially required** because `Chunk.page`/JSON metadata exist; if indexed parent/child constraints or compressed original PDF storage become required, stop and create a separate approved migration. Rollback disables PDF parsing policy and capability while preserving current DB volume and previously published source versions; do not auto-delete or rebuild unrelated data. OCR, DOCX, image embeddings and advanced layout/semantic reranking remain deferred to focused tasks.

## O. Mandatory Completion Checklist

- [ ] Current source paths and task dependencies verified against working tree before code changes.
- [ ] Parser installation/license/resource limits evaluated with actual PDF fixtures.
- [ ] Page/heading/table projection and provenance implemented; silent empty extraction blocked.
- [ ] Shared content-aware policy and existing PostgreSQL ingestion/job/publication reused without duplicates.
- [ ] Model-token unit declarations and oversize/table policies verified, no misleading 500-token claim.
- [ ] Correctness, negative/security, restart, update and regression suites executed with evidence.
- [ ] Page-citation/table-retrieval evaluation recorded with controlled baseline comparison.
- [ ] Documentation and feature advertisement match implemented parser capabilities.
- [ ] Migration/rollback decisions explicit, no applied SQL overwritten and no data erased.
- [ ] Measurable acceptance evidence and actual commands captured before marking COMPLETE.

**Task remains PROPOSED until Section O and live extraction/search evidence pass.**

# TASK-RAG-PDF-001 — Restartable seekable PDF page windows for 200 MiB and 1000 pages

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-PDF-001-bounded-page-window-processing.md

## A. Title

Restartable seekable PDF page windows for 200 MiB and 1000 pages.

## B. Context / Problem

Raising 32 to 1000 would bypass neither PdfPage/PdfBlock validators nor whole-document bytes/JSON/result limits and single conversion wall timer. Need page-level bounded work, not only HTTP async.

## C. Current Repository State

pdf_models.py PdfLimits max 8 MiB/32 pages, PdfPage/PdfBlock page<=32, PdfDocument blocks<=4096; pdf_parser.py pushes bytes into subprocess stdin; pdf_worker.py uses BytesIO/pypdf and Docling DocumentStream, 180s CPU-only conversion and 8 MiB result; parse_source creates complete extraction.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Accept candidate 100/200 MiB, 256/1000-page TEXT-LAYER PDFs through bounded independent windows with durable replay and exact global page provenance, without falsely claiming OCR.

## E. Scope

- Whole-file seekable safety preflight
- immutable original SHA verification
- Docling 1-based page_range 16/32-page windows
- window checkpoints
- per-window resource caps
- existing table/numeric integrity
- global page identity.

## F. Non-Goals

- No whole-document BytesIO or stdin payload, no 1000-page PdfDocument object, no unlimited JSON, no automatic GPU/OCR, no 210s completion SLA.

## G. Architecture / Boundaries

AssetStorePort.open -> seekable safety preflight -> sandboxed Docling Path/page_range -> checked window results -> persisted checkpoints -> existing PDF chunking -> staged index. Keep active version unchanged until all windows pass.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

PdfWindow{original_sha256,page_start,page_end,total_pages,parser_revision,assets_revision,blocks,warnings,checksum}; separate global pages/bytes from per-window blocks/cells/chars/memory/time/output; 1-based global page and stable block IDs.

## I. Repository Files / Components Impacted

EDIT pdf_models.py, pdf_parser.py, pdf_worker.py, pdf_sandbox.py, parsing.py, pdf_chunk_preparation.py, pdf_chunking_adapter.py and checkpoint/test layers; reuse Docling model manifest.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Read staged original via trusted seekable file, enforce PDF object/decompression, unsafe actions, encrypted and unsupported geometry bounds.
2. Verify pinned Docling convert(Path, page_range=(start,end), max_num_pages, max_file_size) semantics, and independently verify returned global page IDs.
3. Spawn quota-limited subprocess per bounded window; no 200 MiB stdin nor one large result object.
4. Persist each verified window and checksum with parser/profile revisions; resume failed windows only.
5. Preserve heading/table/row/numeric/page/box provenance across windows, with explicit unsupported scanned pages.
6. Complete document only after all declared pages accounted for; failed window cannot publish.
7. Benchmark actual supported CPU/GPU configurations rather than assuming GPU helps.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Use offline sandbox, trusted scoped original ref only, no worker path traversal, no external services, bounded RAM/CPU/disk/GPU per process, poisoned compressed PDF refusal.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

32/33/255/256/999/1000/1001 page inputs, 8/100/200 MiB, huge content streams, PDF encryption, malicious objects, numeric/table boundaries, empty/scanned pages, kill/restart/replay, actual memory and page-quality evidence.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] 200 MiB never materialized as one PDF subprocess byte payload
- [ ] all pages counted with exact global IDs
- [ ] no partial ready version
- [ ] preserved numeric/table fidelity
- [ ] 1000-page capability off until on-host qualification.

## N. Documentation / Migration / Compatibility / Rollback

Current 8 MiB/32 pages remains default; later 100 MiB/256 then 200 MiB/1000 only after quality and resource gates pass.

Update affected OpenAPI, capability limits, operator docs and migration plans. New SQL schema must be additive; preserve accepted originals and prior active source generations.

## O. Mandatory Completion Checklist

- [ ] Reinspect source/SQL/tests and update Section C if changed.
- [ ] Confirm reuse of existing source/job/parser/chunker/storage owners.
- [ ] Prove workspace isolation, failure, disconnect, replay, crash and rollback paths.
- [ ] Test contracts, migration and affected regression suites.
- [ ] Record real resource and quality evidence or mark NOT TESTED/BLOCKED.
- [ ] Update docs and checked acceptance items with links to evidence.
- [ ] Record modified files, executed commands and commit.
- [ ] Mark COMPLETE only after every applicable gate passes.

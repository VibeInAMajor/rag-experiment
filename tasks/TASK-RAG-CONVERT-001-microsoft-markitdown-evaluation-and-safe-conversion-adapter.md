# TASK-RAG-CONVERT-001 — Evaluate Microsoft MarkItDown for loss-aware Markdown conversion

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — implementation blueprint, no runtime claim  
**Priority:** P1  
**Dependencies:** completed RAG-PARSE-001/RAG-002; CONTENT-001 for exact originals  
**Source reviewed:** cb7fe844084133b7e09a623e0e39767af1e0d9f1  
**Target:** tasks/TASK-RAG-CONVERT-001-microsoft-markitdown-evaluation-and-safe-conversion-adapter.md

## A. Title

Evaluate Microsoft MarkItDown for loss-aware Markdown conversion

## B. Context / Problem

The Microsoft open-source MarkItDown utility converts common PDF, Office, HTML and other files into Markdown for text analysis. **Markdown is not a more efficient database storage engine**: PostgreSQL already stores indexed text and JSONB, and converting original files loses potentially important figures, page coordinates, merged tables and slide/sheet metadata. MarkItDown can help some formats but must be benchmarked against already-present Docling/native parsers, with original bytes retained. Its README warns conversion runs with process I/O privileges; OCR/vision plugins and Azure Document Intelligence/Content Understanding are separate optional and possibly billable services.

## C. Current Repository State

[parsing.py](../apps/workbench/parsing/parsing.py) and [parser_registry.py](../apps/workbench/parsing/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/chunking/chunking.py), [ingestion.py](../apps/workbench/ingestion/ingestion.py) and [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [models.py](../apps/workbench/persistence/models.py) and [postgres.py](../apps/workbench/postgres/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [schemas.py](../apps/workbench/contracts/schemas.py) own API/capabilities. [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py), [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
Existing Markdown ingestion preserves structural headings/fences; current project has no MarkItDown application adapter. Official Microsoft MarkItDown docs https://github.com/microsoft/markitdown warn it targets analysis rather than human high-fidelity conversion. Existing Docling PDF is being qualified and must not be discarded; repository state may advance, so confirm parser registry and tests before coding.

**Verification limit:** this is a source-backed task, not proof that the proposed feature exists. Re-inspect current code at implementation start.

## D. Goal

A per-format GO/NO-GO comparison identifies where MarkItDown improves retrieval or engineering cost without unacceptable source fidelity, privacy or original-evidence loss. If approved, output is an explicitly versioned derived Markdown representation, not the canonical source.

## E. Scope

Evaluation of built-in offline converter versus current Native/Docling for at least DOCX/PPTX/XLSX/PDF/HTML/Markdown; structural and source-span fidelity, citations, indexed bytes and CPU/GPU/network costs; security of plugins and remote variants; optional post-GO adapter qualification.

## F. Non-Goals

No unconditional install of all optional dependencies, no default external URL access, no automatic cloud OCR, no replacement of source bytes or PDF evidence by Markdown, and no parser registry activation without measured tests.

## G. Architecture / Boundaries

Source bytes -> existing safe format inspection -> optional qualified converter adapter -> ParsedElements plus DerivedMarkdown ContentRepresentation -> existing chunker -> PostgreSQL. CONTENT-001 owns original source and links; converter cannot redefine WorkspaceContext or bypass sandbox.

## H. Contracts / Interfaces / Data Model

DerivedConversion{source/version hash,format,converter_id/revision,derived_markdown_sha256,asset_id,source_to_derived_span_map,loss_report,confidence_status,processor_elapsed_ms,feature_coverage}; source original hash always preserved. MarkItDown Markdown should be searchable only if required data/provenance checks pass. Vendor/cloud modules require explicit opt-in provider capability.

External schema changes MUST be reviewed in Pydantic/OpenAPI/client and versioned explicitly.

## I. Repository Files / Components Impacted

Use [parsing.py](../apps/workbench/parsing/parsing.py), [parser_registry.py](../apps/workbench/parsing/parser_registry.py), [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py), [ingestion.py](../apps/workbench/ingestion/ingestion.py); CREATE apps/workbench/parsing/tests/test_markitdown_comparison.py, safe non-sensitive file fixtures and tasks/MARKITDOWN_CONVERSION_DECISION_2026-11-23.md. Only after GO may conversion_adapters.py and pinned dependency be introduced. MUST NOT touch applied migrations or current Live index during trial.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/parsing/parser_registry.py`](../apps/workbench/parsing/parser_registry.py) | trusted file classification and qualified parsers |
| [`apps/workbench/parsing/parsing.py`](../apps/workbench/parsing/parsing.py) | ParsedDocument/ParsedElement and Markdown fences |
| [`apps/workbench/parsing/pdf/pdf_worker.py`](../apps/workbench/parsing/pdf/pdf_worker.py) | existing isolated Docling text/table parser |
| [`apps/workbench/parsing/pdf/pdf_models.py`](../apps/workbench/parsing/pdf/pdf_models.py) | page/box/table structure to compare against Markdown |
| [`apps/workbench/chunking/pdf/pdf_chunking_adapter.py`](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) | Docling HybridChunker and structural retrieval text |
| [`apps/workbench/ingestion/ingestion.py`](../apps/workbench/ingestion/ingestion.py) | approved ingestion and source fingerprints |
| [`apps/workbench/parsing/tests/test_parsing.py`](../apps/workbench/parsing/tests/test_parsing.py) | Markdown structure/fenced blocks tests |
| [`apps/workbench/chunking/pdf/tests/test_pdf_chunking.py`](../apps/workbench/chunking/pdf/tests/test_pdf_chunking.py) | page/table golden test |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/20-implementation-step-03-parsing-and-chunking.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/20-implementation-step-03-parsing-and-chunking.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## J. Implementation Requirements — ordered blueprint

1. Freeze current converter/version/license and security assumptions; test in a no-network sandbox with no enabled plugins and smallest dependency set.
2. Create >=12 representative files across 6 classes and 40 labeled retrieval/citation questions, including merged cells, images, diagram, scan, tables and multilingual text.
3. Run MarkItDown and qualified existing converter on identical source bytes; compare output markdown, layout/figure/table and page/source spans, not just length.
4. Compute source/evidence hit@5, nDCG where judgments exist, cell/numeric accuracy, heading preservation, lost-element rate, byte size, parse latency p50/p95 and memory.
5. Review optional OCR plugin and Azure endpoints separately for data egress, recurring cost, model dependencies and restricted access. No silent remote calls.
6. Publish per-format GO/NO-GO with deployment/license, precise limitations, rollback and approval. Do not install production plugin merely because it generated readable Markdown.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Pin Microsoft MarkItDown source/version/license. Run built-in converter in an isolated child with no network, no optional plugins, bounded I/O and safe local paths. Contrast optional Azure Document Intelligence and vision plugin (not assumed local).

**J8.** Build ≥12 golden DOCX/PPTX/XLSX/PDF/HTML/Markdown docs with headings, numeric tables, merged cells, diagrams and source page/slide/sheet reference labels.

**J9.** Run MarkItDown and current Docling/native parsers on identical bytes. Compare structural element coverage, page/cell location, code blocks, charts, image loss and parse warnings; do not use output length alone as a quality metric.

**J10.** Treat Markdown as a derived ContentRepresentation with original immutable source hash and map to source spans when possible. If page references missing, disable precise citations for that format.

**J11.** Evaluate ≥40 labeled retrieval/evidence questions, RAG quality and model-token/index cost with same embedding profile and source generation; report memory/CPU/p95.

**J12.** Make format-specific GO/NO-GO; a PDF diagram or spreadsheet may need Docling/native even if Markdown is pretty; attach acceptance thresholds and user privacy decision.

**J13.** Only after format GO add optional adapter to parser registry with new profile and safe fallback; preserve current HTML/ZIP/PDF security fences and original asset storage.

**Cross-cutting constraints:** Do not import model/converter/cloud or queue SDK into core, and do not change existing PostgreSQL authoritative source.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

Compare >=12 files and 40 ground-truth queries, exact numeric/table/page citations, malicious Office/ZIP/PDF embedded references, invalid HTML, network-blocked conversion, image-only scan, Cyrillic, timeout, resource exhaustion. Record real outputs and all failures; maintain existing ingestion/search regression.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

### L.1. Task-specific reproducible test vectors

- [ ] 12+ source files, 40+ gold evidence pairs; original/reconstructed hash and table numeric exactness.
- [ ] Dangerous Office/PDF/ZIP, embedded URL/HTTP, network disabled, plugin missing/unsupported, Cyrillic, huge input and timeout.
- [ ] No auto-install `markitdown[all]`, no cloud egress, missing structural evidence is a visible error/warning.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

## M. Acceptance Criteria

- [ ] No original bytes lost when converting
- [ ] At least 12 files and 40 label-backed queries evaluated
- [ ] Structural table/page/diagram fidelity and lost items quantified
- [ ] Markdown text size versus source bytes and index cost separately measured
- [ ] No unapproved plugin/cloud or filesystem/network access
- [ ] GO/NO-GO for each input format, with license/privacy/cost and source precision
- [ ] No current converter replaced before benchmark/approval

## N. Documentation / Migration / Compatibility / Rollback

Evaluation is additive and no schema migration. Post-GO conversion remains a derived representation linked to the unchanged original, default disabled; feature gate can roll back to prior parser without deleting source versions/assets.

## O. Mandatory Completion Checklist

- [ ] Recheck source/architecture ownership before coding.
- [ ] Reuse existing parser/chunker/source publisher and provider-neutral ports.
- [ ] Contracts, auth, bounds, versions and failure states tested.
- [ ] Measured evaluation/gold data and negative cases recorded.
- [ ] No silent fallback, wrong score or partial ready claim.
- [ ] Retry, rollback, source/asset preservation tested.
- [ ] Hatch/SQL/browser regression suites executed and outputs linked.
- [ ] Operator documentation and capability gates updated truthfully.
- [ ] Modified file paths, resulting commit and safe evidence linked.
- [ ] Task remains PROPOSED until all acceptance gates pass.

**A–O scope change rule:** if a new migration, provider or authorization boundary is needed, revise the task before implementing.

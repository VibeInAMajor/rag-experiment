# TASK-RAG-PARSE-001 — Deterministic file/element type detection and qualified parser registry

**Created:** 2026-11-21  
**Updated:** 2026-11-22
**Status:** COMPLETE — internal parser qualified; downstream consuming gates closed by CHUNK-001 and RAG-002
**Priority:** P0 — before generalizable chunking/ingestion  
**Dependencies:** TASK-ARCH-001, TASK-API-001, TASK-DB-001; coordinates with TASK-RAG-CHUNK-001 and TASK-RAG-002  
**Repository snapshot reviewed:** implementation base `81e17e404014ed054736826868c775e4800f8fd3`; original blueprint reviewed `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target:** `tasks/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md`  
**Architecture:** [Content-aware chunking and parser routing](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Create an application-owned, immutable, fail-closed parser/format registry and shared typed structural-element contract. Its first qualified candidates are plain text and Markdown; other common formats are declared *planned* without advertising them as working.

## B. Context / Problem

The initial ingestion plan accepts TXT/Markdown by an extension/MIME check; upcoming Python/PDF/Office/table/config/transcript tasks would otherwise each invent its own detection, parser registration, error types and provenance. The user-provided decision tree also shows that selecting chunkers from extension alone is insufficient: one PDF can contain paragraphs and tables. Establish one small boundary for **verified source format → qualified parser → element kinds → chunking policy** before implementing multiple parsers. Do not create a general plugin loader or execute parser class names supplied by users.

## C. Current Repository State

| Verified path / symbol | Existing behavior | Consequence |
| --- | --- | --- |
| [`haystack/components/routers/file_type_router.py`](../haystack/components/routers/file_type_router.py) `FileTypeRouter` | Classifies Paths using MIME guessed from extension and ByteStreams from metadata; unmatched/failed outputs. | **Reuse where useful inside trusted Haystack pipelines**, but it is NOT a byte-signature/magic or adversarial-upload verifier. |
| [`haystack/components/converters/multi_file_converter.py`](../haystack/components/converters/multi_file_converter.py) `MultiFileConverter` | Already routes TXT, MD, PDF, CSV, DOCX, HTML, JSON, PPTX, XLSX to Haystack converters. MD currently handled by text converter; PDF uses `PyPDFToDocument` (no OCR). | Do not duplicate the converter suite; do not treat flattened outputs as proof of faithful structure. |
| [`haystack/components/converters/txt.py`](../haystack/components/converters/txt.py) / [`markdown.py`](../haystack/components/converters/markdown.py) | Text and Markdown converters exist; can log failures and return zero documents. | Extraction result must be checked explicitly. |
| [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../haystack/components/preprocessors/embedding_based_document_splitter.py) | Semantic `EmbeddingBasedDocumentSplitter` already exists. | Advanced policy is future inference work, **not** a new splitter library implementation. |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) / [`boundary.py`](../apps/workbench/api/boundary.py) | Current read-only FastAPI/strict boundary. | No public upload or format capability currently; registry must not claim one. |
| [`apps/workbench/api/contracts.py`](../apps/workbench/api/contracts.py) | Versioned v1 contracts and `CapabilitiesResponse.features.documents/search`. | Add upload/format advertisement only when its consuming HTTP workflow is really ready, in TASK-RAG-002. |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | `Source`, `SourceVersion`, `Chunk`, `WorkspaceContext` metadata/identity types. | Reuse provenance concepts; no new storage or database SDK in policy. |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | `PostgresPersistence.publish_source()` uses scoped atomic version publication. | Keep all writes in existing port; this task performs no writes. |
| [`apps/workbench/web/src/domain/catalog.ts`](../apps/workbench/web/src/domain/catalog.ts) | UI displays generic parser/chunker fields and ambiguous 500/50 size. | Neither UI labels nor filename are authoritative parser/profile selection. |
| [`tasks/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md`](TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) | Referenced blueprint was absent at implementation base; this change adds an explicitly planned handoff. | Its future input is a typed, **verified** parser/element result from this task. |

**Reinspection on 2026-11-21:** `FileTypeRouter` trusts extension/metadata; `MultiFileConverter` sends Markdown through the text converter and PDF through `PyPDFToDocument` without OCR. Existing text extraction can return zero documents on failure. No `parsing.py`, `parser_registry.py` or `ingestion.py` existed at the implementation base. This change adds the first two as internal application modules; ingestion remains absent. The architecture page and both referenced downstream task documents were also absent; this change creates an actual format matrix and explicitly planned handoffs. Navigation documents reside in `docs-website/PROJECT_MAP.md` and `docs-website/ENGINEERING.md`, despite stale root `docs/` links.

Broad formats remain library/upstream possibilities, not app-supported uploads. Existing PostgreSQL lexical search, scoped publication and the initial migration remain unchanged.

## D. Goal

Given bounded bytes and untrusted filename/declared MIME, return exactly one typed **verified** allowlisted format or a stable refusal; select exactly one approved installed parser descriptor; output ordered, typed structural elements and a metadata-only processing classification for the downstream policy resolver. Registry outcomes are deterministic for identical bytes and pinned revisions. Never advertise unavailable/deferred parsers as executable.

## E. Scope

- Define `InspectedSource`, `ParserDescriptor`, `ParsedElement`, `ParsedDocument` (or equivalent app-owned names in prevailing conventions), stable `format_id` vocabulary and low-cardinality failures.
- Implement `inspect_format(bytes, declared_type, safe_basename, upload_limits)` for initial `.txt/.md`; support standard MIME aliases and UTF-8/BOM; reject conflict, NUL, whitespace-only, over-size and unreadable input.
- Define a **static, reviewed registry** of common format families from architecture table, each with `qualified`, `available`, `parser_id/revision`, dependencies, output element types and explicit constraints; only enable actually tested adapters.
- Reuse Haystack `TextFileToDocument`, `MarkdownToDocument`, `MarkdownHeaderSplitter`, and `FileTypeRouter` where appropriate; retain original Markdown for headings/code fences instead of losing structure in conversion.
- Return ordered typed paragraph/heading/code_fence/table-text *only where actually parsed*. Unqualified tables/code fences are preserved as protected raw Markdown spans with warnings, not falsely parsed table cells or AST nodes.
- Add isolated tests, README/decision documentation and downstream handoff to CHUNK-001/RAG-002.

## F. Non-Goals

No HTTP upload routes, DB migrations, actual DOCX/PDF/XLSX/email parsing, OCR/ASR, remote document downloads, zip extraction, ML classifier, semantic/agentic chunking, tokenizer changes, arbitrary class loading, production authentication or UI format picker. Broad registry entries are **planned metadata**, not enabled capabilities.

## G. Architecture / Boundaries

- [x] Domain/policy: deterministic `format_id`, verified classification, parser capability metadata.
- [x] Port: output element contract consumed by chunking; parser adapters belong outside neutral core.
- [x] Security/governance: untrusted upload inspection, bounded parsing, sanitized failure codes and source scope.
- [x] Observability/evidence: parser ID/revision, format ID, selection/rejection code, element counts, wall time; no raw content.
- [ ] Persistence: N/A — metadata projection only; persistence is TASK-RAG-002.
- [ ] Agent runtime: N/A — never execute source content or AI agent.
- [x] Documentation/CI: tests, architecture matrix and truthful status.

Use existing Haystack converter/router primitives rather than a second duplicate conversion engine. An app-level **security gate** remains necessary because the library FileTypeRouter trusts external MIME/extension rather than inspecting uploaded bytes.

## H. Contracts / Interfaces / Data Model

```text
format_id: enum-like, versioned canonical identifiers:
  plain_text | markdown | pdf | word_document | presentation | workbook | delimited_table
  | json | json_lines | yaml | toml | xml | python | source_code | email
  | timed_transcript | audio | video | raster_image | unsupported

InspectedSource:
  original_name, safe_basename, declared_mime?, verified_mime, format_id,
  content_sha256, bytes_count, detector_revision, evidence_codes[], ambiguous: bool

ParserDescriptor:
  parser_id, parser_revision, accepted_format_ids[], available, qualified,
  dependency_revisions[], max_bytes, max_elements, deadline_ms,
  emitted_element_kinds[], required_provenance[]

ParsedElement:
  element_id, order, kind, text? / bounded reference?, parent_anchor?,
  heading_path?, page?, slide?, sheet?, row/col ranges?, line ranges?,
  speaker?, time spans?, source_span?, warning_codes[]

ParsedDocument:
  format_id, parser_id, parser_revision, source_sha256, elements[], warning_codes[]
```

- Canonical format detection MUST NOT return a selected parser when evidence is contradictory. ZIP-based Office formats share a ZIP signature: validate approved container manifest under strict limits rather than routing all `PK` files to DOCX.
- Initial literal enabled `format_id`s: `plain_text`, `markdown` **only if** concrete parsing succeeds in tests; optionally expose internal planned registry, never public runtime capabilities before TASK-RAG-002 integration.
- The app `Chunk` contract and PostgreSQL metadata remain unchanged here. No speculative source IDs generated from filename.
- Known failures: `UNSUPPORTED_FORMAT`, `FORMAT_MISMATCH`, `PARSER_UNAVAILABLE`, `PARSE_FAILED`, `EMPTY_EXTRACTION`, `CONTENT_LIMIT_EXCEEDED`, `STRUCTURE_LOSS`; normalize via existing `ErrorResponse` when HTTP later exists.

## I. Repository Files / Components Impacted

| Path | Change / owner |
| --- | --- |
| `apps/workbench/api/parser_registry.py` | **CREATE** only one compact allowlisted descriptor registry + availability checks; no plugin discovery. |
| `apps/workbench/api/parsing.py` | **CREATE** neutral source inspection, immutable contracts, typed projection and safe operational metadata. |
| `apps/workbench/api/parsing_adapters.py` | **CREATE** isolated Haystack byte extraction; no caller-controlled names, paths or metadata reach the converter. |
| `apps/workbench/api/tests/test_parser_registry.py` | **CREATE** exhaustive matrix, rejection and deterministic fixtures. |
| `apps/workbench/api/tests/test_parsing.py` | **CREATE** TXT/MD raw bytes, BOM, headings, malformed Unicode, false MIME, over-size. |
| `apps/workbench/api/tests/test_http_contract.py` | Extend the existing architecture import check to recognize the reviewed parser adapter while preserving the neutral-core provider ban. |
| `docs-website/docs/architecture/content-aware-chunking-strategy.md` | **CREATE** actual `available/qualified/planned` matrix and conservative structure/provenance contract. |
| `tasks/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md` and `tasks/TASK-RAG-002-ingest-text-and-markdown.md` | **CREATE** explicitly planned intake/decision handoffs; executable consumers were absent. |
| `apps/workbench/api/README.md`, `docs-website/PROJECT_MAP.md`, `docs-website/sidebars.js` | Document/navigate actual internal behavior without public upload advertisement. |
| `tasks/evidence/parser-registry-2026-11-21/` | Record focused/full application checks and JUnit evidence. |
| `releasenotes/notes/qualified-text-parser-registry-f7ff0422c6fc5558.yaml` | Add a release note for the internal qualified parser boundary. |

`pyproject.toml` remains unchanged: the existing pinned app Haystack dependency supplies the reused text converter; no new global or optional Markdown dependency is needed.

**Must NOT change:** `haystack/` implementations, `apps/workbench/api/migrations/0001_initial.up.sql`, `PostgresPersistence` write semantics, existing search score contract, frontend Preview fixtures or validation-only service.

## J. Implementation Requirements — ordered blueprint

### J1. Freeze evidence and compatibility

1. Reinspect actual commit, `FileTypeRouter` MIME behavior, `MultiFileConverter` route/output semantics, and parsed TXT/Markdown exceptions; update Section C if drift occurs.
2. Map allowed file extensions and MIME aliases to canonical `format_id`, with `unsupported` and `unavailable` separate. Record conflict handling and risk surface for each class in an inspectable matrix.
3. Define explicit allocation limits (first TXT/MD upload remains **1 MiB** per TASK-RAG-002), maximum element counts and inspection time. No embedded network or filesystem targets.

**Gate J1:** one versioned format matrix exists; library availability is explicitly distinct from application support.

### J2. Implement fail-closed classification

1. Use bounded magic/header checks and decoding. Text can have no distinctive signature: require valid UTF-8 (optional BOM) and a reviewed extension/MIME pair.
2. For ZIP/Office, mark `not_qualified` until specific manifest inspector approved; refuse archives rather than probing each as an Office document.
3. Normalize and bound basenames without using them as filesystem paths; reject traversal, fake extension, invalid encoding, conflicting MIME and oversized payload.
4. Return stable reason codes instead of guessing text on format mismatch. No `.pdf` labeled `plain_text` after a failed PDF parse.

**Gate J2:** mutation of filename/MIME cannot promote unsupported binary into an enabled parser; malformed inputs fail closed.

### J3. Qualified TXT/Markdown parse projection

1. Keep `TextFileToDocument` for real TXT extraction where suitable; verify exactly one nonempty document or record `PARSE_FAILED/EMPTY_EXTRACTION`.
2. Parse Markdown headings **before any flattening**, preserving heading hierarchy and code fences; expose protected spans or explicit warning when structural element extraction is incomplete.
3. Assign deterministic source spans and element ordering, but do not invent page/line/speaker metadata that cannot be justified.
4. Separate raw extracted text from safe operational metadata; `ParsedDocument` remains immutable downstream data.

**Gate J3:** 20+ representative TXT/MD fixtures with markdown tables, code fences, Cyrillic, BOM, long sections and empty output pass; zero fabricated provenance.

### J4. Registry and policy handoff

1. Wire CHUNK-001 `ChunkingInput` to `ParsedDocument`, including verified `format_id`, structures, parser revision and selection reasons; avoid copying MIME logic into chunking.
2. Assert unavailable formats return an explicit reason and never invoke a placeholder parser.
3. If a new format is enabled in a later task, require **parser + chunking + stored version + read/retrieval** integration test before adding it to public capabilities.

**Gate J4:** deterministic dispatcher calls a parser exactly once for accepted input; the policy receives verified elements only.

### J5. Security, observability, test evidence

1. Apply no-untrusted-code-execution, no-network, timeout, memory and content-limit policies; no `.yaml` object constructors or XML entity resolution at this stage.
2. Log `format_id`, `parser_id`, revision, fallback/error reason, byte/element counts and duration; never document text, secrets or raw untrusted filenames.
3. Run app-focused tests using Hatch and record exact output, SKIPs and quality artifacts under task evidence directories when implementation exists.

## K. Security / Governance / Observability

Treat all input bytes, filenames, user-provided MIME and future parser metadata as untrusted. Enforce server-resolved `WorkspaceContext` in consuming workflow; source classification never grants access. Disallow executable content, macros, YAML object creation, XML external entities, remote fetches, unsafe ZIP extraction and parser-specified arbitrary import paths. No SDK errors or source excerpts in logs/traces. Record safe correlation IDs, stable failure codes and revisions. Define temporary-file disposal through ingestion task; parser registry itself stores nothing and cannot change retention.

## L. Testing / Evaluation / Runtime Verification

- **Unit:** each format alias and representative MIME; deterministic same input; no false enablement. `.md` with headings/fences; `.txt` UTF-8 BOM; misleading `.pdf` named `.txt`; `.docx` ZIP fingerprint; random binary; null bytes; path traversal.
- **Contracts:** versioned `ParsedElement` shape and parser descriptor; no accidental SDK/Pydantic leaks in neutral policy.
- **Negative/security:** unsupported extension, mislabeled MIME, nested/invalid container, corrupt Unicode, empty Markdown converter output, timeouts and missing parser dependency.
- **Integration (once consumed):** real RAG-002 TXT/MD upload produces the same elements/chunks and PostgreSQL active version; other formats rejected, no fixture fallback.
- **Static/regression:** `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types` and appropriate targeted pytest. Re-run validator/lexical tests if contract changes.
- **Quality:** element coverage, structure-fidelity golden, FTS findability of one known term; no claim about embeddings or RAG answer accuracy.

### Executed internal checks and deferred gates

Exact command output and focused/full JUnit reports are in the [evidence directory](evidence/parser-registry-2026-11-21/). The application lint/format and type checks pass; focused parser/registry fixtures and the full application regression suite pass. Container-backed PostgreSQL tests skip without explicit `WORKBENCH_TEST_ADMIN_DSN` and `WORKBENCH_TEST_APP_DSN`. The evidence summary records final counts and reasons; no storage integration result is inferred from those skips.

Fixture coverage includes reviewed aliases, all planned registry families, known binary signatures and misleading names, corrupt/control/empty text, BOM/Cyrillic, deterministic spans/heading anchors, protected raw Markdown, converter cardinality/empty/changed/error outputs, missing dependencies, one-dispatch behavior, immutable contracts, safe logs and byte/element/deadline refusals. This is a scenario coverage summary; no numerical line/branch coverage is claimed.

At the original parser qualification base, consuming chunking, upload, publication and FTS-after-ingestion were unexecuted. The 2026-11-22 [CHUNK-001 implementation](TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) now consumes the immutable parser contract through `prepare_chunks(...)`, including actual diagnostic HTTP parser-to-chunk verification. Public TXT/Markdown upload, active-version publication and FTS findability after ingestion remain RAG-002 gates. Frontend/build/browser, full upstream Haystack suite and Docusaurus build were not run for this internal application change; relative links in the new task/architecture documents and scoped `git diff --check` were checked.

## M. Acceptance Criteria

### Additional real HTTP verification — 2026-11-22

Executed `hatch run workbench-api:python -m scripts.workbench_parser_smoke` against a real temporary loopback Uvicorn subprocess, using the existing application parser and Haystack converter without mocks. The run exercises 17 parser HTTP requests: four successful source cases with exact deterministic replays and nine explicit refusals. The real repository architecture Markdown file produces 29 ordered elements; the TXT file, controlled BOM/Cyrillic/CRLF Markdown with table/fence, and exact 1 MiB text also succeed. Incorrect signatures/MIME, traversal, invalid UTF-8, empty input, planned Office/archives, oversized bytes and excessive element counts are refused. Hashes and exact source spans/nonblank coverage are asserted.

Evidence is recorded locally at `tasks/evidence/parser-runtime-2026-11-22.json` under the existing evidence ignore policy. The main API on `127.0.0.1:8011` is probed before/after: readiness, capabilities, database counts and corpus revision remain unchanged. The diagnostic process is stopped and its listener closure checked. The reusable script and API README describe the precise verification boundary.

This is internal-parser integration over actual TCP/HTTP, not evidence of a parser/upload route on the main API or of ingestion/persistence/retrieval. Those downstream gates below remain open. Production application and parser implementation files are unchanged by this verification follow-up.

- [x] At least 30 positive/negative format-identification cases cover aliases, corrupt text, misleading magic, over-size and unsupported Office/archives.
- [x] Every successful TXT/Markdown parse has exactly one qualified parser descriptor and a revisioned `ParsedDocument` with nonempty ordered elements.
- [x] Unqualified formats return an explicit `unsupported/unavailable` refusal, not success, empty input or silent generic text fallback.
- [x] Same input/revisions produce identical parsing decisions and normalized structural anchors; no fabricated page/speaker/table provenance.
- [x] Caller-controlled parser paths/imports, external URLs and model IDs are never interpreted as execution selectors, network targets or filesystem paths; source content is never executed.
- [x] Existing `TextFileToDocument` extraction is reused; `FileTypeRouter` and Markdown primitives were examined with reuse decisions recorded; no second blanket converter implementation is created.
- [x] Actual tests, scenario coverage summary, resource-bound negative evidence and docs updates are recorded; repository and public API backward compatibility are preserved.

## N. Documentation / Migration / Compatibility / Rollback

Markdown architecture matrix records **library/upstream/planned/qualified** independently. No SQL migration/HTTP API change in this task. The first public format capabilities must be implemented and versioned in a consuming task after real route/storage success. Processing fingerprints incorporate parser and detection revisions; a changed parser cannot silently reclassify old chunks. Rollback disables a qualified parser descriptor, does not delete existing versions or PostgreSQL volume. PDF/Python/Office/tabular/structured/transcript adapters are deferred to their focused tasks.

### Implementation decisions

- Reuse `TextFileToDocument` over a bounded in-memory `ByteStream` for both TXT and Markdown; require exactly one nonempty extraction. Preserve Markdown before flattening. `MarkdownToDocument` is not used because its plain-text projection loses required raw structure and introduces unnecessary optional Markdown dependencies. `MarkdownHeaderSplitter` is not the element authority because its public output synthesizes page/split metadata and does not expose the required original spans. `FileTypeRouter` remains a trusted-pipeline router, not the upload security gate.
- Isolate Haystack imports and extraction in `parsing_adapters.py`; keep inspection/contracts/projection in neutral `parsing.py` and static metadata in `parser_registry.py`. The existing architecture import test explicitly recognizes the adapter without widening the neutral-core provider ban.
- Recognize only an unindented single-line ATX/Setext heading subset and paragraph text conservatively. Preserve fences/tables as `protected_raw` with `CODE_FENCE_UNPARSED`, `UNCLOSED_CODE_FENCE` and `TABLE_UNPARSED`; preserve multiline Setext, frontmatter, HTML, lists and container/indented syntax with `MARKDOWN_STRUCTURE_UNPARSED`. No table/AST/page/speaker provenance is fabricated.
- Use detector revision `text-inspection-r1`, structural contract `parsed-elements-v1`, byte SHA256 and deterministic decoded-character spans/anchors. The registry owns parser/dependency revisions; the future processing fingerprint also includes the contract and approved chunking policy.
- Centralized default reviewed bounds are 1 MiB, 4,096 elements and a shared 2,000 ms cooperative deadline checked between synchronous stages/blocks. No worker/process isolation is claimed; a blocked library call or scan within one block cannot be preempted by cooperative checks. Heavier adapters require separate isolation qualification.
- Signature checks deny reviewed binary/executable/archive patterns and misleading filename/MIME evidence. They do not guarantee universal executable/polyglot detection or classify all possible semantic content; valid accepted text remains inert and is never executed.
- CHUNK-001/RAG-002 had no executable consumer at the original parser base. As of 2026-11-22, CHUNK-001 consumes the verified `ParsedDocument` without a duplicated classifier and qualifies internal preparation; RAG-002 now consumes the same contract for durable upload/publication/retrieval; its local live gates and final independent artifact audit passed. See the [successor task](TASK-RAG-002-ingest-text-and-markdown.md). Internal parser/chunker completion cannot serve as upload/storage/retrieval qualification.

### Successor integration qualification — 2026-11-22

The original parser and diagnostic runtime observations above remain historical. The separate [RAG-002 workflow](TASK-RAG-002-ingest-text-and-markdown.md) now closes upload/publication/read/retrieval gates with real same-volume migration, two TXT/Markdown uploads, API/database recovery and visible browser searches. Its [independent audit](evidence/ingestion-2026-11-22/evidence-audit.json) passed; this successor evidence does not retroactively change the earlier parser test counts or advertise other formats.

## O. Mandatory Completion Checklist

- [x] Section C reverified against actual files and migrations; protected runtime/storage contracts remain unchanged.
- [x] Format aliases, known-signature checks, parser statuses, typed elements and explicit refusal states implemented.
- [x] Security review/tests cover misleading format extensions, archive signatures, MIME injection, unsafe names and nonexecution; signature-detection limitations are explicit.
- [x] CHUNK-001 consumes the verified parser contract without a duplicated classifier; its internal tests and diagnostic HTTP execution qualify the parser-to-chunk handoff.
- [x] RAG-002 consumes the contract in a workspace-scoped upload/publication workflow. **Successor RAG-002 implemented this outside the original parser scope; local live gates and final independent artifact audit passed; see [RAG-002 evidence](evidence/ingestion-2026-11-22/evidence-audit.json).**
- [x] Internal unit, negative, contract, static and application regression gates executed; exact evidence referenced.
- [x] Consuming parser → chunking → stored version → read/retrieval integration gate executed. **Successor RAG-002 now supplies real same-volume upload/publication/read/retrieval and restart evidence; final independent artifact audit passed. Original parser test skips remain historical and do not establish these later gates.**
- [x] Docs/capabilities report only real qualified behavior; no public upload/capability contract changed.
- [x] Rollback/versioning and operational limitations documented.
- [ ] All completion gates met before changing status to COMPLETE. **Internal implementation is qualified; the broader consumer checklist remains open.**

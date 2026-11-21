---
title: Content-aware parser and chunking boundary
---

# Content-aware parser and chunking boundary

**Updated:** 2026-11-21  
**Scope:** Workbench application policy; separate from the Haystack converter catalog and public HTTP capabilities.

The application boundary is **bounded source bytes → verified format → qualified parser → ordered structural elements → chunking policy**. Filename, declared MIME and Workbench component labels are untrusted hints. Classification does not authorize a workspace or publish a source version. The [runtime contract](rag-runtime-contract.md) continues to own API, retrieval and persistence semantics.

The implementation task is [TASK-RAG-PARSE-001](../../../tasks/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md). Chunking and ingestion remain planned consumers in [CHUNK-001](../../../tasks/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) and [RAG-002](../../../tasks/TASK-RAG-002-ingest-text-and-markdown.md). Parser qualification alone does not add an upload route or public supported-format advertisement.

## Format matrix

The revisioned static registry in `apps/workbench/api/parser_registry.py` is the executable source of truth. `qualified` means the application adapter has a bounded tested contract; `available` additionally depends on the installed dependency revisions. A converter class in Haystack does not establish either application property. Planned entries cannot invoke a placeholder or fall back to plain text.

| Canonical format | Candidate source evidence | Haystack/library building blocks | Application state | Remaining qualification work |
| --- | --- | --- | --- | --- |
| `plain_text` | Reviewed `.txt` and MIME pair, valid UTF-8 with optional BOM, no forbidden controls or conflicting signature | `TextFileToDocument` | Qualified byte-only adapter, subject to dependency availability | Consuming chunking/storage/retrieval workflow |
| `markdown` | Reviewed Markdown extension and MIME pair, same text checks | `TextFileToDocument`; `MarkdownToDocument` and `MarkdownHeaderSplitter` examined | Qualified conservative raw Markdown projection, subject to dependency availability | Broader syntax, structured tables/code and consuming workflow |
| `pdf` | Future bounded PDF verifier | `PyPDFToDocument`; no OCR in `MultiFileConverter` | Planned; unavailable to application dispatcher | PDF inspection, extraction fidelity, scanned pages and mixed elements |
| `word_document` | Future approved Office manifest inspector | `DOCXToDocument` | Planned; unavailable | Manifest and resource limits, structure, macros and embedded objects |
| `presentation` | Future approved Office manifest inspector | `PPTXToDocument` | Planned; unavailable | Slides, order, notes, media and provenance |
| `workbook` | Future approved Office manifest inspector | `XLSXToDocument` | Planned; unavailable | Sheets/cells/ranges, formulas and resource limits |
| `delimited_table` | Future dialect/schema verifier | `CSVToDocument` | Planned; unavailable | Delimiters, encoding, quoted cells and row/column contracts |
| `json` | Future strict bounded JSON verifier | `JSONConverter` | Planned; unavailable | Schema, nesting limits and element projection |
| `json_lines` | Future strict bounded line verifier | No qualified app binding | Planned; unavailable | Per-line parsing, schema and provenance |
| `yaml`, `toml`, `xml` | Future format-specific strict verifier | No qualified app binding | Planned; unavailable | Safe scalar-only loading where applicable; no constructors, entities or network |
| `python`, `source_code` | Future language-specific inspection | No qualified app binding | Planned; unavailable | Syntax/AST policy, language bounds and nonexecution guarantee |
| `email` | Future bounded message inspection | No qualified app binding | Planned; unavailable | MIME parts, attachments, headers and nested limits |
| `timed_transcript` | Future time/speaker format inspection | No qualified app binding | Planned; unavailable | Timing, overlap and justified speaker provenance |
| `audio`, `video` | Future media inspection | No qualified app binding | Planned; unavailable | Media limits, explicit ASR and timestamp qualification |
| `raster_image` | Future image inspection | No qualified app binding | Planned; unavailable | Image limits and explicit OCR qualification |
| `unsupported` | Unknown format, archive or unapproved source | No adapter | Unsupported | Separate reviewed format task |

ZIP magic alone never identifies an Office document. This slice refuses archives without opening, extracting or guessing their contents. Known PDF, ZIP, executable and common binary signatures are refused despite text names or MIME claims. This is a reviewed text allowlist with signature checks, not universal executable/polyglot detection; accepted source content is never executed.

The initial enabled evidence pairs are deliberately small:

| Format | Extensions | Declared MIME aliases | Verified MIME | Parser revision |
| --- | --- | --- | --- | --- |
| `plain_text` | `.txt` | `text/plain` | `text/plain` | `haystack-text-r1` |
| `markdown` | `.md`, `.markdown` | `text/markdown`, `text/x-markdown`, `text/plain` | `text/markdown` | `raw-markdown-r1` |

Declared MIME may be absent; otherwise it must agree with the reviewed extension and may include only the accepted UTF-8 charset parameter. Extension/MIME case is normalized. A Markdown extension with `text/plain` remains Markdown; a `.txt` source with `text/markdown` is refused. `application/octet-stream` is not a fallback alias. Planned-family evidence aliases live in the same immutable `format_rules()` table but never qualify their parser. A pinned `haystack-ai==3.5.0` installation is required for the initial adapters.

## Inspection and failure policy

Inspection accepts in-memory bytes only. It does not open filename paths, fetch URLs, import caller-selected parsers or execute source content. The default source cap is **1 MiB**, the element cap is **4,096**, and the shared cooperative deadline is **2,000 ms**. Limits are centralized in the registry; callers may tighten limits, but cannot widen reviewed descriptor limits. The synchronous adapter checks time between stages and scanner blocks; this is not hard process isolation and cannot preempt a blocked library call or a scan within one block. Future heavier adapters need a separately reviewed isolation strategy.

Names must be bounded basenames, with traversal, path separators, device/alternate-stream names, controls and misleading names refused. MIME is normalized through an explicit reviewed allowlist rather than platform-dependent MIME guessing. Corrupt UTF-8, conflicting evidence, NUL/control data, empty content and oversized input fail before extraction. Accepted UTF-8 BOM is removed for text projection while the byte SHA256 still identifies the exact original bytes.

| Failure code | Meaning |
| --- | --- |
| `UNSUPPORTED_FORMAT` | No approved source format; there is no generic text fallback |
| `FORMAT_MISMATCH` | Claimed format, byte evidence or safe-name rules conflict |
| `PARSER_UNAVAILABLE` | Format is planned/unqualified or an approved adapter's dependency is unavailable |
| `PARSE_FAILED` | Approved adapter failed or returned an invalid extraction result |
| `EMPTY_EXTRACTION` | Source/extraction has no usable nonwhitespace content |
| `CONTENT_LIMIT_EXCEEDED` | Byte, element or elapsed processing budget was exceeded |
| `STRUCTURE_LOSS` | A required structural guarantee could not be preserved |

Failures expose stable safe codes. Future HTTP integration maps them through the existing error envelope; this slice adds no HTTP error contract. Diagnostics contain format/parser IDs and revisions, reason codes, byte/element counts and duration. Content, source excerpts, credentials, exception internals and raw untrusted filenames stay out of operational logs.

## Structural projection and provenance

`InspectedSource`, `ParsedElement` and `ParsedDocument` are immutable application data. Haystack `Document`, SDK models and caller-controlled metadata do not become chunking-policy input. Successful documents record the verified format, original-byte SHA256, detector/parser revisions, ordered elements and bounded warning codes. The detector revision is `text-inspection-r1`; the structural contract is `parsed-elements-v1`. The registry owns parser IDs/revisions.

Both formats use the existing `TextFileToDocument` extraction over a `ByteStream`, isolated in `apps/workbench/api/parsing_adapters.py`. `parsing.py` and the registry have no direct Haystack/SDK imports. Exactly one nonempty, source-preserving document is required. Markdown uses source text before any flattening. The scanner qualifies only an unindented, single-line ATX/Setext heading subset and retains its hierarchy. Multiline Setext titles, indented/container syntax, frontmatter, HTML and lists remain protected with `MARKDOWN_STRUCTURE_UNPARSED` rather than claiming a complete Markdown AST. Tables and fenced code remain protected raw Markdown with `TABLE_UNPARSED` and `CODE_FENCE_UNPARSED` warnings, without claiming table cells, language ASTs or executable semantics. An unterminated fence has `UNCLOSED_CODE_FENCE`; its interior headings cannot become ordinary document headings.

Metadata-only classification records observed element kinds, whether protected spans exist and selection reasons. Downstream policy can make a conservative decision without rereading untrusted source content as instructions.

Source spans refer to the decoded UTF-8 text after optional BOM removal, using half-open character offsets. Observed line ranges are derived from that text. Element order, IDs and heading anchors must be deterministic for identical source bytes and revisions. No page, sheet, slide, speaker or time metadata is invented. Heading context and parent anchors describe only observed headings.

`MarkdownToDocument` produces flattened text and has optional Markdown dependencies; it is not the structural authority here. `MarkdownHeaderSplitter` supplies library header chunking with page/split metadata, rather than this source-element contract. `FileTypeRouter` trusts extension/metadata and cannot perform adversarial-upload verification. These primitives remain available for trusted pipelines; this boundary does not duplicate their blanket converter suite or modify `haystack/`.

## Consumer handoff and versioning

The future chunking resolver accepts a successful `ParsedDocument`, including verified format, element kinds, protected spans, warnings, parser revision and detector evidence. It must not rerun MIME/extension classification or silently split a protected span as a parsed table or code AST. Unsupported strategies produce a stable refusal rather than a generic fallback.

Ingestion resolves `WorkspaceContext` independently on the server, inspects/parses exactly once, then invokes the chunking policy. It uses the existing `Source`/`SourceVersion`/`Chunk` contracts and `PostgresPersistence.publish_source()` for staged atomic publication. This parser work introduces no database writes, migration, source identity derived from filenames, embedding request or document retention policy.

The consuming processing fingerprint must include detector revision, parser ID/revision, relevant dependency revisions, chunking revision/configuration and source byte SHA256. A parser change must not silently relabel old chunks. A later format becomes publicly advertised only after **parser + chunking + stored version + read/retrieval** integration evidence passes. Disabling an approved descriptor is the rollback; preserve existing versions and database volumes.

## Verification

The parser task records exact commands and results under its [task evidence directory](../../../tasks/evidence/parser-registry-2026-11-21/). The relevant checks are `hatch run workbench-api:check`, `hatch run workbench-api:test` and `hatch run workbench-api:types`, plus focused parser fixtures. Positive structure fixtures and negative spoofing, archive, Unicode, filename, missing-dependency and resource-budget cases qualify this internal boundary. Container-backed PostgreSQL tests require explicit test DSNs and skip without them. HTTP upload/FTS findability after ingestion, embeddings and answer quality remain separate evidence gates.

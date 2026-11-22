---
title: Content-aware parser and chunking boundary
---

# Content-aware parser and chunking boundary

**Updated:** 2026-11-22\
**Scope:** Workbench application policy; separate from the Haystack converter catalog and public HTTP capabilities.

The application boundary is **bounded source bytes → verified format → qualified parser → ordered structural elements → chunking policy**. Filename, declared MIME and Workbench component labels are untrusted hints. Classification does not authorize a workspace or publish a source version. The [runtime contract](rag-runtime-contract.md) continues to own API, retrieval and persistence semantics.

The parser task is [TASK-RAG-PARSE-001](../../../tasks/completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md). [CHUNK-001](../../../tasks/completed/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md) implements internal token-budgeted chunk preparation; [RAG-002](../../../tasks/completed/TASK-RAG-002-ingest-text-and-markdown.md) now consumes these seams in the separate [durable ingestion workflow](durable-text-ingestion.md), whose local upload/publication/read/retrieval and restart gates passed; final independent artifact audit passed. Internal parser/chunker qualification does not add an upload route or public supported-format advertisement.

## Configured ingestion successor

The [operator processing configuration](document-processing-configuration.md) now maps all approved recursive-splitter settings into this existing seam using `text-token-r2`. Shipped startup selects English required sentences with explicit Russian support, rather than the original RAG-002 unqualified structural policy; unsupported configured sentence locales fail closed. The independent native guard is enabled by the shipped operator YAML and remains separately counted. No automatic language detection, model inference or rewriting of existing chunks occurs. Original internal `text-token-r1` and RAG-002 measurements below retain their historical scope. Configuration-specific acceptance passed with full application/offline/native-counter and local live/restart checks.

## Format matrix

The revisioned static registry in `apps/workbench/api/parser_registry.py` is the executable source of truth. `qualified` means the application adapter has a bounded tested contract; `available` additionally depends on the installed dependency revisions. A converter class in Haystack does not establish either application property. Planned entries cannot invoke a placeholder or fall back to plain text.

| Canonical format | Candidate source evidence | Haystack/library building blocks | Application state | Remaining qualification work |
| --- | --- | --- | --- | --- |
| `plain_text` | Reviewed `.txt` and MIME pair, valid UTF-8 with optional BOM, no forbidden controls or conflicting signature | `TextFileToDocument`, `RecursiveDocumentSplitter` | Qualified byte-only parser and internal token chunker, subject to dependency/resources | Consuming upload/storage/retrieval workflow |
| `markdown` | Reviewed Markdown extension and MIME pair, same text checks | `TextFileToDocument`, `MarkdownHeaderSplitter`, `RecursiveDocumentSplitter`; flattening converter examined | Qualified conservative raw Markdown projection and internal section-bounded token chunker | Broader syntax, structured tables/code and consuming workflow |
| `pdf` | Future bounded PDF verifier | `PyPDFToDocument`; no OCR in `MultiFileConverter` | Planned; unavailable to application dispatcher | PDF inspection, extraction fidelity, scanned pages and mixed elements |
| `word_document` | Future approved Office manifest inspector | `DOCXToDocument` | Planned; unavailable | Manifest and resource limits, structure, macros and embedded objects |
| `presentation` | Future approved Office manifest inspector | `PPTXToDocument` | Planned; unavailable | Slides, order, notes, media and provenance |
| `workbook` | Future approved Office manifest inspector | `XLSXToDocument` | Planned; unavailable | Sheets/cells/ranges, formulas and resource limits |
| `delimited_table` | Future dialect/schema verifier | `CSVToDocument` | Planned; unavailable | Delimiters, encoding, quoted cells and row/column contracts |
| `json` | Future strict bounded JSON verifier | `JSONConverter` | Planned; unavailable | Schema, nesting limits and element projection |
| `json_lines` | Future strict bounded line verifier | No qualified app binding | Planned; unavailable | Per-line parsing, schema and provenance |
| `yaml`, `toml`, `xml` | Future format-specific strict verifier | No qualified app binding | Planned; unavailable | Safe scalar-only loading where applicable; no constructors, entities or network |
| `python` | `.py`, reviewed Python/plain MIME, strict UTF-8 and valid Python AST | `PythonCodeSplitter`, line `DocumentSplitter` | Qualified `python_ast` through the shared durable upload path | Repository syncing, semantic retrieval and code-specific UI remain separate |
| `source_code` | Future language-specific inspection | No qualified app binding | Planned; unavailable | Non-Python languages and their independent safety/structure qualification |
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
| `python` | `.py` | `text/x-python`, `application/x-python-code`, `text/plain` | `text/x-python` | `python-source-r1` |

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

The internal chunking resolver accepts a successful `ParsedDocument`, including verified format, element kinds, protected spans, warnings, parser revision and detector evidence. It does not rerun MIME/extension classification or split a protected span as a parsed table or code AST. Unsupported strategies produce a stable refusal rather than a generic fallback. Source/version IDs and an explicit application language hint accompany the parsed result; classification never creates identities or grants workspace access.

Ingestion resolves `WorkspaceContext` independently on the server, inspects/parses exactly once, then invokes the chunking policy. It uses the existing `Source`/`SourceVersion`/`Chunk` contracts and `PostgresPersistence.publish_source()` for staged atomic publication. This parser work introduces no database writes, migration, source identity derived from filenames, embedding request or document retention policy.

The processing fingerprint includes source/parse/profile/counter/resource and relevant transformation revisions. Changing parser, separator order, language/resource revision, overlap, token counter or profile is a reprocessing event; it must not silently relabel old chunks or reuse incompatible embeddings. A later format becomes publicly advertised only after **parser + chunking + stored version + read/retrieval** integration evidence passes. Disabling an approved descriptor/profile is the rollback; preserve existing versions and database volumes.

## Token-budgeted chunking policy

The baseline is **500 tokens with target overlap 50 tokens**, measured by **`tiktoken:o200k_base`**. These are neither words, characters nor Qwen-native model tokens. The application exposes `prepare_chunks(...)`, now consumed by the separate durable ingestion workflow; the pure immutable resolver lives in `chunking_profiles.py`, orchestration/provenance lives in `chunking.py`, and Haystack/tokenizer dependencies stay in `chunking_adapters.py`. The default profile is `text-token`, revision `text-token-r1`, unit `token`. The caller supplies an allowlisted typed profile, not raw separators, regular expressions, executable strategy names or content-selected configuration.

| Effective policy | Boundaries and accounting | Visible condition |
| --- | --- | --- |
| EN/RU sentence-aware prose | Paragraph → NLTK `sentence` → newline → literal space refinement in Haystack `RecursiveDocumentSplitter`, with `split_unit="token"`, `tokenizer_encoding="o200k_base"`, `split_length=500`, `split_overlap=50` | EN or RU hint and validated installed Punkt resources; both sentence segmentation and token counting operate together |
| Structural token fallback | Paragraph/newline and reviewed literal punctuation; terminal token splitting retains token-sized limits | Approved Ukrainian hint, missing/mismatched EN/RU sentence resource or explicit structural-profile request is recorded in `fallback_reasons` |
| Markdown sections | Verified heading context selects `markdown_sections`; approved Haystack header handling and recursive refinement operate inside parser-authorized sections/protected boundaries | Markdown with usable verified headings; no-heading Markdown has an explicit `missing_usable_headings` fallback |
| Optional exact-model admission | The configured pinned local Qwen counter validates complete eventual embedding input and its distinct budget | Actual local assets/counts are qualified; missing/mismatched counter or over-budget input refuses admission, without claiming served-TEI parity |

`ModelTokenAdmission.embedding_input(content, heading_path=...)` formats prefix, optional per-chunk observed heading context, content and suffix. The exact counter owns model-required special-marker/token rules; admission and the future embedding adapter must count/send the same formatted input. Fake-counter tests cover generic seam/refusal behavior; actual local-Qwen tests and HTTP measurements additionally verify the reviewed serialized tokenizer. This does not enable embeddings or establish served-TEI parity.

The optional `model_token_counter.py` adapter loads only an operator-selected local directory, never a path from source content. Its reviewed identity is `Qwen/Qwen3-Embedding-4B`, revision `5cf2132abc99cad020ac570b19d031efec650f2b`, with `tokenizers==0.23.3` and fixed SHA256 checks for `tokenizer.json`, `tokenizer_config.json` and `config.json`. The serialized tokenizer applies NFC and one `<|endoftext|>` suffix token (ID **151643**); this follows its actual postprocessor rather than guessing from config EOS `<|im_end|>` ID 151645. No automatic BOS/chat-template/padding/truncation is applied. The metadata manifest fingerprints these choices without publishing the filesystem path. No weights, custom model code, Hub lookup or TEI request is needed to count tokens.

Only **English (`en`), Russian (`ru`) and Ukrainian (`uk`)** source-language hints are accepted. EN/RU use their own provisioned NLTK sentence models. UK uses the explicit token-budgeted punctuation/paragraph/line fallback and is never sent to an English model; `require_sentences=True` instead refuses unavailable Ukrainian sentence support. Every other language is deferred and returns `UNSUPPORTED_LANGUAGE`. The implementation does not infer language from filenames/content, and arbitrary Unicode in a safety fixture does not qualify another language. Sentence language/resource revision, actual counter identity and fallback reasons remain part of the effective decision and fingerprint.

`MarkdownHeaderSplitter` has an ATX syntax subset different from the parser and no Setext mode. Parser elements therefore remain the authority for heading/protected structure and original source spans; upstream metadata cannot promote a quoted/fenced heading or synthesize physical pages. A native/parser section discrepancy is surfaced as `HEADER_BOUNDARIES_RECONCILED`. A fenced Python example remains inert Markdown, never a source-wide `python_ast` decision. Protected tables/fences/complex blocks are retained intact; an oversized protected unit fails with `CONTENT_LIMIT_EXCEEDED` / `PROTECTED_SPAN_OVERFLOW` rather than being silently sliced into syntactically invalid fragments.

Overlap is confined to a verified section/prose span and never crosses a protected boundary, source or version. Requested overlap and measured effective overlap are distinct: the profile requests 50 tokens, while a valid source-character boundary or a natural break can affect actual overlap. Prepared metadata records `requested_overlap`, `actual_overlap_tokens` and `length_tiktoken`; effective overlap is at most 50 tokens in the default profile and zero at structure boundaries. Token budgets are rechecked after the actual splitter output; no oversized, blank or overlap-only trailing record is publishable. Distinct repeated occurrences keep distinct source positions and identities.

Native Haystack output is validated for exact source substrings/offsets, coverage and token bounds. Token-byte boundaries can otherwise introduce replacement characters in no-space Unicode. Only invalid native output triggers the bounded terminal repair over original source characters with UTF-8-safe token boundaries, emitting `NATIVE_OUTPUT_REPAIRED`. This is a declared recovery path under the same token budget, not silent conversion to character sizing or a second general splitter engine.

Prepared content stays within the existing 32,768-character `Chunk.content` limit, at most 10,000 chunks, 16,384 JSON metadata bytes per chunk and 50 MiB of total prepared UTF-8 content. Preparation checks a 10-second cooperative budget between chunk emissions; this is not process isolation or preemption of a blocked dependency. It returns the complete immutable tuple or refuses without a publishable partial result. `PreparedChunk.to_chunk(title=...)` validates the existing persistence record and performs no write.

Before SDK work, small-target/high-overlap variants also face a conservative token-capacity bound, `target_size + (max_chunks - 1) * (target_size - overlap)`. Exceeding it produces a `MAX_CHUNKS` refusal. Unicode overlap round-down could theoretically allow fewer actual chunks, so this preflight can conservatively reject such variants; the baseline is unaffected. Actual output count is checked separately, with no truncation.

Source spans are half-open offsets into the exact parser-decoded source; coverage and offsets are verified against that source, including CRLF, Unicode and repeated text. Unpaginated TXT/Markdown has no physical page even if an upstream splitter emits `page_number=1`.

The [LangChain recursive splitter guide](https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter) is an algorithm reference only: its small character-counted demonstration does not set this product's token defaults. Haystack already provides ordered recursive splitting, so no LangChain runtime dependency or document-model adapter is added. Resource setup is explicit; normal indexing/tests must not discover missing assets by downloading them in the background.

### Provision resources explicitly

From the repository root, after Hatch is available:

```powershell
hatch run workbench-api:chunking-setup
```

The app environment pins `nltk==3.10.4`, `tiktoken==0.14.0` and this repository's Haystack 3.5.0. Setup fetches only the reviewed official Punkt archive at a pinned repository commit and the `o200k_base` encoding blob, checks fixed SHA256 digests/size bounds, and writes only the eight allowlisted EN/RU table files plus encoding under ignored `.cache/workbench-chunking/`. It does not fetch a model, source document, arbitrary URL or Qwen tokenizer.

Runtime resource inspection verifies local package versions, encoding/config identity and per-language table hashes without a network request. A missing/changed encoding is `TOKEN_COUNTER_UNAVAILABLE`; missing/changed sentence assets produce the declared token-based fallback, or `SENTENCE_RESOURCE_UNAVAILABLE` when sentences are required. Sentence profiles record the selected language and hashed resource revision. Re-running setup is the explicit recovery for missing assets; normal preparation does not download them.

The pinned Haystack adapter supplies the verified local encoding and sentence tokenizer, then marks its setup state warm to bypass URL-backed encoding warm-up. That small private-state dependency is scoped to Haystack 3.5.0 and covered by adapter tests; an upstream upgrade requires requalification. No Haystack splitting implementation is edited or copied. SDK debug messages that could include heading text are suppressed at this adapter boundary.

## Verification

The parser task records exact commands and results under its [task evidence directory](../../../tasks/evidence/parser-registry-2026-11-21/); CHUNK-001 records its own resource and fixture qualification. The relevant checks are `hatch run workbench-api:check`, `hatch run workbench-api:test` and `hatch run workbench-api:types`, plus focused parser/chunker fixtures. The curated chunking manifest contains 25 bounded TXT/Markdown inputs with EN/RU/UK hints, long/no-space Unicode safety text, literal punctuation, CRLF, headings/protected blocks, repeated occurrences, empty input and inert prompt-injection attempts. Other language hints are negative refusal tests. Tests validate actual token sizes, source coverage, deterministic offsets/identity, isolation, fallback and safe failure rather than inferring correctness from constructor settings.

Final EN/RU/UK CHUNK-001 evidence is recorded in the [2026-11-22 evidence directory](../../../tasks/evidence/chunking-2026-11-22/): **255 focused tests passed** (98 profile, 61 adapter, 78 pipeline, 18 local-counter); **579 full API tests passed, 69 skipped** for missing explicit database test DSNs. Ruff/format and mypy passed for 47 application files; both setup/smoke scripts passed their static checks. All 18 actual/local-counter tests ran with an explicitly configured local-tokenizer test directory. Asset-backed tests skip when that directory is absent; no default tokenizer path is assumed.

The real diagnostic HTTP run uses:

```powershell
hatch run workbench-api:python -m scripts.workbench_parser_smoke --chunking --evidence tasks/evidence/chunking-2026-11-22/runtime.json
```

The 25-case manifest yielded **23 accepted inputs and 95 chunks** in each mode: minimum 3, maximum 500, mean 286.484 tiktoken tokens. Baseline `runtime.json` records 17 parser plus 53 chunker HTTP requests. Optional `runtime-qwen.json` records 17 parser plus 55 chunker requests, adding actual one-token and Russian 500-Qwen-token admission refusals. Across both runs, **142 HTTP requests** completed; the main API remained ready with unchanged capabilities/corpus and both temporary listeners closed. Diagnostic routes are never installed or advertised in the production API.

The optional counter run uses an explicit operator choice, for example the user's existing local directory:

```powershell
hatch run workbench-api:python -m scripts.workbench_parser_smoke --chunking --qwen-tokenizer-dir 'A:\AI\TEI\qwen3-4b' --evidence tasks/evidence/chunking-2026-11-22/runtime-qwen.json
```

The artifact records raw chunk tiktoken length and both counters on the **same formatted embedding input** separately. Representative EN/RU/UK prose chunks each count 500 under tiktoken on that input, but **501 / 745 / 667** under local Qwen, including its suffix. Therefore a 500-tiktoken budget does not promise a 500-Qwen-token budget. Configured exact admission rejects `MODEL_TOKEN_LIMIT_EXCEEDED`; it neither truncates nor silently rechunks. Local tokenizer correctness is distinct from parity with a future served TEI/model runtime.

Container-backed PostgreSQL tests require explicit test DSNs and skip without them. The separate RAG-002 workflow supplies local public HTTP upload/FTS findability and same-volume recovery evidence. Served-TEI parity, semantic retrieval recall, embeddings and answer quality remain separate gates; original internal measurements below do not claim those capabilities. Sentence/paragraph boundaries are preferences under a hard token budget, not measured quality improvements or guarantees that an oversized sentence remains whole.

## Python AST ingestion

The shared upload route now admits `.py` as verified `python_source` content and resolves `python_ast` / `python-ast-r1`. Other programming languages remain unavailable. `PythonCodeSplitter` owns syntax-aware grouping; standard `ast` traversal only validates and annotates declarations, including nested names. No uploaded source is executed or imported. Invalid syntax returns `UNPARSEABLE_SOURCE` (HTTP 400); no prose fallback occurs.

The fixed primary target is **60 effective lines**, with one effective line defined as `ceil(characters / 45)`. This is a grouping target, not a physical-line or token cap. Whole units can exceed it. Docstrings, decorators, imports, comments and blank lines stay in exact source slices. A source element spans the whole module; the native splitter owns its AST boundaries. The application annotates symbols without implementing a second AST splitter.

Characterization found that `preserve_class_definition=True` prepends noncontiguous class signatures, native start lines omit leading comments, and native secondary parts copy the whole-unit range and log source identifiers. The adapter therefore uses the measured `preserve_class_definition=False` exception, retains class/symbol context as metadata, and verifies exact contiguous native output. The native overflow path is disabled within the 1 MiB bound; the same public line `DocumentSplitter` supplies bounded secondary pieces instead, with independently verified ranges and no identifier logging. No upstream Haystack source is changed.

Above **180 effective lines** or **32,768 characters**, a primary group uses secondary windows of **60 physical newline-delimited lines**, with at most **5 lines** of overlap. An indivisible oversized line is refused rather than truncated. Secondary content is not promised to parse independently. Each piece retains `start_line`, `end_line`, `unit_kinds`, bounded `symbols` (qualified declaration, kind, original range, class and decorators), safe `source_file`, `parent_structural_id`, `secondary_split`, index/total and actual overlap lines. A single unambiguous innermost declaration also exposes `qualified_symbol`, optional `class_name` and `decorators`. Nested-class bodies remain native units; generated definitions have no inferred symbol guarantee. Greedy grouping can couple adjacent units; content hashes remain reusable only when the actual chunk content is unchanged.

`length_tiktoken` and the independent optional `length_model_token` measure actual final content in their declared units; 500/50 prose settings do not relabel or size Python units. Native admission includes configured prefixes/suffixes and refuses excess without inference or automatic rechunking. Byte, AST-node, declaration, metadata, chunk/corpus and cooperative deadline limits apply. This is bounded local parsing, not process-level isolation.

Publication reuses the same reservation, idempotency, version guard, job-coupled transaction, RLS and PostgreSQL tables. `python-ast-ingestion-v1` records a language-independent code policy; no migration or symbol table is added. TXT/Markdown profiles and lexical response shapes remain unchanged. Search returns the same source/version/chunk IDs and raw `postgres_ts_rank_cd`; exact line/symbol provenance is available from GET chunks. Documents upload/line UI remains separate. Rollback means disabling the Python format qualification in a compatible release and restarting the API; it does not delete published versions or reset the volume.

The [task and verification report](../../../tasks/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md) distinguishes the ten-file/thirty-two-query synthetic regression comparison from **real-source qualification on the running server**: `apps/workbench/api/ingestion.py` produced 11 stored chunks, exact lines and independently recounted Qwen lengths; syntax rejection, SQL preservation, actual API restart/replay and visible Live search passed. No semantic-search or production-deployment claim is made.

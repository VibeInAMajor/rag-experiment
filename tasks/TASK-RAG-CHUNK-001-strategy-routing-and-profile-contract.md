# TASK-RAG-CHUNK-001 — Content-aware chunking policy resolver and typed processing profiles

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** PROPOSED — implementation blueprint; not yet implemented or tested  
**Priority:** P1 · before first generalizable ingestion splitter  
**Dependencies:** TASK-ARCH-001, TASK-API-001, TASK-DB-001, TASK-RAG-PARSE-001; coordinate integration contract with TASK-RAG-002  
**Repository snapshot reviewed:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target path:** `tasks/TASK-RAG-CHUNK-001-strategy-routing-and-profile-contract.md`  
**Existing runtime contract:** [RAG runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md)  
**Algorithm reference:** [LangChain RecursiveCharacterTextSplitter guide](https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter)  
**Documentation state:** The extended content-aware architecture and parser/ingestion task links are planned inputs, not proven files in the inspected repository snapshot.

## A. Title

Implement a **pure, versioned chunking policy resolver** with deterministic TXT/Markdown strategies, honest token/word units, structural provenance and reproducible golden tests; provide an application-owned seam for later code and layout adapters.

## B. Context / Problem

The current detailed ingestion plan hard-codes `DocumentSplitter(split_by="word", split_length=500, split_overlap=50)`, while the product discussion assumes **500 tokens / 50 tokens** and future documents need structure-aware splitting. Word counts do not equal Qwen model token counts. Applying fixed prose splitting indiscriminately to Markdown, tables or source code destroys meaningful boundaries and harms explainability, differential indexing and source citation. A small explicit decision boundary is needed before adding more file types.

This task does **not** introduce another vector DB, another document registry, a general-purpose document agent or a model-based classifier. It provides an independently testable policy layer that future ingestion can call.

**LangChain review (2026-11-21):** The linked `RecursiveCharacterTextSplitter` guide is an algorithmic reference, **not** a new required Python dependency. Its ordered, progressively finer separators are already supported by the existing Haystack `RecursiveDocumentSplitter`. The required change is to qualify an explicit separator/size/overlap/language policy and test it; adding a second production splitter framework would introduce duplicate document models and dependency overhead without proven benefit.

## C. Current Repository State

Reviewed from the repository snapshot above:

| Exact source | Existing symbol / behavior | Reuse or gap |
| --- | --- | --- |
| [API records](../apps/workbench/api/persistence.py) | `Source`, `SourceVersion`, `Chunk`, `WorkspaceContext`, `PersistencePort` | `Chunk.metadata` holds JSON; profile identity and structural properties may be persisted there without another table initially. |
| [PostgreSQL writer](../apps/workbench/api/postgres.py) | `PostgresPersistence._publish()`, `publish_source()`, `lexical_search_snapshot()` | Reuse atomic version activation; do not create a second writer. |
| [Initial schema](../apps/workbench/api/migrations/0001_initial.up.sql) | `workbench.sources`, `source_versions`, `chunks` with `metadata` JSONB and existing ID constraints | No task-specific schema changes unless measured need. Do not modify applied migration. |
| [API HTTP boundary](../apps/workbench/api/application.py) | `create_app()` / `_Routes`, approved read-only lexical API | No upload API currently in snapshot. Integration belongs to TASK-RAG-002, not this task. |
| [Recursive splitter](../haystack/components/preprocessors/recursive_splitter.py) | `RecursiveDocumentSplitter(split_length, split_overlap, split_unit, separators, tokenizer_encoding)` | Supports paragraph/sentence-aware split; `token` uses tiktoken, NOT a qualified Qwen tokenizer by default. |
| [Markdown splitter](../haystack/components/preprocessors/markdown_header_splitter.py) | `MarkdownHeaderSplitter`, `parent_headers`/`header`, `split_id`; `secondary_split` accepts `word`, `passage`, `period`, `line` | Reuse headers; **no** secondary `token` parameter in inspected version. |
| [Document splitter](../haystack/components/preprocessors/document_splitter.py) | `DocumentSplitter(split_by="word" or "token")` | Do not relabel word counts as model tokens or use `o200k_base` as Qwen tokens. |
| [Plain/Markdown converter](../haystack/components/converters/txt.py), [Markdown converter](../haystack/components/converters/markdown.py) | `TextFileToDocument`, `MarkdownToDocument` can skip/log bad sources | `TASK-RAG-002` validates exactly one nonempty extracted input and preserves headings before flattening. |
| [Existing Python AST component](../haystack/components/preprocessors/python_code_splitter.py) | `PythonCodeSplitter` already exists; extracts class/function structures and line metadata | Future code ingestion MUST reuse it; not implemented in this task. |
| [Workbench editor catalog](../apps/workbench/web/src/domain/catalog.ts) | UI displays a `chunker` with `size=500`, `overlap=50` but lacks exact unit declaration | UI labels are not server policy authority; do not change editor to claim token correctness. |
| [Existing ingestion blueprint](TASK-RAG-002-ingest-text-and-markdown.md) | Section J3 currently prescribes word-based 500/50 for lexical MVP | Replace local hardcoding with this named policy resolution when integrating TASK-RAG-002. |

**Confirmed comparison with the linked LangChain guide:**

| Concern | LangChain `RecursiveCharacterTextSplitter` | Existing Haystack `RecursiveDocumentSplitter` | Implementation decision |
| --- | --- | --- | --- |
| Refinement | Ordered `['\\n\\n', '\\n', ' ', '']` by default | Ordered `['\\n\\n', 'sentence', '\\n', ' ']` by default, then bounded fallback | Reuse Haystack; encode separator order as a named, versioned profile. |
| Size unit | `length_function=len` measures **characters** in the guide's `100/20` example; customizable counter available | `split_unit='word'` by default, or `char`, or `token` via tiktoken | **Never copy LangChain's 100/20 as tokens**; preserve exact units in policy identity and outputs. |
| Sentence handling | No dedicated sentence tokenizer in its default separators | Special `sentence` separator loads NLTK Punkt resources | Only enable sentence-aware policy when a supported language and offline sentence resources are qualified. |
| Separator semantics | Literal by default (`is_separator_regex=False`); regex opt-in | Inspected `_chunk_text()` applies `re.escape` and treats ordinary separators **literally**, despite an imprecise docstring describing regex | Test punctuation and delimiter behavior from actual source; do not infer regex support from docs. |
| Provenance | LangChain `Document`/`add_start_index` conventions | Haystack `Document` metadata with `source_id`, `parent_id`, `split_id`, `split_idx_start` | Preserve Haystack native metadata and application source/version IDs; no LangChain document adapter in the Live path. |

**Offline failure risk:** `haystack/components/preprocessors/sentence_tokenizer.py` can invoke `nltk.download('punkt_tab')` while loading sentence resources. Production-ready processing MUST NOT depend on opportunistic network downloads. The current supported language map includes `en` and `ru`, but **not `uk`**; an unsupported language must not silently be labeled a qualified English sentence split. A no-sentence policy (`['\\n\\n', '\\n', ' ']`) is acceptable as an explicitly named baseline when sentence resources/language are unqualified. No index-quality improvement from either implementation has yet been measured for this product.

**Known misleading configuration:** a fixed 500/50 parameter pair without a `unit` is ambiguous. In inspected Haystack, `DocumentSplitter(split_by="word")` counts words; `RecursiveDocumentSplitter(split_unit="token")` defaults to OpenAI tiktoken. Treat these as distinct, versioned profiles. No observed runtime data-quality failure from this missing layer has been demonstrated yet because upload ingestion is not implemented.

**Additional repository-evidence correction (2026-11-21):** [`haystack/components/routers/file_type_router.py`](../haystack/components/routers/file_type_router.py) and [`haystack/components/converters/multi_file_converter.py`](../haystack/components/converters/multi_file_converter.py) already provide MIME-based routing and several converters. `FileTypeRouter` uses path/ByteStream MIME hints, not cryptographically verified file-content detection. [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../haystack/components/preprocessors/embedding_based_document_splitter.py) already implements embedding-based topic-shift splitting, but no qualified application embedding connection exists. The app has **no installed, qualified multi-format parser registry**; the revised prerequisite [TASK-RAG-PARSE-001](TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) owns that validation boundary. Do not duplicate either existing Haystack component.

## D. Goal

Given a trusted, bounded parsed text/Markdown document, return exactly one validated, explainable `ChunkingDecision`, then produce deterministic nonempty chunks preserving source identity, header paths, structural boundaries and accurate sizing metadata. A run with identical bytes/profile must reproduce normalized chunk contents and source offsets. The consumer must be able to reject an unqualified token profile explicitly. No document is published by this task alone.

## E. Scope

1. Define a small app-owned `ChunkingInput`/`DocumentFeatures`, `ChunkingProfile`, `ChunkingDecision` and `PreparedChunk` contract or an equally small tested existing equivalent.
2. Resolve TXT/prose versus Markdown/heading-first based on trusted parser output and verified input type, **not filename alone**. Return an explicit `strategy`, `profile_revision`, `unit`, `size`, `overlap`, `selection_reason` and `fallback_reason?`.
3. Reuse existing Haystack `RecursiveDocumentSplitter` and `MarkdownHeaderSplitter`. Guarantee section-preserving refinement and truthful overflow handling.
4. Support an exact model-token counter **only through a separately qualified tokenizer adapter**; in its absence, use a named word-based lexical profile. No silent substitution or cloud-model dependency.
5. Produce stable output ordering, structural metadata and a profile fingerprint suitable for TASK-RAG-002's `Chunk` records.
6. Unit/golden/property tests for deterministic strategy decisions, corrupted/ambiguous structure and chunk coverage; documentation of profile use and limitations.
7. Qualify ordered recursive separator profiles against the linked LangChain reference **by observable invariants, not exact framework output parity**. Cover paragraph/sentence/line/word fallback, literal punctuation, offline sentence resources, multilingual text and the counting-unit mismatch. No `langchain-text-splitters` runtime dependency unless a separate benchmark later proves a material gap.

## F. Non-Goals

Not in scope: new HTTP upload routes, database migrations or SQL writes, OCR, Docling installation, DOCX/PDF parsing, Python source ingestion, Tree-sitter, semantic/LLM chunking, embedding generation, vector storage changes, BM25 replacement, multi-tenant production auth, frontend editor parameter redesign or automatic per-query strategy selection.

## G. Architecture / Boundaries

- [x] Domain / application: neutral policy selection and provenance.
- [x] Port / contract: named tokenizer-counting seam for real model-unit limits; no provider type in policy code.
- [x] Retrieval / RAG: chunk quality directly affects the existing PostgreSQL lexical and future embedding search.
- [x] Persistence: return prepared records but **do not write**; TASK-RAG-002 calls current `PersistencePort`.
- [x] Security / governance: no user-supplied executable strategy/class name and no content in logs.
- [x] Observability / evidence: profile selection, fallback codes, token/word histograms.
- [x] Testing and documentation.
- [ ] Agent runtime: N/A — no agent in this task.

Dependency flow:

```text
Application ingestion (TASK-RAG-002)
   -> application-owned chunking decision + splitter orchestration
       -> already existing Haystack splitter(s)
       -> optional neutral token counter
   -> existing PersistencePort -> PostgresPersistence
```

No new `Manager`/`Factory` class is justified. Keep resolver pure and concise, encapsulate tokenizer dependencies only where needed, and do not import provider SDKs into the policy module.

**Parser-contract handoff:** choose prose vs Markdown from PARSE-001 `ParsedDocument.format_id` and typed ordered elements, **not a guessed filename**. A single input may contain mixed headings, code fences, lists and tables; resolve protected element boundaries before size refinement. Update frequency is a versioned *cost/reindex policy hint*, while fact vs multi-hop queries select retrieval-time granularity/parent expansion rather than re-chunking a live source.

## H. Contracts / Interfaces / Data Model

### H0. Recursive separator policy contract

Add to the existing revisioned profile schema, or record an equivalent stable fingerprinted representation:

```text
RecursivePolicy:
  separator_profile_id: prose_paragraph_line_space | prose_sentence_aware
  separators: ordered list of literal delimiters / supported `sentence` sentinel
  unit: word | char | qualified_model_token
  target_size: positive integer; overlap: 0 <= overlap < target_size
  sentence_language?: explicitly qualified ISO language (e.g., en or ru)
  sentence_resource_revision?: pinned offline NLTK Punkt resource identity
  counter_revision?: exact tokenizer revision when qualified_model_token
  hard_character_limit: existing Chunk.content bound
```

- The initial offline-safe lexical baseline is **500 words / 50 words** using `['\\n\\n', '\\n', ' ']` (no NLTK requirement). A sentence-aware variant `['\\n\\n', 'sentence', '\\n', ' ']` requires an explicit tested language and pre-provisioned Punkt data. This is a candidate recommendation, not a claim about measured recall.
- Different separator order, sentence language/resource, counter, overlap or hard limit MUST change the `processing_fingerprint`. The user cannot supply raw regex or arbitrary executable delimiter code.
- A fallback from the sentence-aware variant to the offline variant is **not silent**: return a stable `fallback_reason` and actual profile revision; reject when policy requires strict sentence fidelity.
- A unit expressed as `model_token` is not activated through Haystack's generic tiktoken encoding unless model-token parity is actually qualified; a standalone external `length_function` is not natively provided by the inspected Haystack constructor.

Minimum required semantic fields (exact Python class names are illustrative; follow repository naming when implementing):

```text
ChunkingInput:
  source_type: verified mime/category
  normalized_content: exact extracted text
  structure: optional verified headings / protected code fences / paragraph segments
  source_id: stable server owner reference
  source_version_id: immutable processing version

ChunkingDecision:
  strategy: prose_recursive | markdown_sections
  profile_id: opaque application processing profile
  profile_revision: immutable revision
  unit: word | model_token
  target_size: positive bounded integer
  overlap: nonnegative integer < target_size
  selection_reason: low-cardinality enum
  fallback_reason?: low-cardinality enum
  tokenizer_ref?: qualified tokenizer revision

PreparedChunk:
  content: nonblank text, max 32768 characters for current DB schema
  ordinal: zero-based deterministic sequence
  source_span: verified char offsets when meaningful
  heading_path?: list of headings
  parent_structural_id?: stable section identity
  effective_size: measured in decision's declared unit
  warnings: bounded codes
  processing_fingerprint: stable hash over algorithm+params+parser/tokenizer revisions
```

Profile defaults **for initial local lexical ingestion only**:

| Profile category | Default behavior | Caveat |
| --- | --- | --- |
| General prose | `RecursiveDocumentSplitter` with a **word-based** 500/50 baseline when Qwen tokenizer is not qualified | Display `word`, not `token`; benchmark alternatives. |
| Structured Markdown | `MarkdownHeaderSplitter(keep_headers=True)` followed by bounded same-section refinement | Do not call `secondary_split="token"`; it is absent in this version. |
| Qualified model-token option | Target 500 model tokens and up to 50 within-parent overlap | May be activated only with a verified tokenizer revision and count tests; no silent word fallback. |

Constraints: `0 <= overlap < target_size`, component-instantiation allowlist, bounded max chunks and metadata, all output content traceable to input, oversize document/section reports deterministic failure rather than truncation. `profile_revision` changes with a material algorithm/parameter/tokenizer difference. `Chunk.metadata` stores selected policy, not a secret/tokenizer file path or source contents duplicated in event fields.

## I. Repository Files / Components Impacted

| Path | Action | Expected diff |
| --- | --- | --- |
| `apps/workbench/api/chunking.py` | CREATE | Pure resolve/execute functions; reuse Haystack components; structurally bounded refinement. |
| `apps/workbench/api/chunking_profiles.py` | CREATE ONLY IF NEEDED | Profile validation, immutable revisions; avoid file if small contracts fit `chunking.py`. |
| `apps/workbench/api/tests/test_chunking.py` | CREATE | Unit/golden tests with no PostgreSQL or model service; compare ordered delimiters and length/overlap invariants against the *conceptual* LangChain reference. |
| `apps/workbench/api/tests/fixtures/chunking/` | CREATE ONLY FOR SMALL TEXT FIXTURES | TXT and Markdown representative fixtures including headings, tables, code fences, Unicode; no secrets. |
| `pyproject.toml` | MODIFY ONLY IF NEEDED | App-only optional parsing/tokenizer test dependencies, not the global Haystack distribution. **Do not add `langchain-text-splitters` to production merely to copy recursive splitting.** |
| [`haystack/components/preprocessors/sentence_tokenizer.py`](../haystack/components/preprocessors/sentence_tokenizer.py) | READ / REUSE | Inspect supported languages and NLTK `punkt_tab` loading; never alter framework source for application policy. |
| `docs-website/docs/architecture/content-aware-chunking-strategy.md` | USE/UPDATE | Single decision record, truthful implemented versus planned status. |
| `tasks/TASK-RAG-002-ingest-text-and-markdown.md` | UPDATE SPECIFICATION BEFORE IMPLEMENTATION | Replace direct word splitter construction with the tested resolver contract. |

**Must not change:** `haystack/` core splitters or validators, `apps/workbench/api/migrations/0001_initial.up.sql`, existing lexical scores and OpenAPI, database records/volume, fixture Preview and unrelated UI. Any materially required migration/API change must update the task specification before coding.

**Expanded parser matrix constraint:** this task implements only qualified TXT/Markdown chunking. The canonical [format-to-parser matrix](../docs-website/docs/architecture/content-aware-chunking-strategy.md#4-extended-format-to-parser-matrix) covers PDF, Office, tabular, structured data, code, email and transcripts as **future** parser profiles. No format becomes Live-supported because its extension is listed in architecture or a Haystack converter class exists.

## J. Implementation Requirements — ordered executable blueprint

### J1. Contract and evidence freeze

1. Re-read the source files above and confirm current signatures and actual optional dependencies at task start. Record any drift from the inspected commit.
2. Record the profile-unit mismatch between the current `TASK-RAG-002` word splitter and the desired 500-token Qwen target. Do not change the claim to tokens until a qualified tokenizer is available.
3. Freeze a small normalized `ChunkingInput` contract. Accepted MIME/extension/content verification is performed by the ingestion boundary; policy receives **verified** classifications, never unrestricted user-supplied import paths.
4. Define immutable policy revision and fingerprint input fields. Include text transformations, headings, tokenizer identity and overlap.

**J1 gate:** unit tests reject an unknown policy, an unknown unit, negative/equal-to-size overlap, missing required tokenizer and unknown structure type.

### J2. Implement plain-prose and Markdown resolution

1. TXT with trustworthy prose-like structure resolves to `prose_recursive` and the named lexical word baseline. The decision contains an exact explanation code such as `plain_text_without_structural_blocks`.
2. Markdown with trusted ATX headings resolves to `markdown_sections`; preserve heading hierarchy and fenced blocks. When no recognized headings, use an explicit text fallback with `missing_usable_headings` and record the reason.
3. Ensure a `.md` holding fenced Python code **does not** select `python_ast` for the entire source. Mixed segment handling is a future overlay; report preserved fenced blocks.
4. Reject unsupported PDF/code types in this task. Do not fabricate their structure.
5. When target overlap is used, apply it **only within a verified section/parent**, never over a new heading or another source.

**J2 gate:** goldens show same strategy and same normalized content for repeated inputs, preserved header paths, and explicit fallback codes for Markdown without headings.

### J3. Reuse Haystack splitters with bounded refinement

1. Construct **one** `RecursiveDocumentSplitter` for prose with explicit `split_unit='word'`, `split_length=500`, `split_overlap=50` and a versioned **ordered separator list**. Start from `['\\n\\n', '\\n', ' ']` when offline sentence data is unqualified. This counts **words, not Qwen tokens**. Do not install LangChain as a redundant production splitter.
2. To enable true sentence-aware refinement, use the existing special `sentence` separator and `sentence_splitter_params` only after the correct NLTK `punkt_tab` resources have been pinned/provisioned offline for an explicitly supported language. Include resource/language revision in the profile. Never let tokenizer warm-up silently download language data; test the missing-resource path as a bounded, safe failure. Document a genuinely separate non-sentence profile for unsupported languages.
3. Preserve exact source text, punctuation, Unicode, newline and separator positions. Inspect actual repository implementation: it escapes ordinary separator strings (`re.escape`) while treating `sentence` specially; assert literal punctuation such as `.` behaves as expected. No raw regex execution is an approved policy feature here.
4. Test both paragraphs larger than the target and a single unbroken text span that triggers the component's last-resort fixed split. For languages without word spaces, reject or choose a separately qualified **character-unit** profile rather than treating 1 giant 'word' as within a valid 500-token budget. Account explicitly for any differences between whitespace/word counting and the model tokenizer.
5. Construct `MarkdownHeaderSplitter(keep_headers=True)` **before** flattening Markdown, preserving `header` and `parent_headers`. Do not invoke nonexistent token secondary split.
6. For oversized sections, use a separate **unit-honest** refinement stage. Retain original metadata and offsets; test order/coverage and protect fenced code and table spans from arbitrary silent slicing. If a protected span cannot fit a qualified hard cap, fail with a typed error until an explicit overflow adapter is implemented.
7. Trim empty artifacts, prevent duplicate-only trailing chunks and ensure no processed content disappears silently. Define and test consistent treatment of headings added to child retrieval text.
8. Reject any prepared content that exceeds current `Chunk.content` 32,768-character bound or would overflow configured corpus/chunk budgets. Return diagnostic codes, not partially publishable output.

**J3 gate:** section/paragraph/sentence boundary fixtures pass, with zero empty chunks, zero fabricated pages, no unaccounted content loss, and bounded overflow behavior.

### J4. Qualified tokenizer seam (do not auto-enable a model)

1. Introduce the smallest interface needed to count exact model tokens. Fake counters must be accepted for deterministic unit tests; production policy resolution uses a pinned-qualified tokenizer only when explicitly configured.
2. Count *actual embedder input*, including selected heading/context prefix, once. Verify output sizes and encoded-token parity against the pinned model tokenizer; a generic `o200k_base` count must not pass as Qwen parity.
3. Reject token-based profile selection when tokenizer is missing, revision drifted or uncertain. Keep word-only lexical policy available and accurately labeled.
4. Do not request TEI inference merely to split a file. Tokenizer loading is an isolated adapter capability, not an OpenAI/TEI SDK import into the core.

**J4 gate:** unit test proves that 500 words with the wrong tokenizer is not accepted as 500 model tokens; exact counting test is required before enabling token profile.

### J5. Provenance, idempotence and integration seam

1. Project policy identity/revision, unit/size/overlap, heading path, spans, selection/fallback reasons and warnings to bounded JSON-serializable metadata compatible with existing `Chunk.metadata`.
2. Define deterministic normalized chunk ordering and collision-safe per-occurrence identities for later persistence; do not deduplicate distinct occurrences purely because text matches.
3. Expose a small `prepare_chunks(...)` application function for TASK-RAG-002. Reuse its existing content hashes/source/version ownership and existing atomic publication method.
4. Emit operational events with strategy ID, revision, chunk count, size histogram, fallback code, parse/split elapsed time. Do **not** log document content, model secrets, vectors or arbitrary exception strings.
5. Document that a processing revision change is a delta-reindex event. It must not silently reuse embeddings computed with an incompatible preprocessing profile.

**J5 gate:** prepared chunks pass `Chunk` validation, are reproducible, and contain no raw secret/source text in diagnostics. No database calls occur in unit-only routing.

### J6. Regression, docs and handoff

1. Add a small **pure** resolver test matrix: plain prose, short Markdown, nested headings, heading-only Markdown, code fences, table-like Markdown, Unicode/Cyrillic, huge unbroken text, empty, invalid profile, repeated paragraph, overlap edge and token counter drift.
2. Add **recursive algorithm goldens** for (a) multiple paragraphs; (b) one huge paragraph; (c) long sentence; (d) empty line/CRLF; (e) literal `.`/regex-like delimiters; (f) duplicate sentences/offsets; (g) EN and RU sentence resources; (h) unsupported UK sentence policy; (i) Chinese/Japanese/Thai no-space/Unicode punctuation; (j) absent NLTK resources with outbound network denied; (k) 0%, 10%, 20% overlap and over-limit refusal; (l) char-vs-word-vs-model-token mismatch.
3. In a **documentation-only comparison**, map the LangChain guide's character-count 100/20 example to a Haystack **character** test; separately test the desired word-based 500/50 profile. Do not assert identical text/chunk counts across frameworks because sentence engines and overlap algorithms differ. Assert measurable invariants instead: unchanged logical content coverage (discounting intended overlap), bounded lengths, accurate provenance offsets, no fabricated pages, no crossing protected structures, and deterministic results.
4. Add property tests for repeatability, order, coverage and strict size constraints; add negative tests for prompt-injection text that tries to select a strategy or emit logs.
5. Update architecture decision record and TASK-RAG-002 J3 references with this real contract. Do not mark PDF/AST/semantic support implemented.
6. Record exact checks and outcomes; a successful unit suite is NOT an end-to-end upload demonstration.

**J6 gate:** all focused checks pass and the ingestion blueprint uses the resolver without introducing duplicate publication logic.

## K. Security / Governance / Observability

- All strategy resolution happens in trusted application code; file content/filename can never select arbitrary Python imports, SQL, provider models, plugins or filesystem paths.
- Keep workspace identity server-resolved. The resolver has no permission to change workspace scope or fetch other sources.
- Preserve metadata needed for citations and active-version publication. Treat document text as untrusted data, not instructions.
- Log only bounded low-cardinality strategy/error IDs, profile revision, counts, durations; redact content, credentials, vectors and tokenized source snippets.
- Tokenizer/model profile references are identifiers, not resolved secrets or raw service addresses.
- Use existing data retention rules; do not retain uploaded bytes or extracted text in a second cache without a reviewed retention contract.

## L. Testing / Evaluation / Runtime Verification

| Level | Test and required assertion |
| --- | --- |
| Pure unit | Policy resolves same inputs deterministically; unknown format, invalid overlap, no tokenizer and empty input fail safely. |
| Splitter integration | Real `RecursiveDocumentSplitter` and `MarkdownHeaderSplitter` preserve heading metadata and contain no blank chunks; ordered paragraph/line/sentence/fallback separators and overlap are exercised on actual source text. |
| Offline sentence resources | NLTK `punkt_tab` missing/available, supported EN/RU, unsupported UK and CJK/no-space: no implicit download, silent language assumption or unbounded char output. |
| LangChain reference comparison | Explicitly verify LangChain's documented default **characters**, ordered separators and optional `length_function` vs Haystack's word/char/token behavior; avoid introducing an unproved second runtime dependency. |
| Compatibility | `PreparedChunk` payload is compatible with existing `Chunk` validators and metadata size bound. |
| Negative / adversarial | Content impersonating config, suspicious MIME/extension mismatch (ingestion boundary), fenced code and table overflow do not enable unsafe routes. |
| Regression | Existing PostgreSQL lexical / validator / UI test suites remain unchanged and pass relevant targeted checks. |
| Evaluation | Measure chunk counts, repeat-token ratio, real unit length distribution, blank/lost bytes, warnings, processing latency and query recall once ingested. |
| Runtime verification | Optional app-environment smoke with no live database; no automatic model/tokenizer download in normal tests. |

Project uses Hatch. Run the **app-specific existing** commands from repository root (adjust `hatch` environment only if inspected configuration differs):

```text
hatch --version
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
```

For frontend-regression coverage only if UI impacted indirectly:

```text
cd apps/workbench/web
npm run typecheck
npm test
```

Record actual command output in task evidence; do not claim pass based solely on code review or local fixture success.

- The parser/strategy boundary consumes an **actually verified, revisioned** PARSE-001 format and typed elements; raw upload extension and user MIME never directly select a privileged chunker.
- Code/PDF/tables/chat are explicitly planned or unavailable until their own task gates; the emitted format list is not mistaken for enabled UI capability.

## M. Acceptance Criteria

- [ ] 100% of supported TXT/Markdown inputs resolve to exactly one allowlisted, revisioned policy with an explicit **correct** unit.
- [ ] A model-token profile without a qualified tokenizer fails; a word-based profile never reports itself as Qwen tokens.
- [ ] Markdown heading hierarchy, ordering and source traceability survive into every applicable prepared chunk.
- [ ] Structural overlap never crosses a section, source or workspace boundary.
- [ ] No blank chunk, duplicate-only trailing chunk, silent input loss or oversized publishable chunk is emitted in fixture matrix.
- [ ] Repeating identical input/profile produces identical ordered normalized chunks and metadata except explicitly non-deterministic operational IDs.
- [ ] Different processing profile revisions produce incompatible processing fingerprints for delta/reindex logic.
- [ ] No new DB document table, in-memory Live corpus or Haystack core fork is introduced.
- [ ] At least 20 curated TXT/Markdown test inputs and 15 positive/negative unit+integration scenarios run and report results; no unsupported file family is advertised as enabled.
- [ ] Recursive splitting is implemented via the existing Haystack component with explicit versioned separator order and **honest** `word`/`char` units; the LangChain sample's 100/20 **character** counts are not described as tokens or copied blindly.
- [ ] Tests cover paragraph/sentence/line/word/fixed fallback, literal punctuation/Unicode, repeatable offsets, and unsupported language/resource handling with outbound network disabled.
- [ ] Zero implicit NLTK downloads during parsing/splitting; either qualified offline sentence resources exist or a documented no-sentence profile is selected with the correct fallback reason.
- [ ] `processing_fingerprint` changes whenever separator order, sentence-resource revision or unit changes; any hidden fallback is forbidden.
- [ ] Relevant Hatch checks and documentation pass; measured artifacts recorded, limitations clearly stated.

## N. Documentation / Migration / Compatibility / Rollback

- Docs: canonical runtime contract plus a later content-aware architecture decision record (if committed), TASK-RAG-002 J3 handoff, app README when integrated, and truthful profiles. Record LangChain as an *algorithm reference only* and Haystack as the selected implementation.
- Database migration: **N/A — policy engine returns prepared data only**. Metadata stays within current JSONB; indexed relational parent-child schema is a separately reviewed change.
- API migration: **N/A — no HTTP routes in this task**. Future listing of available policies needs explicit contract revision and capability qualification.
- Existing 500-word lexical behavior may be retained as a named profile; an eventual Qwen-token profile is a **distinct** revision and must not rewrite prior chunk manifests in place.
- Rollback: disable policy selection integration and select the previous explicit lexical word profile in the consuming ingestion service; never delete existing document versions or DB volume.
- Deferred: code AST, page-aware PDFs, DOCX, table reconstruction, Tree-sitter and semantic splitting have separate tasks and acceptance gates.

## O. Mandatory Completion Checklist

- [ ] Actual source code, tests, dependencies and docs re-inspected; Section C updated if current state drifted.
- [ ] Decision/profile contracts implemented with no provider SDK leaking into core policy.
- [ ] TXT and Markdown candidates tested, token-vs-word mismatch eliminated from authoritative labels.
- [ ] Recursive splitting reference behavior, explicit separator order, language choice, no implicit downloads and character/word/model-token ceilings tested.
- [ ] Required failures, boundaries, metadata and determinism tests pass.
- [ ] Reuse documented (actual Haystack splitters, existing persistence model); no duplicate writer.
- [ ] All relevant quality commands executed with recorded output and limitations.
- [ ] Security, source authority, workspace isolation and logging redaction reviewed.
- [ ] Docs and downstream ingestion task are consistent with implemented behavior.
- [ ] Each unchecked acceptance criterion is resolved or explicitly blocks COMPLETE.
- [ ] Evidence paths, implementation commit and any necessary rollback notes recorded.

**Task remains PROPOSED until actual implementation and evidence satisfy Section O.**
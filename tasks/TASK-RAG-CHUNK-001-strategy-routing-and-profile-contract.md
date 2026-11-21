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

Implement a **pure, versioned chunking policy resolver** with deterministic **sentence/paragraph-aware, token-budgeted** TXT/Markdown strategies, accurate counter identity, structural provenance and reproducible golden tests; provide an application-owned seam for later code and layout adapters.

## B. Context / Problem

The current detailed ingestion plan hard-codes `DocumentSplitter(split_by="word", split_length=500, split_overlap=50)`, while the product discussion assumes **500 tokens / 50 tokens** and future documents need structure-aware splitting. The baseline must remain **500 tokens with 50-token overlap**, not 500 words or the 100-character demonstration in LangChain. The two splitting dimensions are independent: **NLTK sentence/paragraph/line detection selects boundaries; a token counter enforces size/overlap, with token-level emergency fallback**. The built-in tiktoken counter does not necessarily equal the Qwen tokenizer, but that is a counter-identity distinction, **not a reason to disable the token-based baseline**. Applying fixed prose splitting indiscriminately to Markdown, tables or source code destroys meaningful boundaries and harms explainability, differential indexing and source citation. A small explicit decision boundary is needed before adding more file types.

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
| [Recursive splitter](../haystack/components/preprocessors/recursive_splitter.py) | `RecursiveDocumentSplitter(split_length, split_overlap, split_unit, separators, tokenizer_encoding)` | **Supports NLTK sentence boundaries and tiktoken token counting in the same instance** with `split_unit="token"` and `"sentence"` in `separators`; use this combined algorithm. The default tiktoken `o200k_base` is not the Qwen model tokenizer. |
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
| Size unit | `length_function=len` measures **characters** in its small `100/20` demonstration; a custom counter is possible | `split_unit='token'` uses tiktoken; `word`/`char` are distinct optional units | The **product default is 500 tokens / 50-token overlap**, measured by the named counter. LangChain's 100 characters is not a product setting. |
| Sentence handling | Splits at paragraph/line/space delimiters by default | Special `sentence` separator uses NLTK Punkt; token size still works simultaneously | **Enable the combined sentence-aware + token-counted profile by default for supported languages**. Add/provision NLTK and `punkt_tab`; do not disable sentence boundaries merely because extra resources are needed. |
| Separator semantics | Literal by default (`is_separator_regex=False`); regex opt-in | Inspected `_chunk_text()` applies `re.escape` and treats ordinary separators **literally**, despite an imprecise docstring describing regex | Test punctuation and delimiter behavior from actual source; do not infer regex support from docs. |
| Provenance | LangChain `Document`/`add_start_index` conventions | Haystack `Document` metadata with `source_id`, `parent_id`, `split_id`, `split_idx_start` | Preserve Haystack native metadata and application source/version IDs; no LangChain document adapter in the Live path. |

**NLTK is a supported dependency, not a blocker:** `haystack/components/preprocessors/sentence_tokenizer.py` may call `nltk.download('punkt_tab')` if the resource is absent. Include NLTK and the required Punkt resources in the app environment and local/deployment setup; test their presence at initialization and record the language/resource revision. Prefer provisioning during build/setup rather than unexpected downloads during indexing. The inspected language map supports `en` and `ru` but not `uk`; explicitly choose a Ukrainian-compatible segmentation policy or a **token-budgeted** paragraph/line/punctuation fallback (with reason), never silently replace it with an English Punkt model or character-based size unit. Missing resources may fail startup or select an explicitly declared **token-based** fallback; the fallback must never quietly become word- or character-sized. Quality gains are hypotheses until measured.

**Known misleading configuration:** a fixed 500/50 parameter pair without a `unit` is ambiguous. The desired `RecursiveDocumentSplitter(split_unit="token", split_length=500, split_overlap=50)` counts **tiktoken tokens** with the explicitly recorded encoding, while the previous `DocumentSplitter(split_by="word")` counts **words**. Keep these separate; do not mislabel generic tiktoken counts as Qwen-native tokens. No observed runtime data-quality failure from this missing layer has been demonstrated yet because upload ingestion is not implemented.

**Additional repository-evidence correction (2026-11-21):** [`haystack/components/routers/file_type_router.py`](../haystack/components/routers/file_type_router.py) and [`haystack/components/converters/multi_file_converter.py`](../haystack/components/converters/multi_file_converter.py) already provide MIME-based routing and several converters. `FileTypeRouter` uses path/ByteStream MIME hints, not cryptographically verified file-content detection. [`haystack/components/preprocessors/embedding_based_document_splitter.py`](../haystack/components/preprocessors/embedding_based_document_splitter.py) already implements embedding-based topic-shift splitting, but no qualified application embedding connection exists. The app has **no installed, qualified multi-format parser registry**; the revised prerequisite [TASK-RAG-PARSE-001](TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) owns that validation boundary. Do not duplicate either existing Haystack component.

## D. Goal

Given a trusted, bounded parsed text/Markdown document, return exactly one validated, explainable `ChunkingDecision`, then produce deterministic nonempty chunks preserving source identity, header paths, structural boundaries and **500/50 token-bounded sizing for the primary prose profile**. Paragraph and sentence segmentation work **with** token counting; the terminal fallback uses token slicing, not a switch to character or word sizing. Repeated bytes/profile produce reproducible chunk contents/offsets. Record the actual counter encoding (`tiktoken:o200k_base` initially); validate Qwen-native token length separately when an exact embedding budget is enforced. No document is published by this task alone.

## E. Scope

1. Define a small app-owned `ChunkingInput`/`DocumentFeatures`, `ChunkingProfile`, `ChunkingDecision` and `PreparedChunk` contract or an equally small tested existing equivalent.
2. Resolve TXT/prose versus Markdown/heading-first based on trusted parser output and verified input type, **not filename alone**. Return an explicit `strategy`, `profile_revision`, `unit`, `size`, `overlap`, `selection_reason` and `fallback_reason?`.
3. Reuse existing Haystack `RecursiveDocumentSplitter` and `MarkdownHeaderSplitter`. Guarantee section-preserving refinement and truthful overflow handling.
4. Make the built-in **tiktoken token-counted + NLTK sentence-aware** profile the enabled primary candidate at **500/50 tokens**; record encoding and sentence language in an immutable profile. Support an optional exact Qwen-model token counter through a separate adapter for final embedder-budget admission checks; lack of Qwen-native parity MUST NOT silently convert token splitting into word/character splitting or block the lexical MVP. Do not call a tiktoken count an exact Qwen count.
5. Produce stable output ordering, structural metadata and a profile fingerprint suitable for TASK-RAG-002's `Chunk` records.
6. Unit/golden/property tests for deterministic strategy decisions, corrupted/ambiguous structure and chunk coverage; documentation of profile use and limitations.
7. Qualify ordered recursive separator profiles against the linked LangChain reference **by observable invariants, not exact framework output parity**. Cover combined paragraph/sentence/line segmentation **under a token budget**, literal punctuation, provisioned NLTK resources, multilingual text, terminal token slicing and accurate counter identification. No `langchain-text-splitters` runtime dependency unless a separate benchmark later proves a material gap.

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
  separator_profile_id: prose_token_sentence_aware | prose_token_structural_fallback
  separators: ordered literal delimiters with optional supported `sentence` sentinel
  size_unit: token                        # mainline; word/char only explicit benchmark profiles
  token_counter: tiktoken                 # Haystack built-in counter
  tokenizer_encoding: o200k_base         # tiktoken encoding, NOT Qwen tokenizer
  target_size: 500                       # tokens in the declared counter
  overlap: 50                            # tokens in the declared counter
  sentence_language?: en | ru | other specifically qualified language
  sentence_resource_revision?: pinned/provisioned NLTK Punkt resource identity
  model_counter_revision?: separately qualified exact Qwen tokenizer, if used
  hard_character_limit: existing Chunk.content bound
```

- **Primary TXT/prose profile:** `RecursiveDocumentSplitter(split_length=500, split_overlap=50, split_unit="token", tokenizer_encoding="o200k_base", separators=["\\n\\n", "sentence", "\\n", " "])`. Provision NLTK and the selected language's `punkt_tab`; both sentence boundaries and token budget are enabled simultaneously. The final fallback in the existing recursive component is token slicing when natural separators cannot fit the budget. **Do not replace with a 100-character, 500-word or 500-character default.** This is a candidate product baseline, not a measured-recall claim.
- Different separator order, sentence language/resource, counter, overlap or hard limit MUST change the `processing_fingerprint`. The user cannot supply raw regex or arbitrary executable delimiter code.
- For unsupported languages or missing sentence resources, a separately versioned **token-counted** paragraph/line/punctuation fallback may be chosen with a visible `fallback_reason`; when sentence fidelity is mandatory, return a typed error. Both profiles use `split_unit="token"` with the same declared counter and token-size budget; neither falls back to word/character chunk limits.
- `token` denotes an actual **tiktoken-encoding token**, not an approximation in words or characters. `model_token` denotes the **exact pinned embedding-model tokenizer**; do not conflate them. Haystack's inspected recursive constructor supports `tokenizer_encoding` but no external `length_function`. A Qwen token counter can independently validate the final embedding input and, if necessary, request a versioned stricter refinement strategy; do not claim native parity without measuring it.

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
  unit: token | model_token | word | char  # default token; non-token units only explicit opt-in tests
  target_size: positive bounded integer  # 500 for baseline
  overlap: nonnegative integer < target_size  # 50 for baseline
  selection_reason: low-cardinality enum
  fallback_reason?: low-cardinality enum
  token_counter: tiktoken | exact_model | none
  tokenizer_ref: encoding/revision required for token or model_token

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
| General prose (supported NLTK sentence locale) | **500 tiktoken tokens / 50-token overlap**; recursive paragraph → NLTK sentence → newline → word-separator refinement; terminal **token** slicing | Enable both NLTK sentence boundaries and `split_unit="token"`; publish actual encoding, language and resource revision. |
| Plain text with unqualified sentence locale | Same **500/50 token-based** recursive profile with explicit paragraph/line/punctuation separators; `fallback_reason` required | Do **not** downgrade to char/word sizing or silently assume English sentence segmentation. |
| Structured Markdown | `MarkdownHeaderSplitter(keep_headers=True, secondary_split=None)` followed by the **500/50 token-based recursive splitter per section** | Do not call nonexistent `secondary_split="token"`; keep overlaps within section, preserve headings/fences/tables. |
| Exact model-token admission | Count final indexed/embedder text with pinned Qwen tokenizer when present; validate model input budget and investigate mismatches | An unavailable model tokenizer is **not** grounds to disable the operational 500/50 tiktoken profile; do not claim the numbers are Qwen tokens. |

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
2. Record the mismatch between the earlier RAG-002 word splitter and the requested **500-token/50-token** recursive profile. Configure `split_unit="token"` immediately and label it accurately as `tiktoken:o200k_base` token counts; do **not** describe it as Qwen-native token parity before comparison.
3. Freeze a small normalized `ChunkingInput` contract. Accepted MIME/extension/content verification is performed by the ingestion boundary; policy receives **verified** classifications, never unrestricted user-supplied import paths.
4. Define immutable policy revision and fingerprint input fields. Include text transformations, headings, tokenizer identity and overlap.

**J1 gate:** unit tests reject an unknown policy, an unknown unit, negative/equal-to-size overlap, missing required tokenizer and unknown structure type.

### J2. Implement plain-prose and Markdown resolution

1. TXT with trustworthy prose-like structure resolves to `prose_recursive` and the named **500-token/50-token NLTK + tiktoken baseline** for a supported sentence language. The decision contains an exact explanation code such as `plain_text_without_structural_blocks`.
2. Markdown with trusted ATX headings resolves to `markdown_sections`; preserve heading hierarchy and fenced blocks. When no recognized headings, use an explicit text fallback with `missing_usable_headings` and record the reason.
3. Ensure a `.md` holding fenced Python code **does not** select `python_ast` for the entire source. Mixed segment handling is a future overlay; report preserved fenced blocks.
4. Reject unsupported PDF/code types in this task. Do not fabricate their structure.
5. When target overlap is used, apply it **only within a verified section/parent**, never over a new heading or another source.

**J2 gate:** goldens show same strategy and same normalized content for repeated inputs, preserved header paths, and explicit fallback codes for Markdown without headings.

### J3. Reuse Haystack splitters with bounded refinement

1. Use **one existing Haystack recursive splitter** that combines NLTK sentence boundaries with a tiktoken **token** budget:

   ```python
   # Combined boundary-aware and token-budgeted prose splitting; no extra splitter framework.
   splitter = RecursiveDocumentSplitter(
       split_length=500,
       split_overlap=50,
       split_unit="token",
       tokenizer_encoding="o200k_base",
       separators=["\n\n", "sentence", "\n", " "],
       sentence_splitter_params={"language": "ru", "keep_white_spaces": True},
   )
   ```

   The example uses Russian; select `en` or another **actually supported/qualified** sentence language for other corpora. For every final chunk, record length and overlap in `tiktoken:o200k_base` tokens, not words, characters or assumed Qwen tokens. The example and LangChain's 100/20 **character** demo are not interchangeable.
2. Include NLTK and the appropriate `punkt_tab` resources in the approved app/runtime dependencies. Prepare assets in setup/deployment so warm-up does not unexpectedly download data; the existence of an additional dependency is **not** a reason to remove `sentence` from the default supported-language profile. Test warm-up, language selection, resource mismatch and service restart.
3. The actual algorithm is: try whole paragraphs, then **NLTK sentence boundaries**, then line/space delimiters; when a piece still exceeds **500 tiktoken tokens**, the component's final bounded split is **token-based**, not character-based. The `split_overlap=50` is also counted in the same encoding. Make the order and length counter independently configurable as one revisioned profile. Validate bounds, content coverage and overlap after the actual splitter call.
4. For Ukrainian and other languages without a supported Punkt language, choose a documented **token-budgeted** punctuation/paragraph/line policy (or add a tested language-aware sentence boundary adapter); emit an explicit locale fallback reason. For CJK/Thai and no-space text, add qualified Unicode punctuation delimiters where useful and keep terminal splitting by tokens. **Never** switch to character counting merely because word boundaries are absent.
5. Preserve source text, punctuation, Unicode, CRLF/newlines and positional spans. Inspect the actual code: ordinary separators are escaped via `re.escape`, while `sentence` is special. Assert literal punctuation behavior and guard against false offsets introduced by overlap or repeated text. No user-defined regex or executable delimiter is permitted.
6. For Markdown, run `MarkdownHeaderSplitter(keep_headers=True, secondary_split=None)` on the original Markdown **before flattening**. Apply the same **token-budgeted** `RecursiveDocumentSplitter` independently to oversized sections; keep 50-token overlap **within a section** only and preserve heading hierarchy, code fences and table spans. The Markdown splitter's own secondary token mode does not exist in this version, so do not enable it or use a 500-word substitute.
7. If a code fence/table/other protected unit exceeds the budget, use an explicit versioned structure-preserving refinement or emit a typed overflow error. Never silently cut a syntactic structure to satisfy 500 tokens when such cutting would invalidate its meaning. For ordinary prose with no protected structure, token-level last-resort fallback is allowed.
8. Trim empty artifacts, prevent overlap-only duplicate chunks and ensure all real content is accounted for. `RecursiveDocumentSplitter` can emit `page_number=1` for unpaginated TXT: **do not** project this as an actual source page or citation when the parser provided no physical page provenance.
9. Reject prepared content beyond the current `Chunk.content` 32,768-character limit or the bounded corpus/chunk limits. Return diagnostic codes; no partial data becomes publishable.

**J3 gate:** section/paragraph/sentence boundary fixtures pass, with zero empty chunks, zero fabricated pages, no unaccounted content loss, and bounded overflow behavior.

### J4. Tokenizer accounting and optional exact-model admission (no artificial lexical blocker)

1. The **built-in `tiktoken:o200k_base` counter is immediately usable** with the inspected Haystack component for the proposed 500/50 **tiktoken-token** baseline. Keep encoder/encoding/version in the processing fingerprint; do not label generic tiktoken tokens as Qwen-native units. `token` must never mean `word` or `char`.
2. Separately support the smallest app-owned adapter needed to count **exact Qwen-model tokens** when the pinned tokenizer becomes available (e.g., tokenizer assets packaged with a specific model revision). Count the actual eventual embedding input, including heading/context prefixes and model-required markers/special tokens; no TEI inference is needed to count tokens.
3. If model-token measurements exceed the configured embedding admission budget, apply a **specified, versioned and structure-safe refinement** or reject that document with a typed error; never silently truncate or call the tiktoken count an exact model count. The embedding admission gate is separate from the already functional lexical token splitter.
4. Use fake counters and real tiktoken length tests in unit/integration tests. Record `length_tiktoken`, and when a pinned exact tokenizer is present, `length_model_token` and the observed delta, with an explicit `counter_revision`; empty counters or revision mismatches are errors only for profiles that require them.
5. Keep optional tokenizer dependencies in the app adapter/environment, not the domain policy. NLTK is intentionally enabled for supported locales; do not disable it to avoid dependency installation.

**J4 gate:** a real `RecursiveDocumentSplitter(split_unit="token")` generates reproducible **500/50 encoding-token** chunks, no word/char fallback, and model-token budget checks behave correctly **when** a pinned exact model counter is configured.

### J5. Provenance, idempotence and integration seam

1. Project policy identity/revision, unit/size/overlap, heading path, spans, selection/fallback reasons and warnings to bounded JSON-serializable metadata compatible with existing `Chunk.metadata`.
2. Define deterministic normalized chunk ordering and collision-safe per-occurrence identities for later persistence; do not deduplicate distinct occurrences purely because text matches.
3. Expose a small `prepare_chunks(...)` application function for TASK-RAG-002. Reuse its existing content hashes/source/version ownership and existing atomic publication method.
4. Emit operational events with strategy ID, revision, chunk count, size histogram, fallback code, parse/split elapsed time. Do **not** log document content, model secrets, vectors or arbitrary exception strings.
5. Document that a processing revision change is a delta-reindex event. It must not silently reuse embeddings computed with an incompatible preprocessing profile.

**J5 gate:** prepared chunks pass `Chunk` validation, are reproducible, and contain no raw secret/source text in diagnostics. No database calls occur in unit-only routing.

### J6. Regression, docs and handoff

1. Add a small **pure** resolver test matrix: plain prose, short Markdown, nested headings, heading-only Markdown, code fences, table-like Markdown, Unicode/Cyrillic, huge unbroken text, empty, invalid profile, repeated paragraph, overlap edge and token counter drift.
2. Add **combined sentence + token goldens** for (a) multiple paragraphs; (b) one huge paragraph; (c) long sentence; (d) empty line/CRLF; (e) literal `.`/regex-like delimiters; (f) repeated sentences/offsets; (g) EN/RU NLTK resources; (h) unsupported UK locale with **token** fallback; (i) CJK/Thai no-space/punctuation; (j) missing resources with deterministic declared behavior; (k) 0/50/100 tokens of overlap; (l) **tiktoken-vs-Qwen** counts when the real tokenizer is available; (m) provenance of unpaginated TXT.
3. Treat the LangChain `100/20` **characters** example as an educational reference only. Validate the real **500-token/50-token** Haystack profile on the same content with exact `tiktoken:o200k_base` counts; outputs need not match LangChain because delimiters and NLTK sentence boundaries differ. Assert content coverage (accounting for overlap), every chunk <=500 counted tokens, valid overlap and offsets, no fabricated pages, no crossing protected structures and deterministic processing.
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
| Pure unit | Policy resolves same inputs deterministically; unknown format, invalid overlap, missing **required tiktoken encoding**, unavailable NLTK locale/resources and empty input fail safely or select an explicit token-based fallback. |
| Splitter integration | **Combined NLTK sentence-aware + token-sized** `RecursiveDocumentSplitter` enforces <=500 tiktoken tokens and 50-token overlap, preserving heading metadata through `MarkdownHeaderSplitter`; natural boundaries and terminal **token** fallback are exercised. |
| Sentence resources | Package/test NLTK `punkt_tab`, supported EN/RU, unsupported UK and CJK/no-space; resource absence is visible and never triggers silent word/character sizing. Provision resources during setup; avoid surprising downloads during ingestion. |
| LangChain reference comparison | Explicitly verify LangChain's demonstration uses **characters**, whereas the selected Haystack policy uses **tokens** with NLTK sentence boundaries; do not copy `chunk_size=100` into production or introduce a redundant runtime dependency. |
| Compatibility | `PreparedChunk` payload is compatible with existing `Chunk` validators and metadata size bound. |
| Negative / adversarial | Content impersonating config, suspicious MIME/extension mismatch (ingestion boundary), fenced code and table overflow do not enable unsafe routes. |
| Regression | Existing PostgreSQL lexical / validator / UI test suites remain unchanged and pass relevant targeted checks. |
| Evaluation | Measure actual **tiktoken** chunk-size distribution/maximum, requested 50-token overlap, sentence and paragraph integrity, long-span token fallback, repeated-token overhead, content coverage, NLTK language fallback, latency and later query recall; report Qwen-native count delta separately when available. |
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
- [ ] The **500/50 tiktoken-token default is usable** without an exact Qwen tokenizer; it is never mislabeled as Qwen-native. Only an optional `model_token`-exact profile fails when its pinned tokenizer is absent.
- [ ] Markdown heading hierarchy, ordering and source traceability survive into every applicable prepared chunk.
- [ ] Structural overlap never crosses a section, source or workspace boundary.
- [ ] No blank chunk, duplicate-only trailing chunk, silent input loss or oversized publishable chunk is emitted in fixture matrix.
- [ ] Repeating identical input/profile produces identical ordered normalized chunks and metadata except explicitly non-deterministic operational IDs.
- [ ] Different processing profile revisions produce incompatible processing fingerprints for delta/reindex logic.
- [ ] No new DB document table, in-memory Live corpus or Haystack core fork is introduced.
- [ ] At least 20 curated TXT/Markdown test inputs and 15 positive/negative unit+integration scenarios run and report results; no unsupported file family is advertised as enabled.
- [ ] Recursive splitting uses the existing Haystack component **with NLTK `sentence` and `split_unit="token"` simultaneously** for supported locales, explicit `500` tiktoken-token size and `50` tiktoken-token overlap. No 100-character/500-word replacement and no unapproved second splitter implementation.
- [ ] Tests cover paragraph/sentence/line/word/fixed fallback, literal punctuation/Unicode, repeatable offsets, and unsupported language/resource handling with outbound network disabled.
- [ ] Required NLTK/Punkt resources are installed and tested for supported languages; missing/unsupported-language behavior is explicit, remains **token-counted** or fails safely, and never silently changes units. Prefer pre-provisioning to unexpected runtime downloads.
- [ ] `processing_fingerprint` changes whenever separator order, sentence-resource revision or unit changes; any hidden fallback is forbidden.
- [ ] Relevant Hatch checks and documentation pass; measured artifacts recorded, limitations clearly stated.

## N. Documentation / Migration / Compatibility / Rollback

- Docs: canonical runtime contract plus a later content-aware architecture decision record (if committed), TASK-RAG-002 J3 handoff, app README when integrated, and truthful profiles. Record LangChain as an *algorithm reference only* and Haystack as the selected implementation.
- Database migration: **N/A — policy engine returns prepared data only**. Metadata stays within current JSONB; indexed relational parent-child schema is a separately reviewed change.
- API migration: **N/A — no HTTP routes in this task**. Future listing of available policies needs explicit contract revision and capability qualification.
- The prior word-based 500/50 proposal is **superseded before ingestion implementation** by the 500/50 **tiktoken-token + NLTK sentence-aware** default. A future exact Qwen-token budget uses a distinct counter/revision and must not reinterpret prior manifests; character or word units are opt-in benchmarks, not silent fallbacks.
- Rollback: disable policy selection integration and select the previous explicit lexical word profile in the consuming ingestion service; never delete existing document versions or DB volume.
- Deferred: code AST, page-aware PDFs, DOCX, table reconstruction, Tree-sitter and semantic splitting have separate tasks and acceptance gates.

## O. Mandatory Completion Checklist

- [ ] Actual source code, tests, dependencies and docs re-inspected; Section C updated if current state drifted.
- [ ] Decision/profile contracts implemented with no provider SDK leaking into core policy.
- [ ] TXT and Markdown **500/50 tiktoken-token** candidates tested with NLTK sentence boundaries, and tiktoken-vs-Qwen-native distinction explicit in all authoritative labels.
- [ ] Combined NLTK sentence segmentation + token counting, 500/50 token limits, token-only hard fallback, language/resource setup, and optional exact model-token admission tested.
- [ ] Required failures, boundaries, metadata and determinism tests pass.
- [ ] Reuse documented (actual Haystack splitters, existing persistence model); no duplicate writer.
- [ ] All relevant quality commands executed with recorded output and limitations.
- [ ] Security, source authority, workspace isolation and logging redaction reviewed.
- [ ] Docs and downstream ingestion task are consistent with implemented behavior.
- [ ] Each unchecked acceptance criterion is resolved or explicitly blocks COMPLETE.
- [ ] Evidence paths, implementation commit and any necessary rollback notes recorded.

**Task remains PROPOSED until actual implementation and evidence satisfy Section O.**
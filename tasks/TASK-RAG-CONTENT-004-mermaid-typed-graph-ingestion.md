# TASK-RAG-CONTENT-004 — Mermaid source parsing, typed relations, and search projections

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint; no approved Mermaid structural parser currently exists  
**Priority:** P1 — Markdown structural enrichment after representation foundation  
**Dependencies:** TASK-RAG-CONTENT-001; completed TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002; evidence consumer TASK-RAG-CONTENT-005  
**Repository snapshot inspected:** 522c2cb38aff746e65a8f04ea48d88d3695fc5a9  
**Target:** tasks/TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md

## A. Title

Extract Mermaid fenced blocks from Markdown, validate syntax with a pinned offline parser, derive approved diagram-type-specific relational structures, preserve the **exact original Mermaid source**, and index deterministic graph summaries with source-version and line-range evidence.

## B. Context / Problem

Mermaid is not an image requiring OCR. The Mermaid text already encodes graph structure, including directional edges, labels, ordered messages, inheritance and ER cardinalities. Treating it as a generic code fence and then recursively splitting after an arbitrary token count breaks graph semantics. Sending a rendered SVG to a VLM wastes exact source information and adds inference error. But treating a Mermaid syntax validator as a complete graph extractor is also incorrect: validation may only return a diagram type, not nodes, edges or exact sequencing. Each supported Mermaid family needs a deliberately qualified AST/grammar projection.

## C. Current Repository State

### C0. Source and parser-family status reconciliation

**Source reinspection 2026-11-23:** [parsing.py](../apps/workbench/api/parsing.py) already recognizes Markdown fenced blocks as `ParsedElement.PROTECTED_RAW`. [parser_registry.py](../apps/workbench/api/parser_registry.py) has no qualified Mermaid grammar adapter, and no one has implemented a Mermaid source-to-graph schema yet. [PARSE-004](check/TASK-RAG-PARSE-004-structured-data-and-devops-parsers.md) separately proposes safe JSON/YAML/JSONL extraction, not Mermaid.

| Source | Verified implementation / missing behavior |
| --- | --- |
| [parsing.py](../apps/workbench/api/parsing.py) | Markdown parser recognizes fenced blocks, emits ParsedElement with kind PROTECTED_RAW, text/source_span and line ranges; it does not parse a Mermaid AST or register diagram relations. |
| [parser_registry.py](../apps/workbench/api/parser_registry.py) | FormatId.MARKDOWN and ElementKind.PROTECTED_RAW are qualified, with bounded UTF-8 input; no Mermaid-specific element kinds or language grammar capability. |
| [chunking.py](../apps/workbench/api/chunking.py) | Token-aware Markdown chunks and structure-preserving control exist; it cannot by itself recover arrows/conditions from a code fence. |
| [chunking_profiles.py](../apps/workbench/api/chunking_profiles.py) | Immutable processing revisions/token counters; adding source-to-graph projection must change processing fingerprint. |
| [ingestion.py](../apps/workbench/api/ingestion.py) and [ingestion_http.py](../apps/workbench/api/ingestion_http.py) | Durable TXT/Markdown ingestion, idempotency and scoped publishing; add structure only through these existing seams. |
| [persistence.py](../apps/workbench/api/persistence.py), [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) | Current SourceVersion/Chunk identity and PostgreSQL publication; do not start a second graph database or document store. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | Typed original/structured/derived representations and source assets. Mermaid uses these rather than a new independent schema. |
| [Mermaid documentation](https://mermaid.js.org/config/usage.html) | mermaid.parse validates syntax and reports diagramType; it does NOT promise a stable application-level graph AST or complete nodes/edges for every type. |
| [Workbench UI](../apps/workbench/web/src/domain/catalog.ts) | Visual node catalog is an editor representation; it does not authorize execution of arbitrary Mermaid or Markdown scripts. |

No existing approved diagram-family parser in the application was found in the inspected sources. This is a missing capability, not an observed regression. Parser/editor dependencies may evolve; inspect them again before implementation.

## D. Goal

For each qualified Mermaid fenced block in an authorized Markdown source, persist exact source bytes, identify diagram family, generate a typed, deterministic, validated structural representation and bounded searchable summaries, and link every derived relation to original line/character spans. The original Markdown document and its non-Mermaid text must remain searchable. For invalid/unsupported diagrams, return an explicit unsupported/partial-structure state without executing or fabricating a graph.

## E. Scope

- Detect fenced Mermaid blocks using existing Markdown scanner before generic protected-span chunk splitting, with precise line and decoded-text span plus original byte asset mapping.
- Pin an offline syntax validator and a separate reviewed structural extractor for each family; initial required families: flowchart and sequenceDiagram, then classDiagram/erDiagram ONLY after their specific semantics pass gold tests.
- Define a shared graph envelope plus family-specific schemas preserving attributes, groups, chronological ordering, cardinality and edge labels where relevant.
- Register original source, deterministic parsed graph, readable retrieval projection and optional inert preview rendition as separate ContentRepresentations under CONTENT-001.
- Generate child chunks at logical graph/subgraph/message-group boundaries rather than splitting Mermaid source in half; link each child to parent diagram and exact evidence.
- Provide safe error and capability reporting, unit and end-to-end gold tests with source/version persistence.

## F. Non-Goals

No OCR, no VLM diagram interpretation of Mermaid, no browser-executed Markdown directives, no arbitrary scripting, no network calls, no new graph database, no direct import of user-selected JavaScript modules or CDN assets, no dependence on Mermaid rendering for semantic correctness, and no claim that unsupported diagram families are understood. Static preview rendering (if chosen later) must never become an authority for structure.

## G. Architecture / Boundaries

### G0. Explicit PARSE/CONTENT ownership contract — no duplicate parsing/persistence

- **Input detection owner:** existing Markdown [parsing.py](../apps/workbench/api/parsing.py) emits protected fenced elements with exact line/source spans. This task consumes those elements. It MUST NOT build a second Markdown scanner/registry that duplicates `PARSE-001`.
- **This task's unique role:** parse/validate Mermaid syntax and typed diagram-family relations from the existing `mermaid` fenced source (flowchart/sequence first). Preserve exact original code via [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) and deterministic source-to-graph links; derived summaries become searchable via current chunking/ingestion.
- **Separate structured data:** [PARSE-004](check/TASK-RAG-PARSE-004-structured-data-and-devops-parsers.md) owns YAML/JSON record path and value fidelity. A YAML string containing `flowchart` is **not** implicitly Mermaid. An explicit future field-to-Mermaid adapter would need separate scope and tests.
- **Distinct visual graphs:** [CONTENT-003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) analyzes diagram *pixels* and yields model-inferred relations; Mermaid AST is deterministic_parse. Do not run VLM on Mermaid source or conflate their trust status.
- **Evidence endpoint:** [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) owns authorized retrieval of original source and stable citations; not this parser adapter.

[x] parsing and domain schemas, [x] app-level per-family adapter registry, [x] current chunking/ingestion, [x] CONTENT-001 asset/representation port, [x] existing PostgreSQL, [x] security/observability, [x] eval/docs; [ ] agent runtime. Data flow:

    Verified Markdown -> ParsedElement.PROTECTED_RAW (fence mermaid)
      -> Mermaid syntax family check (offline/versioned)
      -> allowlisted family-specific AST adapter
      -> typed graph with exact source spans and relation ordering
      -> deterministic retrieval projection and parent/subgraph chunks
      -> existing job-coupled publication + CONTENT-001 representations
      -> existing PostgreSQL lexical search + future Evidence Resolver

Provider/tooling differences live in adapters; application policy acts on typed, parser-independent graph contracts. Imported Markdown cannot run JS, change workspace, execute calls or force an unapproved parser.

## H. Contracts / Interfaces / Data Model

**MermaidSource**: workspace/source/version/element IDs, exact original source asset_id+SHA256, decoded source range and original byte mapping (distinguish UTF-8 bytes from Python codepoint offsets), Markdown fence start/end line, fence language, diagram_type?, syntax status and parser revision. If source normalization is necessary, retain exact bytes separately, and include normalization policy in fingerprint.

**TypedDiagram**: diagram_id, family (flowchart, sequence, class, er, unsupported), schema_revision, source_element_id, parser_id/revision, provenance_kind deterministic_parse, nodes/edges/groups/annotations depending on family, bounded original position references, warning codes. Every node/edge must map to source token/span or be explicitly derived; unknown linkage stays null.

Flowchart: node IDs/labels/shapes, directed/undirected edges, edge label/condition, subgraph membership and direction. Sequence: participants, lifelines, messages with exact order, arrow type, activations/notes, branches/loops and chronology; do not reduce to an unordered graph. Class: classes/attributes/methods, inheritance/aggregation/composition and relation direction; ER: entity names, cardinality/optionality and relationship labels. Each family adapter has a **separate** validated schema and capability flag. No generic node-edge projection may erase ordering or cardinality.

**ContentRepresentations**: exact Mermaid source (original); validated deterministic structured graph (never model_inferred); retrieval_text summary derived from its supported facts with a stable summary generator revision; optional display_image (rendered, DERIVED, never original evidence). Subgraph children link parent element, source/version and exact range. All output respects existing Chunk.character and qualified token limits. Split edges/message groups only with enough reference context to preserve named endpoints.

**Failure semantics**: MERMAID_INVALID_SYNTAX, MERMAID_UNSUPPORTED_TYPE, MERMAID_UNSUPPORTED_CONSTRUCT, MERMAID_RESOURCE_LIMIT, MERMAID_UNSAFE_DIRECTIVE, MERMAID_AMBIGUOUS_REFERENCE. Preserve exact original source and an explicit failure/warning state; no graph summary on semantic-parse failure. Old Markdown indexing remains available if policy allows indexing a raw protected block as DATA with a clear warning. UI must not show a structured graph as successfully extracted for rejected code.

## I. Repository Files / Components Impacted

CREATE app-owned mermaid_models.py, mermaid_ingestion.py, mermaid_adapters.py (family registry) and tests/test_mermaid_parsing.py plus tests/test_mermaid_ingestion.py; if using Node/JS parser, isolate a pinned offline worker with bounded stdin/stdout and no network or dynamic module resolution, rather than a browser parser used as backend truth. MODIFY minimally parsing.py to annotate mermaid fences without altering generic Markdown blocks, parser_registry.py for qualified element kind/capabilities, chunking.py and chunking_profiles.py for protected diagram context/profiles, ingestion.py to compose the approved adapter, and the CONTENT-001 representation mapping. Update operator lockfile only for reviewed parser dependencies. Update docs-website/docs/architecture/content-aware-chunking-strategy.md and API README. MUST NOT modify haystack/ upstream, current lexical scoring, applied migrations 0001/0002, unrelated upload policies, validator semantics or Preview fixtures. Representation schema changes belong to CONTENT-001; stop and revise this task if additional SQL is required.

## J. Implementation Requirements

### J1 — source identification and safety
Use the existing Markdown scanner, not a second regular-expression parser over entire input. Test triple/quadruple backticks, tilde fences, indentation, nesting/quotes, unclosed fences, case/whitespace of language info and Unicode codepoint-to-byte mapping. Identify Mermaid only when language tag qualifies; a code block containing the word "mermaid" is not enough. Cap individual code block bytes, token count, number of diagrams per document and total parser work. Preserve original source bytes/hashes even for malformed code.

### J2 — qualify grammar and structural adapters
Pin parser version and its license. Verify exactly which family-specific AST APIs are stable; Mermaid parse may validate syntax only. If necessary use a bounded reviewed grammar/token extractor, not regex guesses for arbitrary syntax. Implement allowlist: at minimum flowchart and sequence. Add class/ER adapters only with coverage tests; advertise other types as unsupported rather than faking node edges. Block directives, click/link callbacks, HTML/script-like constructs, external resources and arbitrary configuration overrides from source content. Do not invoke a browser SVG renderer as your parser.

### J3 — faithful relation/ordering projection
Preserve source token spans and exact labels, subgraphs, conditional edge labels and arrow direction; for sequence ensure message order and branching semantics. Normalize identifiers deterministically, detect ambiguous/reused IDs and validate all references. Classes/ER require separate exact relation/cardinality validation. Summary generation must be deterministic from validated structure, not an LLM paraphrase that changes YES to NO. Unknown semantics are represented as unsupported and do not become an asserted relation.

### J4 — chunks, source links and idempotence
Register exact original Mermaid asset and typed graph representation under one source_version/element. Build indexable description child chunks, one per coherent graph fragment or message group, with parent diagram and source evidence IDs; do not split original code at arbitrary 500 token boundaries. Include processing parser/summary revision in existing chunking fingerprint so a grammar upgrade triggers appropriate reindexing. Publish through the existing UploadReservation/SourceVersion transaction; keep the old active version on parser error or conflicting idempotency key.

### J5 — safe read/preview and capability disclosure
Expose raw source/typed structure/evidence only through CONTENT-001 secured read seam. If rendering is later included, require inert static SVG sanitized with strict or sandbox security; disable Mermaid click/href/network and never accept source-defined initialization directives that relax policy. Use distinct flags for syntax_validated, structure_extracted and preview_renderable. A missing parser means original source remains safely accessible but no fake structured graph.

### J6 — evaluation and test matrix
Build ≥32 non-sensitive Mermaid gold fixtures: at least 8 flowcharts with branching labels, 8 sequences with message ordering and alt/loop, 8 class and 8 ER fixtures (class/ER may be explicitly unsupported until qualified; count as negative, not parser success). Include malformed, nested, unknown construct, unclosed fence and malicious directive cases. Test 25+ labeled source-to-relationship questions for supported families. Exact metrics: node/edge/condition coverage, message-order agreement, cardinality/relationship correctness where supported, false asserted relation rate, relation/evidence attribution, source-byte integrity, indexed chunk recall. Test restart, idempotent reupload and safe Mermaid failure while retaining other Markdown paragraphs.

## K. Security / Governance / Observability

Mermaid content is untrusted executable-looking text. Never execute user-provided JS or render with permissive HTML/click directives. Require pinned offline grammar in bounded process/module and no external content fetch, import or eval. Source content cannot select a parser version or mutate operator config. Workspace scope and RLS apply to raw source, graph, captions and searchable children. Avoid storing raw source/body in traces or browser logs; use trace ID, source/diagram ID, diagram family, parser revision, validation error code, node/edge count and elapsed time. Preserve byte-accurate source evidence for legal/audit; escaping and sanitization do not replace source truth. No credentials in parser environment.

## L. Testing / Evaluation / Runtime Verification

Run Hatch workbench-api:check/test/types and targeted new tests. Use the current app's safe UTF-8 and Markdown regression fixtures plus 32 new deterministic Mermaid samples. Mock structural worker must return typed candidate data for unit tests; **real grammar adapter tests are mandatory** before claiming family support. Negative tests: invalid syntax, unsupported family, ambiguous edges, changed annotation, malicious HTML/click, external href, infinite/nested code, parser timeout, too-large block, Unicode offsets, crossed Markdown headings, foreign workspace, blob hash mismatch and duplicate upload. Integration on disposable PostgreSQL: upload Markdown with one prose paragraph and Mermaid, search both, follow evidence to original diagram source, compare relation type/direction; restart with no reseed. Record actual test output, supported construct list and known failures.

## M. Acceptance Criteria

- [ ] Exact source for every Mermaid block is preserved byte-for-byte and linked to source version/Markdown line range.
- [ ] Flowchart and sequence grammar adapters pass approved gold cases with exact directed relationships and preserved message ordering; unsupported families visibly fail closed.
- [ ] Existing Markdown paragraphs and non-Mermaid fences retain their current indexing behavior.
- [ ] A conditional edge (Yes vs No) cannot be reversed or fabricated without failing gold relation tests.
- [ ] Large diagrams produce bounded parent-linked child searchable representations, not severed Mermaid source code.
- [ ] Every structured relation resolves to an original source span; derived SVG or summary is never labeled original.
- [ ] Untrusted directives, URLs/scripts/HTML and resource overflow fail safely and cannot execute or fetch remote content.
- [ ] 32 fixtures, 25+ supported relation questions, per-family counts, precision/false-assertion metrics and failure cases are recorded.
- [ ] Existing PostgreSQL active-version, tenant, retry, Markdown and lexical regressions remain green.
- [ ] Capabilities and operator docs distinguish validated syntax, supported structure and unsupported types.

## N. Documentation / Migration / Compatibility / Rollback

Use CONTENT-001 representation storage and the current Chunk model; no new graph DB. Historic Markdown content lacks structured representation until explicitly reprocessed with a new immutable parser/processing fingerprint. Keep raw source available and defer reindexing of existing tenant content to a separate approved job. Roll out flowchart/sequence after tests, then class/ER only per capability gate; do not flip broad Mermaid=true prematurely. Roll back structural adapter by disabling semantic projections while preserving original Markdown bytes, existing text indexing and previous versions. Document exact grammar version/construct support and safe rendering restrictions.

## O. Mandatory Completion Checklist

- [ ] Current Markdown parser and chunking source re-inspected; exact source offsets and bytes verified.
- [ ] Pinned offline grammar, per-family schema, bounded worker and no arbitrary executable path.
- [ ] Original Mermaid source, typed structure and retrieval description stored as distinct provenance representations.
- [ ] Conditional edges and sequence order proven on real gold fixtures.
- [ ] Parent/child chunks and exact source evidence link verified in PostgreSQL.
- [ ] Unsupported diagram types and malicious directives fail closed.
- [ ] Cross-workspace, restart, rollback and idempotency checks pass.
- [ ] Existing Markdown/SQL/API regression tests pass unchanged.
- [ ] Source links and supported-family docs updated with real measurements.
- [ ] Mark COMPLETE only when all enabled-family gates have executed evidence.

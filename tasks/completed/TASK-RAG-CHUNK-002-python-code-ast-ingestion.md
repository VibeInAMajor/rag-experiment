# TASK-RAG-CHUNK-002 — Python syntax-aware chunking through the existing ingestion workflow

**Created:** 2026-11-21  
**Updated:** 2026-11-24  
**Status:** COMPLETE — real-source running-server, SQL, restart/replay, browser and regression gates passed  
**Priority:** P1 · specialized document class  
**Dependencies:** TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001; downstream UI behavior covered by TASK-UI-003 or a separately scoped extension  
**Original blueprint snapshot:** `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`  
**Target path:** `tasks/TASK-RAG-CHUNK-002-python-code-ast-ingestion.md`  
**Architecture decision:** [Content-aware chunking](../../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Add an allowlisted `.py` ingestion class that reuses Haystack's existing `PythonCodeSplitter` to preserve Python modules, classes, functions, methods, decorators, docstrings, imports and exact line provenance, with bounded overflow and existing PostgreSQL publication.

## B. Context / Problem

Plain prose chunking can cut a class in the middle of a method, detach a decorator or discard the signature needed to identify a symbol. Source-code retrieval should target coherent syntax units, not arbitrary fixed 500-word/500-token windows. The repository **already implements** an AST-based Python splitter; introducing Tree-sitter to parse Python again would duplicate functionality. Nevertheless, the current Workbench HTTP write API does not allow `.py` uploads, and the existing Python splitter's native sizing is by **effective lines**, not exact Qwen tokens. Both conditions require deliberate integration and tests.

## C. Repository audit

**Current checkout, inspected 2026-11-22:** the supplied blueprint predates durable ingestion. The actual service already has bounded multipart upload, durable jobs, atomic PostgreSQL publication, RLS, configured prose splitting and native admission. These existing owners were extended; no second uploader, writer, AST splitter or schema migration was introduced. The table below preserves the original discovery context; Section P records the implemented result.

| Source path / symbol | Current behavior / gap |
| --- | --- |
| [`haystack/components/preprocessors/python_code_splitter.py`](../../haystack/components/preprocessors/python_code_splitter.py) `PythonCodeSplitter` | Already uses Python `ast`; produces units for imports, classes, functions/methods and other statements, preserves line ranges, handles oversize units via line `DocumentSplitter`; can raise `SyntaxError`. Its constructor uses `min_effective_lines`, `max_effective_lines`, `expected_chars_per_line`, `oversized_factor`, `strip_docstrings`, `preserve_class_definition`, `secondary_split_overlap`/`_length`; no token-length contract. Metadata includes `start_line`, `end_line`, `unit_kinds`, `include_classes` and conditional decorator/qualified symbol fields. |
| [`haystack/components/preprocessors/document_splitter.py`](../../haystack/components/preprocessors/document_splitter.py) | Has line/word/token splitting. Token mode is generic tiktoken unless separately qualified; do not use for exact Qwen count by default. |
| [`apps/workbench/persistence/models.py`](../../apps/workbench/persistence/models.py) `Chunk`/`Source`/`SourceVersion` | Stable workspace/source/version/chunk IDs, content/metadata validation and exact chunk content limit exist. |
| [`apps/workbench/postgres/postgres.py`](../../apps/workbench/postgres/postgres.py) `_publish()` | Atomic version publication already exists; reuse its job-coupled variant delivered by TASK-RAG-002. |
| [`apps/workbench/api/application.py`](../../apps/workbench/api/application.py) / [`boundary.py`](../../apps/workbench/api/boundary.py) | Only current read-only routes inspected; planned TASK-RAG-002 adds bounded multipart upload and durable jobs for TXT/Markdown. Extend that handler, do not create a second upload path. |
| [`tasks/TASK-RAG-002-ingest-text-and-markdown.md`](TASK-RAG-002-ingest-text-and-markdown.md) | Initial explicit `.txt`/`.md` allowlist; `.py` remains unsupported until this task qualifies it. |
| [`apps/workbench/retrieval/lexical.py`](../../apps/workbench/retrieval/lexical.py) | `LexicalService` executes approved PostgreSQL `simple` FTS, score `postgres_ts_rank_cd`, over persisted active chunks. This is NOT semantic code search. |
| [`apps/workbench/web/src/views/DocumentsView.tsx`](../../apps/workbench/web/src/views/DocumentsView.tsx) | Demonstration model; future live UI must not invent an AST parse report or unsupported file class. |

**Original design gap:** Python was previously unqualified. The implementation and measured runtime result supersede that state; synthetic comparison and real-source server qualification are explicitly separate.

## D. Goal

A bounded UTF-8 Python source file is uploaded using the **same** authorized, durable ingest operation; AST-aware chunks are published to current PostgreSQL tables; each has truthful symbol/line metadata. Live lexical search finds distinctive method/identifier text from those stored chunks. A corrupt/invalid Python file fails explicitly without replacing the previously active version of that source.

## E. Scope

1. Extend trusted document classification, MIME/extension rules and ingestion capabilities for `.py` only.
2. Route verified Python to `python_ast` processing policy from TASK-RAG-CHUNK-001, retaining immutable profile revision and tokenizer-unit truth.
3. Use `PythonCodeSplitter` as primary splitter, not a new Python parser or `exec`/`eval`.
4. Preserve module/class/method/function boundaries and provenance; validate output with current persistence `Chunk` model.
5. Apply a safe hard-cap policy for giant definitions while recording overflow flags, counts and line ranges; do not silently lose declarations.
6. Publish via the existing job reservation/atomic version switch and test the same credential, workspace, retry and restart boundaries.
7. Add code-specific retrieval quality fixtures and source navigation metadata.

## F. Non-Goals

No JavaScript, TypeScript, Go, Java, Tree-sitter grammars, type inference, static execution, lint/fix of source, arbitrary code evaluation, source repository syncing, Git parsing, embeddings, code generation, graph-of-imports storage or GitHub repository access. These remain independent future capabilities. Do not promise code semantic retrieval with the PostgreSQL keyword profile.

## G. Architecture / Boundaries

- [x] Application ingestion: classify and route code, reuse existing job lifecycle.
- [x] Retrieval/RAG: use existing `PythonCodeSplitter`, existing lexical profile.
- [x] Port/contracts: process profile token-counter seam shared with TEXT, no Python-file-specific DB writer.
- [x] Persistence: current `Chunk.metadata` and atomic existing store only.
- [x] Security/governance: never execute uploaded source or import arbitrary modules.
- [x] Observability/evidence: source/line/symbol coverage, fallback telemetry, no source code in logs.
- [x] Infrastructure/test/docs: format-specific tests, app-only optional dependencies if required.
- [ ] Agent runtime: N/A — no agent execution.

Flow: verified multipart `.py` -> existing ingestion service -> chunking resolver -> `PythonCodeSplitter` -> bounded output verifier -> existing job-coupled `_publish()` -> PostgreSQL -> approved lexical route. Do not route code to an external provider purely from UI labels.

## H. Contracts / Interfaces / Data Model

- `verified_document_type=python_source` only after matching allowlisted suffix, content type and strict UTF-8 decoding. `.py` served as `text/x-python` / `text/plain` (specific allowlist to be validated against browser/OS), reject contradictory `application/pdf` and foreign file types.
- `strategy=python_ast`, immutable `processing_profile_revision`, `split_unit=effective_line` for primary AST grouping, optional `model_token` **only when qualified tokenizer checks actual final input**. Native `max_effective_lines` must not be called a 200-token limit.
- `Chunk.metadata` must preserve `start_line`, `end_line`, `unit_kinds`, `qualified_symbol?`, `class_name?`, `decorators?`, `source_file` safe basename, `parent_structural_id?`, `secondary_split`, `secondary_split_index/total` for oversize cases, plus existing source/version/processing fingerprint. Store only serializable, bounded values.
- API ingestion response/job schema from TASK-RAG-002 is reused verbatim; new document class is a capability extension, not a new `/code/upload` endpoint. If the v1 upload allowlist is intentionally expanded, update the documented request types/capabilities and tests before enabling.
- Missing line/page data must be omitted, not fabricated. Code uses **line range**, not a page number. `score_type` remains `postgres_ts_rank_cd`.
- Syntax error is a user-safe bounded code (`UNPARSEABLE_SOURCE` or the chosen existing app enum); details returned to UI may include safe line number but not raw code or interpreter traceback.

## I. Repository Files / Components Impacted

| Path | Expected change |
| --- | --- |
| `apps/workbench/chunking/chunking.py` | Extend allowlisted resolver with Python strategy and adapter to existing component; avoid duplicated token budget verifier. |
| `apps/workbench/ingestion/ingestion.py` (or actual module introduced by TASK-RAG-002) | Use shared upload/job path and materialized source version; no second writer. |
| `apps/workbench/contracts/schemas.py` | Extend validated media-type capability/document type enum only if required by the *actual* implemented API contract; additive backwards-compatible change. |
| `apps/workbench/api/boundary.py` | Extend exact allowlist for `.py` only; preserve size, path and security checks. |
| `apps/workbench/chunking/tests/test_chunking.py` | Add AST and fallback unit cases. |
| `apps/workbench/api/tests/test_ingestion_routes.py` or actual task-created equivalent | Add multipart `.py`, status, search and negative tests. |
| `apps/workbench/api/tests/fixtures/chunking/` | Small Python fixture files with decorators, methods, comments, imports and syntax errors. |
| `apps/workbench/api/README.md`; `docs-website/docs/architecture/content-aware-chunking-strategy.md` | Update real supported file classes and evidence. |
| `apps/workbench/web/src/views/DocumentsView.tsx` | Change only if necessary to display already-authoritative line/source metadata; prefer follow-up UI task. |

**MUST NOT change:** `haystack/components/preprocessors/python_code_splitter.py` or other upstream Haystack source for application-specific behavior, existing migration `0001`, existing PostgreSQL read rank semantics, the validator registry as an execution router, unrelated backend profiles, or frontend fixture Preview.

## J. Implementation Requirements — ordered executable blueprint

### J1. Verify and characterize the existing splitter

1. Read the actual `PythonCodeSplitter` constructor and `run()` against the current project snapshot. List supported AST node types, class/method merge rules, overflow behavior and whether syntax errors are propagated.
2. Build a small Python source fixture containing imports, module docstring, decorated sync/async methods, nested classes, duplicated method names in separate classes, comments and blank lines.
3. Run the existing component *without executing the source*. Save its chunks/metadata as inspectable goldens; test repeated invocation stability. Measure effective lines versus the separate model token count on the same fixture when available.
4. Document cases the existing parser cannot guarantee, especially oversized functions and dynamically generated definitions.

**Gate:** proven behavior in local unit tests; no invented AST capabilities, no Tree-sitter installation for Python.

### J2. Register and validate the new document policy

1. Add `python_source` to the allowlisted server-side content verifier; extension and MIME are hints, content UTF-8 plus AST parse establish validity. Do not use a class chosen by input filename string as an import target.
2. Add `python_ast` policy to the existing resolver, with semantic `effective_line` units and a strict fallback for `SyntaxError`. No silent fallback to prose on malformed Python unless explicitly approved and labelled as `unsafe_syntax_fallback` (default: reject).
3. Use `strip_docstrings=False` initially so docstrings remain retrievable as code text. `preserve_class_definition=True` unless measured evidence proves different output is safer.
4. Enforce the same 1 MiB upload/transport limit chosen by TASK-RAG-002 and the current 32,768-character chunk DB limit; if large source outputs violate the limits, respond with typed size errors and leave old active version unchanged.

**Gate:** valid `.py` selects AST, invalid `.py` rejects with truthful code, `.txt` containing Python-like text stays plain unless explicitly classified as code by trusted content policy.

### J3. Preserve semantics and bounded oversize handling

1. Keep whole functions/methods where possible; use existing secondary line split on oversized functions. Retain `qualified_symbol` and `start_line/end_line` across secondary parts; do not claim original AST units remain intact when a function is split.
2. Do not apply 50-token overlap indiscriminately across unrelated symbols. Primary AST chunks should have no cross-symbol overlap. Secondary oversized splits may use bounded line overlap with `secondary_split=True`.
3. Attach necessary class/module signature context as **metadata** or verified source excerpts, never as a claim that the original body contains text that was not present. Count any contextual prefix if it becomes embedding input.
4. Explicitly test code containing long string literals and non-Latin identifiers; ensure size checks are in actual declared units, not guessed word-to-token ratios.
5. Chunk identifiers must distinguish duplicate method bodies and distinguish class/line occurrence. Changing only one method should leave other chunk content hashes stable under compatible profiles for future delta-vector reuse.

**Gate:** no silently truncated methods, decorators or comments; oversized behavior fully annotated and bounded.

### J4. Wire the approved ingestion and persistence path

1. Extend the TASK-RAG-002 media-type allowlist and parsing dispatch without copying multipart handlers, jobs or idempotency reservation.
2. Persist prepared code chunks via existing `PersistencePort` / PostgreSQL writer and transactional publication. Preserve an unchanged previous version after parser or persistence failure.
3. Return existing job and upload statuses with precise parsing/chunking stages; no fabricated `page`, no fake AST preview.
4. Verify `GET document`, `GET chunks`, and the existing `POST /search` return the same real `source_id`/`version_id`/`chunk_id` identities and appropriate type/line metadata.
5. If live Documents UI is modified, show line range and symbol from real metadata, not inferred from UI filename. Keep Preview data visibly separate.

**Gate:** one Python file creates an active PostgreSQL source; exact method name query returns its persisted code content with correct source and line provenance.

### J5. Negative, correctness and quality evaluation

1. Tests: syntax error, invalid Unicode/NUL, `.py` MIME mismatch, huge single-function overflow, too many AST units, line-range off-by-one, decorated function, async method, nested class, duplicate method names, truncated source bytes, malicious content string, nonexistent workspace, repeated identical upload, changed upload, concurrent updates, database outage and restart.
2. Index at least 10 small Python modules in test fixtures, with ≥20 hand-labelled symbol/identifier queries spanning methods, classes and import references.
3. Compare AST chunks versus a **separate** prose-control policy on the same files, same PostgreSQL lexical ranker, same top-k, reporting symbol hit@5, evidence precision, duplicated tokens, total chunks and indexing duration. No fabricated semantic-retrieval gain.
4. Assert that parser failures leave old active source version and search results intact, and that no raw source code is emitted to operational logs.
5. Add security regression that documents are stored as data only: no `exec`, `eval`, `compile`, module import by uploaded name, or command execution is reachable from upload input.

**Gate:** documented code-family retrieval comparison and all negative/rollback tests pass.

## K. Security / Governance / Observability

Treat all uploaded code as untrusted potentially secret-bearing **data**. Parsing with `ast.parse` is not permission to evaluate or import it; no dynamic language loading/requirements installation, subprocess execution, external VCS clone or filesystem traversal. Validation and persistence must remain workspace-scoped, use current application-role RLS and sanitize title/metadata. Source code, credentials, AST objects and traceback text are forbidden in logs. Emit only bounded error codes, token/line size histograms, strategy IDs, chunk counts, elapsed times and correlation IDs. Preserve source/version integrity and document retention policy of TASK-RAG-002; never auto-disclose private code in user-facing error messages.

## L. Testing / Evaluation / Runtime Verification

Use app-specific Hatch checks from project root:

```text
hatch --version
hatch run workbench-api:check
hatch run workbench-api:test
hatch run workbench-api:types
```

Container-backed tests must use explicitly configured **disposable** PostgreSQL test connections; otherwise report SKIPPED, not PASS. Add focused tests for `PythonCodeSplitter` actual behavior and API upload/read/search using `httpx.AsyncClient` + lifespan (patterns already in `apps/workbench/api/tests/test_lexical_routes.py`). Run existing lexical/validator/frontend regressions when touching shared code. Capture parser error, no-data-leak, unchanged-reindex and code-quality benchmark evidence under `tasks/evidence/` only with non-sensitive fixture content and a documented reference.

## M. Acceptance Criteria

- [x] Valid Python uploaded through the existing authorized API produces only `python_ast` chunks, never a new in-memory Live corpus.
- [x] Existing `PythonCodeSplitter` reused without a duplicate Python AST implementation or upstream library modification.
- [x] Class/function/method symbols and verified start/end line ranges survive in stored chunk metadata; no invented PDF page numbers.
- [x] Identical source/profile publishes deterministically (or is classified unchanged) with zero unintended duplicate source versions.
- [x] Oversized functions use explicit bounded secondary behavior and metadata; no chunk breaches `Chunk.content` and corpus size constraints.
- [x] Syntax errors, size violations, MIME mismatch and database failures never replace the prior active version and return sanitized errors.
- [x] Exact identifier lexical retrieval returns the actual persisted code chunk and raw truthful `postgres_ts_rank_cd` score.
- [x] 10+ code files, 20+ labelled code queries and adversarial/negative cases produce a report comparing AST policy with prose baseline.
- [x] No uploaded code is executed, imported or transmitted to an unapproved service; logs include no source text or secrets.
- [x] Backward-compatible TXT/Markdown upload and existing lexical API/browser smoke remain green.

## N. Documentation / Migration / Compatibility / Rollback

- File type extension is additive. Existing `.txt`/`.md` processing profiles and `SearchResponse` semantics remain unchanged.
- Database migration: **N/A — current chunk JSON metadata supports code provenance**. If a typed indexed symbol table later becomes necessary, stop and define a separate migration task; never rewrite `0001`.
- Update API contract/README, architecture strategy matrix and task-local examples to show `.py` only after runtime qualification. Do not display it as supported while handler still rejects it.
- Roll back by disabling the `.py` approved ingestion policy and retaining already published content according to existing retention/authorization rules. No automatic deletion or DB volume reset; older versions remain auditable.
- Deferred Tree-sitter languages, semantic code embeddings, repository connectors, code-specific ranker and code execution belong to separate measured tasks.

## O. Mandatory Completion Checklist

- [x] Re-inspected current code and confirmed `PythonCodeSplitter` signatures/behavior.
- [x] Allowed `.py` only through shared bounded upload/authorization/job path.
- [x] AST policy implemented with proven provenance, overflow and unit correctness.
- [x] All scope, parsing, failure, rollback and code-execution safety tests pass.
- [x] Existing PostgreSQL store/active version/read score contracts reused, no duplicates.
- [x] Performance and symbol retrieval evaluation recorded with verified test inputs.
- [x] Docs/contracts/feature advertisements match what runtime actually supports.
- [x] All CI/quality commands actually executed or explicit blocked reasons recorded.
- [x] Acceptance criteria checked against measurable evidence with no unsupported PASS.
- [x] Completion report includes changed files, reused components, known limitations and rollback path.

**Completed on 2026-11-22 after the measured gates below passed.**

## P. Executed implementation and qualification

### Implemented ownership and reuse

- `parser_registry.py` adds only the qualified Python class and reviewed `.py` MIME aliases; strict bytes/name/transport limits remain shared. `parsing.py` retains the exact module as one typed source element and checks bounded syntax/declaration annotations. `python_code.py` uses standard AST only for validation/annotations and delegates chunk boundaries to the existing public `PythonCodeSplitter`.
- `chunking_profiles.py` supplies fixed `python-ast-r1` in effective-line units. `chunking.py` selects it through the existing resolver, reuses common `PreparedChunk`, model admission, deterministic occurrence IDs and persistence validation, and projects bounded code metadata. Native tokenizer counting is independent of both effective lines and tiktoken.
- `ingestion.py` and `ingestion_http.py` reuse the existing durable job, update guard, idempotency, scoped publication and GET chunks contracts. The Python ingestion revision is `python-ast-ingestion-v1`; prose policies remain unchanged. No upload input chooses a parser import, path, provider or execution target.
- Existing `PostgresPersistence`, job-coupled publication, RLS and raw `postgres_ts_rank_cd` remain the only storage/ranking path. No migrations or upstream Haystack files changed. Search response shapes remain unchanged; source/version/chunk IDs correlate to authoritative GET chunks metadata.
- Tests include a checked-in splitter characterization golden, exact CR/LF/CRLF source slices, decorated sync/async and nested declarations, repeated names, inert side-effect expressions, long-line/AST limits, safe failures, concurrency, unchanged updates, replay, application recreation and the real persistence failure contour. New fixtures contain only EN/RU/UK comments/strings.

### Real-source qualification on the running server — required user gate

This gate used the actual project file `apps/workbench/ingestion/ingestion.py`, not generated fixture text or an ASGI client. The running loopback API was updated through the existing launcher; the existing PostgreSQL volume was preserved. `scripts/workbench_python_probe.py` uses TCP HTTP on port 8011 and application-role repeatable-read SQL. It records hashes and IDs without retaining the uploaded source body in reports.

- Actual source: **27,168 bytes**, SHA256 `41bf6e6c709a0e5f9dd0874fadcad29bce6d475571f2e67bc54ddde069ab2732`.
- Uploaded source ID: `6619037462294ef08b6f001bcd5e3adf`; version ID: `efb8fc4007fa47b784bbafb6e7cb115c`. The live configured policy persisted **11 AST chunks / 28 declaration symbols**. Every chunk matched the real original line slice; independent local Qwen recounts matched every server count/revision. This is tokenizer admission, without model inference.
- [Live upload](../evidence/python-ast-2026-11-22/live-upload.json) confirms a deliberately syntax-corrupted update of the same real source returned `UNPARSEABLE_SOURCE` without changing the active chunks/search results. All preexisting sources, versions, chunks and jobs were preserved. The only new retained data is this source/version/11 chunks and its qualification jobs; corpus counts changed from **12 sources / 22 chunks** to **13 / 33**.
- After an actual API process stop/start, [restart evidence](../evidence/python-ast-2026-11-22/live-after-restart.json) confirms unchanged source/version/chunk identities, exact content/lines, Qwen counts, search scores and terminal same-key replay. [HTTP/file/SQL parity](../evidence/python-ast-2026-11-22/live-sql-parity.json) explicitly compares all chunk identities and content hashes with persisted SQL rows. [Final corpus audit](../evidence/python-ast-2026-11-22/final-corpus-audit.json) confirms later tests did not alter this state.
- The existing side browser performed a real Keyword search for `IngestionService`: **Live / Completed**, `ingestion.py`, the same source/version/chunk IDs and raw score **0.10000000149011612**. [Browser evidence](../evidence/python-ast-2026-11-22/live-browser.json), [visible result](../evidence/python-ast-2026-11-22/live-browser.jpg). The page was left open. The existing result UI truthfully says Page unavailable; inline code line/symbol UI remains separate.
- [Operational log check](../evidence/python-ast-2026-11-22/operational-log-check.json) found no sampled real-source body markers in the API logs; source/secret exclusion also has automated regression coverage.

### Separate synthetic regression comparison

The ten committed code modules and **32 hand-labelled queries** (20 methods, 10 classes, 2 import references) are test inputs only. They are not used as proof that the live server processed real source. Each policy used its own disposable PostgreSQL database with identical source bytes, the same lexical ranker and actual top-k **5**, through real ASGI HTTP. [Input/hash audit](../evidence/python-ast-2026-11-22/evaluation-audit.json), [labels](../../apps/workbench/chunking/tests/fixtures/python/queries.json).

| Measured policy | Symbol hit@5 | Chunks | Actual overlap tokens | Evidence precision | Sequential upload + chunk-read time |
| --- | --- | --- | --- | --- | --- |
| Python AST | 32/32 | 20 | 0 | 0.941176 | 1251.92 ms |
| Prose control, 500/50 tiktoken | 32/32 | 40 | 1500 | 0.260870 | 1482.19 ms |

Reports: [AST](../evidence/python-ast-2026-11-22/code-quality-python_ast.json), [prose](../evidence/python-ast-2026-11-22/code-quality-prose_control.json), [benchmark test result](../evidence/python-ast-2026-11-22/code-family.xml). Evidence precision here is the explicitly defined share of returned labelled-source chunks containing both the queried identifier and its hand-labelled context marker. It measures fixture context completeness, not general semantic quality. Timing is one local sequential run including chunk reads, not an SLA or a throughput claim. AST did not improve exact-identifier hit@5 on this corpus; both policies found every labelled symbol.

### Checks actually run

- `hatch --version`: 1.18.2.
- `hatch run workbench-api:check`: Ruff and format passed; `hatch run workbench-api:types`: **82 files**, passed. Probe Ruff/mypy and the edited validator registry checks passed.
- `hatch run workbench-api:python -m pytest -q -o addopts='' -o log_cli=false apps/workbench/api/tests apps/workbench/validator/tests`: **925 passed, zero skips**, 93.35 seconds. Explicit disposable application/admin test connections and pinned native tokenizer assets were configured. [Final JUnit](../evidence/python-ast-2026-11-22/backend-verified.xml), [log](../evidence/python-ast-2026-11-22/backend-verified.log). API tests comprise 892 cases and validator tests 33.
- After extending query families from 20 method cases to 32 method/class/import cases, the two affected disposable-database benchmark cases were rerun and passed; Ruff/mypy remained green. Production-code changes after the full run were limited to docstrings; final Ruff/mypy passed again. The earlier combined `backend-final.*` artifacts capture the discovered validator catalog failure before its repair and are not the final result.
- Workbench `npm run typecheck`, `npm run format:check`, `npm test -- --run` (**270 tests / 13 files**) and `npm run build` passed; logs are under the same evidence directory. The real browser search above also passed.
- Release-note YAML was checked and affected file diffs inspected. Full upstream Haystack tests and the documentation-site build were not run; neither upstream splitter code nor the frontend implementation changed. No remote deployment or production throughput guarantee is claimed.

### Bugs found, decisions and limits

1. Upstream class-signature prefixes do not describe contiguous original slices; native line starts omit leading comments; native secondary ranges describe the whole unit and its warning logs source symbol names. The application avoids these measured behaviors without modifying upstream code: exact source bodies, class context in metadata, public line splitter fallback and verified per-piece ranges. The native overflow branch is disabled within the upload byte bound.
2. The first storage test exposed tuple-valued decorator metadata, which the existing strict JSON record rejected. Projection now emits JSON lists and real PostgreSQL tests verify it.
3. The validator catalog was missing the existing frontend `keyword-search` kind. Required regression tests exposed it; an explicit **unsupported constructor validation** descriptor restores catalog parity. It does not route ingestion or enable keyword execution in the validator. All 33 validator tests passed afterward.
4. Nested classes remain the native splitter's units; generated/dynamic definitions have no inferred symbol coverage. Greedy primary grouping can couple neighboring units; content-hash reuse requires unchanged actual chunk text. Secondary chunks may be partial syntax, with explicit flags. Single lines or bounded metadata that cannot fit are rejected, preserving the previous version. Deadlines are cooperative, not subprocess isolation.
5. The implementation adds only `.py` and its safe error/provenance vocabulary. Existing TXT/Markdown policy/replay semantics, PostgreSQL schemas and lexical scores are preserved. The Documents upload/code-line UI is deferred as specified; GET chunks already exposes authoritative provenance.
6. Rollback disables Python qualification in a compatible API release and restarts the process. It preserves already published versions and requires no migration, destructive downgrade, volume reset or automatic deletion. Existing working-tree changes from prior tasks were retained.

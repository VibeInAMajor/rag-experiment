# TASK-RAG-PARSE-004 — JSON/JSONL/YAML/TOML/XML and DevOps configuration ingestion

**Created:** 2026-11-21  
**Updated:** 2026-11-24  
**Status:** PROPOSED — blueprint; no parser activation yet  
**Priority:** P1/P2 — structured data and developer documentation  
**Dependencies:** TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001; Python AST is independent TASK-RAG-CHUNK-002  
**Repository snapshot reviewed:** `522c2cb38aff746e65a8f04ea48d88d3695fc5a9`  
**Target:** `tasks/TASK-RAG-PARSE-004-structured-data-and-devops-parsers.md  
**Architecture:** [Content-aware format/strategy matrix](../docs-website/docs/architecture/content-aware-chunking-strategy.md)

## A. Title

Implement safe, structure-preserving parsing for common configuration and record formats **without evaluating their contents**, and integrate it with the same versioned ingestion and PostgreSQL search path. First scope `.json`, `.jsonl`, `.ndjson`, `.yaml`, `.yml`; TOML/INI/XML/PowerShell/SQL/HCL are separately qualified follow-ups, not automatically enabled.

## B. Context / Problem

RAG over Kubernetes manifests, CI YAML, JSON APIs and service configuration fails when a generic prose splitter detaches a key from its parent object or groups unrelated records. Syntax is source evidence, and for DevOps data exact paths, resource kinds, and field names are crucial. The user also requested popular formats beyond office files; use one trusted parser registry and element contract while keeping arbitrary configuration evaluation strictly forbidden.

## C. Current Repository State

**Source audit refreshed 2026-11-23:** [PARSE-001](completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) and [RAG-002](completed/TASK-RAG-002-ingest-text-and-markdown.md) are complete. [parser_registry.py](../apps/workbench/parsing/parser_registry.py) catalogs JSON/YAML candidates but does **not** expose qualified JSON/JSONL/YAML ingestion. [ingestion.py](../apps/workbench/ingestion/ingestion.py) and [ingestion_http.py](../apps/workbench/api/ingestion_http.py) already implement the shared durable upload; no second REST handler or SQL writer is needed. Current [chunking.py](../apps/workbench/chunking/chunking.py) is available for structural policy reuse.

| Source / symbol | Existing capability | Risk/gap |
| --- | --- | --- |
| [`haystack/components/converters/json.py`](../../haystack/components/converters/json.py) `JSONConverter` | Existing JSON converter with configured content key. | Does not by itself prove recursive object path/index/record provenance. |
| [`haystack/components/converters/multi_file_converter.py`](../../haystack/components/converters/multi_file_converter.py) `MultiFileConverter` | JSON handled among text/Office formats. | Reuse when appropriate but don't flatten nested records into undocumented text. |
| [`haystack/components/preprocessors/recursive_splitter.py`](../../haystack/components/preprocessors/recursive_splitter.py) | Bounded general text splitter. | Use only as a secondary splitter inside one protected record/object. |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) | Source/version/chunk fields and JSON metadata in PostgreSQL. | Metadata values bounded and JSON-safe; no provider/client object or giant nested payload. |
| [`apps/workbench/postgres/postgres.py`](../apps/workbench/postgres/postgres.py) | Atomic publication under `WorkspaceContext`; PostgreSQL FTS. | Reuse same persistence; do not store secrets verbatim in logs. |
| [`tasks/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md`](completed/TASK-RAG-PARSE-001-format-detection-and-parser-registry.md) | Typed `ParsedElement` and qualified format registry blueprint. | Extend its descriptors rather than adding another MIME manager. |
| [`haystack/components/preprocessors/python_code_splitter.py`](../../haystack/components/preprocessors/python_code_splitter.py) | Python AST-aware splitter exists. | Not a YAML/JSON/PowerShell parser; no source execution. |

**Missing:** app-owned safe JSON object/JSON Lines/YAML structure adapters; no declared support in public Workbench API.

## D. Goal

For each enabled structured format, parse exactly the selected schema/records with bounded depth/size, preserve object paths and line/record identity, generate versioned stable chunks with section/key context, and retrieve specific keys/values through current PostgreSQL FTS. Invalid syntax, dangerous tags, duplicate keys or source secrets must not cause silent coercion, external resource access or partial publication.

## E. Scope

- `.json`: safe standard parser with strict key/duplicate behavior, bounded nesting, top-level object/array and configurable approved content paths. `JSON Pointer` metadata for every object/record.
- `.jsonl`, `.ndjson`: line-by-line bounded record parsing, accurate line numbers; malformed line fails the source (or an explicitly documented quarantine policy); no silent skip.
- `.yaml`, `.yml`: *safe* YAML loader, reject unapproved tags, excessive aliases, duplicate mapping keys (depending on explicitly tested loader semantics), multi-document Kubernetes resources and resource-identity metadata (`kind`, `apiVersion`, resource `metadata.name`, namespace as **document data**, not an authorization scope).
- Optional `.toml`, `.ini`, `.cfg`, `.properties` and `.xml` behind later per-format tests; XML must disable external entities and have a schema-specific path policy.
- Preserve key/value, object, array item, Kubernetes resource or record boundaries; model-token/word budget secondary split only within approved parents.
- Use existing TASK-RAG-002 job/atomic publication, server-verified file detection, no backend model or scripting engine.

## F. Non-Goals

No YAML `load` with arbitrary Python object creation, `eval`, PowerShell execution, Terraform plan/apply, SQL execution, code transpilation, live infrastructure access, auto-discovery of arbitrary schema definitions, semantic embeddings, XML external entities, connector credentials/secret interpolation or CRUD of underlying systems.

## G. Architecture / Boundaries

### PARSE/CONTENT ownership contract — non-duplication gate

- **Ownership:** PARSE-004 alone implements **safe syntax parsing** and source-path/record provenance for JSON/JSONL/YAML. It uses the existing [parser registry](../apps/workbench/parsing/parser_registry.py), [ParsedElement](../apps/workbench/parsing/parsing.py) and bounded [chunking](../apps/workbench/chunking/chunking.py). A YAML Kubernetes namespace is document data, never a tenant workspace.
- **CONTENT-001:** [CONTENT-001](../TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) owns persisted element/representation IDs and exact original evidence assets; PARSE-004 must not define a second universal `DocumentElement` database or `AssetStorePort`. The parser emits verified JSON pointer/YAML path spans; CONTENT maps them to long-lived source-version-linked elements once implemented.
- **Mermaid:** [CONTENT-004](../TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) is responsible for **Mermaid grammar** only after the existing Markdown fenced-block extraction. JSON/YAML structures that happen to contain strings such as `flowchart TD` remain strings unless a separately approved explicit Mermaid format/field adapter is designed. Do not add a competing Mermaid parser inside PARSE-004.
- **Visual / evidence:** [CONTENT-003](../TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md) is for model-inferred visual diagrams, not Kubernetes manifest topology guessing. [CONTENT-005](../TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) owns secure original source span retrieval and claim verification; PARSE-004 only produces accurate source offsets.

**Qualification modes:** Gate P = format-specific parser/structured chunk + existing PostgreSQL lexical publication (this task); Gate E = durable byte/evidence/representation resolution (CONTENT-001/005 or specialty CONTENT adapter). Gate P may pass while Gate E is NOT_IMPLEMENTED, but Gate P must not claim original evidence or multimodal completeness. No new global parser registry, ContentRepresentation storage or EvidenceResolver is permitted in this task.

`verified source → selected safe parser adapter → typed object/record elements with path/provenance → CHUNK-001 scoped grouping → existing Source/SourceVersion/Chunk + publish_source → PostgreSQL lexical search`. Parsing logic is library-independent at contract boundary, while concrete JSON/YAML/XML libs remain adapter-only. Server decides workspace; configuration source cannot grant authorization via a `namespace`, `workspace_id` or ACL key inside itself.

## H. Contracts / Interfaces / Data Model

`ParsedElement(kind="structured_record", record_id, path, ordinal, line_start?, line_end?, text, parent_path, schema_id?, code_language?, classification_flags[])` plus parser revision and source hash. JSON paths conform to reviewed escaping semantics, e.g. `/spec/template/spec/containers/0/image`. Kubernetes manifest key `metadata.namespace` is only cited text; no tenant routing. Preserve scalar types and repeated keys via explicit rejection, not silently reserialize to a different configuration. Secret values in source may require opt-in exclusion before indexing, with stable redacted placeholders and separately logged count only. `processing_fingerprint` includes formatter/parser revision and redaction policy; changed policy forces safe reindex.

## I. Repository Files / Components Impacted

- CREATE `apps/workbench/parsing/structured.py` or small equivalent in existing task-created `parsing.py`.
- EXTEND `apps/workbench/parsing/parser_registry.py`, `apps/workbench/chunking/chunking.py` and shared `ingestion.py` without duplicate routes/ORM models.
- EXTEND `apps/workbench/contracts/schemas.py` / `apps/workbench/api/openapi.json` and docs/capabilities for each **qualified** format only.
- CREATE `apps/workbench/parsing/tests/test_structured_parsers.py`; EXTEND `test_ingestion_routes.py` and query goldens.
- UPDATE `docs-website/docs/architecture/content-aware-chunking-strategy.md` and API README.
- Do NOT edit core Haystack, existing applied database migration, evaluation score type, or external cloud resources.

## J. Implementation Requirements

### J0. Reconcile completed app owners and format-specific handoffs

1. Confirm current [parser registry](../apps/workbench/parsing/parser_registry.py), [parsing.py](../apps/workbench/parsing/parsing.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [chunking.py](../apps/workbench/chunking/chunking.py), [PostgreSQL publication](../apps/workbench/postgres/postgres_ingestion.py) and [actual contracts](../apps/workbench/contracts/schemas.py). The old blueprint predates completed RAG-002 and PARSE-001; do not reimplement their components.
2. Build a format/element/asset/evidence matrix and mark all unsupported extractions `NOT_QUALIFIED`; record original evidence status separately from parsed text.
3. Align this task's format-specific `ParsedElement` projection with CONTENT-001's long-lived `DocumentElement` contract **without building it here**. Confirm all source/span/line/page/time units are explicitly defined before using them as citations.

### J6. Format boundary regression and CONTENT handoff

Test JSONL malformed row, JSON duplicate keys, YAML alias explosion/unsafe tag, secrets redaction and Kubernetes resources. Compare parsed source key paths with actual source codepoint/line offsets and verify a **separate** CONTENT source-element adapter could later store these spans without duplicate parser models. No Mermaid graph extraction or YAML code execution in this task.

### J1. Strict parser and schema evidence

Build fixture matrix of nested objects, arrays, Unicode keys, duplicated keys, YAML multi-doc, anchors/aliases, invalid YAML tags, JSONL malformed lines, hidden keys and configuration secrets. Choose safe parser versions and bound input size, depth, record count and parse duration. No dynamic Python classes/deserialization from input.

### J2. Stable structural elements

Project records with stable canonical paths and source offsets. For YAML multi-document, retain document ordinal and resource header, including kind/name. Represent comments as text only if parser captures them truthfully; never pretend to preserve absent comments. Redact explicitly classified secret fields when configured, with a versioned transform.

### J3. Bounded structural chunking

Prefer whole object/resource when within budget; subdivide oversized arrays by record and object children with path prefix. Never cut a YAML key/value or JSON string mid-sequence as a primary boundary. For a giant scalar, use a bounded secondary fallback with exact offset metadata and source path.

### J4. Shared ingestion and search

Use approved parser descriptor from PARSE-001 and the same job/atomic PostgreSQL writer. Add real lexical tests targeting a field/key/identifier with correct source path and no other workspace contamination. Ensure updates keep one active version and changed parser revision changes fingerprint.

### J5. Qualification/rollout

Enable `.json`, `.jsonl`, `.ndjson`, `.yaml`, `.yml` independently after 10 golden files and 10 query cases per family; then propose `.toml`, `.ini`, `.xml`, `.sql`, `.tf`, `.hcl`, `.ps1` as follow-up language/schema adapters, not a catch-all converter.

## K. Security / Governance / Observability

Treat configuration as untrusted **data**, not instructions: no remote YAML tags, XML entities, Jinja templating, PowerShell/module imports, shell commands, Terraform backends or SQL. Prevent secrets/credentials being included in traces and error pages. Source content may contain credentials; explicitly define redaction/exclusion policy and tests before indexing such material. Preserve server workspace identity, RLS and connector/source ACL. Audit only safe parser/profile IDs, counts, hashes, timings and error codes, no key-value snippets.

## L. Testing / Evaluation / Runtime Verification

JSON strict duplicate keys; escaped path segments; mixed arrays; invalid number/NaN; YAML anchors/billion-laughs; invalid custom tags; zero documents; multiple Kubernetes resources; JSONL line numbers; gigantic scalar; Unicode; secret-field redaction; wrong format/MIME; parser missing; DB rollback/restart; adversarial prompt-injection text in source; query and source provenance fidelity. Run all app-focused Hatch checks plus historical TXT/Markdown/lexical tests with proof for enabled formats.

## M. Acceptance Criteria

- [ ] Every enabled structured format produces verified path/record IDs and nonempty truthful typed elements; 0 silent generic-text fallbacks.
- [ ] 100% of golden path/line/resource references match source; 0 unauthorized parser object creation or external fetches.
- [ ] Malformed/duplicate/over-budget records produce a documented safe error without partial active-version changes.
- [ ] At least 10 representative files and 10 labeled queries per enabled family recorded with Recall/citation accuracy and cost.
- [ ] No unqualified TOML/XML/SQL/PowerShell/HCL family is advertised as supported.

- [ ] Reuses **completed** PARSE-001/RAG-002/chunking and current API; no duplicate format registry, HTTP upload handler, persistence adapter or version publication.
- [ ] Does **not** implement CONTENT-001 original asset storage/`DocumentElement` persistence or CONTENT-005 evidence resolution; the parser exports accurate source/element spans for later adapters.
- [ ] `JSON/JSONL/YAML` format-specific supported/unsupported visual/attachment/graph cases are labelled truthfully; no inferred OCR/VLM/Mermaid/ASR behavior advertised from parsing.

## N. Documentation / Migration / Compatibility / Rollback

Profile revisions encode schema and transform rules; arbitrary JSON metadata remains bounded and compatible with current `Chunk.metadata`. Add a separate migration if path-based indexes become a measured requirement, not before. Existing upload body/route/error semantics stay stable; rollback disables one descriptor while preserving indexed versions and volume. Enterprise connector ingestion is separate from file parsing.

## O. Mandatory Completion Checklist

- [ ] All new source paths and GitHub-relative links verified from the actual `tasks/` location.
- [ ] PARSE/CONTENT ownership boundaries exercised with fixture tests; no duplicate durable element/asset model.
- [ ] Existing SQL/API/upload/source-version test gates remain passing when new parser family is enabled.


- [ ] Existing converter and format classifier reused rather than duplicated.
- [ ] Safe parser, bounded resource policy and source path provenance implemented.
- [ ] Negative injection/duplicate-key/schema and secret-redaction tests pass.
- [ ] Real PostgreSQL HTTP/retrieval and restart evidence recorded.
- [ ] Capability states and docs truthful for each activated format.
- [ ] No unresolved A–O acceptance items before COMPLETE.

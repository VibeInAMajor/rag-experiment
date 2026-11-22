# TASK-RAG-CONTENT-001 — Structured elements, multiple representations, and immutable original evidence

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — architecture and storage blueprint; not implemented  
**Priority:** P0 — prerequisite for trustworthy multimodal ingestion  
**Dependencies:** completed TASK-RAG-PARSE-001, TASK-RAG-CHUNK-001, TASK-RAG-002, TASK-DB-001; coordinate with active TASK-RAG-CHUNK-003  
**Repository snapshot inspected:** 4dd81abd4b34794edfcafabb623703c67f40be81  
**Target:** tasks/TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md

## A. Title

Establish one provider-neutral, workspace-scoped document element and representation contract supporting original bytes/visual assets, structural relationships, derived descriptions, retrieval projections, and verifiable provenance. This is the foundation for OCR, PDF diagrams, Mermaid, and evidence resolution.

## B. Context / Problem

Current ingestion persists searchable text chunks, but does not preserve a general relation between a structural element, original evidence bytes, observed OCR/layout facts, model-generated descriptions and the chunks derived from them. A diagram cannot be reliably reconstructed from an LLM caption; a table excerpt cannot serve as the original source; an image filename is not an authorized evidence reference. Existing PDF work already projects text/heading/caption/table blocks, but its data model cannot represent full visual graphs and immutable original assets.

The required product model is: Document -> Structured Elements -> Multiple Representations -> Searchable Chunks + Original Evidence. One source element may have raw, OCR, structure, searchable description and image representations; these must remain distinguishable and all tie back to an immutable source version. Rendering and retrieval must not promote an inferred edge or generated claim into an observed fact.

## C. Current Repository State

| Actual source | Inspected current fact | Reuse / gap |
| --- | --- | --- |
| [parser_registry.py](../apps/workbench/api/parser_registry.py) | FormatId, ElementKind and ParserDescriptor have reviewed TXT/Markdown/Python parsers; PDF remains planned in the registry. ElementKind currently includes paragraph/heading/protected_raw/python_source. | Extend one approved vocabulary; do not create another format detector or pretend PDF upload is qualified. |
| [parsing.py](../apps/workbench/api/parsing.py) | Immutable InspectedSource, SourceSpan, ParsedElement, ParsedDocument and ProcessingClassification; Markdown fenced blocks become protected raw spans. | Build on source spans and parser provenance, not arbitrary SDK objects. |
| [persistence.py](../apps/workbench/api/persistence.py) | WorkspaceContext, Source, SourceVersion, Chunk, PersistencePort; Chunk has page and JSON metadata, optional embedding. | Keep existing content table and existing publication port; add source-element/asset/representation ownership. |
| [postgres.py](../apps/workbench/api/postgres.py) and [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) | Tenant-scoped records, active-version publication, durable ingestion jobs. | Extend publication via the same transaction owner; never dual-write an independent corpus. |
| [migrations/0001_initial.up.sql](../apps/workbench/api/migrations/0001_initial.up.sql), [0002_ingestion_jobs.up.sql](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) | Existing applied schema and job migration. | Introduce a NEW additive migration after 0002; never rewrite either applied revision or drop customer data. |
| [pdf_models.py](../apps/workbench/api/pdf_models.py) | PdfPage/PdfBox/PdfCell/PdfBlock(kind text, heading, caption, table) and bounded PdfDocument. | Adapt its actual pages/boxes/tables, without claiming diagram or OCR objects already exist. |
| [pdf_parser.py](../apps/workbench/api/pdf_parser.py), [pdf_worker.py](../apps/workbench/api/pdf_worker.py), [pdf_assets.py](../apps/workbench/api/pdf_assets.py) | Offline, quota-limited Docling subprocess, model asset manifest and text-layer-oriented PDF extraction in progress. | Keep worker isolation; augment only after format capabilities pass separate tests. |
| [ingestion.py](../apps/workbench/api/ingestion.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py), [chunking.py](../apps/workbench/api/chunking.py) | Existing bounded upload, jobs, chunking and scoped publishing. | Reuse; new representation projections feed this path, not a second upload backend. |
| [content-aware architecture](../docs-website/docs/architecture/content-aware-chunking-strategy.md) | Structural parsing and token-budgeted chunk policies; multiple representations and original binary evidence not yet a full persisted contract. | Add an explicit architecture section and cross-task links. |

Inspected repository contains no application-owned DocumentAsset/ContentRepresentation persistence schema, no authorized original asset retrieval API and no model-neutral evidence link registry. These are gaps, not observed production failures. This task MUST re-check the working tree before coding because active PDF work can progress independently.

## D. Goal

An application service can stage original source bytes or a verified derived crop, register immutable version-scoped elements, associate multiple typed representations with one element, project authorized text chunks, and retrieve the **exact** original asset through a scoped evidence reference. All links survive API/DB restart and publishing a newer source version; previous revisions remain immutable. No VLM/OCR inference is performed by this foundation.

## E. Scope

1. Define typed app-owned DocumentElement, ContentRepresentation, DocumentAsset and EvidenceReference models with strict IDs, kind/status/trust vocabulary and provenance.
2. Record parent-child and optional graph-element relationships. Do NOT assume that every representation is a graph; one PDF can have text, tables, diagrams and pictures on the same page.
3. Introduce one AssetStorePort with explicit local-development durable implementation and path/key constraints; future object-store implementations MUST satisfy the same contract. Original bytes and visual crops are bytes, not PostgreSQL giant text columns or base64 in Chunk.metadata.
4. Define PostgreSQL metadata, composite workspace/source/version foreign keys, active-version checks, immutability and row-level security through an additive migration named by the next available revision after 0002.
5. Attach existing searchable Chunk records to representation and element IDs through a small reviewed mapping or additive fields; maintain existing lexical query compatibility.
6. Define bounded artifact staging/publication/cleanup semantics across SQL and blob storage: no false claim of distributed atomicity.
7. Establish a deterministic low-cardinality error taxonomy, capability flags and contract tests; retain all current TXT/Markdown/Python behavior.

## F. Non-Goals

No OCR run, no VLM call, no Mermaid parser, no PDF parser replacement, no code execution, no new vector database, no arbitrary graph runtime, no object-storage cloud account requirement, no content deletion UI and no answer-generation feature in this task. Provider-neutral contract does not imply that multimodal retrieval works today.

## G. Architecture / Boundaries

Affected: [x] domain contracts, [x] application orchestration, [x] storage port, [x] PostgreSQL metadata, [x] retrieval provenance, [x] security, [x] observability, [x] local infrastructure and docs; [ ] agent runtime. Dependency direction: parser / OCR / VLM / Mermaid adapters -> app-owned Element/Representation contracts -> existing ingestion and persistence ports -> PostgreSQL plus an AssetStorePort implementation. Retrieval continues to use current Chunk and postgres-fts-baseline until independently qualified extensions exist.

Proposed ownership graph:

    SourceVersion
      -> DocumentElement (page, block, table, diagram, graph)
            -> ContentRepresentation (original, observed_text, graph, derived_description, retrieval_text)
            -> DocumentAsset (original PDF/image/crop or exact Mermaid source)
            -> ChunkEvidenceLink -> existing Chunk
      -> EvidenceReference (workspace/source/version/element/representation/asset/locator)

Only server-resolved WorkspaceContext grants any read or write. UI-supplied graph node/filename/path is never an asset or workspace authority.

## H. Contracts / Interfaces / Data Model

**DocumentElement**: element_id, workspace_id, source_id, version_id, parent_element_id?, kind (paragraph, heading, table, figure, diagram, chart, code, page, mermaid), sequence, origin type, source_span? (byte/codepoint/line with explicit unit), page_range?, bbox? (coordinate frame and page size required), verification_state (observed/unverified/reviewed), processing_revision and warnings[]. Unknown geometry is null, never page 1 by guess.

**ContentRepresentation**: representation_id, element_id and source/version scope, representation_kind (original_source, OCR_text, extracted_structure, structured_graph, deterministic_summary, model_description, retrieval_projection), encoding/content_type, inline bounded text OR asset_id, provenance_kind (direct_source, deterministic_parse, model_inferred, human_verified), processor_id/revision, input evidence hashes, structured schema version, confidence? (not a permission or an automatic truth signal), status (ready/unverified/failed). It MUST be possible to distinguish an OCR observation from a VLM inference in API and audit.

**DocumentAsset**: asset_id, workspace/source/version scope, content_sha256, media_type, byte_length, storage_ref (internal opaque, NEVER client-controlled path), derivation_parent_asset_id?, crop bbox/page?, storage_state (staged/committed/orphaned), retention_class, encryption metadata reference. Exact original PDF bytes or Mermaid code bytes retain their original hashes. Deduplication MUST respect tenant boundaries even for equal hashes.

**EvidenceReference**: evidence_id, element_id, representation_id?, asset_id?, workspace/source/version, optional page/box/line span, processing revision and integrity hash. Resolved evidence must match the same source/version as the retrieved chunk. A stale evidence ID must not redirect to a newer active version.

**Chunk evidence mapping**: existing chunk_id -> exact version-owned representation_id and element_id (many-to-one allowed); a retrieval projection may include derived context but MUST keep the original excerpt separate. Avoid duplicating long original bytes in metadata.

AssetStorePort: put_staged(content, scope, media_type) -> staged ref; read(scope, ref, bounded_range?) -> verified bytes; commit(ref) and discard(ref); integrity verify and scoped stat; no raw filesystem paths or pre-signed public links exposed to clients. The local adapter must use an operator-controlled storage root outside public web assets, path traversal protection, atomic rename/fsync where supported and crash recovery.

**Critical commit semantics:** SQL and asset store cannot form one atomic transaction. Stage + verify assets first, transactionally commit evidence records and active source-version linkage, then mark/repair storage state via idempotent recovery. Fail closed on uncommitted/missing assets; scheduled orphan cleanup ONLY after a safe grace interval and referential checks. Never return a successful citation for a missing blob.

## I. Repository Files / Components Impacted

CREATE app-owned content_models.py, asset_store.py, postgres_content.py (or narrowly extend existing persistence owner), tests/test_content_contracts.py, tests/test_content_assets.py, tests/test_content_migrations.py, and a new additive SQL/Alembic revision after 0002. MODIFY minimally persistence.py, postgres_ingestion.py, ingestion.py, ingestion_http.py, contracts.py, openapi.json where new evidence capabilities require them, and content-aware-chunking-strategy.md plus API README. REVIEW pdf_models.py/pdf_parser.py for adapter boundaries; do not modify them merely to satisfy this foundation.

MUST NOT modify haystack/ upstream, existing 0001/0002 migrations, current lexical ranking scores, Preview fixtures, or parser registry qualification gates in this task. If schema design requires a second document table or breaking SearchResponse, update task scope and approval first.

## J. Implementation Requirements

### J1 — inspect, draw schema and prove no duplication
Review all C paths and existing migration checksums. Inventory all current source/version/chunk ownership and PDF structure fields; document the extension points and incompatible assumptions. Add the four typed models as strict, frozen/validated data. Define element kind and representation trust-state enums; no SDK/Docling/Pydantic model from an external provider should leak into the domain port.

### J2 — create storage and consistency guarantees
Add additive migration with scoped composite keys and enforced RLS. Introduce assets/elements/representations/chunk-evidence tables only where relationships cannot safely be represented in bounded metadata; cite why each table is necessary. Make original assets immutable. Implement workspace-scoped read/write under existing transaction/connection lifecycle. No schema mutation on API startup; ensure old seed/SQL tests still pass.

### J3 — implement AssetStorePort and lifecycle
Implement a durable local adapter with one small non-sensitive blob. Test duplicate hashes across workspaces remain separately authorized, source hash mismatches fail, path symlinks/traversal are rejected, and a crash after staging or after SQL commit recovers without showing unavailable evidence as success. Add separate operator-configured retention and garbage collection with dry-run default; preserve original data unless cleanup is proven safe.

### J4 — integrate existing chunk publication
Accept prepared element/representation graph from an **approved adapter only**, bind to UploadReservation/SourceVersion and attach evidence references transactionally to published Chunk rows. No partial active version with orphaned link. Preserve existing idempotency fingerprints and source version on failed conversion or missing asset. Distinguish structure-only, metadata-only and searchable-text outputs.

### J5 — expose a minimal secured read seam
Implement provider-neutral evidence lookups behind API auth and RLS (no anonymous blob URL). Add a narrow capability only when asset lifecycle and scoped retrieval tests pass. Document 404 missing/foreign, 409 version mismatch/incomplete, 503 storage unavailable, and 422 contract violations using the existing safe ErrorResponse envelope and actual FastAPI convention. Do not invent evidence for old chunks lacking links.

### J6 — publish compatibility and handoffs
Update architecture diagram, JSON schema examples, migration/retention runbook and successor interfaces for OCR/VLM/Mermaid. Provide a fake parser producer for unit tests and no dependency on real GPU or PDF files. Run end-to-end proof with a synthetic source, two elements, multiple representations, linked chunk and exact original bytes after database/API restart.

## K. Security / Governance / Observability

Original files may contain secrets and personal data. Enforce workspace scope and app-role FORCE RLS on metadata, and equivalent access policy on bytes. Reject user-authored asset paths, SSRF URLs, HTML or executable representations; never log original files, OCR text, VLM descriptions, Mermaid payloads, credentials, encryption keys or vectors. Protect any later renderer with inert text defaults. Source text is untrusted evidence, not instructions. Bound byte count, decompression, asset count and API range reads. Operational logs: trace_id, workspace/source/version/element/asset opaque IDs, processor revision, safe error_code, duration/size, no payload. Explicit retention/encryption/backups and auditability of staged/orphaned assets. Treat confidence as a measured quality field, not authorization.

## L. Testing / Evaluation / Runtime Verification

Use existing Hatch workbench-api:check, workbench-api:test and workbench-api:types; scoped tests must use disposable PostgreSQL and a temporary asset root, never the operator's live data. Required matrix: 1) schema migrate populated 0002 -> new head and no-op rerun, 2) RLS cross-workspace source/asset/representation reads, 3) duplicate content tenant separation, 4) exact SHA256 original-byte roundtrip, 5) multiple representations for one element, 6) many-to-one chunk links, 7) missing/altered blob, 8) stage/commit/crash/orphan cleanup and source-version rollback, 9) API restart and DB restart with retained blob root, 10) malformed spans/boxes/oversized metadata, 11) old lexical/ingestion/regression tests. Include a test that a model_inferred representation is never mislabeled direct_source. Record actual SQL/HTTP/blob evidence and failure codes.

## M. Acceptance Criteria

- [ ] All four typed contracts pass schema and forbidden cross-scope reference tests.
- [ ] 0001 and 0002 histories remain byte-identical; additive migration upgrades an existing populated schema without data loss.
- [ ] At least one exact original binary and one exact Mermaid source fixture can be stored and retrieved byte-for-byte with matching hash after restart.
- [ ] One element can hold at least three distinguishable representations, including a model_inferred one that is NOT promoted to verified evidence.
- [ ] Existing indexed Chunk maps to exact element/source/version/representation; retrieval ranking remains unchanged.
- [ ] Failed upload/asset write never makes a partially linked new active version visible; orphan states are detectable and recoverable.
- [ ] Cross-workspace and stale version attempts return safe failures with zero unauthorized asset bytes.
- [ ] New features are advertised only after passing storage/auth readiness; no new embedding/GPU service required.
- [ ] All relevant API, migration, source and restart regression gates have actual recorded outputs.

## N. Documentation / Migration / Compatibility / Rollback

New schema revision only; existing source/version/chunk identities and postgres-fts-baseline remain backward compatible. Historic chunks lacking evidence mappings may return explicit EVIDENCE_NOT_AVAILABLE; do not invent original assets. Migration/backfill of old content requires a separately approved policy and must not fabricate original bytes from retrieval snippets. Rollout: disabled-by-default representation/asset support, then qualified test workspace, then upload consumers. Rollback disables new routes/capability while preserving raw assets and metadata; do not delete customer blobs or run destructive downgrade. Future S3-compatible store, encryption-at-rest provider and automated retention are adapter implementations, not schema changes to core contracts.

## O. Mandatory Completion Checklist

- [ ] Reinspect current repository and active PDF work before implementation; update C/I if materially changed.
- [ ] Reuse current parser, upload jobs, active-version publication, Chunk and WorkspaceContext paths.
- [ ] Confirm asset, representation, evidence and error contracts with downstream task owners.
- [ ] Schema, byte store, recovery and authorization tests executed and evidenced.
- [ ] No false atomicity or fabricated citation/trust claims.
- [ ] Evidence lookup with exact original bytes succeeds after restart.
- [ ] Old source, UI, lexical and migration tests pass.
- [ ] Docs/rollout/rollback and unsupported capability states documented.
- [ ] Update status to COMPLETE only with proof for every applicable M criterion.

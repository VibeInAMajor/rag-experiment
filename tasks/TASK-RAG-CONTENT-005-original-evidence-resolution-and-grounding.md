# TASK-RAG-CONTENT-005 — Source evidence resolution, grounding, and citation verification

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint; source evidence resolver not yet present  
**Priority:** P1 — trust boundary for multimodal retrieval and future answers  
**Dependencies:** TASK-RAG-CONTENT-001; CONTENT-002/003/004 integrations provide format-specific evidence (may roll out separately); completed TASK-RAG-001/TASK-RAG-002  
**Repository snapshot inspected:** 4dd81abd4b34794edfcafabb623703c67f40be81  
**Target:** tasks/TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md

## A. Title

Implement a tenant-authorized Evidence Resolver that maps every retrievable text chunk or derived diagram representation back to the exact immutable original source version, page/box/line or graph statement, and verifies citation integrity without promoting OCR/VLM guesses into facts.

## B. Context / Problem

A RAG result may contain a synthesized caption for a flowchart or an OCR reconstruction of a scanned PDF. Such text is useful for search but is not itself the original evidence. Returning a persuasive answer with a source title and invented page number is worse than returning no citation. Source provenance must survive splitting, version updates, file conversions, API restart and model revisions. There is also a privacy risk: a guessed evidence ID must not reveal an original PDF/image from another workspace. Existing SearchResponse has chunk provenance, but not a complete verified original-asset resolution contract.

## C. Current Repository State

| Source | Current behavior / evidence gap |
| --- | --- |
| [persistence.py](../apps/workbench/api/persistence.py) | Chunk has workspace/source/version/chunk IDs, content, optional page and metadata; no mandatory original-asset evidence reference. |
| [postgres.py](../apps/workbench/api/postgres.py) | Lexical search uses active scoped versions and real PostgreSQL ranking, can return document IDs, not original page crops. |
| [lexical.py](../apps/workbench/api/lexical.py) and [projection.py](../apps/workbench/api/projection.py) | Server-owned result ranks, trace IDs, source_version_id and score_type postgres_ts_rank_cd; no evidence-resolver link traversal. |
| [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py) | v1 HTTP contracts and server-authenticated workspace scope; no asset/evidence read endpoint in inspected repository. |
| [ingestion.py](../apps/workbench/api/ingestion.py), [ingestion_http.py](../apps/workbench/api/ingestion_http.py) | Existing idempotent publication and document/chunk read; must not be bypassed by a separate evidence store. |
| [parsing.py](../apps/workbench/api/parsing.py) | SourceSpan of decoded text and line ranges for Markdown; distinguish byte offsets/Unicode when resolving original. |
| [pdf_models.py](../apps/workbench/api/pdf_models.py) | Validated PDF page/bbox coordinates, tables; no original page raster/blob reader. |
| [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) | Provides original asset, representation, element, link and workspace-scoped storage contract; implementation is a hard prerequisite. |
| [CONTENT-002](TASK-RAG-CONTENT-002-scanned-pdf-ocr-and-layout.md), [003](TASK-RAG-CONTENT-003-visual-diagrams-charts-and-graph-extraction.md), [004](TASK-RAG-CONTENT-004-mermaid-typed-graph-ingestion.md) | Produce OCR, visual and source diagram evidence with distinct trust/provenance statuses. |
| [Current UI views](../apps/workbench/web/src/views/RunsView.tsx) | Textual run display; no original page/diagram evidence preview implementation is guaranteed by current code. |

There are currently no proven structured-graph edge citations or byte-for-byte original diagram references exposed by the API. Existing source_version_id/page are necessary but not sufficient for verifiable visual grounding. Do not claim a deployed answer generator is present merely because future RAG answers are discussed.

## D. Goal

For each authorized search hit carrying an evidence link, resolve a structured evidence bundle containing the **exact** immutable original source locator and authorized bytes/preview when requested, recorded observed/inferred representations and integrity status. On unchanged source versions the same evidence ID resolves identically across restarts. On a newer source version, the previous reference stays bound to its original version or yields an explicit unavailable outcome; it MUST NOT silently redirect. A verification helper classifies deterministic integrity/coverage and semantic claims as verified, unsupported, ambiguous or requires_review with inspectable reasons.

## E. Scope

- Define provider-neutral EvidenceResolverPort/service using CONTENT-001 records and AssetStorePort.
- Provide secure GET routes for evidence metadata and bounded original/raster/source-range bytes, using existing WorkspaceContext and RLS.
- Link optional evidence refs to SearchResult/Chunk without changing lexical scoring or requiring the old corpus to have fabricated original assets.
- Resolve text excerpt spans, PDF 1-based page and bounded crop, table cell provenance, diagram graph node/edge source spans, Mermaid exact bytes/line range; include processor/trust status.
- Add integrity checks: hash/revision/source ownership, bbox and offset containment, links between child/parent, representation type and verified source.
- Expose a deterministic pre-answer evidence check that can refuse invalid/insufficient provenance. Future answer-generation integration consumes this gate and is outside this task.
- Add tests, API contract, operator audit evidence and a minimal UI-friendly reference contract (not a full interactive PDF viewer).

## F. Non-Goals

No new arbitrary LLM generator, no universal fact-checking guarantee, no embeddings/reranking upgrade, no unapproved public storage URLs, no full document annotation UI, no automatic human reviewer service, no hallucination detection by a single LLM judgment, no altering original source to fit a citation and no resynthesizing an original graph from a description. A verified hash proves bytes, not the semantic truth of a VLM-derived claim.

## G. Architecture / Boundaries

[x] application domain evidence contracts, [x] scoped storage + representation links, [x] HTTP and retrieval projection, [x] security/RLS, [x] observability, [x] tests/docs; [ ] arbitrary agent runtime, [ ] new vector provider. Pipeline:

    SearchResult chunk_id / source_version_id
       -> lookup immutable ChunkEvidenceLink and representation
       -> check WorkspaceContext + source/version + active/historic scope
       -> load original AssetStorePort bytes / decoded source span
       -> verify SHA256, page/box/line/graph link
       -> EvidenceBundle with status and provenance
       -> citation/check gate -> user-facing source reference

No consumer can supply arbitrary filesystem path, source URL or untrusted SQL filter. Content-representation graph stays provider neutral; actual OCR/VLM/graph adapters only produce provenance, not permissions.

## H. Contracts / Interfaces / Data Model

**EvidenceResolveRequest**: authorized workspace from server context, evidence_id or (source_id,version_id,chunk_id), requested view metadata_only/original_range/page_crop/structured_graph, bounded byte budget and optional expected hash/revision. No caller-supplied storage key, arbitrary URL, or implicit "latest version".

**EvidenceBundle**: evidence_id, source_id/version_id/element_id, optional representation_id and asset_id, immutable content_sha256 and asset_sha256, kind/origin, trust/provenance status (direct_source, deterministic_parse, observed_OCR, model_inferred, human_verified), location with explicit unit (page+bbox+coordinate_frame; byte/character/line ranges; Mermaid block and node/edge refs), original_available, representation_available, verification_status and safe warnings. A model-inferred edge must never appear as directly observed; boolean supported_by_original is not set true solely by vision model self-confidence.

**CitationReference**: stable opaque reference scoped to workspace, source version and element, plus hash; render a link to a narrow authorized API route (no direct public blob URL). Never format a PDF page citation without a verified page. Markdown source-range citation must preserve exact codepoint/byte mapping, including non-ASCII.

**Verifier output**: integrity_ok or reason codes HASH_MISMATCH, STALE_VERSION, ORIGINAL_MISSING, SCOPE_MISMATCH, SPAN_OUT_OF_BOUNDS, UNVERIFIED_INFERENCE, PARTIAL_EVIDENCE, UNSUPPORTED_CLAIM, REVIEW_REQUIRED. Report which check passed and which lacks data; do not reduce all outcomes to a misleading percentage.

**Endpoint proposals** (finalize against current application.py and contracts.py before code): GET /api/v1/workspaces/{workspace_id}/evidence/{evidence_id} -> typed bundle metadata; GET /api/v1/workspaces/{workspace_id}/evidence/{evidence_id}/original?view=... -> authorized bounded bytes or crop; optional POST /api/v1/workspaces/{workspace_id}/evidence/verify -> bounded source references and claim structure without executing an LLM. Use existing nested ErrorResponse and request/trace IDs; foreign/missing references 404, invalid request 400, version conflicts 409, storage unavailable 503. Images/byte ranges streamed with correct Content-Type, Content-Length, safe Content-Disposition, no inline HTML and restrictive caching.

**Backward compatibility**: SearchResponse remains valid for old lexical-only sources; optional evidence_refs[] may be populated only when actual CONTENT-001 links exist. Absent references mean evidence_unavailable, NOT a missing page invented from chunk order. Chunk.score and score_type do not change.

## I. Repository Files / Components Impacted

CREATE app-owned evidence.py, evidence_verification.py, evidence_http.py (or a narrowly scoped route class analogous to ingestion_http.py), and tests/test_evidence_resolver.py, tests/test_evidence_http.py, tests/test_evidence_grounding.py. REUSE CONTENT-001 asset_store.py/content_models.py and Postgres metadata/link implementation; extend persistence.py and postgres.py read ports minimally as needed. MODIFY contracts.py/openapi.json and application.py to register safe routes and optional SearchResult evidence links; projection.py may add links only after checking source/version. Update docs-website/docs/architecture/rag-runtime-contract.md, content-aware-chunking-strategy.md and API README. MAY add a separate UI task for a preview panel; do NOT modify RunsView/ResultsPanel unless explicitly scoped with browser tests. MUST NOT change upstream haystack/, 0001/0002 migration history, search rank scores, active-version publication behavior, constructor validation or Preview fixtures.

## J. Implementation Requirements

### J1 — freeze requirements and make a source map
Reinspect current contracts and completed CONTENT-001 implementation, identifying exact provenance fields and SQL ownership. Build a matrix for direct TXT/Markdown original ranges, page PDF crops, table row/cell, scan OCR and model graph, plus Mermaid fenced block. Distinguish observed source facts versus derived descriptions. Resolve missing representation mapping explicitly rather than guessing fallback citations.

### J2 — implement scoped resolver and locator validation
Build one query path from chunk -> representation -> element -> source_version -> asset, all under WorkspaceContext and PostgreSQL RLS. Verify source/version identity at every join, not only once at API edge. Validate byte/character/line range boundaries, page/bbox origin and chart/diagram graph IDs against stored element. Recompute hash/check byte length before returning data; stale/missing/orphaned assets produce safe failure and never the wrong version's content.

### J3 — add authorized evidence endpoints
Read endpoints only from stored ID references; never accept a user URL or local path. Implement bounded byte streaming and optional safe rendering crop by verified page location. Set Cache-Control no-store for sensitive content, disable CORS wildcard with credentials and avoid content sniffing vulnerabilities. Advertise separate evidence_metadata and original_asset_access capabilities only when service ready and assets store verified. No model call in evidence reads.

### J4 — provide honest citation and verification
Add evidence_refs to SearchResult or a sidecar endpoint by existing run ID/Chunk where allowed. Write deterministic integrity validation of hashes, containment and graph relation source-line attribution. A VLM-inferred chart number remains unverified even if the PNG is intact. For Mermaid, AST deterministic relation can be syntax-grounded to exact source span; do not claim an arbitrary inferred semantic conclusion automatically. If evidence is partial, return REVIEW_REQUIRED/INCOMPLETE rather than a plausible fabricated caption. No text-generation adapter may bypass required citation-validation capability once enabled in a later task.

### J5 — exercise retrieval-to-original flow
Use synthetic non-sensitive records for: (a) Markdown paragraph source span, (b) Mermaid branch condition, (c) normal PDF table/page crop, (d) scanned OCR page, (e) visual chart with an unsupported numeric assertion. Search via postgres-fts-baseline, resolve each returned element to exact versioned source, and compare input hashes and paths with gold; test old version after guarded source update. A new version is not allowed to replace the referenced old evidence.

### J6 — audit, performance and negative paths
Collect 30+ manually labelled evidence queries/citations across element families (some may be declared pending if upstream format tasks not qualified). Measure evidence-availability rate, exact page/line/crop attribution, wrong-version rate, false-verified rate and resolver latency p50/p95. A 0% false-verified rate is a hard correctness gate for crafted model-inferred edge/number cases, not a statistical assurance. Test missing/corrupted asset, wrong tenant, guessed evidence ID, stale cursor, oversized range, invalid coordinate frame, hash collision, incomplete OCR, parser rev drift, restart and deletion/retention interaction. Verify no raw customer content in telemetry.

## K. Security / Governance / Observability

Evidence bytes are often more sensitive than summaries. Access must be checked for workspace, source, version, element and exact asset on every request; never rely only on an opaque ID. Disable direct unauthenticated paths, unbounded ranges, public signed URLs and browser cache of original assets. Originals may contain malicious PDF/HTML/SVG/Markdown; set safe Content-Type and restrictive response headers, and never execute embedded instructions. Prompt-injection content is a displayed source, not an instruction to the resolver or future answer model. Track hashes, version, trust and pipeline revision. Log safe IDs, status codes and latency without OCR bodies, full charts, diagram images, source text, credentials or secrets. Retention/deletion requires coordinating immutable citations and source legal policy; do not silently leave dangling public assets.

## L. Testing / Evaluation / Runtime Verification

Run existing Hatch workbench-api check/test/types, disposable PostgreSQL with CONTENT-001 temporary asset root, frontend contract tests only if SearchResult display changes. Unit tests for evidence graph joins, locator bounds, crop coordinate conversion, exact byte/UTF-8 span matching, SHA checks and trust-state transitions. Integration: authorized GET metadata/original; 404 foreign/unknown, 409 inconsistent version, 503 corrupted/missing store; restart API and DB without reseeding; idempotent source publication and retention state transitions. E2E smoke: one search hit per qualified input family resolves original evidence; unsupported OCR/visual case returns incomplete not fake citation. Record metrics and all mismatches in Markdown evidence. Do not mark visual/scan tests PASS when their upstream producer is unimplemented; block relevant acceptance gate until source exists.

## M. Acceptance Criteria

- [ ] Every resolved evidence reference includes exact workspace/source/version/element identity and verified original hash or explicit unavailable status.
- [ ] Bounded authorized original PDF/image and Mermaid/TXT bytes can be retrieved without exposing storage paths, and remain byte-exact after restart.
- [ ] Old evidence ID stays tied to old immutable source version across guarded update; never silently redirects to new content.
- [ ] Scoped reads deny forged/foreign IDs and missing/orphaned assets with zero leaked bytes.
- [ ] At least 30 gold evidence/citation checks are executed for qualified input families, with exact page, span, bbox and graph edge agreement measured.
- [ ] Model-inferred/ambiguous diagram edge and chart number do NOT become automatically verified facts; adversarial false-verified count = 0.
- [ ] Search ranking, raw score_type and existing schema compatibility unchanged; old chunks without source assets report evidence unavailable honestly.
- [ ] Source/crop byte caps and restricted content rendering prevent untrusted PDF/HTML/URL execution.
- [ ] Cross-restart, mutation rollback and asset corruption paths have real evidence logs.
- [ ] All relevant API, SQL, security and regression tests pass; operator docs/capability flags match actual behavior.

## N. Documentation / Migration / Compatibility / Rollback

Reuse CONTENT-001 migration and source-element/representation tables; any additional DB index/key requires an explicit reviewed additive migration and update to this task. New API routes and optional SearchResult evidence_refs are additive and guarded by contract revision tests; no retroactive rewrites of old references. Deploy evidence metadata first, binary read second, citation verification third, each with readiness gate. Rollback disables resolver/read endpoints and evidence capability but **retains original assets and historical source versions**; avoid deleting data to "fix" broken citations. Later full generative answer grounding consumes this evidence gate in a separate explicit task; this task does not promise universal semantic truth verification.

## O. Mandatory Completion Checklist

- [ ] Confirm source schemas and CONTENT-001 implementation before coding, without duplicate asset store.
- [ ] Correct scoped Postgres joins, asset hashes and source/version pinning verified.
- [ ] Citation schema represents page/box/line/graph relation without invented fields.
- [ ] HTTP evidence access respects size, content type, RLS and cache controls.
- [ ] No model-inferred description automatically becomes a trusted original fact.
- [ ] Search-to-evidence roundtrip and old-version persistence pass with real fixtures.
- [ ] All failure/security/restart/corruption cases executed and diagnosed safely.
- [ ] 30+ evidence checks with false-verified, citation and latency metrics recorded.
- [ ] API docs, capabilities, rollback and retention behavior match implementation.
- [ ] Status COMPLETE only after all applicable observable tests have evidence.

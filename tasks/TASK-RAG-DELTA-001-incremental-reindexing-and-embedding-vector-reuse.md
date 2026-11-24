# TASK-RAG-DELTA-001 — Version-aware chunk deltas and safe embedding reuse

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** PROPOSED — implementation blueprint, no runtime claim  
**Priority:** P1  
**Dependencies:** EMBED-002, INDEX-001, PROFILE-001; CONTENT-001 for evidence  
**Source reviewed:** cb7fe844084133b7e09a623e0e39767af1e0d9f1  
**Target:** tasks/TASK-RAG-DELTA-001-incremental-reindexing-and-embedding-vector-reuse.md

## A. Title

Version-aware chunk deltas and safe embedding reuse

## B. Context / Problem

The current publisher handles whole-source unchanged detection using source and processing fingerprint, while changing a small part of a document will otherwise require rebuilding embeddings. Reusing vectors by raw text hash alone is wrong when headings, task instructions, normalization or model/tokenizer revision differ. We need safe per-chunk matching linked to source version, profile and tenant.

## C. Current Repository State

[parsing.py](../apps/workbench/parsing/parsing.py) and [parser_registry.py](../apps/workbench/parsing/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/chunking/chunking.py), [ingestion.py](../apps/workbench/ingestion/ingestion.py) and [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [models.py](../apps/workbench/persistence/models.py) and [postgres.py](../apps/workbench/postgres/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [schemas.py](../apps/workbench/contracts/schemas.py) own API/capabilities. [pdf_worker.py](../apps/workbench/parsing/pdf/pdf_worker.py), [pdf_models.py](../apps/workbench/parsing/pdf/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/chunking/pdf/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
[postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) returns unchanged on matching active content_hash and processing_profile_fingerprint. [chunking.py](../apps/workbench/chunking/chunking.py) prepares structured chunks; [ingestion.py](../apps/workbench/ingestion/ingestion.py) persists processing identity. No cross-version per-chunk model-input vector reuse registry exists.

**Verification limit:** this is a source-backed task, not proof that the proposed feature exists. Re-inspect current code at implementation start.

## D. Goal

A 100-chunk source edit reuses compatible unchanged vectors while new version remains fully attributable to correct source spans; model/profiles changes invalidate reuse deterministically. Partial failures never activate incomplete semantic generation.

## E. Scope

Stable per-chunk model input fingerprint, structural delta plan, duplicate-instance provenance, tenant-safe embedding reuse ledger, selective embedding jobs, qualification and savings metrics.

## F. Non-Goals

No global cross-workspace cache by default, no semantic VLM guess that texts are equal, no reused vectors after tokenizer/model/context mismatch, no removal of source history.

## G. Architecture / Boundaries

Versioned source/chunks -> DeltaPlanner -> compare compatible (workspace+input_hash+model/profile) -> vector reuse or EmbeddingPort miss -> new generation activation through existing Postgres writer and index revision. Same original EvidenceReference remains linked by version, not by text alone.

## H. Contracts / Interfaces / Data Model

ReuseKey{workspace_id,model_input_sha256 including heading+instruction,tokenizer_digest,model_digest,embedding_profile_revision,dimensions,normalization_revision}; DeltaPlan{new_source_version,old_source_version,unchanged,modified,added,removed,reused_vectors,new_vectors,skipped_reason}. Reused vector record must not overwrite original chunk source offsets or asset references.

External schema changes MUST be reviewed in Pydantic/OpenAPI/client and versioned explicitly.

## I. Repository Files / Components Impacted

CREATE apps/workbench/ingestion/delta_indexing.py, apps/workbench/ingestion/tests/test_delta_indexing.py, golden fixtures with code, MD and tables. MODIFY embedding ingestion backfill implementation minimally and reuse [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) and CONTENT-001 evidence links. No new source store.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

### I.1. Source-level reuse matrix — refreshed 2026-11-23

**Recipient code anchors (real files, inspected):**

| Repository file | Existing owner; exact integration role |
| --- | --- |
| [`apps/workbench/ingestion/ingestion.py`](../apps/workbench/ingestion/ingestion.py) | full-source SHA and processing profile recorded on upload |
| [`apps/workbench/postgres/postgres_ingestion.py`](../apps/workbench/postgres/postgres_ingestion.py) | unchanged source/idempotent replay and complete source version switch |
| [`apps/workbench/chunking/chunking.py`](../apps/workbench/chunking/chunking.py) | PreparedChunk and structural identity+profile fingerprint |
| [`apps/workbench/chunking/chunking_adapters.py`](../apps/workbench/chunking/chunking_adapters.py) | source-provenance-compatible projection into prepared chunks |
| [`apps/workbench/persistence/models.py`](../apps/workbench/persistence/models.py) | Chunk/SourceVersion models and workspace ownership |
| [`apps/workbench/postgres/postgres.py`](../apps/workbench/postgres/postgres.py) | existing active source version and vector_search; no physical point alias |
| [`apps/workbench/api/tests/test_python_ingestion.py`](../apps/workbench/api/tests/test_python_ingestion.py) | code source-update and AST provenance fixture |
| [`apps/workbench/postgres/tests/test_ingestion_persistence.py`](../apps/workbench/postgres/tests/test_ingestion_persistence.py) | duplicate, conflict, failure and version checks |

**Pinned previous-project candidates (do NOT copy unlicensed code or Qdrant/SQLite infrastructure):** donor commit `955fd049949d3fc462d555be14774e4b255aa15c`.

| Pinned previous-project source | Targeted symbol/behavior |
| --- | --- |
| [`src/enterprise_ai_pipeline/rag/chunk_delta.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/chunk_delta.py) | plan_chunk_delta multiset matching preserving repeated occurrences, verified point presence |
| [`src/rag_reference/cache/document_delta_lookup.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/rag_reference/cache/document_delta_lookup.py) | DocumentDeltaLookup direct prior-version lookup avoiding global snapshot scan |
| [`src/rag_reference/indexing/chunk_delta_execution.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/rag_reference/indexing/chunk_delta_execution.py) | SourceDeltaContext/materialized_chunk_delta mapping |
| [`src/rag_reference/indexing/document_delta_plan.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/rag_reference/indexing/document_delta_plan.py) | DocumentDeltaPlan new/changed/deleted/renamed source cases |
| [`src/rag_reference/indexing/physical_delta.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/rag_reference/indexing/physical_delta.py) | plan_saved_corpus logic; conceptual only, no Qdrant pools |
| [`tests/pipeline/test_chunk_level_repository_delta.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_chunk_level_repository_delta.py) | chunk differential and duplicate occurrence test scenarios |
| [`tests/pipeline/test_document_delta_refresh.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_document_delta_refresh.py) | source rename/delete/change/restart scenarios |
| [`tests/pipeline/test_rag_chunk_delta_runtime.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_rag_chunk_delta_runtime.py) | test_duplicate_occurrence_add_remove_never_rewrites_inherited_vector and source replay |
| [`tests/pipeline/test_semantic_restore_delta_lifecycle.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_semantic_restore_delta_lifecycle.py) | model profile mismatch and stale target repair scenarios |
| [`LICENSE.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) | literal port requires owner permission |

**Reuse decision gate:** compare current component to donor behavior, list reusable algorithm/contract, incompatibilities and the exact owner of PostgreSQL/model/tokenizer state. Code copying requires permission under [donor LICENSE](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md); otherwise independently implement compatible behavior and port test **scenarios**. Existing completed Workbench components must not be replaced without a measurable reason.

## J. Implementation Requirements — ordered blueprint

1. Map source fingerprints and exact embedder input composition to define compatibility including heading and task instructions.
2. Compute deterministic diff using structural anchors and bounded matching; repeated identical paragraphs remain distinct occurrences.
3. Implement tenant-scoped immutable vector reuse lookup and new version references inside transactional generation workflow.
4. Run EmbeddingPort only on misses, publish semantic generation only after eligible coverage completed, leave old active on failure.
5. Test 100-chunk one-edit, same body different heading, tokenizer/model change, repeated paragraph, tenant copy, concurrency and restart.
6. Report measured GPU requests/tokens avoided and quality/citation stability; explicit full reindex fallback on incompatible state.

### J7–J14. Detailed, source-grounded implementation handoff — 2026-11-23

**Step J7 —** Introduce SourceObservation/SourceDelta strictly scoped to `(workspace_id,source_id,namespace)` and cryptographic source + parser/chunker/model profile hashes; compare only exact content, not mtime alone. A deletion or rename event requires an authorized observed source list, not intuition from one upload.

**Step J8 —** Adapt donor `plan_chunk_delta(source_id, previous_members, current_chunks, compatible, verified_point_ids, representation_profile)` into provider-neutral Workbench `plan_chunk_reuse` over immutable existing Chunk occurrences and prepared content. Preserve `deque` multiset matching for repeated identical passages.

**Step J9 —** Do not copy donor `physical_vector_identity` (Qdrant-specific); replace the reusable-vector key with `(workspace, full embedding model input digest, model/profile version, dimension, normalization)` and verify vector row actually exists in PostgreSQL before reuse.

**Step J10 —** Use donor `DocumentDeltaLookup` direct version/identity lookup pattern to avoid scanning all chunks or hashing whole corpus per source update; co-design with INDEX-001 persisted generation, not another O(N) snapshot scan.

**Step J11 —** Treat shifted page/line as **new provenance** with old embedding values only if full model input unchanged. Two copies of an identical paragraph must retain independent `chunk_id`, source offsets and citation; identical text is not permission to inherit old ACL.

**Step J12 —** Implement unit cases NEW, UNCHANGED, CHANGED, DELETED, RENAME, METADATA/ACL, PROFILE_CHANGE. A rename in content-store is metadata-only only when workspace/source rules permit; no fabricated rename inferred from coincidentally same bytes.

**Step J13 —** Document provider reuse assumptions and exact caller boundary: `PostgresPersistence` owns vector checks and generation commitment; DeltaPlanner is pure; content matching never causes direct Qdrant/SQLite import.

**Step J14 —** Measure one paragraph/method edit on 100-chunk Markdown/Python/PDF fixtures; require expected vector call reduction but no source-index inconsistency, cross-tenant leak or profile-mismatch reuse. Port donor test **scenarios**, not donor whole test runtime.

**Mandatory dependency handshake:** [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) supplies durable vector jobs; [INDEX-001](TASK-RAG-INDEX-001-persisted-revision-and-consistent-search-snapshots.md) supplies source generation; planner must not bypass TPM-001.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

100+ chunk baseline, one edit => expected >=95 unaffected vector reuse when model input unchanged; 0 reuse for incompatible model profiles, no cross-tenant leakage, duplicates/source spans, source update race, restart. Measure real model calls, reindex duration and Recall@k.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

### L.1. Reuse-specific test migration and verification

- [ ] 100-chunk one edit: >=95 compatible unchanged vectors reused; code AST method insertion, duplicate passage add/remove, changed heading/prefix, model digest change (0 incompatible reuse), source ACL change, tenant B identical source (no reuse).
- [ ] Source update interrupted before version activation and after vector batch, late result, restart with partial embedding cache, unknown physical availability, deleted source cleanup and read during reindex.
- [ ] Golden source/chunk version and provider invocation counter proof; compare inherited/rebuilt output to full reindex and check RLS and exact citations.

**Proof requirements:** record donor behavior source commit, recipient code and exact executed test commands. Donor unit tests **do not** demonstrate recipient functionality; recipient CI evidence must exercise the actual PostgreSQL/TEI/client paths. Capture a fixture-vs-runtime result matrix, error correlation and no-secrets logs.

## M. Acceptance Criteria

- [ ] Only exact compatible model input fingerprints allow reuse
- [ ] One small edit reuses >=95 unchanged vectors under stable structure
- [ ] Any model/tokenizer/instruction change invalidates affected vectors
- [ ] Duplicate source occurrences retain independent citations
- [ ] No foreign tenant vector reuse
- [ ] New index generation publishes only after full required vector coverage
- [ ] Actual saved tokens/inference time measured
- [ ] All source/SQL/embedding regression tests pass

- [ ] Donor plan_chunk_delta duplicate-occurrence and physical-existence semantics explicitly mapped to PostgreSQL, not copied Qdrant APIs
- [ ] Donor test_chunk_level_repository_delta and test_rag_chunk_delta_runtime scenarios reproduced independently in recipient tests
- [ ] Reused vectors cannot inherit stale source/page/ACL/tenant metadata; new occurrence citations remain correct
- [ ] A missing/invalid vector or incompatible model/processing profile always requires new inference rather than optimistic reuse

## N. Documentation / Migration / Compatibility / Rollback

Delta reuse is a gated optimization. Disable it to perform full versioned reembedding while retaining old source/index generations. No destructive migration or modification to existing evidence bytes.

## O. Mandatory Completion Checklist

- [ ] Recheck source/architecture ownership before coding.
- [ ] Reuse existing parser/chunker/source publisher and provider-neutral ports.
- [ ] Contracts, auth, bounds, versions and failure states tested.
- [ ] Measured evaluation/gold data and negative cases recorded.
- [ ] No silent fallback, wrong score or partial ready claim.
- [ ] Retry, rollback, source/asset preservation tested.
- [ ] Hatch/SQL/browser regression suites executed and outputs linked.
- [ ] Operator documentation and capability gates updated truthfully.
- [ ] Modified file paths, resulting commit and safe evidence linked.
- [ ] Task remains PROPOSED until all acceptance gates pass.

**A–O scope change rule:** if a new migration, provider or authorization boundary is needed, revise the task before implementing.

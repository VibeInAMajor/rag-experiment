# TASK-RAG-DELTA-001 — Version-aware chunk deltas and safe embedding reuse

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
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

[parsing.py](../apps/workbench/api/parsing.py) and [parser_registry.py](../apps/workbench/api/parser_registry.py) own verified file classification; [chunking.py](../apps/workbench/api/chunking.py), [ingestion.py](../apps/workbench/api/ingestion.py) and [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) implement bounded parsing, jobs and PostgreSQL publication. [persistence.py](../apps/workbench/api/persistence.py) and [postgres.py](../apps/workbench/api/postgres.py) own workspace-scoped source versions and lexical/vector storage. [application.py](../apps/workbench/api/application.py), [contracts.py](../apps/workbench/api/contracts.py) own API/capabilities. [pdf_worker.py](../apps/workbench/api/pdf_worker.py), [pdf_models.py](../apps/workbench/api/pdf_models.py), [pdf_chunking_adapter.py](../apps/workbench/api/pdf_chunking_adapter.py) already implement substantial offline Docling text/table processing; do not duplicate them.
[postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) returns unchanged on matching active content_hash and processing_profile_fingerprint. [chunking.py](../apps/workbench/api/chunking.py) prepares structured chunks; [ingestion.py](../apps/workbench/api/ingestion.py) persists processing identity. No cross-version per-chunk model-input vector reuse registry exists.

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

CREATE apps/workbench/api/delta_indexing.py, tests/test_delta_indexing.py, golden fixtures with code, MD and tables. MODIFY embedding ingestion backfill implementation minimally and reuse [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) and CONTENT-001 evidence links. No new source store.

MUST NOT modify applied 0001/0002, framework haystack/, unrelated Live profile score labels, Preview fixtures or authority of existing store.

## J. Implementation Requirements — ordered blueprint

1. Map source fingerprints and exact embedder input composition to define compatibility including heading and task instructions.
2. Compute deterministic diff using structural anchors and bounded matching; repeated identical paragraphs remain distinct occurrences.
3. Implement tenant-scoped immutable vector reuse lookup and new version references inside transactional generation workflow.
4. Run EmbeddingPort only on misses, publish semantic generation only after eligible coverage completed, leave old active on failure.
5. Test 100-chunk one-edit, same body different heading, tokenizer/model change, repeated paragraph, tenant copy, concurrency and restart.
6. Report measured GPU requests/tokens avoided and quality/citation stability; explicit full reindex fallback on incompatible state.

## K. Security / Governance / Observability

Server-derived WorkspaceContext and FORCE RLS are required. Never log original source/asset text, credentials, embedding vectors, model prompts, token secrets or unsafe user paths. Content and model outputs are untrusted data. Use bounded CPU/GPU/network/provider work, safe error codes, trace/job/profile revisions and retention; cross-tenant, canceled, stale and resource-exhaustion tests mandatory.

## L. Testing / Evaluation / Runtime Verification

100+ chunk baseline, one edit => expected >=95 unaffected vector reuse when model input unchanged; 0 reuse for incompatible model profiles, no cross-tenant leakage, duplicates/source spans, source update race, restart. Measure real model calls, reindex duration and Recall@k.

Run the existing Hatch app-specific check/test/types scripts on disposable test data, plus web typecheck/test/build for any UI changes. Distinguish mocked failures from real operator qualification; no invented timings.

## M. Acceptance Criteria

- [ ] Only exact compatible model input fingerprints allow reuse
- [ ] One small edit reuses >=95 unchanged vectors under stable structure
- [ ] Any model/tokenizer/instruction change invalidates affected vectors
- [ ] Duplicate source occurrences retain independent citations
- [ ] No foreign tenant vector reuse
- [ ] New index generation publishes only after full required vector coverage
- [ ] Actual saved tokens/inference time measured
- [ ] All source/SQL/embedding regression tests pass

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

# TASK-RAG-EMBED-002 — Durable generation-aware embedding ingestion, resumable backfill and initial delta reuse

**Created:** 2026-11-23  
**Updated:** 2026-11-24
**Status:** COMPLETE — durable backfill/reuse/restarts, controlled source-grounded quality and predeclared ten-minute steady-window gate pass; whole-run utilization 91.992753788% remains explicitly below exact 92%; broader TPM-001 stays IN PROGRESS
**Priority:** P0  
**Dependencies:** EMBED-001, INDEX-001; completed RAG-002/DB-001, coordinate PROFILE-001  , **[TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md)**
**Repository snapshot inspected:** 4d3292f81e55aa66cda4df97831b7eefe7b1f858 plus this task's working-tree changes
**Target location:** tasks/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md

## A. Title

Durable generation-aware embedding ingestion, resumable backfill and initial delta reuse

## B. Context / Problem

Today sources publish successfully as lexical chunks with embedding=None. On adding real vector processing, a document may be searchable lexically before semantic indexing is ready. Embedding failures must not corrupt source publication, claim dense readiness or force reupload of unchanged content. We need a resumable, idempotent, workspace-scoped embedding job path and active generation. Profile/model/chunk text changes must invalidate only relevant vectors.

## C. Current Repository State

**Implementation reinspection (2026-11-24):** INDEX-001 and PROFILE-001 are complete through applied migrations 0003/0004. EMBED-001 now provides the neutral immutable embedding port/profile, exact Qwen tokenizer, strict local TEI adapter and trusted named-volume deployment attestation. The current dedicated Qwen3-Embedding-4B profile produces actual full 2560-dimensional normalized vectors; main HTTP retrieval remains lexical-only. Its old admission owner is deliberately qualification-only, so it cannot satisfy this task's requested production-style 0.92/0.95 or ten-minute backlog proof. The user explicitly authorizes the necessary measured-capacity TPM-001 prerequisite here. No extra generative model, Ollama dependency or LLM judge is authorized for quality evaluation.

**Source inspection (2026-11-23):** [SQL migration 0001](../apps/workbench/api/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../apps/workbench/api/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../apps/workbench/api/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../apps/workbench/api/contracts.py), [API route owner](../apps/workbench/api/application.py), [Haystack lexical profile](../apps/workbench/api/lexical.py) and [runtime decision](../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
[postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) complete_ingestion_with_publication explicitly requires all chunks to have null embedding (lexical ingestion); DO NOT remove that guard blindly. [persistence.py](../apps/workbench/api/persistence.py) validates profile_id/dimensions. [postgres.py](../apps/workbench/api/postgres.py) _validate_embedding verifies registered dimensions, vector_search exact cosine; no job table for embedding backfill. [embedding_profiles](../apps/workbench/api/migrations/0001_initial.up.sql) only has synthetic-test-v1 initially, not a qualified real Qwen profile.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

## D. Goal

After a lexical source is published, a durable embedding job can process every eligible **active** chunk of a chosen model profile, persist exact finite vectors with idempotent keys and generation metadata, survive restart and expose honest coverage. Partial or stale vectors are never mixed into a qualified Live dense profile. A source update invalidates/reembeds changed chunks while reusing only explicitly safe compatible content/profile embeddings.

## E. Scope

Add additive schema for semantic model profiles, embedding jobs and generation/coverage (coordinate INDEX-001/PROFILE-001), bounded embedding worker initially in-process or reusable durable queue, batch/admission retries, deterministic idempotency, backfill CLI, source-update scheduling and cancellation, transactional readiness and exact-vector validation.

**User-requested live acceptance:** calibrate actual dedicated endpoint capacity, then run a backlogged ten-minute workload through one shared query/document owner with a 0.92 operating target and independent 0.95 rolling admission ceiling. Distinguish estimates, provider-reported completions, shortages and shared-GPU conditions; do not manufacture a capacity or claim the target merely because it is configured. Evaluate retrieval objectively against fixed original source texts and manually specified relevant chunk IDs using persisted exact cosine, Recall@k/MRR/nDCG and source/version/tenant provenance. Qwen remains the embedding provider; it is not used as a generative correctness judge.

## F. Non-Goals

No ANN tuning (ANN-001), no direct new browser upload path, no automatic vector search exposure before DENSE-001, no global shared cache across tenants, no remote providers without approval, no blind in-place model-upgrade of all old vectors.

## G. Architecture / Boundaries

Existing source ingest remains lexical-first. New embedding queue receives immutable chunk IDs/version hashes, requests EmbeddingPort adapter, stores typed EmbeddingGeneration rows bound to active source snapshot; a semantic index generation becomes ready only when required coverage passes and model identity matches. SQL writes use server workspace scope/RLS and existing connection lifecycle. Avoid holding a write transaction over GPU inference.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

EmbeddingJob{workspace,job_id,source_version_id,model_profile_revision,input_fingerprint,status queued/running/retryable_failed/completed/stale,attempts,cursor,started_at,finished_at}; EmbeddingRecord{chunk_id,source_version,model_profile,model_digest,input_hash,dim,vector_storage_ref,created_at}; EmbeddingCoverage{workspace,index_generation,profile,eligible_active_chunks,ready_embeddings,stale_embeddings,coverage_fraction,ready_boolean,checkpoint}. Content hashes include actual model input heading/instruction, parser/chunk profile revision, normalization and model digest. Do not mutate old vectors when the profile revision changes; separate generation namespace or table/pointer may be necessary.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

## I. Repository Files / Components Impacted

MODIFY [persistence.py](../apps/workbench/api/persistence.py), [postgres.py](../apps/workbench/api/postgres.py), [postgres_ingestion.py](../apps/workbench/api/postgres_ingestion.py) only through reviewed port; CREATE embedding_ingestion.py, embedding_jobs.py, tests/test_embedding_ingestion.py, next additive migration(s) after INDEX-001 schema; extend profiles.py, application.py capabilities and ops docs. MUST NOT alter lexical chunking and publication atomicity or original evidence links, applied 0001/0002 or static seed.

**Reviewed implementation boundary:** `embedding_jobs.py` owns durable internal types; the PostgreSQL embedding mixin/next additive migration own jobs, generation-fenced vectors and same-tenant cache. `embedding_ingestion.py` owns leased bounded processing through the existing adapter. `embedding_capacity.py` owns the one measured TPM scheduler; the old qualification owner is not a second production limiter. The shared backfill/calibration CLI composes existing assets/runtime attestation. `scripts/workbench_embedding_evaluate.py`, the fixed multilingual JSON fixture and recipient tests own objective quality/provenance checks; no model judge or generator is introduced. Internal exact search and CLI coverage do not enable Dense HTTP/UI or require speculative API fields. Any actual HTTP contract change would require all existing DTO/client gates; leaving the frontend and lexical API unchanged is preferred.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

### I.1. Source-level reuse matrix — refreshed 2026-11-24

**Recipient code anchors (real files, inspected):**

| Repository file | Existing owner; exact integration role |
| --- | --- |
| [`apps/workbench/api/ingestion.py`](../apps/workbench/api/ingestion.py) | synchronous parse/chunk followed by existing durable job; no model inference |
| [`apps/workbench/api/postgres_ingestion.py`](../apps/workbench/api/postgres_ingestion.py) | complete_ingestion_with_publication currently requires null embeddings and owns terminal job transaction |
| [`apps/workbench/api/postgres.py`](../apps/workbench/api/postgres.py) | _publish and vector_search, registered profile dimension checks |
| [`apps/workbench/api/persistence.py`](../apps/workbench/api/persistence.py) | source/version/chunk identities and EmbeddingProfile guards |
| [`apps/workbench/api/migrations/0001_initial.up.sql`](../apps/workbench/api/migrations/0001_initial.up.sql) | embedding_profiles, nullable vector, CHECK dimension; do not rewrite |
| [`apps/workbench/api/migrations/0002_ingestion_jobs.up.sql`](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) | existing indexing jobs are not durable embedding jobs |
| [`apps/workbench/api/tests/test_ingestion_persistence.py`](../apps/workbench/api/tests/test_ingestion_persistence.py) | source version rollback/replay fixtures |
| [`apps/workbench/api/tests/test_ingestion_resilience.py`](../apps/workbench/api/tests/test_ingestion_resilience.py) | interrupted publishing and current job retry expectations |

**Pinned previous-project candidates (do NOT copy unlicensed code or Qdrant/SQLite infrastructure):** donor commit `955fd049949d3fc462d555be14774e4b255aa15c`.

| Pinned previous-project source | Targeted symbol/behavior |
| --- | --- |
| [`src/enterprise_ai_pipeline/rag/semantic_embedding_preparation.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/semantic_embedding_preparation.py) | EmbeddingPreparation, digest-keyed cache partition, late-result recovery |
| [`src/enterprise_ai_pipeline/rag/embedding_execution.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_execution.py) | bounded execution windows; transport workers do not own source publication |
| [`src/enterprise_ai_pipeline/rag/embedding_dispatch.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_dispatch.py) | capacity reserve/finish through TPM-001 |
| [`src/enterprise_ai_pipeline/rag/embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py) | EmbeddingRequest/Batch and fake provider |
| [`tests/pipeline/test_embeddings_and_vector_store.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_embeddings_and_vector_store.py) | cache/identity/dimension/transport tests |
| [`tests/pipeline/test_semantic_restore_delta_lifecycle.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_semantic_restore_delta_lifecycle.py) | restart and stale-generation repair scenarios |
| [`LICENSE.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) | owner permission required for code transplant |

**Reuse decision gate:** compare current component to donor behavior, list reusable algorithm/contract, incompatibilities and the exact owner of PostgreSQL/model/tokenizer state. Code copying requires permission under [donor LICENSE](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md); otherwise independently implement compatible behavior and port test **scenarios**. Existing completed Workbench components must not be replaced without a measurable reason.

**Inspected implementation decision (2026-11-24):** donor preparation blob `42d8dce6970eb3d0ff9df7896a432ece55e3363b`, execution blob `2ebfe78d3b3785708eb0584e1fc7e282f7f036e5` and lifecycle-test blob `9a9ea7696a43ef1bada638b187f2f62e19d49515` were fetched at the pin above. They inform cache-partition, bounded-execution, paid-late-result and restoration scenarios; no donor implementation is copied. PostgreSQL transactions/RLS/generations, the existing neutral port/tokenizer and one shared measured governor retain recipient ownership. No Qdrant/SQLite stack or donor throughput claim is transplanted. Objective retrieval labels/metrics are independently implemented and use no model judge.

## J. Implementation Requirements — ordered blueprint

1. J1 — Inventory publication write ownership and dimension rules; design job+coverage schema with workspace FKs, RLS and idempotent unique (chunk/version/model_profile/input_hash). Model how a source replacement supersedes its old vector candidates and how a model revision creates a new semantic generation.
2. J2 — Add a bounded CLI to backfill active sources in batches without rescanning entire corpus on every query; enqueue jobs idempotently via source-version and index-generation identity. Do not keep a DB transaction open during embedding requests; reserve/lease work with expiry and cancellation.
3. J3 — Use the qualified EmbeddingPort to embed verified model input, validate exact dimensions/finite/normalization and persist vector under the selected immutable profile. Chunk source/version/hash must be rechecked in the same transaction that writes vectors to reject stale work.
4. J4 — Record coverage and readiness from durable checkpoints, not a boolean UI flag; make profile unavailable until complete/approved coverage. Retries bounded with exponential backoff; poison inputs quarantined with safe codes and operator recovery.
5. J5 — Test source unchanged, one-chunk edit, model revision, tokenization change, duplicate job, crash between inference/write, network timeout and partial backfill. Reuse only compatible same-tenant cached vectors; prove fingerprint correctness.
6. J6 — Run 10k–100k synthetic/real-fake benchmark; verify no silent vector loss across API/DB restart. Publish non-destructive reindex and rollback runbook with dry-run manifest.

All implementation methods use descriptive domain names (not task identifiers); all new behavior is fail-closed and traceable. No acceptance box is checked merely because a file was created.

### J7–J14. Detailed, source-grounded implementation handoff — 2026-11-23

**Step J7 —** Keep existing lexical publication intact: never remove the `chunk.embedding is None` guard from postgres_ingestion.py merely to force embeddings through HTTP upload. Add a distinct durable embedding job/backfill stage that runs after current source/version commit.

**Step J8 —** Define embedding job key `(workspace_id,source_id,version_id,chunk_id,model_profile_revision,input_digest)`, with lease, retries, checkpoint and generation ownership; persist in an additive migration with FORCE RLS and guaranteed non-superuser role.

**Step J9 —** Compute the complete text to embed before a provider call: section/heading/context prefix, query-vs-document instruction and tokenizer/profile digest. Model-input SHA, source occurrence and profile revision differ from bare `content_hash` and must be separately persisted.

**Step J10 —** Borrow donor semantic_embedding_preparation's cache partition pattern and bounded execution windows; do not import Qdrant physical-point identities or caller-owned SQLite writes. Database operations must stay in PostgresPersistence adapter and use current source/version constraints.

**Step J11 —** Send 100% of batches through one TPM-001 scheduler shared with live query embeddings. Lease releases only on known provider-not-sent or safe expiry; reserve before sending, reconcile provider/proxy token usage separately, no background worker bypass.

**Step J12 —** After each vector batch, re-check that the source/version and model/processing profile still match the job before saving vectors. A newer source supersedes stale jobs; no mixed 2560/1536 or query/description instruction vectors in one read generation.

**Step J13 —** Publish a semantic index generation only when required eligible active chunk coverage is complete and every vector has a correct model/profile/dimension hash. Partial failures retain lexical readiness and show a truthful `NOT_READY` dense capability.

**Step J14 —** Run model-down/restart/TEI 429, OOM, duplicate queue and source replacement tests; compare provider calls saved by compatible prior cache; preserve existing ingestion_idempotency and active version semantics.

**Mandatory dependency handshake:** [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) owns 0.92 desired / 0.95 hard admission and all query/document model calls; do not implement an independent limiter.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

Real qualified model optional GPU integration and fake provider deterministic tests; 100+ chunks, mixed languages, source update, quota/429, network outage, stale job/lease, wrong dimension, missing asset, RLS tenant denial, source version swap, crash recovery, latency/throughput and PostgreSQL migration/rollback. Acceptance requires 100% coverage on a known small supported corpus; larger backfill completeness reported with counts.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

### L.1. Reuse-specific test migration and verification

**Executed acceptance (2026-11-24):** [full report](evidence/embedding-2026-11-24/report.md). Main corpus reached 44/44 full 2560-dimensional vectors, retained across actual API/PostgreSQL restarts with unchanged content digests. Real multipart upload produced 50 chunks; a one-word edit regenerated one input and reused 49, returning 58/58 coverage with the seed. The 102-chunk fixture and 52-query before/after exact retrieval audits pass provenance with unchanged measured relevance; no-answer/hard-negative limitations remain explicit. The 600.969-second run passes its predeclared steady-window rule with median 92.141081157%, 53/55 windows in the 90–95% band and zero independently replayed hard breaches. Whole-run utilization is **91.992753788%, BELOW exact 92%**, and is not rounded into achievement. Storage-only 100k and actual 10k server-restart tests use fake 32-dimensional vectors and zero model calls. The 1279-pass full application suite plus late focused regressions are recorded separately. Browser checks are inapplicable because no frontend/HTTP DTO changes were made.

- [x] Objective quality: 102 active main-workspace chunks, 12 historical-version and 12 foreign-workspace sentinels, 52 EN/RU/UK/code/cross-language/no-answer queries; exact original-source SHA/chunk spans/input/profile/generation provenance. Report actual Recall/MRR/nDCG@1/5/10 and primary-evidence recall; raw nearest-neighbor no-answer candidates are not fabricated abstention or truth scores.

- [x] test_embedding_ingestion.py + integration: 8-source seed and actual uploaded 20+ chunks produce eligible semantic coverage exactly 100%, with correct vector dimension and per-workspace RLS.
- [x] Fault injection: late paid result after new source generation, interrupted write, duplicate job, complete job with missing vector, ungoverned API client, 429 with retry cooldown; no false-ready profile.
- [x] Performance: a backlogged governed 10-minute run records TPM target 0.92 and hard 0.95 admission but only claims success when provider reports/qualified proxy supports the measurement.

**Proof requirements:** record donor behavior source commit, recipient code and exact executed test commands. Donor unit tests **do not** demonstrate recipient functionality; recipient CI evidence must exercise the actual PostgreSQL/TEI/client paths. Capture a fixture-vs-runtime result matrix, error correlation and no-secrets logs.

## M. Acceptance Criteria

- [x] Lexical ingest remains available while embedding worker is offline; no half-ready dense advertised
- [x] Every ready vector has exact source/version/chunk/profile digest and finite verified dimension
- [x] Small corpus eligible active chunks reach 100% coverage with stable generation and real vector lookup
- [x] Stop/restart resumes job without duplicates or stale writes
- [x] Same-key retry and unchanged compatible text do not regenerate vectors unnecessarily
- [x] Changing source text/model/profile invalidates stale embeddings correctly
- [x] Cross-workspace cache reuse forbidden unless separately security-reviewed
- [x] Database migrations and existing lexical/Evidence regression pass

- [x] All provider calls from embedding jobs use exactly the TPM-001 dispatch budget
- [x] Stale/superseded source vectors cannot be attached to an active new generation
- [x] Original lexical source publication contract remains operational when TEI is offline; its null-embedding/atomicity guards are preserved while durable work is queued separately

## N. Documentation / Migration / Compatibility / Rollback

New schema additive and staged; semantic generation pointer only activated after coverage gate. Disable embedding worker on errors while preserving lexical search and stored vectors for later safe recovery. Do not mutate applied 0001/0002, delete original source assets or silently expose old vectors with a new model identity.

Update [API README](../apps/workbench/api/README.md), architecture and this task with exact evidence and compatibility details before marking ready.

## O. Mandatory Completion Checklist

- [x] Section C revalidated against actual repository and completed tasks; gaps identified with source evidence.
- [x] Existing ports/services reused without duplicate SQL, tokenizer, registry or provider coupling.
- [x] Contracts, state machine and failure/retry/rollback conditions tested.
- [x] Tenant isolation, secret hygiene, input bounds and negative scenarios verified.
- [x] Real performance/quality baseline and release gate metrics recorded where applicable.
- [x] Unit, contract, integration, security and applicable browser tests actually executed.
- [x] API/capabilities/documentation reflect only working qualified features.
- [x] Non-destructive rollback and data preservation proven.
- [x] Actual modified paths, commit, revision and sanitized evidence linked.
- [x] Status changed to COMPLETE only with all measurable criteria supported.

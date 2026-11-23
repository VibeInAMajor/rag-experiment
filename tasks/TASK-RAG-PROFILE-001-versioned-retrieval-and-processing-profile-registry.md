# TASK-RAG-PROFILE-001 — Approved versioned lexical, dense, hybrid and indexing profile registry

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — detailed implementation blueprint; no code changes or runtime tests in this task publication  
**Priority:** P0  
**Dependencies:** Completed API-001 and ARCH-001; coordinate INDEX-001 and EMBED-001 before new mode activation  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target location:** tasks/TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md

## A. Title

Approved versioned lexical, dense, hybrid and indexing profile registry

## B. Context / Problem

The current public contract supports one approved lexical profile via constant POSTGRES_FTS_PROFILE_ID and _REVISION. SearchRequest includes profile_id and expected_profile_revision, but multiple provider-neutral profiles, eligible workspace/corpus, embedding model revisions, candidate caps, score semantics and rollout activation rules are not implemented. A 500/50 chunking policy can be configured without proving a dense model exists. Product requires versioned, truthful capability negotiation and no user-authored graph execution.

## C. Current Repository State

**Source inspection (2026-11-23):** [SQL migration 0001](../apps/workbench/api/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../apps/workbench/api/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../apps/workbench/api/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../apps/workbench/api/contracts.py), [API route owner](../apps/workbench/api/application.py), [Haystack lexical profile](../apps/workbench/api/lexical.py) and [runtime decision](../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
[profiles.py](../apps/workbench/api/profiles.py) declares only postgres-fts-baseline-r1; [application.py](../apps/workbench/api/application.py) _capabilities and _search check fixed lexical IDs and fields; [apps/workbench/document_processing.yaml](../apps/workbench/document_processing.yaml) selects tiktoken o200k_base and independently guarded native Qwen tokens, not a working embedding service. [web App.tsx](../apps/workbench/web/src/App.tsx) has Preview and Live logic. Existing constructor validator on another port checks component construction, not execution authorization.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

## D. Goal

One registered server-approved profile contract covers lexical, dense, hybrid and optionally BM25 variants and their index/data/processor dependencies. UI can discover only usable profiles, submit a revision-fenced request and view exact algorithm/score semantics. Unknown/retired/partial profiles fail before provider or SQL invocation.

## E. Scope

Typed ProfileDefinition/Registry and capability qualifiers, durable profile revisions/rollout state, safe config loader, execution policy mapping to allowlisted Haystack compositions, feature gates, selected profile in UI (only after qualifying backend), auditable candidate/top-K and score-type policies, migration and tests.

## F. Non-Goals

No database/rank improvements or new embedding provider by this task; no dynamic arbitrary node JSON deserialization, no secret-bearing admin API, no editing raw provider DSNs through browser, no global toggle overriding workspace auth.

## G. Architecture / Boundaries

Application policy selects approved ProfileDefinition -> provider-neutral EmbeddingPort/RetrievalPort/IndexGeneration -> concrete adapters. Infra and model IDs live in the composition layer. Server Workbench API owns readiness and validation; UI is a consumer only. Keep existing validator separate.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

ProfileDefinition: profile_id, profile_revision, kind(lexical|dense|hybrid|bm25), workspace eligibility, corpus/index generation selector, model_profile_id?, parser/chunk_profile_revision?, score_type and direction, top_k/query bounds, candidate_k per retriever, fusion algorithm/rrf_k?, filtering policy, profile_state(draft|qualified|active|retired), capability_requirements, timeout, request/ingest/retrieval policy_hash. API request remains {query,top_k,profile_id,expected_profile_revision} until explicitly versioned extension. Query paths return selected profile/index_generation plus per-stage timings only if measured. A config change creates a NEW revision; no in-place drift.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

## I. Repository Files / Components Impacted

MODIFY [profiles.py](../apps/workbench/api/profiles.py), [contracts.py](../apps/workbench/api/contracts.py), [application.py](../apps/workbench/api/application.py), [services.py](../apps/workbench/api/services.py), [lexical.py](../apps/workbench/api/lexical.py), [apps/workbench/document_processing.yaml](../apps/workbench/document_processing.yaml) only for linked provenance; CREATE app-owned profile_registry.py and tests/test_profile_registry.py; UI use [App.tsx](../apps/workbench/web/src/App.tsx) and shared typed API client when ready. MUST NOT edit framework haystack/, existing graph schemaVersion:1 silently or enable unsupported profiles.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

### I.1. Concrete implementation ownership — source reinspection 2026-11-23

| Existing file (direct link) | Symbol, contract and test reuse |
| --- | --- |
| [`apps/workbench/api/profiles.py`](../apps/workbench/api/profiles.py) | currently only postgres-fts-baseline-r1 |
| [`apps/workbench/api/contracts.py`](../apps/workbench/api/contracts.py) | SearchRequest.expected_profile_revision and CapabilitiesResponse |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) | _capabilities/_search fixed allowlist |
| [`apps/workbench/api/lexical.py`](../apps/workbench/api/lexical.py) | approved Haystack baseline |
| [`apps/workbench/web/src/domain/approvedExecution.ts`](../apps/workbench/web/src/domain/approvedExecution.ts) | strict client graph matcher |
| [`apps/workbench/web/src/api/decode.ts`](../apps/workbench/web/src/api/decode.ts) | runtime API contract validation |
| [`apps/workbench/api/tests/test_http_contract.py`](../apps/workbench/api/tests/test_http_contract.py) | profile revision and 409/503 tests |

**Related project, pinned audit sources (architecture/test patterns only):** [`src/enterprise_ai_pipeline/rag/embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py); [`src/enterprise_ai_pipeline/rag/embedding_capacity.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity.py). Donor uses a different physical Qdrant/SQLite index; no code copying without [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) review.

## J. Implementation Requirements — ordered blueprint

1. J1 — Inventory profile constants, Pydantic discriminator literals, capability UI and current errors. Freeze lexical baseline revision and outward contract snapshots. Define explicit score types: postgres_ts_rank_cd, bm25_raw, cosine_distance, rrf_score; never present any as calibrated probability.
2. J2 — Build strict immutable registry using bounded operator configuration. Reject duplicate IDs, invalid model/index dimensions, unknown score directions, missing dependencies and provider SDK names in core domain. Separate display labels from executable profile identifiers.
3. J3 — Implement readiness qualification per profile: real schema, active corpus generation, embedding coverage/model revision and ANN conditions where required; draft/retired profiles must not appear in executable capabilities.
4. J4 — Add app-owned profile resolution to FastAPI, preserving four-field requests, request/capability revision fencing and stable nested error envelope (409 stale/unsupported). Route only to a reviewed composition table, never arbitrary Python class names.
5. J5 — Add typed browser profile selector/diagnostics with fail-closed unknown variants and an explicit Preview vs Live separation; preserving current keyword-only Live path as default. Do not infer a profile from canvas node label.
6. J6 — Test stale profile under live update, concurrent requests, partial index, rollback, missing model provider, invalid config, duplicate IDs and no accidental fallback. Publish profile lifecycle/compatibility runbook.

All implementation methods use descriptive domain names (not task identifiers); all new behavior is fail-closed and traceable. No acceptance box is checked merely because a file was created.

### J7–J13. Executable, file-specific implementation sequence

**J7.** Freeze existing four-field search contract and keyword Live browser behavior; audit component labels versus actual executable backend profiles.

**J8.** Define immutable profile registry for lexical, exact dense, ANN dense, hybrid/RRF, optional BM25 and embedding profiles, with source/index generation and per-workspace authorization.

**J9.** Model `capacity_policy_id` as distinct field referencing TPM-001 (desired 0.92, hard 0.95) without exposing numeric quota controls to untrusted clients.

**J10.** Qualify each profile against actual adapter, embedding coverage, GIN/ANN physical index status, model revision and API authorization; status planned does not imply runnable.

**J11.** Replace hardcoded single profile dispatch with static allowlisted provider-neutral composition; NEVER deserialize arbitrary Python or user graph into runtime components.

**J12.** Extend frontend discovery selector, JSON schema, error status and stale profile invalidation. Test no fallback to fixture Preview on network outage.

**J13.** Test 409 stale, unknown RRF, mixed model versions, missing TPM policy, 503 unready, wrong workspace and old lexical golden regression.

**Cross-task evidence boundary:** [Index/Profile/Dense/ANN/Hybrid roadmap](RAG_INDEX_RETRIEVAL_ENTERPRISE_IMPLEMENTATION_PLAN_2026-11-23.md); [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) is the single owner of actual 0.92/0.95 model admission, and does not turn missing model measurements into success.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

Registry decoder/unit tests; malformed profiles; unsupported score/profile pairing; version mismatch HTTP 409; readiness 503 during missing embedding; UI no fallback, old exact keyword graph; request replay and live reload; cross-workspace profile selection negative; smoke lexical unchanged. Capture safe example CapabilitiesResponse and app revision.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

### L.1. Specialized test matrix / release gate

- [ ] Execute primary owner-specific tests named in I.1 and new focused unit and disposable PostgreSQL integration tests for this stage; attach actual commands/output.
- [ ] Prove 400/404/409/429/503/504 failure/cancellation, source-version drift, tenant RLS, safe trace IDs and absence of fixture fallback.
- [ ] Compare real source/result identities with independently checked PostgreSQL response and report quality/latency sample counts; no synthetic numerical performance claims.
- [ ] Re-run workbench-api Hatch check/test/types and (if browser touched) npm typecheck/test/build, Preview/validation/Live browser regression.

## M. Acceptance Criteria

- [ ] Baseline lexical profile remains byte-compatible and continues passing current gold tests
- [ ] New profiles must be qualified before Live advertisement and execution
- [ ] Stale/retired/unknown profile yields 409 and zero SQL/embedding work
- [ ] Profile revision and source/index generation are visible and traceable
- [ ] API and UI do not fabricate BM25, cosine or RRF scores
- [ ] No arbitrary Haystack graph execution via profile input
- [ ] Out-of-bounds top_k/candidate_k rejected before search
- [ ] All contract/unit/e2e regression gates recorded

## N. Documentation / Migration / Compatibility / Rollback

Registry migrations additive if durable state is required. Roll out as read-only capabilities then approved execution. Disable new profile on error while leaving previous lexical generation visible; never rewrite historical profile identity. Model changes require independent embedding generations, not mutating old rows in place.

Update [API README](../apps/workbench/api/README.md), architecture and this task with exact evidence and compatibility details before marking ready.

## O. Mandatory Completion Checklist

- [ ] Section C revalidated against actual repository and completed tasks; gaps identified with source evidence.
- [ ] Existing ports/services reused without duplicate SQL, tokenizer, registry or provider coupling.
- [ ] Contracts, state machine and failure/retry/rollback conditions tested.
- [ ] Tenant isolation, secret hygiene, input bounds and negative scenarios verified.
- [ ] Real performance/quality baseline and release gate metrics recorded where applicable.
- [ ] Unit, contract, integration, security and applicable browser tests actually executed.
- [ ] API/capabilities/documentation reflect only working qualified features.
- [ ] Non-destructive rollback and data preservation proven.
- [ ] Actual modified paths, commit, revision and sanitized evidence linked.
- [ ] Status changed to COMPLETE only with all measurable criteria supported.

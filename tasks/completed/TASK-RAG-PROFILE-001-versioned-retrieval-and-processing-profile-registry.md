# TASK-RAG-PROFILE-001 — Approved versioned lexical, dense, hybrid and indexing profile registry

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** COMPLETE — immutable registry, durable rollout, API/client fences, real PostgreSQL/browser checks and local migration passed
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

**Implementation reinspection (2026-11-23):** working-tree base is `44866bb7e7dc01993bbaefefdec1ab1985951cc7`, including the completed INDEX-001 changes. Additive migration `0003`, `postgres_indexes.py`, `PersistencePort.current_index_generation()` and `corpus_summary()` now own persisted lexical generations; `0003` was explicitly applied to the existing development database. Preserve the applied SQL and all prior working-tree changes. The HTTP and browser still hardcode the single lexical profile. Real embedding, ANN, hybrid and BM25 execution are absent and must remain unavailable. Navigation references actually live in [`docs-website/PROJECT_MAP.md`](../docs-website/PROJECT_MAP.md) and [`docs-website/ENGINEERING.md`](../docs-website/ENGINEERING.md).

## D. Goal

One registered server-approved profile contract covers lexical, dense, hybrid and optionally BM25 variants and their index/data/processor dependencies. UI can discover only usable profiles, submit a revision-fenced request and view exact algorithm/score semantics. Unknown/retired/partial profiles fail before retrieval SQL or embedding/provider work. Pure malformed, unknown-ID and unknown configured-revision preflight rejects before persistence. A known profile's live retirement or revision change requires a bounded durable metadata fence; those metadata reads are not represented as zero SQL.

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

**Reconciled implementation ownership:** the pure typed registry belongs in `profile_registry.py`; durable revisions, workspace rollout/audit state and explicit operator commands belong in a PostgreSQL adapter and the next additive `0004` migration, reusing `db_migrations.py`. Extend persistence/configuration seams and runtime composition without moving SQL into application policy. Focused integration tests cover the registry's actual route/lifecycle behavior. The browser selector extends existing discovery/cancellation and typed decoders. The existing document-processing settings and fingerprint remain the processor source of truth; this task links their provenance rather than creating another parser/chunker registry.

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
2. J2 — Build strict immutable registry using bounded operator configuration. Reject duplicate `(profile_id, profile_revision)` pairs, invalid model/index dimensions, unknown score directions, missing dependencies and provider SDK names in core domain. Multiple distinct immutable revisions of one profile ID are retained for audited rollout/rollback; the durable workspace binding selects at most one current revision of that ID. Separate display labels from executable profile identifiers.
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

- [x] Execute primary owner-specific tests named in I.1 and new focused unit and disposable PostgreSQL integration tests for this stage; attach actual commands/output.
- [x] Prove 400/404/409/429/503/504 failure/cancellation, source-version drift, tenant RLS, safe trace IDs and absence of fixture fallback.
- [x] Compare real source/result identities with independently checked PostgreSQL response and report quality/latency sample counts; no synthetic numerical performance claims.
- [x] Re-run workbench-api Hatch check/test/types and (if browser touched) npm typecheck/test/build, Preview/validation/Live browser regression.

## M. Acceptance Criteria

- [x] Baseline lexical profile remains byte-compatible and continues passing current gold tests
- [x] New profiles must be qualified before Live advertisement and execution
- [x] Stale/retired/unknown profile yields 409 and zero retrieval/embedding work; pure unknown/malformed/configuration-revision preflight performs no persistence, while live durable state uses a bounded metadata fence
- [x] Profile revision and source/index generation are visible and traceable
- [x] API and UI do not fabricate BM25, cosine or RRF scores
- [x] No arbitrary Haystack graph execution via profile input
- [x] Out-of-bounds top_k/candidate_k rejected before search
- [x] All contract/unit/e2e regression gates recorded

## N. Documentation / Migration / Compatibility / Rollback

Registry migrations additive if durable state is required. Roll out as read-only capabilities then approved execution. Disable new profile on error while leaving previous lexical generation visible; never rewrite historical profile identity. Model changes require independent embedding generations, not mutating old rows in place.

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

## P. Implementation and qualification record — 2026-11-23

Implementation uses working-tree base `44866bb7e7dc01993bbaefefdec1ab1985951cc7` and preserves preceding INDEX-001 changes and applied `0001`–`0003` SQL. The [profile operations guide](../docs-website/docs/architecture/profile-registry.md) owns exact configuration/lifecycle/rollback commands. The [qualification report](evidence/profile-2026-11-23/report.md) links actual HTTP, SQL, browser and regression artifacts; this task does not imply a commit or production deployment.

### Reuse, changed owners and intentional contract decisions

- `profile_registry.py` adds frozen typed definitions, safe bounded YAML, policy hashes and exact identity/workspace resolution. It reuses the established document-processing YAML node decoder rather than introducing another loader policy.
- Additive `0004`, `postgres_profiles.py` and existing `db_migrations.py` own immutable definitions, workspace rollout/audit state, compare-and-set lifecycle changes and atomic administrator promotion/rollback. The application role reads these records; startup does not write them.
- `profiles.py`, configuration, persistence/service composition, `lexical.py`, the existing PostgreSQL adapter and HTTP boundary reuse source generations, RLS, the approved FTS Haystack component and projection. Policy and rollout fences are checked in the same read snapshot before candidate SQL; wrong result attribution refuses safely.
- The browser's existing discovery, decoder, selector/session and graph matcher consume approved lexical identities and bounds. Unknown/stale/withdrawn selections require refresh and explicit choice; Preview, constructor validation and Live provenance remain separate.
- Applied source/vector data, `schemaVersion: 1`, the four-field request, baseline descriptor/response keys and raw score meaning stay compatible. Existing descriptor schemas admit other approved lexical IDs/revisions and tighter limits, with matching regenerated OpenAPI/client validation. Existing `corpus_revision` remains the visible persisted source/index identity; internal policy hash and numeric index generation are logged without adding baseline response fields.
- Existing document-processing settings and per-source fingerprints remain authoritative. Optional processing/model/capacity references cannot attest their own compatibility. Only actual `postgres_fts` compositions qualify; semantic/ANN/RRF/BM25 execution remains unavailable.

### Executed focused and runtime checks

`hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_profile_routes.py --tb=short --junitxml=tasks/evidence/profile-2026-11-23/profile-routes.xml` passed **24 real PostgreSQL tests** in 18.44 seconds, after explicit disposable-test DSN configuration. The registry owner additionally tested malformed policies/configuration, immutable drift, populated migration/backfill and the workspace-binding budget. The [route artifact](evidence/profile-2026-11-23/profile-routes.xml) and [focused registry/route artifact](evidence/profile-2026-11-23/profile-regressions.xml) preserve exact case results.

The [isolated HTTP artifact](evidence/profile-2026-11-23/http-rollout.json) records two actual lexical profiles on an owned UUID-named database and API port 8021, administrator retirement/reactivation, retired-request HTTP 409, independent application-role SQL identity/score parity, and actual API process restart with the same corpus/results. The owned API/database were cleaned up. No main application data is used as synthetic test input.

The [sanitized browser artifact](evidence/profile-2026-11-23/browser-smoke.json) records real selection of `postgres-fts-focused` / `focused-r1` with top-K ceiling 3 and truthful FTS output. Actual withdrawal leaves no selected replacement, disables Run and hides old results; explicit baseline recovery works. Existing Preview/validator smokes and Live regression passed separately; the Live regression includes three real queries, nine injected failures and Stop/late-response behavior. Screenshots cover 1440/1100 selection and explicit baseline recovery. Frontend typecheck/format/build and 350 tests in 18 files passed; regenerated OpenAPI/client-focused checks passed 97 tests.

### Risks and bugs addressed

Review caught a non-atomic promotion/rollback window, source growth between application and SQL qualification, missing result policy attribution and binding-budget overflow that could hide the existing baseline. Shared transactional promotion, same-snapshot admission, strict result provenance and the pre-write 64-binding guard address those cases. Known durable retirement checks use bounded metadata SQL; they are not falsely described as zero SQL. Profile/file reload and database lifecycle update are separate: load new configured revisions on API restart before promoting them, retain the preceding revision for rollback, and use the current rollout version for compare-and-set changes.

Native model/TPM/ANN/semantic qualification remains owned by its separate tasks. Retired bindings count toward the workspace budget; no unreviewed deletion/retention workflow is introduced.

### Final regression and quality results

The final `hatch run workbench-api:test --tb=short --junitxml=tasks/evidence/profile-2026-11-23/full-tests.xml` run passed **984 tests**, with **16 skipped**, zero failures/errors, in 253.44 seconds. All profile/PostgreSQL cases executed. Every skip is a native Qwen tokenizer counting/provisioning case requiring absent `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; no model admission is certified. The [JUnit property](evidence/profile-2026-11-23/full-tests.xml) records lexical exact 10/10 and the same three diagnostic paraphrase misses. HTTP 400/404/409/429/503/504, cancellation, source-version, RLS and SQL parity regression cases passed.

`hatch run workbench-api:check` and `hatch run workbench-api:types` passed across 100 API source files; [quality output](evidence/profile-2026-11-23/quality-checks.txt) is retained. The combined focused [registry/route artifact](evidence/profile-2026-11-23/profile-regressions.xml) records 54 passes and zero skips. The new script/route suite also passed focused Ruff/format and mypy checks. Documentation relative targets, strict UTF-8/newlines, unique sidebar entry, Node sidebar syntax, release-note backticks and `git diff --check` passed. Docusaurus full build was not run because its `node_modules` is absent; Haystack core checks were not run because framework code is unchanged. Actual frontend/browser gates are recorded above.

### Existing local upgrade and completion

After stopping the verified old API, the existing development database was backed up to `workbench-before-0004-20261123-210904.dump` and its archive list verified. The explicit migrator upgraded `0003` → `0004` compatibly. Counts and full-record SHA-256 signatures matched for all nine preceding tables, including source/vector data and persisted generation history. Manifest reconciliation remained consistent at generation 1, with 15 active sources and 44 active chunks. No reseed or extra main profile alias was introduced.

The restarted actual API 8011 returned readiness 200 and the qualified baseline. Its real PostgreSQL query returned three results matching independently checked SQL identities/raw scores. [Local deployment evidence](evidence/profile-2026-11-23/deployment.json) records backup hash, table signatures, profile/corpus identity and safe trace `8991171fa702478ab512d8e3a8cf1df1`; [the full report](evidence/profile-2026-11-23/report.md) records boundaries and reproduction. Status is COMPLETE for this profile-registry task, without implying semantic inference, ANN, new production authentication or a production deployment.

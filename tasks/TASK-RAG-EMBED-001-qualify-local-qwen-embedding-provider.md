# TASK-RAG-EMBED-001 — Qualify local Qwen3-Embedding-4B provider and model-neutral embedding port

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — detailed implementation blueprint; no code changes or runtime tests in this task publication  
**Priority:** P0  
**Dependencies:** Completed DB-001, parser/chunking profiles; coordinate PROFILE-001 and EMBED-002  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target location:** tasks/TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md

## A. Title

Qualify local Qwen3-Embedding-4B provider and model-neutral embedding port

## B. Context / Problem

The current database accepts nullable vectors and a synthetic-test-v1 embedding profile; actual ingestion never calls a model and currently blocks non-null embeddings in the durable publication path. Before changing storage, qualify the intended local TEI Qwen3-Embedding-4B runtime and its real I/O contract on the RTX 4090 24GB; prior discussions also considered Ollama. Never infer model identity from a URL, JSON field label or a generic tokenizer.

## C. Current Repository State

**Source inspection (2026-11-23):** [SQL migration 0001](../apps/workbench/api/migrations/0001_initial.up.sql) contains workbench.sources, source_versions, chunks and nullable public.vector embeddings, generated tsvector and GIN; [migration 0002](../apps/workbench/api/migrations/0002_ingestion_jobs.up.sql) adds transactional durable jobs. [PostgresPersistence](../apps/workbench/api/postgres.py) owns _publish(), _corpus_snapshot(), lexical_search_snapshot() and vector_search(). [Postgres ingestion](../apps/workbench/api/postgres_ingestion.py) calls _publish in the same transaction as terminal job completion. [FastAPI contracts](../apps/workbench/api/contracts.py), [API route owner](../apps/workbench/api/application.py), [Haystack lexical profile](../apps/workbench/api/lexical.py) and [runtime decision](../docs-website/docs/architecture/rag-runtime-contract.md) are the current authority. The local only workspace resolver is not production multi-tenancy.
[model_token_counter.py](../apps/workbench/api/model_token_counter.py) counts actual tokens for admission but is not an embedding transport. [document_processing.yaml](../apps/workbench/document_processing.yaml) uses o200k_base split and a native model guard. The [runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) currently selects local TEI at 127.0.0.1:8081 and Qwen3-Embedding-4B up to 2560 dimensions, but explicitly requires runtime verification. vector_search exists for exact cosine; no model output is recorded. External Qwen model card reports up to 2560 output dimensions with MRL support.

**Evidence discipline:** paths and symbols above were read from the inspected commit; readiness/throughput on another machine have not been measured by creating this task. At implementation start recheck source, tests and manifest against working tree; when source differs, update this A–O blueprint before expanding scope.

## D. Goal

Provider-neutral EmbeddingPort supports query and document embeddings from a **verified** local model profile with deterministic input preparation, versioned tokenizer/model digest, finite normalized output and bounded error/time/throughput behavior. A live smoke on configured hardware records real 2560-dimension vectors or explicitly documents a different verified dimension; a provider outage never produces synthetic vectors.

## E. Scope

Qualify runtime endpoint, model digest, version, instruction/prefix behavior, max tokens and output dimensions; local TEI adapter via approved API, optional alternative adapter only with equivalent tests; query/document text input policies, bounded concurrency/retry/TPM; fake provider and real gated smoke; embedding profile registration and runbook.

## F. Non-Goals

No backfill, no DB mass writes, no ANN, no hybrid, no cloud default or API keys in docs, no general answer generator. Choosing local TEI here does not architecturally prohibit another provider adapter.

## G. Architecture / Boundaries

EmbeddingPort accepts EmbeddingRequest(profile_id, task_kind, texts, input_hashes, deadline) and returns typed EmbeddingBatch. TEI/Ollama implementations live in adapter module; domain/application orchestrator cannot import SDKs. Tokens budget, output normalization and model digest checked before vector persistence.

**Mandatory boundaries:** domain/application must not import provider-specific SDKs, HTTP does not execute browser-authored graph JSON or raw SQL, persistence stays behind app-owned ports. Review [canonical runtime contract](../docs-website/docs/architecture/rag-runtime-contract.md) and previously delivered [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) when evidence is relevant.

## H. Contracts / Interfaces / Data Model

EmbeddingProfile: model_profile_id/revision, provider_adapter_id, model_digest, tokenizer_digest, input_format_revision, task_kind document/query, dimension (verified, 32..2560 subject actual), normalized boolean, max_tokens, max_batch_tokens, max_batch_items, supported instruction behavior, timeout, retryable errors. EmbeddingBatch: vectors ordered 1:1 with hashes/IDs, finite list float of exactly profile dims, token counts, model_revision, timing; reject wrong ordering, NaN, short arrays or response model mismatch. Normalization/float precision must be explicit; query-vs-doc instruction rules must be pinned.

All new externally exposed fields require exact Pydantic/OpenAPI agreement and a matching typed client decoder; additional fields never imply a feature is executable. Validate malformed and unauthorized inputs before expensive provider work.

## I. Repository Files / Components Impacted

CREATE apps/workbench/api/embedding.py (port/types), embedding_adapters.py (local TEI adapter or task-approved path), tests/test_embedding_adapter.py, tests/test_embedding_model_smoke.py (gated); MODIFY profiles.py, config.py and ops docs only for qualified model profile and reference; update dedicated configuration e.g. apps/workbench/embedding_profiles.yaml with placeholders only. Read model_token_counter.py and current token profile; MUST NOT change SQL 0001/0002, current PostgreSQL index/scoring or Preview fixtures.

**MUST NOT:** duplicate source registry, migration ownership, transport adapters, file ingestion jobs or framework components. If another component is materially affected, revise this section and its tests before coding.

### I.1. Source-level reuse matrix — refreshed 2026-11-23

**Recipient code anchors (real files, inspected):**

| Repository file | Existing owner; exact integration role |
| --- | --- |
| [`apps/workbench/api/model_token_counter.py`](../apps/workbench/api/model_token_counter.py) | native model tokenizer input admission, NOT model embedding transport |
| [`apps/workbench/api/document_processing.py`](../apps/workbench/api/document_processing.py) | processing profile and token settings; do not confuse with throughput TPM |
| [`apps/workbench/document_processing.yaml`](../apps/workbench/document_processing.yaml) | current o200k_base 500/50 and pinned native admission policy |
| [`apps/workbench/api/config.py`](../apps/workbench/api/config.py) | runtime settings, no committed secret or permissive endpoint |
| [`apps/workbench/api/profiles.py`](../apps/workbench/api/profiles.py) | only lexical server profile exists, new embedding capability must be qualified |
| [`apps/workbench/api/tests/test_model_token_counter.py`](../apps/workbench/api/tests/test_model_token_counter.py) | existing source-token tests; preserve |
| [`docs-website/docs/architecture/rag-runtime-contract.md`](../docs-website/docs/architecture/rag-runtime-contract.md) | TEI Qwen target, expected 2560 and transport qualification |

**Pinned previous-project candidates (do NOT copy unlicensed code or Qdrant/SQLite infrastructure):** donor commit `955fd049949d3fc462d555be14774e4b255aa15c`.

| Pinned previous-project source | Targeted symbol/behavior |
| --- | --- |
| [`src/enterprise_ai_pipeline/providers/tei_embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_embeddings.py) | TEIEmbeddingProvider.prepare_transport/_tokens/_dispatch_execute |
| [`src/enterprise_ai_pipeline/providers/tei_profile.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_profile.py) | TEIProfile and model/digest/capacity validation; donor target defaults differ |
| [`src/enterprise_ai_pipeline/rag/embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py) | EmbeddingRequest/Batch/Provider contracts and FakeEmbeddingProvider |
| [`src/enterprise_ai_pipeline/rag/embedding_capacity.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity.py) | capacity policy; must not duplicate TPM-001 |
| [`tests/pipeline/test_tei_embedding_provider.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_tei_embedding_provider.py) | model/response, request batching, tokenizer/gated test scenarios |
| [`LICENSE.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) | PolyForm Strict: explicit cross-product permission before literal copy |

**Reuse decision gate:** compare current component to donor behavior, list reusable algorithm/contract, incompatibilities and the exact owner of PostgreSQL/model/tokenizer state. Code copying requires permission under [donor LICENSE](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md); otherwise independently implement compatible behavior and port test **scenarios**. Existing completed Workbench components must not be replaced without a measurable reason.

## J. Implementation Requirements — ordered blueprint

1. J1 — Inspect actual local TEI health/model metadata, served endpoint, response field naming, error shapes, startup options and the pinned Qwen model/tokenizer digest. Distinguish model card nominal 2560 from real service output; document local CUDA/device memory and max batch size without asserting unobserved throughput.
2. J2 — Define model-neutral port and typed versions; keep public error codes model-unavailable/rate-limited/invalid-dimension/request-too-large without exposing URLs/tokens. Unit-test fake deterministic provider with known vectors, ordered batches and cancellation.
3. J3 — Implement the reviewed local adapter with explicit query/doc instruction/text format, tokenizer counted on **actual sent text**, bounded batch cardinality and concurrency; no silent switch to another provider on failure. Require validated finite vector lengths and optional normalization policy.
4. J4 — Register qualified model profile with verified dimensions/digest/normalization; run document and query embedding smoke on at least 30 representative texts (EN/RU/UK/code/long text). Test repeatability and cross-language behavior, report cosine similarity distributions not unsupported quality guarantees.
5. J5 — Benchmark RTX 4090: warm/cold latency p50/p95, throughput tokens/s, max concurrent requests, memory peak, retries, timeouts; use current runtime and bounded admissions. Define defaults from measured limits, not guess-based TPM.
6. J6 — Produce adapter/reference tests and safe setup guide. Gate capability until model responds, signature matches and all required errors are controlled.

All implementation methods use descriptive domain names (not task identifiers); all new behavior is fail-closed and traceable. No acceptance box is checked merely because a file was created.

### J7–J14. Detailed, source-grounded implementation handoff — 2026-11-23

**Step J7 —** Define one app-owned EmbeddingPort interface accepting immutable profile, purpose=query/document, ordered ID/text items and monotonic deadline. Ensure no donor package import in domain and fail if local real model service has not been positively attested.

**Step J8 —** Compare the donor TEI native `/embed` payload (`inputs`, `truncate:false`, `normalize:true`) against the running Workbench endpoint; explicitly test `/v1/embeddings` versus `/embed` and select exactly one qualified adapter. Document response shape, rate headers (if any), timeout and batch semantics; do not assume native returned token usage.

**Step J9 —** Model qualification: read `/info`/health as appropriate, pin served model digest and tokenizer digest, reject response mismatch, preserve query instruction/character encoding and log no full input. Verify exactly 2560 (or actual measured) finite values, norm, stable ordering and no implicit truncation.

**Step J10 —** Make EmbeddingPort emit `usage_provenance=provider_reported|tokenizer_counted_proxy|unknown`; the donor's TEI adapter frequently returns its locally tokenized count as usage_tokens. Do not call a token-count proxy measured provider-reported completed TPM.

**Step J11 —** Integrate «reserve -> provider -> finish» only through TPM-001's one shared governor when active; query and document transports cannot open an ungoverned second provider client. A model health probe is not an inference capacity bypass.

**Step J12 —** Write a real model-gated smoke on a local RTX 4090 and 30 representative texts (EN/RU/UK/code/boundary lengths), recording p50/p95, 2560-dim validation, GPU peak, model token parity and the observed/unknown actual usage field. Keep fake provider pure unit tests completely offline.

**Step J13 —** Record donor reuse decision: code copying subject to LICENSE permission; otherwise adapt interface and test scenarios independently. Qdrant/SQLite code and historical TPM claims are not portable to the Workbench database.

**Mandatory dependency handshake:** [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) owns 0.92 desired / 0.95 hard admission and all query/document model calls; do not implement an independent limiter.

## K. Security / Governance / Observability

Enforce server-resolved WorkspaceContext and database RLS on each operation. Never trust client-supplied scope, source/file paths, graph JSON or model IDs as authorization. Protect secrets through runtime secret references; redact input text, original assets, embeddings, DSNs, API keys and model prompts from traces. Log only safe opaque IDs, profile/generation/revision, status/error category, counts, timings and trace_id. Handle prompt-injected document text as untrusted data. Bound request/token/GPU/SQL memory and concurrency; record retention and cross-workspace negative tests. Do not equate quality-confidence with authorization.

## L. Testing / Evaluation / Runtime Verification

Provider fake and optional real TEI smoke; 30 mixed texts, Unicode, empty, over token cap, wrong dimension, NaN, duplicate missing result, out of order, 429/503/timeout, canceled call, model hot reload identity drift, tokenizer mismatch and network outage. Verify no credentials in logs and no vector output inferred from token guard. No DB reindexing required for this task.

**Execution baseline:** use existing Hatch application commands `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types`, the pinned PostgreSQL Docker environment and explicitly disposable test data. If UI changes, run `npm run typecheck`, `npm test`, `npm run build` from `apps/workbench/web`, plus existing Preview/validator/Live smoke. Capture exact executed commands, versions, sanitized HTTP/SQL and real PASS/FAIL/SKIP results; NO invented latency.

### L.1. Reuse-specific test migration and verification

- [ ] test_embedding_adapter.py: invalid model digest, missing/changed tokenizer, unsupported request dimension, NaN/zero norm, row count mismatch, order reversal, TEI 429/timeout/redirects, invalid UTF-8 and missing usage.
- [ ] test_embedding_model_smoke.py (explicitly enabled): 30 texts with an actual local model, query/doc instruction parity, normalized vector lengths and no cloud network.
- [ ] Model/TPM integration: with TPM-001 no simultaneous query+document reservations over hard 0.95; if capacity unknown, fail safely and report NOT_QUALIFIED, not a fake quota.

**Proof requirements:** record donor behavior source commit, recipient code and exact executed test commands. Donor unit tests **do not** demonstrate recipient functionality; recipient CI evidence must exercise the actual PostgreSQL/TEI/client paths. Capture a fixture-vs-runtime result matrix, error correlation and no-secrets logs.

## M. Acceptance Criteria

- [ ] One model-neutral EmbeddingPort with fake tests and verified local TEI adapter
- [ ] Actual served model digest/tokenizer/output dimensions recorded; no assumption that 2560 is observed before probe
- [ ] Real 30-text query/doc smoke returns finite properly normalized vectors with correct ordering and task formatting
- [ ] Runtime failure/identity drift disables provider capability without synthetic fallback
- [ ] Measured tokens/s, memory and latency are recorded on actual target GPU or explicitly NOT TESTED
- [ ] No raw texts in logs or cloud requests enabled by default
- [ ] Existing FTS, token chunking and DB regression checks pass

- [ ] A pinned donor source-to-recipient decision table records whether exact TEI adapter can be reused and why
- [ ] Observed usage provenance is never conflated with provider billed/actual tokens
- [ ] Real provider requests are quota-governed by one TPM-001 owner; a separate ungoverned embedding client cannot pass tests

## N. Documentation / Migration / Compatibility / Rollback

Preserve provider-neutral API and keep model disabled if unqualified; no DB migration here. Alternate runtime adapters only after same qualification. Upstream model updates require new model profile revision and downstream reembedding, not same identity under new weights.

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

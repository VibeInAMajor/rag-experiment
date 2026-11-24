# TASK-RAG-TPM-001 — Adaptive embedding TPM/RPM governor with 0.92 target and 0.95 hard ceiling

**Created:** 2026-11-23  
**Updated:** 2026-11-24  
**Status:** IN PROGRESS — EMBED-002's measured single-owner prerequisite passes its actual ten-minute steady-window/hard-ceiling gate; broader 30-minute and wider concurrency matrix remain unrun
**Priority:** P0 — independent prerequisite for high-volume real embedding ingestion  
**Dependencies:** [EMBED-001](TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md), [PROFILE-001](TASK-RAG-PROFILE-001-versioned-retrieval-and-processing-profile-registry.md); block actual real dispatch until EMBED-001 validates runtime; integrate into [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) and [SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md).  
**Recipient repository source inspected:** `4d3292f81e55aa66cda4df97831b7eefe7b1f858` plus this task's working-tree changes (historical proposal: `fe171f5273b2dfa3db536c8bc8ffeae8f3aa582e`)
**Donor source pinned:** `955fd049949d3fc462d555be14774e4b255aa15c`  
**Target:** `tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md`  
**Canonical progress/checklist:** [MVP plan](../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md)

## A. Title

**EMBED-001 bootstrap boundary (2026-11-23):** this task remains open for production admission. Its J1 exception for an explicit conservative single-test qualification profile is implemented by the app-owned `embedding_dispatch.py` boundary: one in-flight request, exclusive deployment file lock, bounded cumulative requests/native-token estimates and deadlines, shared query/document `reserve → mark_sent → finish`, with no post-send charge refund. This is a finite model-I/O qualification run, not calibrated sustainable capacity. Normal production dispatch remains refused with unknown capacity; no rolling 0.95 ceiling, adaptive 0.92 target, saturation/fairness or steady-window performance acceptance is claimed. See [EMBED-001 evidence](evidence/embedding-2026-11-23/report.md) and its [operator guide](../docs-website/docs/architecture/local-embedding-provider.md).

**EMBED-002 required dependency (2026-11-24):** the user authorizes the measured shared governor needed for real durable backfill and a ten-minute 0.92-target experiment. `embedding_capacity.py` is the sole measured owner, sharing its deployment lease boundary with qualification mode. Calibration, persisted rolling charges, bounded queues/RPM/workspace fairness and expiring runtime-bound capacity are independently implemented; they do not reuse donor quota claims. No acceptance box is checked until actual evidence in [EMBED-002's report](evidence/embedding-2026-11-24/report.md) supports it. The physical GPU remains shared, and no generative quality judge is introduced.

**Qualification scope:** EMBED-002 accepts only its required measured single-owner prerequisite after the actual 600-second gate. This broader task stays IN PROGRESS for the unrun 30-minute and wider batch/concurrency matrix. The observed 622592-token/minute denominator is the highest sustainable result among the declared tested candidates, not a globally proven GPU maximum or an assigned quota over other projects.

**Required-scope result (2026-11-24):** [actual evidence](evidence/embedding-2026-11-24/report.md) records 600.969 seconds, unchanged Q/profile/code hashes, continuous ready backlog, zero errors/unknown usage/hard breaches and an independent event replay. Steady median was 92.141081157%, with 53/55 steady windows in the 90–95% band, satisfying the predeclared gate. Whole-run completed utilization was **91.992753788%, BELOW exact 92%**; this limitation remains visible. This result completes the required EMBED-002 dependency without marking the broader checklist below complete or claiming a TPM UI/global GPU allocation.

Implement an application-owned **shared deployment capacity governor** for text embeddings with desired utilization `0.92` and independent hard **rolling-60-second admission ceiling `0.95`**, reusing/adapting vetted donor components and test scenarios without importing Qdrant, its runtime or an unapproved code license.

## B. Context / Problem

The target local TEI/Qwen3-Embedding-4B GPU service has finite **measured sustainable capacity**, even without a cloud provider quota. At the proposal baseline, Workbench had token counting and local ingestion but lacked a qualified embedding adapter and measured shared admission. EMBED-001 subsequently qualified the real adapter; the EMBED-002 implementation now adds the measured shared dispatcher and actual main-corpus backfill. The current [execution report](evidence/embedding-2026-11-24/report.md) separates completed gates from the pending ten-minute experiment. A query and ingestion worker must not independently send at 92% of the same quota. Token estimates and successful provider usage are different measurements, and the donor TEI adapter may report its own tokenizer-counted usage rather than native provider-reported usage.

The donor code is a valuable starting point but its defaults differ: `EmbeddingCapacityPolicy.target_utilization_ratio = 0.85`, whereas donor `TEIProfile.target_utilization_ratio = 0.9`. In the current donor `EmbeddingDispatchController._wait_needed` the rolling reservation budget is **the full assigned tpm**, not `0.95 * Q_TPM`; configuring target 0.92 alone does not prove a 95% hard ceiling. We must introduce independent policy fields for operating target and hard admission budget, then run deterministic and live capacity tests.

## C. Current Repository State

### Recipient: verified existing owners and gaps

The table below records the proposal baseline. Current recipients are `embedding_capacity.py` for the measured shared governor, `embedding_ingestion.py` for leased bounded work and the backfill/calibration CLIs for explicit runtime composition. `embedding_jobs.py` and `postgres_embeddings.py` add generation-fenced persistence through migration `0005`. The qualified adapter/model/tokenizer remain reused; lexical HTTP retrieval remains unchanged. Actual calibration and main backfill are linked in the execution report; they do not by themselves prove a ten-minute 92% completion result.

| Path / symbol | Existing implementation | Reuse / gap |
| --- | --- | --- |
| [model_token_counter.py](../apps/workbench/embedding/model_token_counter.py) | Pinned native Qwen tokenizer admission support for processing limits | This counts/model-bounds inputs; it is **not** a TPM dispatcher or completed usage meter. |
| [document_processing.yaml](../apps/workbench/document_processing.yaml) and [document_processing.py](../apps/workbench/configuration/document_processing.py) | Explicit 500/50 `o200k_base` token chunking and optional native model guard | Do not conflate splitter tokens with embeddings' actual query/document input token counts. |
| [ingestion.py](../apps/workbench/ingestion/ingestion.py) | Bounded parse/chunk/publish workflow; no model embedding requests | Future embedding worker must request shared capacity **before** provider send. |
| [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) | Durable job reservations and active source/version publication | No quota accounting in DB by default; avoid holding write transaction while waiting on capacity. |
| [profiles.py](../apps/workbench/retrieval/profiles.py) | Only `postgres-fts-baseline-r1` executable profile | New governor settings belong to independently qualified embedding/deployment profile. |
| [lexical.py](../apps/workbench/retrieval/lexical.py) | Real Haystack lexical retrieval; no query model call | Keep lexical search available on TEI/TPM outage; future Dense QueryEmbedder shares the governor. |
| [config.py](../apps/workbench/configuration/config.py), [boundary.py](../apps/workbench/api/boundary.py) | Validated local configuration and safe event logging | Add explicit non-secret TPM policy and redacted diagnostics; never mutate FastAPI readiness to fake success. |
| [tests/test_model_token_counter.py](../apps/workbench/embedding/tests/test_model_token_counter.py), [tests/test_ingestion_stability.py](../apps/workbench/api/tests/test_ingestion_stability.py) | Token and upload capacity regression | Add separate scheduler tests without duplicating input-splitting tests. |

### Donor: exact code and portability decision

| Pinned donor source | Symbols | Proposed reuse | Constraint |
| --- | --- | --- | --- |
| [`rag/embedding_dispatch.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_dispatch.py) | `EmbeddingDispatchController.reserve/finish`, `_wait_needed`, `_pacing_rates`, `_capacity` | Reuse algorithm/contract for reservations, bounded condition waits, retry cooldown, capacity state and reconciliation | Process-local controller; improve **independent** 0.95 hard ceiling and multi-worker ownership. |
| [`rag/embedding_capacity.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity.py) | `EmbeddingCapacityPolicy`, `AssignedEmbeddingCapacity`, `EmbeddingCapacityObservation`, `EmbeddingDispatchScope` | Adapt immutable validated policy, assigned local benchmark capacity and cancellable deadlines | Default is 0.85, not 0.92; local capacity must be measured and share must be explicit. |
| [`rag/embedding_capacity_windows.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity_windows.py) | `EmbeddingCapacityWindows.advance/success/tokens_per_minute` | Reuse duration-weighted completed windows, saturation/unknown states, no fabricated success | Unknown provider actual usage = NOT_MEASURABLE for that metric. |
| [`rag/embedding_execution.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_execution.py) | `execute_embedding_windows` bounded concurrent transport pump | Reuse bounded concurrency and late-paid-result recovery pattern | Adapt to async FastAPI/worker ownership, not donor `ThreadPoolExecutor` wholesale. |
| [`providers/tei_embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_embeddings.py) | `TEIEmbeddingProvider._dispatch_execute`, `prepare_transport`, `_tokens` | Use explicit reserve → execute → finish integration with proper error ownership and model identity | Donor uses native TEI `/embed`; Workbench may use OpenAI-compatible `/v1/embeddings`; verify actually served endpoint. Donor `usage_tokens` is often local tokenizer count, not native usage. |
| [`rag/embeddings.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py) | `EmbeddingRequest`, `EmbeddingBatch`, `EmbeddingProvider`, fake | Reuse neutral model contracts and tests conceptually | Do not force donor types/SDK or duplicate Workbench's new EmbeddingPort. |
| [TPM smoothing audit](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md) | Weighted pacing, batch packing, ready-watermark, failure investigation and instrumentation design | Implementation/benchmark **guide**; audit is not evidence that Workbench achieved 92–95% | Original donor audit reports problems with source starvation, quota confidence and missing capacity proof; do not copy optimistic conclusions. |
| [TEI unit tests](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_tei_embedding_provider.py), [embedding/vector tests](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_embeddings_and_vector_store.py) | Transport error/dimension/selection cases | Port scenarios into independent Workbench fake-provider and real local TEI gated tests | Do not import donor test infrastructure relying on Qdrant/SQLite. |
| [LICENSE.md](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md) | PolyForm Strict 1.0.0 / Authorized Evaluation | **Owner license/rights gate before copying donor implementation** | Source available is not unrestricted reuse. If rights not documented, implement compatible behavior independently; preserve provenance and external dependency notices. |

**Inspection evidence:** the donor's `_capacity` explicitly supports `AssignedEmbeddingCapacity.provenance="local-benchmark-limit"`, without pretending self-hosted TEI has cloud rate-limit headers. `safe_share` unset leaves state `SHARE_UNCONFIRMED`. The 60-second completion windows call a missing-usage observation `NOT_MEASURABLE`; they also label source-starved periods. The donor is not a distributed rate limiter.

## D. Goal

After an operator-defined, **measured** sustainable `Q_TPM`, the deployment dispatches bounded document and interactive-query embedding requests through one shared quota authority, aiming at **0.92 × Q_TPM** under sustained eligible demand while never admitting estimated/reserved token charges over **0.95 × Q_TPM in ANY rolling 60-second window**, including overlapping requests and window boundaries. The system reports actual/provider-reported completed TPM separately from estimated and tokenizer-counted proxy usage, and refuses to claim a target pass where provider usage or capacity is unknown.

## E. Scope

1. Provider-neutral capacity and dispatch port with versioned immutable config; adapt pinned donor algorithms where licensed and compatible.
2. Precise separation of `Q_TPM`, `target_tpm`, `hard_admission_tpm`, `max_in_flight`, `max_batch_tokens`, `max_batch_items`, `rpm`, saturation windows and per-request deadlines.
3. Rolling-60-second reservation/in-flight safety with **independent** hard ceiling, adaptive pacing, cooldown/recovery and a bounded pending-ready packet queue.
4. Shared capacity owner for query and indexing within one process; explicit fallback to a shared coordinator/leases BEFORE multiple workers/replicas send to the same model endpoint.
5. Tokenization/batch planning with actual query/document instruction prefixes and pinned tokenizer; no silent text truncation and no unknown provider usage advertised as actual.
6. Trace/event/measurement contract, fake deterministic clock and provider, live benchmark protocol and operational fail-closed behavior.
7. Port donor tests/scenarios, including source starvation, quota changes, rolling-window boundaries, 429, timeout, cancellation, retry, duplicate batch, local model unavailable and GPU OOM.

## F. Non-Goals

No guaranteed 92% completed throughput without adequate workload and real sustainable model capacity; no fake provider response headers, no forcing another cloud service, no global Qdrant/SQLite runtime, no heavy queue dependency before measured necessity, no unbounded background admission, no GPU benchmark assumed from donor TEI instance, no automatic source reindex just to retune TPM, and no priority scheme that starves interactive queries.

## G. Architecture / Boundaries

[x] App policy: governed `EmbeddingDispatchPort`; [x] provider adapter: existing/qualified local TEI service; [x] ingestion/retrieval: embedded in one shared inference boundary; [x] security, observability and operations; [ ] new document store. Contracts point from domain/application to ports; concrete adapter/runtime/dispatcher is composition-only.

```text
TXT/MD/PDF chunk producer / future backfill
                                     | 
Live query embedding -> Ready Packet Packer (single shared quota scope)
                                     |
                        CapacityGovernor (TPM+RPM+inflight)
                                     |
                     reserve estimate + rolling 60s 95% guard
                                     |
              async/bounded TEI provider (Query/Document inputs)
                                     |
                 finish(reservation, measured/proxy usage)
                                     |
             actual vector result -> existing PostgreSQL port
                                     |
              measured saturation / utilization telemetry
```

No SQL source-write transaction is held during wait or GPU inference. A canceled request cannot release already-sent provider quota as if it never arrived. Late paid results must be reconciled with their originating source/version; they cannot publish into a newer target generation silently.

## H. Contracts / Interfaces / Data Model

**Operator settings** (conceptual YAML; not existing config):

```yaml
embedding_capacity:
  capacity_source: local-benchmark-limit
  sustainable_tpm: null               # MUST be measured and approved
  sustainable_rpm: null               # MUST be measured or derived conservatively
  utilization_target_ratio: 0.92       # desired admitted send pacing
  rolling_admission_hard_ratio: 0.95   # independent hard ceiling
  safe_share: 1.0                     # only if deployment has exclusive ownership
  max_in_flight: 1                     # initial conservative value; benchmark 1/2/4
  max_batch_items: 8                  # benchmark 1/4/8/16
  max_batch_tokens: null             # from actual token/model qualification
  max_queued_packets: 32
  max_queued_tokens: null
  queue_admission_timeout_seconds: 30
  priority_policy: interactive_fair_share
  usage_provenance_policy: require_explicit
```

`Q_TPM = min(operator_measured_sustainable_tpm, applicable_runtime_limit, shared_capacity_budget)`. The last two may be unknown, so absence of validated capacity is **not** permission for optimistic 95%. `target_tpm = 0.92 × Q_TPM`; `hard_tpm = 0.95 × Q_TPM`. In every rolling 60-second interval `sum(estimated_admission_tokens_for_attempts + held_unreconciled_reservations) <= hard_tpm`. This is admission safety, NOT necessarily the observed billed-token ceiling (provider may charge differently). RPM, short 1s/10s bursts, inflight and provider-specific headroom are **additional independent** constraints.

`EmbeddingCapacityScope` = {deployment_id, model_profile_revision, capacity_owner_id, resource_group, workspace_request_priority, deadline, cancellation}. `EmbeddingReservation` has estimated input tokens, sent_monotonic, policy version, reference to request/job and usage provenance. `EmbeddingCompletion` stores provider_reported_tokens? or tokenizer_counted_proxy_tokens?, model_runtime_ms, success/ambiguous/timeout, rate-limited, retry_after and resolved source version.

**Usage provenance:** the donor TEI adapter sets `EmbeddingBatch.usage_tokens=tokens` computed by its local tokenizer, not necessarily returned in TEI's `/embed` response. If target TEI doesn't expose native usage, the system may report `tokenizer_counted_tpm` and `provider_reported_tpm = UNKNOWN`; it must never describe the proxy as actual billed/completed usage. Completed dispatch **attempt** counts are measurable even when usage tokens are not.

**Window eligibility:** a valid STEADY score requires a full 60s with stable verified capacity/profile, no 429/failures, and ready queue backed up for at least 99% of the window; display EVERY window including `INSUFFICIENT_DEMAND`, `CAPACITY_CHANGED`, `SHARE_UNCONFIRMED`, `NOT_MEASURABLE`, `RECOVERY`. Report eligible-window median/p10/p90, band share (0.90..0.95), server p95, queue wait p95 and failure count. The 0.92 target is a control setpoint, not a guaranteed observed percentage.

## I. Repository Files / Components Impacted

| Existing / proposed location | Required treatment |
| --- | --- |
| [recipient model_token_counter.py](../apps/workbench/embedding/model_token_counter.py) | Reuse pinned tokenizer/output rules; no independent approximate hard quota token counter. |
| [recipient ingestion.py](../apps/workbench/ingestion/ingestion.py), [postgres_ingestion.py](../apps/workbench/postgres/postgres_ingestion.py) | Integration seam: future embedding jobs call governed adapter; no SQL transaction across GPU inference. |
| [recipient document_processing.py](../apps/workbench/configuration/document_processing.py), [config.py](../apps/workbench/configuration/config.py) | Separate settings for token input-size and embedding TPM; no hardcoded model vendor in application core. |
| [recipient tests/test_model_token_counter.py](../apps/workbench/embedding/tests/test_model_token_counter.py) | Preserve split/admission tests; separate fake clock dispatch tests. |
| Existing `apps/workbench/embedding/embedding_capacity.py` and `apps/workbench/embedding/embedding_dispatch.py`; optional new `apps/workbench/embedding/embedding_capacity_windows.py` and `apps/workbench/embedding/embedding_packet_packing.py` only if existing owner cannot satisfy the contract | Adapt **minimum sufficient** donor contracts; no duplicate dispatch if EMBED-001 already adds it. |
| New `apps/workbench/embedding/tests/test_embedding_capacity.py`, `test_embedding_dispatch.py`, `test_embedding_telemetry.py` | Port donor invariants and target-specific 0.92/0.95 negative tests. |
| [donor quota audit](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md) | Reference for source-starvation/packing/ramp defects and exact measurement plan; source code cannot be copied without license permission. |
| [EMBED-001](TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md), [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md), [SCALE-002](TASK-RAG-SCALE-002-durable-asynchronous-ingestion-and-tenant-backpressure.md), [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) | MUST coordinate shared governor and actual usage schema; no independent quota governors per request type. |

MUST NOT change applied migrations 0001/0002, core Haystack algorithms, native FTS score semantics, original source version publication or UI Preview fixtures. If a distributed shared quota table/service is required, add a separate narrowly scoped contract/migration decision BEFORE concurrent workers are allowed.

## J. Implementation Requirements — ordered coding blueprint

### J1. Source-audited capacity contract and reuse rights

1. Pin donor commit `955fd049949d3fc462d555be14774e4b255aa15c`, re-open the exact code/test sources from C and donor license; obtain explicit ownership/license permission before literal code copying. Record donor-used algorithms, third-party dependencies and Workbench-specific changes in an adoption table.
2. Inspect Workbench current TEI and tokenizer configuration. Determine which running endpoint is really serving Qwen, model/tokenizer digest and whether it exposes trusted actual usage, RPM and effective quota. No live 4090 benchmark results should be inferred from another application.
3. Freeze `sustainable_tpm` as **unset** until local saturation benchmark; explicitly define exclusive versus shared endpoint owner, operator approval and per-deployment profile revision.

**J1 gate:** no provider execution starts through a governor configured with unknown optimistic TPM; an intentionally conservative single-test request may still be allowed through an explicit separate qualification profile.

### J2. Adapt process-local governor and independent hard ratio

1. Implement `reserve`/`finish`, monotonic clock, deadline/cancel checks and bounded reservation history from donor patterns; write testable pure functions for rolling admission and target pacing. Do not copy unrelated Qdrant/SQLite orchestration.
2. Add **two distinct settings** `utilization_target_ratio` and `rolling_admission_hard_ratio`. In `_wait_needed` compare total outstanding admission charges to `0.95 × verified Q_TPM`, NOT full Q_TPM. Ensure target `0.92 × Q_TPM` pacing is not inadvertently multiplied by `0.95` a second time.
3. Use monotonic timestamps, a genuine sliding 60-second window, exact-boundary tests (t=0, 59.999, 60.000), overlapping requests and longer pending completions; account for estimated tokens **before dispatch** and do not refund failed/ambiguous sent requests until safe expiry.
4. Enforce independent RPM and microburst counts, max in-flight and wait deadlines. Handle rate-limit/provider unavailable with bounded cooldown, ramp-down and gradual recovery; repeated 429 cannot spin, exhaust condition threads or cause silent retries.

**J2 gate:** fake-clock simulation demonstrates **zero hard-cap breaches** in every sliding 60s attempt window under saturated demand, even when configured desired ratio is 0.92.

### J3. Share scope across query and indexing

1. Define one capacity owner per `deployment/model_revision`; future QueryEmbedder, DocumentEmbedder and async embedding backfill acquire it. Disable direct provider bypass paths; preserve independent read-only lexical requests.
2. Implement bounded packet queue with max byte/token/items/time controls and work-class fair share: query priority should reduce interactive p95 but continuous ingestion must retain minimum progress under sustained queries.
3. A process-local governor must explicitly refuse to advertise **global safety** with multiple worker processes/replicas. Before SCALE-002 concurrent rollout, use a shared persistent/centralized lease service or strict one-process inference gateway; test no double spend.
4. Prepare batches with exact tokenizer counts over actual query/document model input, include instruction/context, reject mismatched model revision and truncation.

**J3 gate:** simultaneous query+indexing fake workload uses one quota ledger, no direct ungated TEI call; one source/tenant cannot monopolize the queue.

### J4. TEI adapter and usage reconciliation

1. Bind the qualified local TEI transport from EMBED-001 to `reserve→send→validate→finish`. Compare target endpoint behavior to donor `TEIEmbeddingProvider`, which uses `/embed`, `normalize:true`, `truncate:false`, strict row count/dimensions and locally tokenized usage; Workbench chooses its actual tested API path.
2. Retain all attempted reservation charges for rolling hard admission. Record provider-reported `usage_tokens` **only** when genuinely emitted by endpoint; otherwise use a separately named tokenizer proxy, and report actual usage unknown.
3. On timeout/connection close/429/OOM, classify `ambiguous` versus `known_not_sent`, preserve safe reservation headroom, retry only under policy and idempotent request ownership. Never let reconciliation release already-sent tokens prematurely.

**J4 gate:** no double `finish`, no fake actual usage, correct safe 503/429/504, full source/version trace and cancellation.

### J5. Capacity feasibility before utilization SLO

1. Benchmark real local Qwen runtime with short/medium/long texts (128/256/512/1024 tokens) and candidate batch sizes 1/4/8/16 and inflight 1/2/4, under measured GPU VRAM and service latency limits.
2. Determine sustainable completion throughput `Q_TPM` using continuous backlogged requests; verify provider/reported versus proxy token usage and short burst/RPM constraints. Do not use a historical TEI result from donor as current Workbench throughput.
3. Test feasibility: throughput bounded by `effective_RPM × mean_tokens_per_success`, `max_inflight × mean_tokens × 60 / p95_latency_seconds`, source preparation rate and downstream store commit rate. If source producer cannot supply 0.92×Q, mark `CAPACITY_NOT_FEASIBLE`, not a limiter FAIL or artificial model traffic.

**J5 gate:** approved Q_TPM, confidence/reliability evidence, service memory safety and deployable policy revision exist.

### J6. Reproducible telemetry, regressions and rollout

1. Record every 60s window with estimated admitted, known/unknown completed, utilization eligibility, queue depth, batch fill ratio, in-flight, wait reasons, backoffs, provider errors, GPU use and search p95. Use [donor window code](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embedding_capacity_windows.py) as a tested starting contract, not as a guaranteed product metric.
2. Unit tests with fake clock: no hard-cap breaches; a policy configured `0.92` desired and `0.95` hard; RPM 1s/10s; input token drift; source starvation; capacity change; unknown usage; cancellation; OOM; query fairness; dual worker rejection.
3. Run full recipient Hatch API checks and applicable browser smoke. Store sanitized benchmark evidence and a control chart of eligible 60s windows. A reported PASS requires **real local model** tests, not a fake provider.
4. Rollout initially disabled, then single inference owner under pinned profile; enable multi-replica only after centrally coordinated quota tests.

**J6 gate:** deterministic safety and measured empirical feasibility verified; observed utilization status is honest even when below target.

## K. Security / Governance / Observability

- Server resolves workspace and model execution permissions; quota policy cannot be changed by uploaded YAML/Markdown or frontend query labels.
- Pinned provider profile, tokenizer/model revisions and endpoint ownership; do not expose internal TEI URL, credentials, raw chunks, queries, vectors or tokenized text in telemetry.
- Avoid adding another API-to-GPU connection bypass; provide an explicit provider-neutral adapter with safe injection tests.
- For shared GPUs, enforce per-workspace fair-share and global hard cap before any send; future multi-worker dispatcher MUST be globally coordinated.
- Logs: `trace_id`, `run_id/job_id`, safe workspace/profile/generation IDs, estimated tokens, usage provenance, duration, queue wait and error reason. Redact content, user paths, secrets and model outputs.
- Model inference is affected by retry/timeout/cancellation; bounded budgets, cooldown and late-result ownership are security and correctness requirements, not optional optimizations.
- Donor source is **PolyForm Strict/Authorized Evaluation**; copying without rights is prohibited. Keep reference to donor commit and reviewer approval in implementation evidence.

## L. Testing / Evaluation / Runtime Verification

Minimum focused tests: fake-clock 1/10/60s boundaries, sliding reserve, exact 0.95 cap, 0.92 target, concurrent inflight, source-producer starvation, batch fill, insufficient demand, unknown usage, provider 429 cooldown, long request crossing window, cancellation/timeout, duplicate job and two-worker contention. A packet large enough to exceed hard ceiling must be split or fail before execution. Port donor invariant scenarios from [test_tei_embedding_provider.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_tei_embedding_provider.py) and [TPM audit](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md); do NOT copy the donor's Qdrant/SQLite fixtures.

Recipient baseline: `hatch run workbench-api:check`, `hatch run workbench-api:test`, `hatch run workbench-api:types` from repository root; real model/hardware smoke only with explicitly enabled local profile. If UI changes, also run `npm run typecheck`, `npm test`, `npm run build` and existing Preview/Live/validator browser regression. Test small corpus and saturated 10-minute/30-minute windows with identical measured Q_TPM; label warmup, unknown and insufficient demand windows separately. Report actual dimensions, usage provenance, VRAM peak, mean batch tokens, request/sec and p95/p99, source/queue saturation, and 60s hard-cap violations.

## M. Acceptance Criteria

- [ ] `sustainable_tpm` has actual local model/hardware evidence; cannot be silently populated from donor benchmark or guessed quota.
- [ ] For a verified `Q_TPM`, **all** synthetic/sliding 60-second admissions obey `sum_estimated_tokens <= 0.95 × Q_TPM`, with zero boundary and concurrency violations.
- [ ] Desired scheduler pacing uses **0.92 × Q_TPM**, independently from hard 0.95; unit tests reject accidental `0.92 × 0.95` double scaling.
- [ ] Query+document/worker embedding share exactly one capacity owner for single-process deployment; multi-replica mode fails closed until shared coordination exists.
- [ ] Runtime 429/timeout/OOM/cancel limits remain enforced and source/job owner consistency maintained.
- [ ] Native provider usage versus tokenizer-counted proxy is distinguishable; an unknown actual usage never becomes numeric `0` or a fake completed TPM.
- [ ] After verified feasibility and saturated work queue, report rolling eligible windows, p10/median/p90 utilization, 90–95% band share and p95 query impact without changing denominators.
- [ ] If real local sustained utilization cannot reach target due to RPM/latency/producer/consumer ceiling, report **NOT FEASIBLE** with a bottleneck diagnosis; do not pretend PASS.
- [ ] Legacy lexical/ingestion/parser source/version behavior unchanged; no Qdrant/OpenSearch dependency or hidden model SDK in core.
- [ ] Donor license decision and source attribution recorded before any literal transplant; test/evidence/rollback docs linked.

## N. Documentation / Migration / Compatibility / Rollback

- Add an operator-owned `embedding_capacity` profile configuration with explicit sustainable TPM, RPM, share, target, hard ratio, limits, observation provenance and revision; do not make it an unchecked browser preference.
- No PostgreSQL schema migration is needed for a single-process in-memory governor; if multiworker lease/capacity authority becomes necessary, create reviewed additive schema and explicit rollout with SCALE-002.
- Keep current lexical search and existing source versions valid when TEI/governor offline. Changing only utilization tuning does not invalidate embeddings; changing model/tokenizer/input profile does.
- Rollback disables governed real embedding profile or returns it to an earlier verified capacity policy while preserving source, vectors and jobs. Do **not** delete data, silently fall back to an ungoverned provider, or force a new corpus.
- Cross-references: [EMBED-001](TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md), [EMBED-002](TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md), [DELTA-001](TASK-RAG-DELTA-001-incremental-reindexing-and-embedding-vector-reuse.md) and [OPS-001](TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md).

## O. Mandatory Completion Checklist

- [ ] Inspect current recipient and pinned donor source, rights/license and current tests; update this specification if symbols/drivers drift.
- [ ] Prove exact independent target/hard ratio implementation with fake clock and model-qualified tests.
- [ ] Confirm one shared governor across query, source ingest and backfill; no bypass.
- [ ] Confirm unknown provider usage and unconfirmed share correctly fail/restrict measurement.
- [ ] Verify durable source/version and tenant scope, correct cancellation and failure reservations.
- [ ] Execute normal Hatch tests, focused fake provider tests and real model smoke with recorded output.
- [ ] Record actual throughput/capacity ceilings, source starvation and p95/VRAM bottlenecks.
- [ ] Mark simulated tests as simulations; only real runtime results support throughput claims.
- [ ] Document startup, operational tuning, monitor alerts, rollback and donor reuse license approval.
- [ ] Mark COMPLETE only when all applicable measurable criteria from M have executed evidence.

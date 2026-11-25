# TASK-RAG-OPS-001 — Cross-stage tracing, quality evaluation and operational observability

**Created:** 2026-11-23  
**Updated:** 2026-11-26  
**Status:** PROPOSED — implementation blueprint, not implemented  
**Priority:** P1  
**Dependencies:** INDEX-001, PROFILE-001; integrate EMBED/DENSE/ANN/HYBRID and CONTENT pipelines as qualified  , [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md)
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md

## A. Title

Cross-stage tracing, quality evaluation and operational observability

## B. Context / Problem

Structured safe logs already exist, but query-time Haystack, SQL, embedding inference, RRF, evidence lookup, indexing jobs and queue workers must be tied together by a trace. Operators need answerable reasons for missing citations, low Recall@k, long-tail latency, model token cost and index readiness. Test evidence currently belongs to isolated suites; enterprise observability requires unified revisioned dashboards and non-leaking evaluation records. Never infer answer quality from latency alone.

## C. Current Repository State

[boundary.py](../apps/workbench/api/boundary.py) already emits safe structured events and request/trace IDs; [postgres.py](../apps/workbench/postgres/postgres.py) logs database_operation duration and status; [lexical.py](../apps/workbench/retrieval/lexical.py) currently disables Haystack tracing in local use. [application.py](../apps/workbench/api/application.py) emits run_id, profile and duration for search. Existing [lexical fixture](../apps/workbench/retrieval/fixtures/lexical-evaluation.json) contains ten exact and three diagnostic queries, insufficient to evaluate multimodal enterprise quality. No full per-stage trace/quality dashboard is qualified.

**Evidence rule:** this source audit is not proof that the proposed new feature is working. Re-read code and tests at task start.

## D. Goal

Every supported Live retrieval or ingestion can be traced end-to-end with safe IDs, exact profile/index generation, resource costs and measured stages; operators can reproduce misses and detect stale indexing, model failure or source loss without reading private contents from telemetry.

## E. Scope

Instrumentation port and approved OTEL/local sink, safe span schema and bounded sampling, read-only health/capability dashboards, corpus/profile versioned RAG evaluations, model tokens/queue/GPU/DB cost metrics, alerts, operator runbook and regression tests.

## F. Non-Goals

No external collector dependency for API readiness, no full text/embedding/asset trace dumps, no invented LLM groundedness score, no requirement to train a judge model, no replacing existing API logs.

## G. Architecture / Boundaries

Application emits domain-safe StageEvent, adapter exports it to OTEL collector or local sink; no SDK in domain. Trace/run/job IDs propagate across API, Haystack, PostgreSQL and workers. Tracing failure drops bounded optional telemetry rather than breaking query; quality eval runner is separate from Live request.

Provider neutrality and source/tenant ownership are mandatory. Do not create empty Manager/Factory wrappers without demonstrated need.

## H. Contracts / Interfaces / Data Model

Span{trace_id,run_id?,job_id?,workspace_hash,source_version?,profile_id/revision,index_generation,stage,status,error_code,duration_ms,chunk_count?,token_count?,model_revision?}; metrics histograms request p50/p95/p99, exact/ANN retrieval, model tokens/s, queue lag, embedding coverage, failed evidence, migration state. Evaluation{corpus_revision,queries,ground_truth,format,language,profile,hit@5,MRR@10,nDCG if labels,source_citation_accuracy,sample_count,failures}. No default raw input/output capture.

## I. Repository Files / Components Impacted

CREATE apps/workbench/observability/tracing.py, apps/workbench/observability/tests/test_observability_redaction.py and apps/workbench/evaluation/tests/test_rag_evaluation.py, docs-website/docs/architecture/rag-observability.md after approval. MODIFY [boundary.py](../apps/workbench/api/boundary.py), [lexical.py](../apps/workbench/retrieval/lexical.py), [postgres.py](../apps/workbench/postgres/postgres.py) and qualifying new components through one port. Reuse tasks/evidence and existing logs, do not modify Haystack framework internals.

MUST NOT modify historical migration 0001/0002, framework haystack/ or unrelated Preview/validator implementations as a shortcut.

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/api/boundary.py`](../apps/workbench/api/boundary.py) | request_meta and log_event safe correlation |
| [`apps/workbench/postgres/postgres.py`](../apps/workbench/postgres/postgres.py) | database_operation duration, outcome, workspace_id, trace_id |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) | run_id and search_completed status |
| [`apps/workbench/retrieval/lexical.py`](../apps/workbench/retrieval/lexical.py) | tracing disabled in current local baseline; no per-stage OTEL |
| [`apps/workbench/api/tests/test_http_contract.py`](../apps/workbench/api/tests/test_http_contract.py) | request/error correlation and safe envelope |
| [`apps/workbench/api/tests/test_lexical_routes.py`](../apps/workbench/api/tests/test_lexical_routes.py) | verified score/latency cases |
| [`apps/workbench/api/tests/test_ingestion_stability.py`](../apps/workbench/api/tests/test_ingestion_stability.py) | job/error paths |
| [`docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md`](../docs-website/docs/tasks/RAG_Live_Lexical_Acceptance_2026-11-22.md) | historical complete lexical evaluation, not an enterprise p95 SLO |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tasks/TASK-M39-030-embedding-TPM-smoothing-audit.md); [`tools/qualification/embedding_smoothing_report.py`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tools/qualification/embedding_smoothing_report.py); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## J. Implementation Requirements — ordered blueprint

1. J1 — Freeze current log schema and trace ID propagation; document SQL, HTTP, model and UI timelines without exposing PII. Mark each existing measured stage and missing metrics.
2. J2 — Add bounded low-cardinality span taxonomy to API, ingestion, embedding, vector/ANN, hybrid, evidence and queue operations. Redact untrusted fields and guard log size; fail open for telemetry outage but never disable authorization.
3. J3 — Implement optional OTEL adapter and local sink with batching, bounded queue/backpressure and retention; tests inject exporter failure/slow subscriber and verify request not blocked.
4. J4 — Build evaluation runner for indexed corpus+profile generations; freeze labels, include misses and errors, compute source-hit@5/10, MRR, evidence/page accuracy, ANN recall vs exact and per-format/paraphrase cohorts.
5. J5 — Configure alerts for generation drift, incomplete embeddings, failed OCR, stale jobs, 503/504, p95 regression, cross-workspace denial anomalies and missing original evidence. Include precise runbooks and ownership.
6. J6 — Benchmark 100+ label-backed queries at multiple corpus sizes; record p50/p95, token/cost budgets, data retention and exporter load, and ensure Preview fake timings never enter Live observations.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Inventory current trace IDs, safe log payloads and where `disable_tracing()` is called. Define tracing port that does not modify Haystack core or log secrets.

**J8.** Create standardized stage names for source parse/chunk, embedding capacity reserve/send/finish, vector upsert, lexical, query model, ANN, RRF and evidence with bounded trace fields.

**J9.** Import [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) eligible-window metrics including target=0.92/hard=0.95, source-starved/not-measurable, estimated/reserved/actual or proxy separately.

**J10.** Add local OpenTelemetry-compatible adapter behind app-owned port, export asynchronous bounded records, with overload/drop counters and fail-nonblocking semantics.

**J11.** Create reproducible evaluation manifests pinned to corpus/index/profile generations: exact term, paraphrase, evidence source/page/crop, code symbol, table numeric accuracy.

**J12.** Alert on stale embeddings, inconsistent index generation, unknown provider usage, 429/503/504, high p95 queue wait, missing asset and tenant authorization anomalies.

**J13.** Run ≥100 real labeled queries and safe logs adversarial tests; include all errors in denominators, copy only historical local records as baseline not new PASS.

**Cross-cutting constraints:** One shared capacity authority [TPM-001](TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) enforces 0.92 desired and 0.95 hard; separate workers cannot bypass it.

### Metric evidence integration (not a new service prerequisite) — 2026-11-26

Reuse existing evaluation artifact owners for metric schema/version, clean/stress runs, source fidelity, chain consistency, calibration, noise, drift and correction window as defined in [quality/content plan](quality/RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md). Consume aggregate counts and trace IDs from existing owners; do not build a competing evaluator, require OTEL for local metrics, log gold/raw prompts or infer production traffic from local probes. Optional alerts only after real drift/freshness baselines, with explicit thresholds and owner. Generation-dependent metrics remain NOT_EVALUATED until qualified.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext and FORCE RLS across all source, asset and index paths. Keep private source bytes, vectors, prompts, credentials, user identifiers and arbitrary URLs out of logs and public evidence. Treat source/model text as untrusted data. Enforce bounded CPU/GPU/DB/network requests, cancellation, timeout, retention, auditing and safe error codes with trace/job/run IDs. Test cross-workspace and provider outage negative cases.

## L. Testing / Evaluation / Runtime Verification

Trace propagation concurrency and cancellation, logs with secret-bearing filenames/queries/URLs, OTel exporter down, metrics cardinality bounds, 100+ gold real query labels with all misses, p95 histogram validity, data generation mismatch, SOURCE RLS, fail-safe alerting and correlation to API 503 errors. Real vs mock evidence separated.

Execute existing Hatch workbench-api:check/test/types, explicit disposable PostgreSQL integration; when UI changes run npm typecheck/test/build and Preview/validator smoke. Attach real command outcomes and mark unrun tests NOT TESTED.

### L.1. Task-specific reproducible test vectors

- [ ] Trace ID propagation API→SQL→embedding queue→provider→generation publication, cancellation and cross-tenant separation.
- [ ] No raw text/embeddings/credentials/asset bytes in logs under malicious input, OTel exporter down not fatal.
- [ ] Eligible TPM 60s distributions, provider/proxy evidence and p95 interactive query under saturated ingest.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

## M. Acceptance Criteria

- [ ] Trace/run/job IDs join SQL, model, retrieval and evidence stages when implemented
- [ ] Raw text/images/DSNs/tokens do not appear in default logs under adversarial tests
- [ ] Exporter failures never block healthy retrieval or source publishing
- [ ] 100+ labeled cases with immutable profile/generation and all failures recorded
- [ ] Per-format/lang retrieval quality and ANN exact-vs-approx regression visible
- [ ] Embedding coverage, backlog, cost and p95 metrics use real samples
- [ ] Alert and incident runbook for stale generation and missing original evidence
- [ ] Legacy lexical, ingestion and UI smoke unchanged

- [ ] Local report consumes versioned metric evidence and actual stage timestamps, with explicit missing metrics; no new telemetry dependency required for current quality.

## N. Documentation / Migration / Compatibility / Rollback

Opt-in adapters, local safe logs remain on errors, no remote telemetry default. Publish retention and security access controls before production. Disable exporter on performance/privacy regression without changing source, vector or index revisions.

## O. Mandatory Completion Checklist

- [ ] Reinspect current source and completed tasks.
- [ ] Confirm API/schema/architecture owners and no duplicated services.
- [ ] Error/status/authorization contracts validated and documented.
- [ ] Original source/version and all relevant profiles preserved.
- [ ] Negative, stress/restart/recovery and security tests actually executed.
- [ ] Real metrics/cost/quality or source-evidence fidelity recorded.
- [ ] CI/Hatch/frontend regression gates passed with logs.
- [ ] New capabilities reflect true current readiness, not planned behavior.
- [ ] Safe non-destructive rollback and operator actions documented.
- [ ] Mark COMPLETE only with linked evidence proving acceptance criteria.

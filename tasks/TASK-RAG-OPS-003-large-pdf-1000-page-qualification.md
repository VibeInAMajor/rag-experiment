# TASK-RAG-OPS-003 — Release-gate 200 MiB and 1000-page ingestion on target server

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — specification only; not implemented or benchmarked  
**Source reviewed:** 44866bb7e7dc01993bbaefefdec1ab1985951cc7  
**Target:** tasks/TASK-RAG-OPS-003-large-pdf-1000-page-qualification.md

## A. Title

Release-gate 200 MiB and 1000-page ingestion on target server.

## B. Context / Problem

Existing limits are application policy, not Qwen/PostgreSQL/hardware. User observed 35 KB PDF about 28s and 16-page dense PDF about 180s; these must be reproduced or marked operator-reported. Async responsiveness is not processing acceleration.

## C. Current Repository State

pdf_worker.py currently AcceleratorOptions(device=cpu,num_threads=4), do_ocr=False; pdf_models.py caps worker memory near 6 GiB, 180s; postgres_ingestion caps 10k chunks/50 MiB; no verified 200 MiB/1000-page evidence. Target NVIDIA RTX 4090 24 GiB and Ollama/Qwen model are qualification inputs, not established throughput.

Static repository evidence only, not a test of deployed server. Reinspect affected source, schema, configuration, tests and runtime before changing code.

## D. Goal

Record reproducible actual memory, disk, CPU, VRAM, latency, page/table coverage, job fairness and crash recovery before enabling any large-file tier.

## E. Scope

- Gold PDF corpus at 1/8/100/200 MiB, 16/32/256/1000 pages and diverse complexity
- full timings by stage, resources and search p95
- CPU/GPU Docling comparison with Ollama
- 1000 job/3 tenant load and security tests
- publish evidence.

## F. Non-Goals

- No speculative SLA, GPU speed claims or disabled PDF safety checks to make demos pass.

## G. Architecture / Boundaries

Disposable benchmark harness -> API/worker/Postgres/PDF metrics and independent gold labels -> explicit release gate; resource budgets pinned to measured hardware profile.

Affected: domain/application, ports/adapters, persistence, security and/or observability as indicated above. Provider-neutral application policy MUST NOT import a concrete parser, vector, cloud or model SDK.

## H. Contracts / Interfaces / Data Model

Evidence: input SHA, pages, parser assets revision, hardware/OS, number samples, upload/queue/parse/index p50/p95, max RSS/CPU/VRAM/disk, page coverage, numeric/table checks, retries and search latency. Publish only empirically passed max_bytes/max_pages tier.

## I. Repository Files / Components Impacted

ADD targeted tests/scripts, tasks/evidence Markdown report, operational runbook and truthfully versioned capabilities. Never run against production corpus.

MUST NOT silently expand scope. Architecture or schema changes require updating this task first.

## J. Implementation Requirements

1. Benchmark baseline sync vs async separately for time-to-accept and total processing time.
2. Qualify tiers 100 MiB/256 pages and then 200 MiB/1000 pages; complex pages and compressed structures mandatory.
3. Test pinned Docling supported CPU and GPU, measuring quality and GPU contention with Ollama/Qwen.
4. Run 1000-job load on 3 workspaces with crashes, replays and queue fairness metrics.
5. Independently verify each page accounted for and exact numeric/table/heading provenance; explicit unsupported OCR/visual status.
6. Record actual PASS/FAIL/BLOCKED and avoid public limit increases from static review.

Any new variables and methods MUST have domain-meaningful names, not task or milestone IDs. Reuse existing app-owned logic and avoid duplicate registries, adapters or publishers.

## K. Security / Governance / Observability

Adversarial PDF actions/encryption/decompression and multipart; wrong-workspace asset/job; disk exhaustion; no-network worker and redacted traces.

All operations MUST use server-derived workspace authority and force tenant isolation. Record sanitized job/stage/trace/resource evidence, never content, secrets or private paths.

## L. Testing / Evaluation / Runtime Verification

Real 200 MiB/1000-page sources, sample counts p50/p95 RSS/VRAM/disk; crash/recovery; three-tenant queue fairness, search p95, numeric/page provenance, adversarial limits; no synthetic PASS claims.

Run applicable targeted Hatch app checks/tests/types and, when touched, npm typecheck/test/build on disposable resources. Actual commands/results MUST be recorded; no test is PASS by documentation alone.

## M. Acceptance Criteria

- [ ] Public 200 MiB/1000-page only after reproducible on-host end-to-end success, accurate page accounting, bounded hardware resources and zero partial ready document.

## N. Documentation / Migration / Compatibility / Rollback

Gradual qualification; disable higher tier and retain accepted jobs/asset bytes if any gate fails.

Update affected OpenAPI, capability limits, operator docs and migration plans. New SQL schema must be additive; preserve accepted originals and prior active source generations.

## O. Mandatory Completion Checklist

- [ ] Reinspect source/SQL/tests and update Section C if changed.
- [ ] Confirm reuse of existing source/job/parser/chunker/storage owners.
- [ ] Prove workspace isolation, failure, disconnect, replay, crash and rollback paths.
- [ ] Test contracts, migration and affected regression suites.
- [ ] Record real resource and quality evidence or mark NOT TESTED/BLOCKED.
- [ ] Update docs and checked acceptance items with links to evidence.
- [ ] Record modified files, executed commands and commit.
- [ ] Mark COMPLETE only after every applicable gate passes.

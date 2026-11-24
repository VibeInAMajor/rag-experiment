---
title: Durable embedding backfill and objective retrieval checks
description: Leased embedding jobs, generation coverage, measured shared admission and source-grounded quality evaluation.
---

# Durable embedding backfill and objective retrieval checks

Lexical publication commits source versions and chunks first. A separate durable worker embeds active chunks using the qualified [local Qwen provider](local-embedding-provider.md), then stores generation-fenced mappings. Model failure leaves lexical retrieval available. Internal semantic coverage and exact-vector diagnostics do not enable Dense HTTP, ANN, hybrid retrieval or generation; the [approved profile registry](profile-registry.md) still controls executable retrieval.

Implementation and live acceptance are tracked in completed [EMBED-002](../../../tasks/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) and its [evidence](../../../tasks/evidence/embedding-2026-11-24/report.md). The actual ten-minute run passed its predeclared steady-window rule: median 92.141081157% of the measured denominator, with zero hard breaches. Whole-run utilization was **91.992753788%, below exact 92%**. Fixed-fixture retrieval metrics and no-answer/hard-negative limitations are recorded separately; they establish no production truth guarantee.

## Storage, source identity and recovery

Additive migration `0005` introduces immutable model-profile definitions, embedding jobs, tenant-local vector cache, chunk mappings and complete semantic generations. Migrations `0001`–`0004` remain unchanged. Existing HTTP ingestion keeps its null-embedding publication guard: GPU inference is not inserted into a lexical source transaction.

The job key binds workspace, source version and immutable model profile. Leases have an owner token, expiry, bounded attempts, a stable chunk cursor and a safe failure category. The worker reads a bounded page, releases the read transaction, prepares exact model inputs and performs provider work. A short write transaction then rechecks lease ownership, active source/version and chunk content before saving vectors and advancing the cursor. Lost ownership or superseded versions cannot attach paid late results to a new active generation.

The cache key includes workspace, profile fingerprint, processing-policy digest and exact formatted input SHA-256. Source occurrence IDs remain separate, allowing compatible unchanged text to reuse a vector within the same workspace. A different workspace cannot reuse that row. Heading context, affixes, tokenizer/model revision and input policy participate in identity; a bare text hash is insufficient. Changed source versions or processing metadata invalidate mappings and schedule work, while compatible existing cache entries remain available.

The finalized `durable-document-input-r2` policy fingerprints stable parser, chunker and admission configuration separately from source-bound processing fingerprints. A file edit must not change the reusable key of every unchanged chunk merely because the source SHA or span layout changed. Those source identities/spans remain mandatory occurrence provenance. Existing correct vectors/mappings from the initial `r1` namespace remain valid; new work uses `r2` and may incur a one-time cold cache. The qualified model profile and capacity denominator do not change because of this policy-key correction.

Coverage reads actual eligible active chunks and matching mappings. An immutable semantic generation is published only when the current lexical generation is fully covered with the selected profile. Partial/disabled/stale work remains not ready. Exact diagnostics fence that generation and profile in one consistent read transaction; nearest rows from a partially covered or different generation are not silently mixed.

Worker restart resumes its durable cursor after lease recovery. A canceled or uncertain sent request retains its capacity charge; it is not automatically treated as provider-not-sent. Provider identity/tokenizer changes require operator recovery and recalibration. Retries and cooldowns are bounded; inspect safe job codes before retrying poison or unavailable work.

## Measured admission and operator commands

The old qualification-only allowance does not establish production capacity. `embedding_capacity.py` owns the measured shared query/document scheduler, backed by one deployment lease and a persisted charge journal. The operating target is `0.92 × measured Q_TPM`; the independent hard rolling-60-second ceiling is `0.95 × Q_TPM`. The target is not multiplied by the hard ratio again. Request/queue/workspace/RPM bounds and deadlines also apply.

Capacity configuration is a bounded, expiring calibration envelope tied to the exact model profile, deployment and runtime evidence. Ordinary startup does not calibrate, enqueue a backfill or activate dense search. The dedicated TEI service and its physical GPU remain shared-resource observations, not a claim of globally exclusive GPU capacity.

The accepted denominator is the highest sustainable result among explicitly tested candidates under the recorded shared-GPU conditions. It is not proof of an absolute hardware maximum. EMBED-002 qualifies the required single-owner admission slice; TPM-001's broader 30-minute and wider concurrency matrix remains separate work.

There is currently **no TPM dashboard in Workbench**. Coverage and admission summaries are available through the operator CLI/JSON; the live experiment additionally records per-window `provider_reported_completed_tokens`, `completed_utilization`, backlog state and hard-admission violations. `rolling_admitted_tokens` is a reservation estimate, while `provider_reported_tokens` is a cumulative completion count; neither should be displayed as an actual rolling completed TPM percentage without its window and quota denominator. A future UI requires its own actual telemetry contract.

Use the existing PostgreSQL environment loader and explicit migration command before the worker on an existing database:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:db-migrate
```

The application uses the unprivileged app DSN; administrator credentials are for the reviewed migration boundary only. Root startup never migrates or resets the database.

Explicitly calibrate the local approved deployment, then inspect eligibility without provider calls:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_capacity_benchmark --calibrate --output .cache/workbench-capacity/calibration.json
hatch run workbench-api:python -m scripts.workbench_embedding_backfill --capacity-config .cache/workbench-capacity/calibration.json --dry-run
```

After reviewing the actual calibration and dry run, start/resume bounded work and inspect coverage:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_backfill --capacity-config .cache/workbench-capacity/calibration.json --output .cache/workbench-capacity/backfill.json
hatch run workbench-api:python -m scripts.workbench_embedding_backfill --capacity-config .cache/workbench-capacity/calibration.json --status
```

`--workspace` selects the trusted operator scope; it is not an HTTP authorization mechanism. `--watch` keeps a worker active for newly queued source versions. `--retry-job` requires an actual inspected job ID. `--disable` stops scheduling for this profile while preserving lexical data, cache rows and historical mappings. No source or model asset is deleted by those operations.

## Objective quality and original-source fidelity

The [fixed fixture](../../../apps/workbench/embedding/fixtures/embedding-retrieval-evaluation.json) contains 102 active main-workspace chunks, 12 historical-version chunks and 12 foreign-workspace chunks, with 52 labeled EN/RU/UK/code/cross-language/no-answer queries. Original UTF-8 source hashes and exact character spans define the oracle. The implementation agent authored this fixed synthetic corpus and its explicit relevance labels in this session; no independent human/expert validation or external labeled dataset was provided. Its fictional policies are not claims about the actual deployment.

The [evaluation harness](../../../scripts/workbench_embedding_evaluate.py) uses actual persisted vectors, exact PostgreSQL cosine ranking and query embeddings through the same shared runtime/governor. It never starts a generative model, uses Ollama or asks Qwen to judge correctness. Qwen remains the embedding provider. Fixture publication uses the existing lexical publication port and is explicitly distinguished from HTTP upload tests.

Before scoring each returned candidate, the harness checks workspace, active source/version, exact chunk bytes/hash, original-source hash, NFC model-input hash, model fingerprint and one stable generation. Foreign/superseded results or changed originals fail the integrity gate regardless of similarity. The fixture transition embeds old versions first, then changes one chunk in each of four sources; eight compatible unchanged chunks must reuse same-tenant vectors. An identical foreign-workspace source must be embedded independently.

Metrics are computed at `k=1,5,10` overall and by language/cohort:

- Recall: retrieved relevant chunks divided by all labeled relevant chunks.
- Primary-evidence recall: retrieved direct-answer chunks (grade 3) divided by all direct-answer chunks; related context at grade 1 is not a direct answer.
- MRR: mean reciprocal rank of the first labeled relevant candidate, limited to the cutoff.
- nDCG: rank-discounted gain `2^grade - 1`, divided by the ideal gain with the same cutoff; the discount is `log2(rank + 1)`.

No-answer queries have no labeled relevant chunk and are excluded from answerable-query averages. Raw nearest-neighbor search can still return candidates. The report exposes forced-neighbor counts and top similarities, marks abstention unimplemented and makes no universal cosine truth threshold. Source fidelity and relevance on a fixed fixture do not prove the original facts are true or that future generated answers are correct. This task adds no answer generator or production trust guarantee.

Offline fixture validation sends no model requests:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_evaluate
```

The real quality CLI requires explicit opt-in, a calibrated capacity file and `WORKBENCH_TEST_APP_DSN` pointing to a parent-created disposable database named `rag_test_*` with migration `0005`. It never creates/drops that database or touches the configured application corpus:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_evaluate --run --prepare-fixture --capacity-config .cache/workbench-capacity/calibration.json --output tasks/evidence/embedding-2026-11-24/quality.json
```

Omit `--prepare-fixture` to evaluate an already prepared fixture corpus. The output records hashes, IDs, scores, counts and timings; it omits raw inputs, source content, vectors and credentials. A successful run means measured integrity/relevance results, not a fabricated quality threshold pass.

## Ten-minute proof, synthetic scale and rollback

The requested ten-minute proof requires a real continuously ready backlog through the durable worker, actual provider usage and every rolling admission window. Record queue starvation, warm-up, failures, actual denominator, shared-GPU memory and query latency separately. A configured `0.92` target does not mean 92% was observed. Unknown usage, insufficient demand or an infeasible workload must be reported rather than assigned a passing percentage.

The separate 10k–100k storage benchmark uses synthetic 32-dimensional vectors and direct bounded persistence pages. It is model-free storage/recovery evidence, not real-worker/GPU throughput or a full-2560 storage-capacity forecast. Real 2560-dimensional durable coverage and retrieval are qualified on the controlled model corpus independently.

For rollback, stop the worker and use its explicit profile-disable command. Keep lexical publication, PostgreSQL data, model assets and already stored vectors. Reenable only the same immutable profile or register a new qualified revision. Destructive schema downgrade belongs to explicitly owned disposable migration tests, not routine recovery.

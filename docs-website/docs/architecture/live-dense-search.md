---
title: Live exact dense search
description: Qualified local query embeddings, complete persisted generations and exact PostgreSQL cosine retrieval.
---

# Live exact dense search

**Updated:** 2026-11-24

Workbench can execute the approved Live Dense graph through a fixed Haystack query embedder and PostgreSQL retriever. The [durable embedding owner](durable-embedding-ingestion.md) supplies the same model profile, native tokenizer, input instruction policy and shared measured admission used by ingestion. PostgreSQL remains the only vector store. No ANN index, cloud fallback or answer generator is introduced.

The default service and Keyword graph retain their lexical behavior. Dense is an explicit runtime composition; merely storing a dense definition or editing a browser graph does not enable it. See [the actual execution record](../../../tasks/evidence/dense-2026-11-24/report.md) for completed baseline gates and measurement boundaries.

## Readiness and result contract

The `postgres-dense-exact` / `postgres-dense-exact-r1` descriptor has `kind=dense_search`, `score_type=cosine_distance`, `score_direction=lower_is_better`, `min_coverage=1`, a pinned `embedding_profile_revision` and the current `index_generation`. It appears only when its active workspace rollout, complete current semantic generation, model identity and measured capacity are available. Missing vectors, retired policy, source generation drift, expired capacity and provider failure cannot become a successful empty result or fixture fallback.

The browser sends the existing four fields to the existing route:

```json
{
  "query": "How can I restore a previous published version?",
  "top_k": 10,
  "profile_id": "postgres-dense-exact",
  "expected_profile_revision": "postgres-dense-exact-r1"
}
```

`POST /api/v1/workspaces/development/search` accepts no vector, provider URL or executable canvas JSON. The server resolves workspace authorization and immutable policy before model work. The development deployment remains restricted to its authorized development workspace; this feature does not establish production tenant authentication.

Each hit preserves persisted `chunk_id`, `source_id`, `source_version_id`, rank, content and optional page. `score` is the actual pgvector cosine distance, with smaller values first. It is neither a percentage nor a calibrated confidence. The response includes model revision/digest, tokenizer digest, input-format revision, embedding-profile revision and index generation. `query_embedding`, `vector_search` and `projection` have server-measured wall durations and timestamps, alongside server request/trace/run identifiers. Embedding wall time includes native preparation, shared admission waiting, HTTP and attestation; it is not GPU kernel time.

Malformed inputs return 400, denied or unknown workspaces 404, stale profile revisions 409, shared admission refusal 429, unavailable model/database/generation 503 and the bounded request deadline 504. Client cancellation propagates to owned model/SQL work. Live never switches to Preview after an error.

## Explicit local operation

Use Hatch and the existing database environment. Keep the current applied migrations and existing vectors. First obtain fresh actual model capacity; historical calibration expires and must never be revived by editing its timestamps:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
hatch run workbench-api:python -m scripts.workbench_embedding_capacity_benchmark --calibrate --output .cache/workbench-capacity/calibration.json
hatch run workbench-api:python -m scripts.workbench_embedding_backfill --capacity-config .cache/workbench-capacity/calibration.json
```

Generate a new local registry file from the central reviewed dense policy and that model profile. The command refuses to overwrite an existing file. It writes configuration only; qualification and activation stay explicit administrator operations:

```powershell
hatch run workbench-api:python -m scripts.workbench_dense_serve --capacity-config .cache/workbench-capacity/calibration.json --write-profile-registry .cache/workbench-capacity/dense-profiles.yaml
$env:WORKBENCH_PROFILE_REGISTRY_CONFIG = '.cache/workbench-capacity/dense-profiles.yaml'
hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles sync
hatch run workbench-api:python -m apps.workbench.postgres.postgres_profiles promote --profile-id postgres-dense-exact --profile-revision postgres-dense-exact-r1
hatch run workbench-api:python -m scripts.workbench_dense_serve --capacity-config .cache/workbench-capacity/calibration.json
```

Stop the previously owned API process before using the same port, or select `--port 8012` for isolated inspection. This launcher reuses the existing local model/runtime verification and one measured governor. It does not migrate, seed, enqueue backfill or activate profiles at startup. A second measured owner refuses the shared deployment lease rather than inventing another quota. Model assets and endpoint are locally attested. Capacity remains an expiring observation under shared physical GPU conditions.

## Reproducible evaluation

The evaluator creates and removes only its own `rag_test_...` database, with ownership markers and the existing migrations. Supply explicit test administrator/application DSNs through `WORKBENCH_TEST_ADMIN_DSN` and `WORKBENCH_TEST_APP_DSN`. It retains the fixed original-source fixture, maps its main workspace to `development` for the existing HTTP authorization boundary, embeds more than 100 active vectors through the shared local model, and compares at least 30 multilingual semantic HTTP queries with an independently issued read-only exact SQL oracle. It also records lexical results for the same paraphrases and ten literal lexical cases.

```powershell
hatch run workbench-api:python -m scripts.workbench_dense_evaluate --run --capacity-config .cache/workbench-capacity/calibration.json --output .cache/workbench-capacity/dense-evaluation.json
```

Reports contain safe identities, hashes, raw distances, fixed relevance metrics and separate provider-inference/embedding/SQL/HTTP wall-time p50/p95 sample counts. Provider inference uses the actual TEI `te_request_inference_duration_sum/count` delta and requires exactly one query completion per sample. It is server inference wall time, not CUDA kernel-only timing. Original text and query vectors are not written into evidence. The source fixture is synthetic and its fixed relevance labels were authored in this repository; these measurements do not establish independently human-reviewed production retrieval quality. Exact nearest-neighbor retrieval still returns neighbors for no-answer queries; semantic abstention remains unimplemented. The separate browser smoke measures response-body-ready through DOM commit and a later animation frame; the HTTP evaluator does not claim browser timing.

The gated `apps/workbench/api/tests/test_dense_model_smoke.py` executes the same real disposable evaluation only when `WORKBENCH_DENSE_LIVE_TEST=1` and `WORKBENCH_DENSE_CAPACITY_CONFIG` selects a fresh measured policy. Default runs skip GPU traffic.

## Rollback and repair

Retire the dense rollout through the existing profile administrator and restart the ordinary lexical service. Preserve embedding vectors, historical source versions and all applied migrations. On source publication, dense coverage must become complete and the exact current generation must be qualified before it can execute. Re-run the existing worker to repair missing coverage, then explicitly promote the reviewed profile. Expired capacity requires fresh measured calibration. ANN acceleration remains a separate rollout and qualification task.

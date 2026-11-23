---
title: Local embedding provider qualification
description: Model identity, bounded qualification, token provenance and rollback for local Qwen embeddings.
---

# Local embedding provider qualification

The Workbench embedding boundary separates immutable model/input policy from its local TEI transport. Query and document requests share one admission owner. Qualification does not publish vectors, change the lexical search API, or enable dense, ANN or hybrid profiles. The [profile registry](profile-registry.md) remains authoritative for executable retrieval policies.

## Identity and input policy

The selected model is `Qwen/Qwen3-Embedding-4B`, revision `5cf2132abc99cad020ac570b19d031efec650f2b`, using full 2560-dimensional output. The model card describes instructions and variable dimensions, but a model card cannot attest a running service. Local qualification must inspect the actual runtime, verify pinned model/tokenizer assets and validate real output. See the [official model card](https://huggingface.co/Qwen/Qwen3-Embedding-4B).

The two expected weight digests come from the [official revision-specific Hugging Face file metadata](https://huggingface.co/api/models/Qwen/Qwen3-Embedding-4B/tree/5cf2132abc99cad020ac570b19d031efec650f2b?recursive=true&expand=true):

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `model-00001-of-00002.safetensors` | 4965826464 | `e70bfe3c970523fb7ef4eddffed2254ce3f1e7150c3de2af4342de129dd756f8` |
| `model-00002-of-00002.safetensors` | 3077765624 | `ed1b87c8e9eb7e535a1a155e4fd00d9f4dba80e58a6db48a4c9f82cede7079c1` |

The existing `LocalQwenTokenCounter` owns tokenizer JSON digests, native special-token behavior and NFC preparation. Count the exact sent text, including the query instruction, with the same pinned assets. Documents receive their prepared content without a query instruction. Queries receive this prefix exactly once:

```text
Instruct: Given a web search query, retrieve relevant passages that answer the query
Query: {query}
```

A revision change, input transformation, pooling change, normalization change or output dimension change requires a new immutable profile identity and requalification. No automatic truncation or output slicing is permitted. Returned vectors must have the expected cardinality and dimension, finite numeric values and a nonzero norm; normalization policy is part of the profile.

`EmbeddingProfile.fingerprint` is the SHA-256 of its canonical complete JSON definition, including the instruction, last-token pooling, inference dtype, output encoding and operational bounds. This deployment selects `inference_dtype:float16` and `output_encoding:float`; the latter means JSON numbers and does not promise extra numerical precision. The adapter checks actual `/info` dtype and pooling. Evidence stores the fingerprint without logging the instruction or source inputs. Editing a profile definition invalidates its prior qualification.

## Transport and attestation

The project deployment target is `rag-workbench-embedding-1` at `http://127.0.0.1:8082`, with its own TEI process and read-only model mount. It shares the physical GPU with other local workloads. Configure only an explicitly approved local service; an unavailable service fails safely without another provider or synthetic fallback. Runtime startup performs no model download.

The [original shared-service qualification](../../../tasks/evidence/embedding-2026-11-23/report.md) used another container on `127.0.0.1:8081`. Its artifacts remain unchanged. The [dedicated bind-mount record](../../../tasks/evidence/embedding-2026-11-23/dedicated-report.md) preserves the accepted 242.17-second baseline. The [current Linux-cache and autostart evidence](../../../tasks/evidence/embedding-2026-11-23/optimized-report.md) records 30.705-second initial process startup, 17.376-second repeat startup and separate governed model proof. These are host-specific process measurements with caches not cleared.

The selected adapter uses OpenAI-compatible `POST /v1/embeddings` with `input` as the ordered final text array, the profile's Hugging Face model ID, `encoding_format:"float"` and `dimensions:2560`. Its response must identify the attested served model, declare `object:"list"` and contain exactly one `object:"embedding"` row at each expected index; reversed indices fail rather than being silently reordered. These fields validate the transport contract but do not independently attest model weights. See the [official TEI API examples](https://huggingface.co/docs/text-embeddings-inference/quick_tour).

Native `/embed` is not an interchangeable production path. It can be compared only by the explicit governed qualification diagnostic. The installed runtime schema, global `auto_truncate:false`, verified model pooling and local exact token limits govern the selected route. No retry, redirect, environment proxy or fallback provider is configured.

On this local TEI deployment `/info` reports `model_sha: null`. A successful metadata request therefore cannot establish the weight revision. Qualification records the immutable container image, the running container's read-only model mount, exact file hashes and the service metadata fingerprint together. It binds the exact `--model-id` command argument and `/info.model_id` to that mount, and checks configured/actual container port bindings from `80/tcp` to the client endpoint `127.0.0.1:8082`. An unrelated matching model directory or container is insufficient. This is operator/container attestation within a trusted local host. It does not prove hostile runtime behavior or detect weights replaced without a metadata change by a compromised operator. Treat any deployment change as invalidating qualification.

## Shared admission and usage

The [TPM task](../../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) owns production query/document admission, a measured sustainable capacity, the 0.92 operating target and independent 0.95 rolling-window ceiling. None of those production capacity claims follows from a short embedding smoke.

Its explicit qualification exception permits one controlled request at a time through a separate bounded qualification profile. The application-owned qualification owner enforces exclusive deployment ownership, one in-flight query or document request, finite cumulative request/token budgets and deadlines. Every attempted send must pass `reserve → mark_sent → finish`. A sent, timed-out, canceled or otherwise ambiguous attempt retains its charge. A provider adapter has no separate rate limiter and cannot execute without this owner. Unknown capacity refuses ordinary production dispatch; no guessed `Q_TPM` is supplied.

If a sent attempt is canceled or ambiguous, the owner refuses all remaining requests even when budget remains: the GPU may still be computing after its client disconnected. Do not automatically retry or create a replacement owner to consume the remaining allowance. Establish that earlier work has stopped, restart the runtime if necessary and repeat deployment attestation before beginning a new explicit qualification run.

The selected OpenAI route must return nonnegative integer `usage.prompt_tokens` and `usage.total_tokens` consistent with the exact sent-text token count. These are `provider_reported` metadata, separately retained alongside the local tokenizer estimate. The installed TEI commit's [OpenAI response implementation](https://github.com/huggingface/text-embeddings-inference/blob/e80ef225ed0e6cb1717ce632a6a84b6cf211bb67/router/src/http/server.rs#L1322) fills both from runtime inference metadata. This establishes observed provider response usage, not billing or sustainable capacity. Native `/embed` array responses do not carry that usage: a native diagnostic's local count remains `tokenizer_counted_proxy`, even when tokenization parity passes. Never substitute a local estimate for a missing provider usage field. Latency and tokens per second describe only the recorded workload and interval.

## Qualification gates and operations

Normal Workbench startup uses the repository-root launcher:

```powershell
& ./start.ps1
```

It calls the embedding helper with `-StartOnly`. An already running owned container is reused without Compose reconciliation or restarting its model process. A stopped owned container starts in the background; first-time provisioning also starts model loading in the background. The UI/API do not wait for embedding metadata or GPU readiness, and their lexical readiness remains independent.

For one-time setup on another checkout, copy `apps/workbench/embedding/.env.example` to the ignored `apps/workbench/embedding/.env` and set `WORKBENCH_EMBEDDING_MODEL_DIRECTORY` there. The qualified host already has its confirmed `A:/AI/TEI/qwen3-4b` path configured, so ordinary root launches need no repeated model-directory argument. Explicit helper arguments/environment take precedence when setup needs a source directory. The [startup/optimization follow-up](../../../tasks/evidence/embedding-2026-11-23/optimized-report.md) records running/stopped/reuse checks and measured cache results separately from the accepted bind-mount baseline.

The project owns [its Compose service](../../../apps/workbench/embedding/compose.yaml) and [PowerShell launcher](../../../apps/workbench/embedding/start.ps1). Docker with NVIDIA GPU support, the pinned image already present locally and an existing Qwen model directory are prerequisites. The service uses `pull_policy:never`, Hugging Face offline settings and a read-only Linux Docker volume mounted at `/models`. First-time setup copies nine approved local assets into the owned `rag-workbench-embedding-qwen3-4b-5cf2132abc99` volume through the [cache preparer](../../../scripts/workbench_embedding_cache.py); it never downloads weights or creates a missing source directory. Set `WORKBENCH_EMBEDDING_MODEL_DIRECTORY` to the existing source directory before explicit setup commands. The launcher also accepts an absolute `-ModelDirectory` argument.

The cache helper has no network or GPU access. It validates source identity, copies only the allowlist into a staging directory, verifies full SHA-256 digests and publishes the complete revision atomically. It preserves the host files without converting weights. Completed-cache reuse checks the approved manifest, file metadata and small-asset hashes; explicit model qualification independently rehashes all nine cached assets before and after the run and checks cached nanosecond timestamps per dispatch. A wrong volume owner/revision or changed cache refuses rather than silently replacing accepted assets. Provisioning cost and extra Docker disk usage are separate from model startup; use the optimization report for actual measured costs.

From the repository root:

```powershell
$env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY = 'A:/AI/TEI/qwen3-4b'
& ./apps/workbench/embedding/start.ps1 -ModelDirectory $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY -StartupEvidence tasks/evidence/embedding-2026-11-23/optimized-startup.json
```

The path shown is the operator-confirmed directory on the qualified host; select the actual approved path on another host. The launcher starts only this Compose service, waits for control-plane `/info` metadata and writes startup evidence without sending an embedding request. The container probe also uses `/info`: [TEI 1.9.4's backend health path](https://github.com/huggingface/text-embeddings-inference/blob/v1.9.4/backends/src/lib.rs#L352) can execute a model forward while recovering, so `/health` is unsuitable for an ungoverned metadata-only startup probe. Its default wait bound is 600 seconds. An occupied endpoint or exited/restarting model process refuses explicitly. A large model can remain loading before its metadata listener is ready; expiration of the observation deadline does not prove a process crash.

Reusing an already metadata-ready process records cold startup as not tested. If observation continues while the same initially loading process remains alive, startup duration is anchored to Docker's process `StartedAt` and the observed successful `/info` probe; launcher elapsed time is separate. This proves control-plane startup, not GPU readiness. Fresh-process provenance is required, and actual model readiness is established only by the subsequent governed embedding run. Runtime attestation and full asset hashes are checked by that qualification command.

The shipped `apps/workbench/embedding_profiles.yaml` contains only a disabled policy:

```yaml
embedding:
  mode: disabled
  endpoint: http://127.0.0.1:8082
  profile: null
```

`ApiSettings.from_env()` reads this through the existing bounded, alias-free YAML machinery. `WORKBENCH_EMBEDDING_CONFIG` selects an explicit operator YAML. Only `disabled` and `qualification_only` are accepted; the latter requires a complete pinned `EmbeddingProfile`. Loading that configuration does not create a model client, set readiness, alter registry rollout or enable ingestion/search. Runtime attestation and the exclusive admission owner remain mandatory. Do not commit machine paths, runtime fingerprints or credentials as portable defaults.

The explicit qualification script first inspects local assets/runtime and checks service tokenizer parity. It verifies the dedicated Compose project/service labels, reviewed command, endpoint binding and read-only model mount:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_qualify --model-directory $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY --container rag-workbench-embedding-1 --endpoint http://127.0.0.1:8082 --output .cache/workbench-embedding-qualify/metadata.json
```

The default command does not request vectors. To enable its bounded real-model run explicitly, add `--run` and select a separate evidence output:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_qualify --model-directory $env:WORKBENCH_EMBEDDING_MODEL_DIRECTORY --container rag-workbench-embedding-1 --endpoint http://127.0.0.1:8082 --run --output tasks/evidence/embedding-2026-11-23/optimized-runtime.json
```

This diagnostic constructs its qualified profile from verified local assets and deployment metadata; ordinary API startup stays disabled. It tests conservative bounds of 8192 native tokens per item/batch, eight items per batch, 30 seconds per adapter request and one concurrent request. These are qualification limits, not maximum model context or sustainable GPU capacity. The separate `test_embedding_model_smoke.py` is gated by `WORKBENCH_TEST_EMBEDDING_LIVE=1` and requires `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; optional `WORKBENCH_TEST_EMBEDDING_REPORT` selects its sanitized report path. Its absence is a deliberate test skip, not a live pass. Successful evidence contains counts, hashes and timings rather than raw inputs or vectors.

The server's `--max-batch-tokens` is 40960 because installed TEI requires that ceiling to cover its advertised maximum input length when automatic truncation is disabled. Its `--max-concurrent-requests:8` setting counts individual input permits, allowing this profile's eight-item batch; it is not the application's concurrency policy. The shared application owner permits only **one HTTP batch at a time** and refuses more than 8192 native tokens per input/batch before send. The server explicitly advertises `Qwen/Qwen3-Embedding-4B` as its served model name. These server compatibility settings do not expand the qualification allowance or establish sustainable GPU capacity.

Use the explicit local smoke, never API startup or HTTP search, to qualify an operator-configured deployment. The evidence must identify exact executed commands, model/container/tokenizer digests, selected endpoint, profile fingerprint and the following gates:

- At least 30 EN/RU/UK/code/long-text items embedded for both query and document purposes, with actual 2560-dimensional finite normalized output.
- Duplicate/reordered inputs compared with singleton results to establish response ordering and repeatability; query formatting and service/local token counts compared explicitly.
- Controlled unavailable/malformed/identity/timeout/429 cases exercised through the recipient implementation. Offline transport faults remain distinct from real provider results.
- Actual GPU identity and sampled memory, observed warm latency and proxy throughput recorded; cold load, saturation, maximum safe concurrency and sustained TPM remain unqualified unless separately measured.
- No vectors or raw inputs in evidence/logs; no database writes, model downloads or cloud requests; existing lexical regressions remain green.

The [current execution evidence](../../../tasks/evidence/embedding-2026-11-23/optimized-report.md) distinguishes actual observations from remaining gates. Process/container startup through metadata readiness is measured separately from the first governed embedding request and warm adapter latency. One-time cache preparation took 69.688 seconds; normal root reuse returned in 0.748 seconds, and root starting a stopped model returned in 1.427 seconds with other Workbench services already healthy. OS file caches may already be warm, TEI can perform its own startup warm-up, and GPU memory samples remain device-wide. Production throughput control and durable vector ingestion remain separate [TPM-001](../../../tasks/TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md) and [EMBED-002](../../../tasks/TASK-RAG-EMBED-002-durable-embedding-ingestion-and-backfill.md) work.

Rollback consists of closing the qualification owner and disabling its explicit configuration. With the same model-directory environment set, stop/remove only this project service:

```powershell
docker compose -p rag-workbench-embedding -f apps/workbench/embedding/compose.yaml stop embedding
docker compose -p rag-workbench-embedding -f apps/workbench/embedding/compose.yaml rm -f embedding
```

The explicit project name also prevents an inherited `COMPOSE_PROJECT_NAME` from selecting another project's service. The read-only source assets, model-cache volume and other containers are preserved. No database migration, corpus generation change, vector backfill or destructive database rollback is part of this task. The existing lexical API and processing policy remain independently usable.

## Source inspection and independent implementation

Donor commit `955fd049949d3fc462d555be14774e4b255aa15c` was inspected for [TEI behavior](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_embeddings.py), [profile semantics](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_profile.py), neutral contracts and its license. No donor implementation is copied. This implementation independently applies the selected Workbench contract and negative-test scenarios.

The donor Qwen profile uses a 1536-dimensional prefix with L2 normalization and a repository-specific query instruction. Those semantics do not match this full-2560 web-search profile. Its locally counted `usage_tokens` also cannot be carried over as provider-reported usage. PostgreSQL, existing native token counting, immutable profile ownership and the single admission boundary remain owned by this repository.

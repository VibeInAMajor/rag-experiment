# Standalone local reranker

This deployment prepares `Qwen/Qwen3-Reranker-0.6B` for future clients. It does not register a Workbench retrieval profile or call the model from the application. Quality qualification remains separate from service readiness.

Prerequisites: Docker Desktop with NVIDIA GPU support, enough shared GPU headroom, and the original model files. This deployment uses the official vLLM 0.34.0 linux/amd64 image pinned by manifest digest. [vLLM's Qwen3 instructions](https://docs.vllm.ai/en/stable/models/pooling_models/scoring/) explain the classification overrides and query/document template. The original snapshot is `e61197ed45024b0ed8a2d74b80b4d909f1255473`; first creation verifies the weight and tokenizer digests.

From the repository root, prepare ignored local configuration once:

```powershell
Copy-Item apps/workbench/reranking/.env.example apps/workbench/reranking/.env
# Edit the absolute model path in .env if necessary.
./apps/workbench/reranking/start.ps1
```

Alternatively pass `-ModelDirectory A:\AI\TEI\qwen3-reranker-0.6b` or set `WORKBENCH_RERANKER_MODEL_DIRECTORY`. Only the model directory is mounted, read-only; downloads and telemetry are disabled. The first creation pulls the pinned runtime image when missing. The source model files are not converted or replaced.

Root `./start.ps1` invokes this launcher with `-StartOnly`: a running container is reused, a stopped container is started, and an absent container is created. Model loading happens in the background. Standalone invocation without `-StartOnly` waits up to 600 seconds for health and verifies the served model. Existing containers are not recreated to apply configuration changes; inspect and deliberately recreate this deployment when changing its settings.

## Local HTTP interface

- Base URL: `http://127.0.0.1:8083`; Docker clients can reach `http://host.docker.internal:8083` on Docker Desktop if host networking permits.
- Health: `GET /health`; model identity: `GET /v1/models`.
- Reranking: `POST /rerank`; pair scoring: `POST /score`.
- Model name: `Qwen/Qwen3-Reranker-0.6B`.

```powershell
$request = @{
    model = 'Qwen/Qwen3-Reranker-0.6B'
    query = 'What is the capital of China?'
    documents = @('The capital of China is Beijing.', 'Gravity attracts objects with mass.')
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8083/rerank -Method Post -ContentType 'application/json' -Body $request
```

Send plain query/document strings: the server applies the original model's instruction template. Larger scores mean greater relevance; these are not calibrated answer correctness probabilities. Runtime context is deliberately limited to **4096 tokens per formatted pair**, with one scheduled sequence and 4096 batched tokens. Oversized inputs are rejected unless a caller explicitly requests runtime-supported truncation; clients should avoid truncating evidence silently. The model's full advertised context is not enabled by this deployment.

GPU float16, eager execution and `gpu_memory_utilization=0.14` reduce initial resource demand. That setting is not a hard VRAM quota or shared admission guarantee; the GPU is shared with embedding containers. Existing embedding capacity evidence predates this additional model process: repeat shared-load qualification before application integration. No latency, throughput or retrieval-quality qualification is implied. The endpoint has no authentication and is published only on host loopback; remote access requires a separate deployment decision.

## Operations

```powershell
docker logs --tail 100 rag-workbench-reranker-1
docker stop rag-workbench-reranker-1
./apps/workbench/reranking/start.ps1
```

Docker restart policy is `unless-stopped`; root startup also starts a deliberately stopped instance when next invoked. Failure to load the model is visible in Docker health/logs. Root startup does not wait for model readiness or make it a Workbench search capability. Database, embeddings and application configuration are independent.

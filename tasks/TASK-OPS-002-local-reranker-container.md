# TASK-OPS-002 — Standalone local Qwen reranker container

**Created:** 2026-11-26  
**Updated:** 2026-11-26  
**Status:** COMPLETE — standalone service running; application integration disabled

## A. Goal

Run the downloaded Qwen3-Reranker-0.6B as a local HTTP service and include its idempotent lifecycle in root `start.ps1`.

## B. Current state

Root startup delegates model lifecycle to `apps/workbench/embedding/start.ps1 -StartOnly`. The original reranker snapshot e61197ed45024b0ed8a2d74b80b4d909f1255473 is downloaded under A:/AI/TEI/qwen3-reranker-0.6b. Docker and shared RTX 4090 are available; about 4.7 GiB device memory was free before deployment.

## C. Scope

Dedicated Compose deployment, PowerShell launcher, operator instructions and root orchestration. Use official vLLM 0.34.0 pinned by linux/amd64 manifest digest and original local safetensors.

## D. Non-goals

No Workbench API adapter, retrieval profile, evaluation qualification, corpus access, migration, application configuration or UI change. RERANK-001/002 remain separate.

## E. Ownership

`apps/workbench/reranking/` owns this independent deployment; root startup owns orchestration. Reuse the existing embedding launcher's running/stopped ownership pattern without changing the embedding service.

## F. Lifecycle

Inspect exact container name and Compose ownership. Reuse running process, start stopped process, create absent service after validating local model and port availability. Root startup uses background model loading; standalone startup waits for Docker health. Never replace foreign containers or occupied ports.

## G. Model identity

Original Qwen/Qwen3-Reranker-0.6B revision above; verify weights and tokenizer SHA-256 before first creation. Bind model directory read-only and disable Hub downloads/telemetry. Use its query/document chat template and documented vLLM classification overrides for yes/no logits.

## H. HTTP contract

Loopback 8083 forwards server 8000. Native vLLM `/health`, `/v1/models`, `/rerank` and `/score`; served model name Qwen/Qwen3-Reranker-0.6B. Scores are relevance ranking signals, not answer correctness probabilities. Runtime pair limit 4096 tokens, one scheduled sequence, no requested truncation.

## I. Resource envelope

GPU dtype float16, eager mode, 0.14 GPU utilization setting, 4096 batched tokens, one scheduled sequence. This is conservative startup configuration, not a hard VRAM limit or qualified shared admission budget. Observe actual device usage and model inference. The first 0.12 attempt failed KV-cache planning (0.30 GiB available vs 0.44 GiB required for 4096 tokens); increase the budget rather than silently reduce the documented context.

## J. Security

Local-only unauthenticated development endpoint; no application credentials or corpus mount. Read-only model assets, no remote model code, bounded Docker logs and restart unless-stopped. Startup preserves existing deployments and data.

## K. Acceptance

- Container becomes healthy and serves the expected model.
- Relevant synthetic document ranks above unrelated text.
- Running startup preserves ID and StartedAt.
- Stopped startup restarts the same container.
- Root startup includes reranker without enabling retrieval integration.

## L. Checks

Hatch version preflight; PowerShell 5.1/7 parser checks, Compose validation, real health/models/rerank, repeat/stopped lifecycle and root startup. No Python/frontend source changes; their suites are outside this deployment-only scope.

## M. Documentation

Add deployment README, project-map owner and API startup link. Add scoped release note. Record actual runtime evidence below, distinguishing startup from quality qualification.

## N. Rollback

Stop/remove only this Compose service and remove the root invocation. Source model and existing database/embedding containers remain intact. Never delete the shared Docker engine or model source directory.

## O. Completion evidence

Completed on 2026-11-26 against checkout `5b35df0` plus scoped working-tree changes. Created `apps/workbench/reranking/compose.yaml`, `start.ps1`, `.env.example` and README; configured ignored local `.env`; added one root launcher call and endpoint output. Updated API startup guidance, project map and scoped release note. Reused the existing embedding launcher's exact-name/Compose-ownership running/stopped lifecycle pattern and root startup mutex. No Python package, database, application API or retrieval-profile changes.

Passed:

- Hatch 1.18.2 preflight; PowerShell 5.1 and 7 parsing; final Compose validation and `git diff --check`; `hatch run reno lint`.
- Real initial creation, Docker health and `/v1/models` identifying Qwen/Qwen3-Reranker-0.6B with 4096-token context.
- Synthetic `/rerank` and `/score` smoke: Beijing passage outranks gravity passage; initial rerank scores approximately 0.999496 vs 0.0000137. An oversized pair is rejected with HTTP 400, without silent truncation.
- Root startup under Windows PowerShell 5.1 and standalone PowerShell 7 reuse the running container with unchanged ID and StartedAt.
- After explicitly stopping only the owned reranker, root PowerShell 7 startup restarts that same container; standalone readiness and HTTP checks pass again with zero automatic restarts.
- Existing project PostgreSQL, project embedding and shared quality embedding preserve their container IDs and StartedAt. Site/API/validator are reused; API readiness remains HTTP 200.

Final container ID: `9e683389d384b7c286225cd4f696db8913552f7f145b72b1d43e8916782891e9`. Published port is only `127.0.0.1:8083`; model source mount is read-only. Total shared-device memory observed after recovery was about 22.2k MiB of 24,564 MiB, not an exclusive reranker allocation or peak-load qualification. Local detailed smoke/lifecycle records are under ignored `.cache/reranker/`.

The initial 0.12 GPU budget failed cache planning and was corrected to 0.14; final startup/restart checks passed. Upstream Torch dtype/deprecation and eager-mode notices remain in runtime logs; no application code suppressions were added. Python/frontend suites, workload latency/throughput, full 32k context and retrieval quality were not tested for this deployment-only change. Shared embedding capacity must be requalified before using this model in application traffic. RERANK-001/002 are not marked qualified or integrated.

# Workbench embedding autostart and model-cache optimization — 2026-11-24

**Status:** COMPLETE. Automatic root-launcher reuse/background start, verified Linux model-cache provisioning, measured process startup and actual governed model output passed. Production TPM remains unqualified.

## Accepted baseline and hypothesis

The [accepted dedicated bind-mount report](dedicated-report.md), [startup](dedicated-startup.json) and [runtime](dedicated-runtime.json) remain unchanged. That process took **242.17 seconds** to metadata readiness; real model output was proved separately through 50 governed requests. This is the comparison baseline, not a cold OS-cache claim.

[Baseline I/O diagnostics](startup-io-baseline.json) identified a Windows-host `9p` bind with `msize=65536`, approximately 228.57 seconds in logged weight loading and a 25.013-second container sequential read. The 61,696 major faults were cumulative after startup/qualification, not an isolated startup counter. A host SHA-256 pass took 7.071 seconds; it is a different operation and is not used as a direct speedup ratio. A small already-cached scattered-read control showed no meaningful Windows/Linux advantage. The controlled full model reload below, rather than these microprobes alone, tests the storage hypothesis.

Docker's [WSL filesystem guidance](https://docs.docker.com/desktop/features/wsl/best-practices/#optimise-file-system-performance-with-bind-mounts) recommends Linux-filesystem data for container filesystem performance. The installed [TEI Candle backend](https://github.com/huggingface/text-embeddings-inference/blob/v1.9.4/backends/candle/src/lib.rs#L254) loads safetensors through memory mapping. These explain the hypothesis; the controlled startup comparison must establish actual improvement on this host.

## Requested launch behavior

Root `start.ps1` calls the project helper with `-StartOnly`. An already running owned container is reused without Compose reconciliation or a model restart. A stopped owned container starts in the background with its existing identity. Missing-container setup uses the confirmed model directory and verified project provisioning, then starts in the background. Workbench UI/API launch does not wait for model readiness; lexical readiness and embedding qualification remain independent.

The helper reads the explicit model-directory argument/environment first and the ignored `apps/workbench/embedding/.env` fallback when first-time setup needs it. The committed `.env.example` describes that local setting. The qualified host already has the confirmed `A:\AI\TEI\qwen3-4b` path configured. No credentials or machine path are committed as runtime defaults.

## Measurement gates

- [x] Source/destination assets match the pinned allowlist; provisioning is atomic and reusable without a model download.
- [x] One-time cache provisioning cost is reported separately from new-process metadata startup.
- [x] Optimized startup uses the same pinned image/model/profile and real process/readiness timestamps.
- [x] Optimized governed query/document output and usage provenance pass against the actual cache-mounted deployment.
- [x] Root launcher running/stopped/repeated branches preserve the correct project; zero foreign-project containers are created.
- [x] Regression/quality results and rollback are recorded without overwriting baseline evidence.

The physical GPU and OS caches remain shared. No saturated throughput, exclusive-device memory or production TPM claim follows from this optimization.

## First measured cache/startup result

[Initial cache preparation](optimized-cache.json) copied and verified the approved assets in **69.688 seconds**, without model conversion, network download or model inference. The actual volume is `rag-workbench-embedding-qwen3-4b-5cf2132abc99`; the runtime mounts it read-only. A subsequent helper cache-reuse check took **0.891 seconds**. Initial provisioning is a separate one-time cost and is not hidden inside the startup comparison.

The first [optimized process startup](optimized-startup.json) ran from `2026-11-23T22:19:49.387Z` to metadata readiness at `2026-11-23T22:20:20.092Z`: **30.705 seconds**, compared with the accepted **242.171-second** bind baseline. This measured **7.887×** reduction is specific to this host and these runs; neither clears OS file caches. Launcher elapsed time after preparation was **32.460 seconds**, sampled device-wide startup peak **23693 MiB**. The pinned image, weight bytes and profile definition remain unchanged.

Logged weight loading fell from **228.570 seconds** to **11.462 seconds**; TEI's internal warm-up took **14.724 seconds** in this optimized run and shares the GPU with the untouched other project. The comparison supports the filesystem optimization on this machine without claiming a universal speedup, exclusive GPU access or a changed inference model.

The [named-volume attestation suite](optimized-attestation-tests.xml) passed **54 offline tests** with one explicitly gated live skip. It verifies owned volume identity/labels, read-only mount, all nine cached asset hashes/sizes against the approved host-source manifest, metadata-only health and per-dispatch cached timestamp checks. The separate explicitly enabled GPU run below supplies real model proof rather than treating that skip as success.

## Root-launcher lifecycle proof

[Actual launcher evidence](startup-launcher.json) passed with ambient `COMPOSE_PROJECT_NAME=foreign-project-guard-test`. Starting the stopped owned container through root `start.ps1` returned in **1.427 seconds** and left model loading in the background, preserving the container ID while changing its process start. Metadata became available **17.376 seconds** after that process start. A subsequent root launch returned in **0.748 seconds** with the same container ID and process `StartedAt`; it did not restart/reconcile the running model. Zero foreign-project containers were created.

The 17.376-second repeat process start used an already provisioned Linux volume with OS caches not cleared. It is recorded separately from the first optimized 30.705-second start; those cache states are not conflated or presented as a guaranteed cold-disk result. Actual model readiness then passed the optimized governed inference gate below. The root timings above were measured with the other Workbench services already healthy; they do not include first-time frontend dependency/build or database setup costs.

## Final optimized model proof

The [explicit real-model test](optimized-live-tests.xml) passed **1 test in 54.12 seconds**, and the [final regression collection](optimized-regressions.xml) passed **235 tests in 6.91 seconds**. [Optimized runtime evidence](optimized-runtime.json) records the actual cache-mounted deployment, all source/cached hashes unchanged after execution and profile fingerprint `b43c64ffe7d2511e0ffd2c15e5458d0651fbf65b57b4f9194998bcb352366f3e`. Deployment-attestation digest is `fd5996cb0d88b610e38ebf61d68420e2dccd3586812641498288abcf2a00a3d0`.

| Model gate | Final observed result |
| --- | --- |
| Workload | 30 EN/RU/UK/code/long texts, all embedded for query and document purposes |
| Full output | 2560 finite components; observed norms 0.9999999688..1.0000000313 |
| Document ordering | All 30 batch/singleton comparisons; minimum cosine 0.999996356 |
| Query repeatability | Five category representatives; minimum cosine 0.999996371 |
| Native parity | Five comparisons, cosine 1, maximum absolute difference 0 |
| Exact token parity | Six service/local token-ID/count comparisons passed |
| Boundary | Exactly 8192 tokens accepted for both purposes; larger repeat refused before send |
| Admission | 50 reservations, sends, finishes and successes; one HTTP batch at a time; no retries or unknown usage |
| Usage provenance | 42,435 provider-reported OpenAI tokens plus 489 native-diagnostic proxy tokens; 42,924 admitted estimates |
| Integrity | All nine host and cached assets unchanged after the run |

The first instrumented adapter call took **859 ms**. The 44 warm OpenAI calls had minimum **406 ms**, p50 **438 ms**, p95 **1172 ms**, maximum **1328 ms**. Provider-reported throughput was **1780.813 tokens/s** over summed complete adapter call durations; the live interval was **30.641 seconds**, excluding full initial/final asset hashing. These calls now include additional cached-file Docker execution and volume attestation before/after dispatch. Their measured latency is higher than the bind qualification's 141/813 ms p50/p95; this is an instrumented qualification-path comparison, not a TEI kernel benchmark or a claim of faster inference.

On the same RTX 4090 (24564 MiB, driver 617.42), inference-phase device-wide baseline was **18665 MiB** and sampled peak **19563 MiB**. The first optimized startup peak was separately **23693 MiB**. Memory is sampled across the shared physical card, not attributed exclusively to this model. Sustained GPU throughput, maximum concurrency and production sustainable TPM remain NOT TESTED / NOT QUALIFIED.

Synthetic matched-document cross-language cosine p50 values were EN/RU **0.694844**, EN/UK **0.641294**, RU/UK **0.927104**; they are diagnostics, not retrieval-quality acceptance. Wrong model/tokenizer identity, injected trusted drift and a local client outage were refused with zero additional inference attempts. The preexisting 8081 project's container ID, process start and restart count zero remained unchanged after all checks.

## Quality, ownership and rollback

Application Ruff/format and mypy passed for **111 files**; both cache/qualification scripts passed separate Ruff/format/mypy checks. PowerShell/Compose/source-text and lifecycle checks are recorded with actual commands in [optimized-quality-checks.txt](optimized-quality-checks.txt). No fresh full PostgreSQL, browser/frontend or upstream-wide suite is claimed: this follow-up changes orchestration/model assets, with no schema or UI change.

Root orchestration is owned by [start.ps1](../../../start.ps1) and the [model helper](../../../apps/workbench/embedding/start.ps1). The [Compose service](../../../apps/workbench/embedding/compose.yaml) mounts only the verified read-only volume; the [cache preparer](../../../scripts/workbench_embedding_cache.py), [qualification verifier](../../../scripts/workbench_embedding_qualify.py) and [cache regression tests](../../../apps/workbench/api/tests/test_embedding_cache.py) share the pinned asset/ownership contract. [Local configuration template](../../../apps/workbench/embedding/.env.example) contains no real machine path or credentials. The ignored `.env` retains this host's confirmed source directory.

To stop/remove only this model container, use `docker compose -p rag-workbench-embedding -f apps/workbench/embedding/compose.yaml stop embedding`, then `docker compose -p rag-workbench-embedding -f apps/workbench/embedding/compose.yaml rm -f embedding`. The external model-cache volume, host assets, unrelated model service and PostgreSQL data remain intact. Stopping it is temporary: the next root launcher starts the owned service again by design. No automatic cache/volume deletion is performed.

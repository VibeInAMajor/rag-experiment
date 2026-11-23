# Dedicated Workbench embedding deployment — 2026-11-24 (Europe/Kiev)

**Status:** COMPLETE. The project-owned TEI service passed new-process startup, strict deployment attestation, governed 30-text query/document qualification and project-isolation checks. Production TPM remains unqualified.

The artifact directory retains the original task date, `embedding-2026-11-23`; the dedicated follow-up crosses midnight into November 24 in Kyiv. All accepted startup and inference results below come from the corrected final deployment artifacts.

## Scope and historical evidence

The [original provider report](report.md) and [original runtime artifact](runtime.json) describe the existing shared service at `127.0.0.1:8081`. They remain historical evidence and are not relabeled as results from this project deployment.

The new deployment target is `rag-workbench-embedding-1` on `127.0.0.1:8082`, with the same pinned Qwen model assets mounted read-only and an immutable TEI image. Separate process, command, labels, mount and port attestation must establish that this project owns the endpoint. Ordinary API settings remain disabled; this work does not enable ingestion, semantic search or production TPM control.

## Startup measurement boundaries

The requested cold-start proof concerns a newly launched process/container loading the model, measured from Docker's actual process `StartedAt` through an observed successful metadata-only `/info` probe. Launcher wall time is recorded separately. This is control-plane startup, not GPU readiness; the latter requires the subsequent governed embedding output. Continuing observation of that same initial loading process after a wait deadline does not restart it or reset the startup clock. Fresh initial process provenance is required; recovery of an older unhealthy process alone is not cold-start evidence. This does not promise empty OS disk caches, exclusive disk bandwidth, an exclusive GPU or a cold first GPU kernel. TEI performs its own startup warm-up outside application request accounting. The first governed client request is therefore reported separately from container startup and warm adapter latency.

The prior shared TEI container is not stopped or repurposed. Both services use the same physical GPU; device-wide memory and latency can include the other process. One application HTTP batch at a time, eight client items and an application-level 8192-token per-item/batch allowance bound this qualification. The server batch ceiling is separately 40960 and its input permit count is eight for installed TEI compatibility. These settings do not establish sustainable TPM or a 0.95 admission ceiling.

## Configuration issue found before acceptance

The first project launch refused the initial server `max-batch-tokens:8192` configuration before model GPU loading: installed TEI requires its batch ceiling to cover the advertised 40960-token maximum input when `auto_truncate:false`. Installed CLI help exposed no independent maximum-input override. Only the failed project container was stopped. The reviewed server ceiling was corrected to 40960; the application profile, shared admission and real qualification remain bounded to 8192 tokens and one in-flight request. Final startup acceptance requires the corrected new-process run below, not the failed launch. The existing shared 8081 service was not changed.

The next process became healthy, but its first eight-item HTTP batch returned 429 because TEI's `max-concurrent-requests:1` counts **individual input permits**, not HTTP batches. The reviewed server setting was corrected to eight permits while the application admission owner still allows only one HTTP batch at a time. Its served model name was also made explicit as `Qwen/Qwen3-Embedding-4B`. Only the project container is recreated for this command change; final cold-load and inference acceptance must describe that corrected process. The [initial failed real-model test](dedicated-initial-live-tests.xml) is retained separately (one failed test); it is not a 50-call success.

Ownership review also fixed an inherited-environment risk: `COMPOSE_PROJECT_NAME` can override Compose's top-level `name`. The launcher now passes `--project-name rag-workbench-embedding` explicitly, and manual stop/remove commands use the same pinned project. Actual deployed labels were already correct; this prevents later operator environments from selecting another project's service.

Governor review found that TEI's `/health` can execute a model forward when the backend is starting or unhealthy. The project probe was changed to metadata-only `/info`, with a 300-second loading grace period; attestation rejects an inference-capable health probe. The final project process is recreated for this configuration change. Startup metadata success is reported separately from model readiness, which must pass under the shared application owner. TEI's own internal startup warm-up is disclosed and is not presented as an application request or provider-reported completed usage. See the [official health implementation](https://github.com/huggingface/text-embeddings-inference/blob/v1.9.4/backends/src/lib.rs#L352).

## Evidence and checks

The final project process passed metadata-only startup. Its [startup artifact](dedicated-startup.json) records process start `2026-11-23T22:04:35.811Z` through successful metadata probe `2026-11-23T22:08:37.982Z`: **242170.5956 ms (242.17 seconds)**. Launcher elapsed time was **243809.4585 ms (243.81 seconds)**. This final invocation records `new_model_process:true`, restart count zero and a sampled shared-device startup memory peak of **23673 MiB**. The subsequent governed embedding run proved actual model readiness. No shared-service inference metrics are copied here.

The inference harness itself reports cold startup as not tested because it attaches after the launcher has loaded the service. That field retains its actual scope: separate launcher evidence above supplies the new-process startup measurement, while the harness supplies subsequent governed GPU proof.

For an earlier intermediate process, the first launcher's original 180-second observation limit expired while weights were still loading. The helper's default was increased to 600 seconds and observation continued against that same process without resetting its startup clock; it reached metadata readiness after 238.08 seconds. That process was later recreated for the reviewed permit and probe changes, so its timing is not the final deployment measurement above. The final process completed under one 600-second launcher invocation. OS caches were not cleared and may have been warm; TEI startup warm-up remains included.

The dedicated [offline attestation suite](dedicated-attestation-tests.xml) passed **41 tests in 6.46 seconds** with one explicitly gated live skip. It includes the Compose-to-attestation command contract, metadata-only health probe, per-input permit setting, explicit served model name, project labels, exact endpoint binding, local model identity and rejection cases. That skipped model test is not runtime proof; actual dedicated inference must be recorded separately.

The updated [focused regression collection](dedicated-regressions.xml) passed **203 tests in 5.97 seconds**, including embedding/configuration/domain/admission and deployment-architecture contracts. Both local weight shards were verified against official pinned digests before launching the new process; full assets were rechecked unchanged after qualification.

Executed: `hatch run workbench-api:python -m pytest apps/workbench/api/tests/test_configuration.py apps/workbench/api/tests/test_embedding_configuration.py apps/workbench/api/tests/test_embedding_adapter.py apps/workbench/api/tests/test_embedding_attestation.py apps/workbench/api/tests/test_embedding_domain.py apps/workbench/api/tests/test_embedding_dispatch.py apps/workbench/api/tests/test_http_contract.py -q --override-ini addopts='' --junitxml=tasks/evidence/embedding-2026-11-23/dedicated-regressions.xml`.

Final scoped quality checks passed: application Ruff/format for 110 files, application mypy for 110 files, separate qualifier Ruff/format/mypy, PowerShell launcher parsing, interpolated Compose configuration, strict UTF-8 across the changed files, sidebar Node syntax and `git diff --check`. No new UI or PostgreSQL code is introduced in this deployment follow-up; a new frontend/browser or full database run is not claimed. The earlier independent database proof remains in the original report.

Exact commands and results are recorded in [dedicated-quality-checks.txt](dedicated-quality-checks.txt).

## Final dedicated model results

The explicit gated [real-model test](dedicated-live-tests.xml) passed **1 test in 30.03 seconds**. [Dedicated runtime evidence](dedicated-runtime.json) binds container `bafcd45ee694b71461c0ba8e745c0da6a2ee35662f008473285a11544e17c3c3` to the project/service labels, pinned image and assets, reviewed command, metadata-only probe and actual `127.0.0.1:8082` binding. Profile fingerprint is `b43c64ffe7d2511e0ffd2c15e5458d0651fbf65b57b4f9194998bcb352366f3e`; deployment-attestation digest is `a8e3c7b3789059b6c9cabcdb52bed8bbf3746ca3d0b483021d8dd0d0598feac1`.

| Gate | Final observed result |
| --- | --- |
| Representative inputs | 30 EN/RU/UK/code/long texts, all embedded for query and document purposes |
| Actual output | Full 2560 finite components; observed norms 0.9999999443..1.0000000313 |
| Document ordering | All 30 batch/singleton comparisons passed; minimum cosine 0.999993190 |
| Query repeatability | Five category representatives passed; minimum cosine 0.999996687 |
| Native diagnostic parity | Five comparisons; cosine 1 and maximum absolute difference 0 |
| Tokenizer parity | Six exact service/local token-ID/count comparisons passed |
| Input boundary | Exactly 8192 native tokens accepted for each purpose; next larger repeat refused before send |
| Shared admission | 50 reserved/sent/finished/successful requests; one HTTP batch at a time; no retries or unknown usage |
| Usage provenance | 42,435 provider-reported OpenAI tokens, 489 native-diagnostic tokenizer proxy tokens; total 42,924 admitted estimates |
| Asset integrity | Complete pinned model/tokenizer/config assets unchanged after the run |

The first external governed adapter call took **453 ms** after metadata startup and verification. The 44 subsequent OpenAI calls had adapter latency minimum **109 ms**, p50 **141 ms**, p95 **813 ms**, maximum **875 ms**. Observed provider-reported throughput was **4166.012 tokens/s**, with summed complete adapter durations including preparation and pre/post attestation as the denominator. The live interval was **14.578 seconds**, excluding full initial/final asset hashing. These are workload observations, not kernel-only measurements or sustainable TPM.

The RTX 4090 reported **24564 MiB** total device memory and driver 617.42. During inference, device-wide baseline was **18740 MiB**, sampled peak **19555 MiB**; the separate startup sample peak above was **23673 MiB**. Other clients share this card and polling may miss shorter peaks. Neither phase is a model-exclusive allocation measurement. Maximum sustainable concurrency, saturation and production sustainable TPM remain **NOT TESTED / NOT QUALIFIED**; application concurrency is deliberately one HTTP batch.

Descriptive cross-language document cosine p50 values were EN/RU **0.694714**, EN/UK **0.641266**, RU/UK **0.927180**. They do not certify retrieval quality or enable semantic search. Real-adapter negative diagnostics refused wrong model/tokenizer digests, injected trusted drift and a locally unreachable client endpoint with **zero additional inference attempts**; injected drift disabled further adapter execution. The dedicated service was not stopped/reloaded for those injected fault cases.

## Reuse and other-project preservation

[Reuse evidence](dedicated-reuse.json) passed with ambient `COMPOSE_PROJECT_NAME=foreign-project-guard-test`: the helper still selected `rag-workbench-embedding`, preserved its container ID/process start/restart count, and created zero foreign-project containers (query exit code zero). Reusing this already-ready process is not another cold-start measurement.

Read-only Docker inspection after qualification also found the preexisting 8081 container's ID, `StartedAt` (`2026-11-23T20:33:36.236Z`) and restart count zero unchanged. The original `runtime.json` and report retain their shared-service provenance. No database or UI behavior changed.

The operator confirmed `A:\AI\TEI\qwen3-4b` as the existing model directory. Launch command from the repository root:

```powershell
& ./apps/workbench/embedding/start.ps1 -ModelDirectory 'A:/AI/TEI/qwen3-4b' -StartupEvidence tasks/evidence/embedding-2026-11-23/dedicated-startup.json
```

## Rollback

Stop/remove only the project-owned service using its reviewed Compose/helper boundary. Preserve the read-only model assets, existing shared TEI service and all PostgreSQL data. No database migration is required.

## Changed ownership

Project service and launch evidence: [compose.yaml](../../../apps/workbench/embedding/compose.yaml), [start.ps1](../../../apps/workbench/embedding/start.ps1). Dedicated attestation/qualification remains in [workbench_embedding_qualify.py](../../../scripts/workbench_embedding_qualify.py) and [recipient tests](../../../apps/workbench/api/tests/test_embedding_attestation.py). Default-disabled endpoint selection remains in [embedding settings](../../../apps/workbench/api/embedding_config.py) and [operator YAML](../../../apps/workbench/embedding_profiles.yaml). The existing provider, tokenizer, one admission owner and profile fingerprint are reused. No second model client, limiter, database or tokenizer is introduced.

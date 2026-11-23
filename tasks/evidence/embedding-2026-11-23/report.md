# Local embedding qualification — 2026-11-23

**Status:** COMPLETE for EMBED-001's internal provider and bounded qualification scope. The corrected deployment-attestation checks, real GPU smoke and backend/database regressions passed. Production TPM and durable vector ingestion remain unqualified successor work.

**Inspected base:** `d9f629ff1d95d1b2c6585e788a09d55849d209f3`, plus this task's working-tree changes. The task file already contained the user's edits before implementation; those edits are preserved. No database migration is required. INDEX-001's 0003 and PROFILE-001's 0004 were applied before this task.

## Evidence boundaries

The deliverable qualifies the internal provider's model I/O and a conservative, exclusive, finite-budget qualification mode. It does not certify production sustainable TPM, adaptive utilization, a 0.95 rolling-window ceiling, concurrent load, vector ingestion, ANN, hybrid retrieval or semantic HTTP capability. Provider failure never becomes synthetic success.

Production TPM-001 remains open. Its explicit J1 qualification exception permits one controlled request at a time through a separate qualification profile while capacity is unknown. A shared qualification owner, rather than an adapter-local limiter, covers both request purposes. No measured sustainable capacity or guessed GPU-derived quota is supplied.

## Source-to-recipient decision

Donor source was fetched read-only at `955fd049949d3fc462d555be14774e4b255aa15c`; implementation is independent and no donor source is copied.

| Inspected source | Finding | Recipient decision |
| --- | --- | --- |
| `providers/tei_embeddings.py`, Git blob `258f46514d3d7eb82841eba022abba69aaf14c87` | Native `inputs`, `truncate:false`, `normalize:true`; bounded/redacted transport; native-token count reported as usage | Independently implement the installed TEI contract and negative scenarios; retain truthful proxy provenance |
| `providers/tei_profile.py` | Qwen full dimension 2560, donor output 1536 through prefix/L2 projection; repository query instruction | Full 2560 dimensions selected; no donor transform or query policy |
| `rag/embeddings.py` | Neutral profile/request/batch/error contracts and deterministic fake | Independent immutable Workbench port with existing native counter and profile owners |
| `tests/pipeline/test_tei_embedding_provider.py` | Deployment mismatch, malformed vectors, redirects, cancellation, limits and failures | Exercise these scenarios against the recipient implementation; donor tests are not recipient evidence |
| `LICENSE.md` | Source-available PolyForm Strict / Authorized Evaluation text | Inspection recorded; no source copying or donor package dependency |
| Existing Workbench owners | Native counter, configuration, immutable profile registry, PostgreSQL | Reuse existing owners; no Qdrant/SQLite stack, duplicate counter or applied-SQL changes |

Pinned sources: [adapter](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_embeddings.py), [profile](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/providers/tei_profile.py), [contract](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/rag/embeddings.py), [tests](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_tei_embedding_provider.py), [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## Runtime inspection before inference

Actual container/file inspection found TEI 1.9.4 with immutable image `sha256:d139efce84ee1d23405d64e4dc0b82d583c463fce3ff707eb65c47a8a1b7f69c`, a read-only pinned-revision model mount and `/info` with `model_sha: null`. Both local weight shards matched the exact revision-specific official SHA-256 and byte sizes in the [operator guide](../../../docs-website/docs/architecture/local-embedding-provider.md). Tokenizer/config assets matched the three existing `LocalQwenTokenCounter` pinned digests. No model weights were downloaded for verification.

The actual TEI source revision is `e80ef225ed0e6cb1717ce632a6a84b6cf211bb67`. Its [OpenAI response path](https://github.com/huggingface/text-embeddings-inference/blob/e80ef225ed0e6cb1717ce632a6a84b6cf211bb67/router/src/http/server.rs#L1322) derives `prompt_tokens` and `total_tokens` from inference metadata. The selected adapter validates that provider-reported usage against the separately retained local token estimate; the donor native-array proxy semantics are not applied to this route.

The metadata-null limitation is explicit: model revision is supported by the trusted operator/container/mount/file chain, not an independent TEI model-sha assertion. Every model call must still validate service metadata identity. This is not hostile-host attestation.

## Live gates

The explicit bounded real-model run and separately gated pytest **passed**. [Sanitized runtime evidence](runtime.json) is the final run after correcting container/model/endpoint attestation, superseding earlier smoke artifacts. It contains actual metadata, per-request identities/counts/norms, token parity and aggregate timings; it contains no source texts or vectors. All measurements below were recomputed from that final artifact.

Executed from the repository root:

```powershell
hatch run workbench-api:python -m scripts.workbench_embedding_qualify --model-directory 'A:/AI/TEI/qwen3-4b' --container portable-tei-local-quality-1 --run --output tasks/evidence/embedding-2026-11-23/runtime.json
```

The final run used `WORKBENCH_TEST_EMBEDDING_LIVE=1`, `WORKBENCH_TEST_QWEN_TOKENIZER_DIR=A:/AI/TEI/qwen3-4b` and `WORKBENCH_TEST_EMBEDDING_REPORT=tasks/evidence/embedding-2026-11-23/runtime.json`, then `hatch run workbench-api:python -m pytest apps/workbench/api/tests/test_embedding_model_smoke.py -q --junitxml=tasks/evidence/embedding-2026-11-23/live-tests.xml`: [**1 passed in 26.98 seconds**](live-tests.xml). This test really executes the GPU path rather than substituting the offline fake. Final trusted-attestation evidence digest: `24cdb63a314cd727bc2574c3c95a9e0bba79e15926436335af2a653582679429`.

Qualified profile revision: `qwen3-4b-web-r1`, fingerprint `b43c64ffe7d2511e0ffd2c15e5458d0651fbf65b57b4f9194998bcb352366f3e`; aggregate model digest `cd97e9cb507f62c0b69e6540ecabbb877508ba71437d2d227f25cd611b8ae67d`; tokenizer digest `3d456a234fcae954923af3a43363d38828146971ce98cbd21fcbe5a97aa7cee7`. Pooling is `last_token`, inference dtype `float16`, output encoding `float` JSON numbers.

| Gate | Observed result |
| --- | --- |
| Representative workload | 30 texts: EN, RU, UK, code and long-text groups; all 30 embedded for document and query purposes |
| Output | Actual 2560 finite components per vector; observed norms 0.9999999691..1.0000000322 |
| Document ordering | All 30 batched outputs compared with their singleton outputs; minimum cosine 0.999989846 |
| Query repeatability | Five category representatives compared between batch and singleton; minimum cosine 0.999995987 |
| Selected endpoint | OpenAI `/v1/embeddings`; five native `/embed` diagnostic comparisons had cosine 1 and maximum absolute difference 0 |
| Native token parity | Service token IDs/counts matched the pinned local tokenizer on six Unicode/instruction/special-token cases |
| Boundary admission | Exactly 8192 actual sent-text tokens accepted for both purposes; next larger repeat refused before model dispatch |
| Shared owner | 50 reservations, sends, finishes and successes; one in-flight maximum; no retries or unknown usage |
| Usage | 42,435 provider-reported OpenAI tokens; 489 native-diagnostic tokenizer proxy tokens; 42,924 admitted estimates total |
| Asset integrity | Full pinned assets hashed before and after; unchanged |

The first observed adapter request took **422 ms**; it is **not a cold-load measurement** because the shared runtime was already running. The 44 subsequent OpenAI calls had warm adapter p50 **141 ms**, p95 **719 ms**, minimum **109 ms**, maximum **875 ms**. Observed provider-reported token throughput was **4352.308 tokens/s**, using summed complete adapter call durations, including input preparation and pre/post attestation. The live experiment interval was 14.062 seconds, excluding full initial/final asset hashing. These are not TEI kernel-only latency/throughput measurements and do not establish sustainable TPM.

The actual GPU was NVIDIA GeForce RTX 4090, driver 617.42, total **24564 MiB**. Device-wide memory was **11126 MiB** before the run and peaked at **12054 MiB** among recorded samples. Other clients may contribute and polling can miss a shorter peak: these are sampled shared-device observations, not model-exclusive allocation measurements. Cold startup, maximum sustainable concurrency, saturated throughput and production sustainable TPM are **NOT TESTED / NOT QUALIFIED**. Qualified concurrency is deliberately one.

Cross-language cosine distributions are descriptive synthetic diagnostics, not retrieval-quality acceptance: EN/RU p50 0.694844, EN/UK p50 0.641294, RU/UK p50 0.927104. No semantic search endpoint, relevance benchmark or downstream representation is certified by those values.

Real-adapter negative diagnostics refused wrong model/tokenizer digests, injected trusted-attestation drift and an unreachable local client endpoint without adding any model inference attempts. Drift returned `IDENTITY_MISMATCH` and disabled the adapter (`NOT_QUALIFIED` on the next request). These failures use injected identity/client conditions; the shared TEI service was not actually stopped or reloaded. Offline tests separately exercise transport HTTP errors, malformed vectors, cancellation and timeouts.

## Checks

Hatch 1.18.2 was verified. [Focused embedding regressions](embedding-tests.xml): **103 passed in 4.09 seconds** (39 transport, 14 domain, 19 admission, 31 configuration); [deployment-attestation mutations](attestation-tests.xml): **20 passed in 3.46 seconds**. The first [full API collection](api-tests.xml) passed **869 tests with 198 skips in 88.92 seconds**; it began before the final configuration tests were added, which the focused run covers. Database/live skips in that collection are not runtime proof. The [full application collection with real disposable PostgreSQL databases](database-tests.xml) then passed **1085 tests with 17 optional asset/model skips in 248.23 seconds**. The separately enabled model run covers this task's actual local GPU requirement. No UI or Haystack public API change was introduced.

Database environment was loaded with the existing `apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin` workflow and explicit test admin/app DSNs, without printing credentials. Command: `hatch run workbench-api:test apps/workbench/api/tests/test_database_migrations.py apps/workbench/api/tests/test_postgres_persistence.py apps/workbench/api/tests/test_index_generations.py apps/workbench/api/tests/test_index_reconciliation.py apps/workbench/api/tests/test_profile_registry.py apps/workbench/api/tests/test_profile_routes.py apps/workbench/api/tests/test_lexical_routes.py apps/workbench/api/tests/test_ingestion_persistence.py --override-ini addopts='' --junitxml=tasks/evidence/embedding-2026-11-23/database-tests.xml`. The Hatch alias always includes the application test root, so this ran the whole application suite rather than only the appended modules. Disposable-database fixtures retained their existing UUID/drop guards; the configured application database was not reset.

Focused governor tests exposed and fixed two implementation defects before live acceptance: concurrent owner warm-up could race on its file lease, and a previously admitted reservation could be marked sent after its caller deadline. The owner now serializes lifecycle changes and rechecks caller/run expiry before send while retaining the reserved charge. [Governor tests](dispatch-tests.xml): **19 passed** after the fixes, including both expiry paths, shared query/document budgets, exclusive owner, forged handles and cancellation/ambiguity accounting. Sent uncertainty now also disables the remaining allowance because server work may outlive its disconnected client; that owner cannot automatically retry. An explicit new run requires operator confirmation that work is stopped and repeated attestation, with a runtime restart when needed. Test failures during implementation are not qualified-runtime failures or successful proof.

Additional defensive review fixed oversized integer vector values that could overflow numeric validation. The adapter/domain now return a safe invalid-response category instead of leaking an arithmetic exception. The immutable model profile now includes explicit last-token pooling and a canonical full-definition fingerprint, including its instruction, rather than relying only on a revision label.

Final independent review identified and fixed a deployment-attestation gap: a matching read-only mount alone did not prove that the TEI command actually selected that mount, or that the inspected container owned the client endpoint. Qualification now requires the exact reviewed command/entrypoint, `--model-id`/`/info.model_id` agreement with the verified read-only mount and both configured/actual container port bindings from `80/tcp` to `127.0.0.1:8081`. All 20 negative mutations and the gated live rerun passed after this fix. The metrics above describe only that corrected final run.

Executed: `hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_embedding_dispatch.py --override-ini addopts='' --junitxml=tasks/evidence/embedding-2026-11-23/dispatch-tests.xml`. Focused Ruff lint/format also passed. Sidebar syntax, release-note backticks, new runbook/report local links and strict UTF-8 passed; no Docusaurus build was run because its local `node_modules` are absent.

[Final quality record](quality-checks.txt): application Ruff lint/format passed for 110 files, mypy passed for 110 source files, and the qualification script's separate Ruff/format/mypy checks passed. Read-only main API discovery at `127.0.0.1:8011` retained lexical-only profiles and existing documents/search capability. Frontend/browser checks and the upstream-wide Haystack suite were not run because this change adds no UI or Haystack public API.

## Rollback and remaining limits

Close the qualification owner and omit/disable explicit qualification configuration. Corpus records, active versions, applied migrations, immutable retrieval profiles and ordinary lexical startup remain unchanged. Production capacity calibration/governor, durable vector publication and retrieval-profile qualification remain successor tasks.

## Changed owners

- Model-neutral requests, profile fingerprint, preparation and output validation: [embedding.py](../../../apps/workbench/api/embedding.py); deterministic mock-provider responses remain confined to recipient tests.
- Local TEI transport and strict response/identity checks: [embedding_adapters.py](../../../apps/workbench/api/embedding_adapters.py).
- Shared finite qualification admission and accounting: [embedding_dispatch.py](../../../apps/workbench/api/embedding_dispatch.py).
- Default-disabled policy: [embedding_config.py](../../../apps/workbench/api/embedding_config.py), [config.py](../../../apps/workbench/api/config.py), [embedding_profiles.yaml](../../../apps/workbench/embedding_profiles.yaml).
- Operator/container/file attestation and explicit bounded GPU proof: [workbench_embedding_qualify.py](../../../scripts/workbench_embedding_qualify.py).
- Recipient tests: [domain](../../../apps/workbench/api/tests/test_embedding_domain.py), [configuration](../../../apps/workbench/api/tests/test_embedding_configuration.py), [transport](../../../apps/workbench/api/tests/test_embedding_adapter.py), [admission](../../../apps/workbench/api/tests/test_embedding_dispatch.py), [attestation](../../../apps/workbench/api/tests/test_embedding_attestation.py), [gated model smoke](../../../apps/workbench/api/tests/test_embedding_model_smoke.py), plus unchanged-capability assertions in [test_http_contract.py](../../../apps/workbench/api/tests/test_http_contract.py).
- Documentation: [operator guide](../../../docs-website/docs/architecture/local-embedding-provider.md), [API README](../../../apps/workbench/api/README.md), [runtime contract](../../../docs-website/docs/architecture/rag-runtime-contract.md), [project map](../../../docs-website/PROJECT_MAP.md), [MVP progress](../../../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md), [sidebar](../../../docs-website/sidebars.js), [EMBED-001](../../TASK-RAG-EMBED-001-qualify-local-qwen-embedding-provider.md), [TPM-001](../../TASK-RAG-TPM-001-adaptive-embedding-capacity-and-cross-project-reuse.md).
- [Release note](../../../releasenotes/notes/workbench-local-embedding-qualification-694bd65b65e5de31.yaml), [.gitignore](../../../.gitignore) and narrowly allowlisted sanitized evidence in this directory.

Existing logic reused: `LocalQwenTokenCounter` and its approved asset manifest, the bounded duplicate-key-denying `_yaml_value` parser, strict `ApiSettings`, existing `Identifier` validation, installed `httpx`/`filelock`, immutable profile/runtime ownership and the existing lexical/PostgreSQL regression suite. No donor implementation, applied migration, ingestion publisher or document store was replaced.

# Qualified Live Dense and exact cosine baseline — 2026-11-24

**Status: COMPLETE for DENSE-001's local development exact dense baseline.** Actual qualified Qwen embeddings, independent SQL/HTTP identity and distance agreement, multilingual labels, browser execution, failures/cancellation and application reconstruction passed. CUDA kernel-only timing is unavailable; actual provider inference wall time is separately measured and explicitly labeled. No production authorization, ANN, hybrid retrieval, answer generation or independently human-reviewed production relevance guarantee is claimed.

## Implementation and existing owners

The task was reinspected against the current modular source tree rather than implementing the obsolete `api/dense.py` paths from its original blueprint. `retrieval/dense.py` now owns fixed Haystack `QueryEmbedder` and `PostgresDenseRetriever` composition. It reuses `EmbeddingPort`, `prepare_embedding_request`, native Qwen token counting, the attested TEI adapter and the existing measured shared query/document governor. Query batches are independently checked before SQL; the browser supplies no vectors, model strings or executable graphs.

`postgres/postgres.py` and `postgres_dense.py` reuse the existing authoritative PostgreSQL port, migration-0005 immutable vectors/mappings, source/version registry and forced workspace RLS. No second store or migration was introduced. Lexical chunk rows retain their null-vector contract. Dense reads require complete matching coverage and active immutable profile/model/source generation; SQL retains the admitted generation/profile fence and deterministic raw cosine order. Source swaps, profile retirement, wrong model/dimensions and partial generation cannot become a live successful result.

`profiles.dense_profile_definition` centrally defines `postgres-dense-exact` / `postgres-dense-exact-r1`. The response adds optional dense provenance and real server stage timestamps. The request retains exactly `query`, `top_k`, `profile_id`, `expected_profile_revision`. Lexical score semantics/default behavior remain compatible. Dense reports raw `cosine_distance` with lower values first. No confidence percentage or BM25 label is substituted.

The frontend reuses discovery, immutable live session records, request cancellation/generation guards and the approved graph allowlist. Its four-node Dense template is available behind an executable capability. Constructor-only validator bindings stay distinct from execution permission. Unsupported graphs issue zero search requests. Preview remains explicit and no live failure produces fixture results.

## Actual model and exact SQL evidence

The previous measured allowance had expired. It was not extended by editing timestamps. A fresh actual calibration against the owned TEI service passed and is retained in [capacity-calibration.json](capacity-calibration.json): observed sustainable denominator **557056 tokens/minute** among the declared tested candidates under the current shared physical GPU conditions. The earlier 622592 result is not reused as current capacity. The current model fingerprint remains `5e3513dc019d264f3009f81febe768b0121d65a3eb9c26c3d304bc7550318354`, with full **2560** dimensions and pinned model/tokenizer assets. This is a fresh expiring admission prerequisite, not another sustained TPM-001 target proof or a globally exclusive GPU quota.

The [initial executed evaluator](runtime-evaluation-initial.json) and [final gated real-model evaluator](runtime-evaluation.json) each prepared an owned disposable database using the existing original-source fixture, publication/backfill port and migrations. Its main workspace alone was explicitly mapped to `development` for the existing server authorization boundary. Source/chunk IDs, original hashes, character spans and fixed relevance labels were retained. Each run reached **102/102 eligible active real vectors**, with 12 historical-version sentinels retained and excluded from active results; foreign-workspace vectors remained separate. Source replacements exercised compatible tenant-local reuse and new-input generation through the existing worker.

The final gated [model smoke test](model-smoke-tests.xml) passed **1 test in 144.27 seconds**. All **52** EN/RU/UK semantic/code/no-answer queries executed through actual API → Haystack → governed local model → PostgreSQL. Every top-10 HTTP result agreed with independently issued read-only application-role SQL for exact persisted chunk/source/version IDs, rank and raw cosine distance. Original content/hash, input hash, profile and index-generation audits also passed. The same 52 paraphrases were submitted to lexical search for direct comparison; all **10/10** additional literal lexical cases returned their labeled chunk in the top ten. Queries produced distinct real rankings.

Final fixed-fixture quality has 46 answerable cases. Recall@1/5/10 is **0.445652 / 0.934783 / 1.0**; primary-evidence recall is **0.673913 / 0.956522 / 1.0**; MRR@10 is **0.942029**. All six no-answer cases still return forced nearest neighbors and one answerable case ranks a hard negative first. These are reported limitations, not hidden failures or a confidence calibration. The original source fixture and labels are synthetic and repository-authored, not an independent production quality dataset.

## Measured latency boundaries

The final evaluator has **52 samples per row**; percentiles use nearest-rank selection. Metric probes were outside the HTTP wall interval. TEI's inference histogram count had to advance by exactly one per query, refusing a contaminated sample. Values below come from the final runtime artifact and are rounded only for presentation.

| Measured interval | p50 ms | p95 ms |
| --- | ---: | ---: |
| TEI server inference (`te_request_inference_duration` delta) | 43.571 | 286.000 |
| Governed embedding adapter wall time | 562 | 796 |
| Dense vector-search stage | 31 | 32 |
| Independent exact SQL oracle including connection | 16 | 47 |
| Complete in-process ASGI HTTP request | 875 | 1157 |

Adapter wall time includes native preparation, admission waiting, HTTP and attestation. Server inference wall time is not a CUDA kernel-only profile. The independent SQL oracle includes connection setup and is separate from the existing pooled vector-search stage. No network RTT, UI rendering or pure GPU kernel duration is inferred from these numbers.

The separate [real browser record](browser-dense.json) passed **10** actual EN/RU/UK queries against the same temporary qualified API. Response-body-ready to React result DOM commit measured p50/p95 **2.5 / 4.4 ms**; response-body-ready to the sampled second animation frame measured **10.2 / 20.9 ms**. The latter is a browser frame-observation proxy, not a guarantee of physical display presentation. It verified ascending raw distances, real source/model/generation provenance, server stages, a deliberately injected HTTP 503 with zero Preview fallback, and an invalid Dense graph with zero search POSTs. The bounded API process was then stopped cleanly.

## Failures, restart and evidence hygiene

The complete API/SQL suites cover malformed 400 requests, denied/unknown-workspace 404, stale-profile 409, shared-admission/provider 429, unavailable model/database/index 503, provider/request 504, client cancellation, source swaps, retirement, partial coverage, output mutation/wrong dimensions and request/trace/run correlation. Provider failures in adversarial route tests are explicit injected fakes; they are not described as stopping the real TEI service. The real service and main application database were not interrupted.

The final model smoke reconstructed a **new FastAPI application/lifespan and PostgreSQL pool** over its same disposable database while retaining the actual model/governor process. The repeated semantic request preserved its top-ten source/chunk IDs, model digest and generation **38**. Maximum observed raw distance difference was **0.0** under the declared `1e-5` repeat-query tolerance; independent SQL agreed again and server trace/run IDs changed. This proves application reconstruction and persisted recovery, not a new operating-system/API process or PostgreSQL container restart. Existing earlier storage/server restart evidence remains owned by EMBED-002 and INDEX-001.

Both disposable evaluation databases were removed through their unique `rag_test_...` names and ownership markers. No DSN, password, original document bodies, query vectors or private provider payloads are emitted in artifacts. The [artifact audit](artifact-safety-audit.json) checks configured secrets, credential-bearing PostgreSQL URLs and long raw vector arrays. Public synthetic query labels and safe IDs/hashes are intentional.

## Executed checks

- Full backend: **1363 passed, 20 skipped in 306.63 seconds**; [actual command output](backend-tests.log). No database test was skipped. Optional GPU/model-asset/tokenizer/storage benchmark gates account for skips; the separate explicit model smoke above actually passed.
- Current exact dense PostgreSQL regressions: [dense-sql-tests.xml](dense-sql-tests.xml), including 100-vector independent SQL order, incomplete/wrong-profile/generation/model/workspace/fence cases.
- Explicit approved-local-tokenizer, native-guard and provisioning tests: **32 passed, zero skipped in 20.68 seconds**; [native-tokenizer-tests.xml](native-tokenizer-tests.xml). These separately close 16 missing-asset environment skips from the broad run without rewriting its original result.
- Evaluator integrity guards: **13 passed, 1 explicit default live skip**; [evaluator-tests.xml](evaluator-tests.xml). The live gate is separately executed above.
- Latest focused dense HTTP route suite: **16 passed**. API Ruff/format and mypy passed **154 Python files**. Standalone evaluator/launcher Ruff/format and mypy passed both scripts.
- Frontend typecheck, Prettier, **18 test files / 364 tests**, and production build passed; Preview and Dense browser checks passed. Constructor-validator focused **37 tests** and its seven-file Ruff/mypy check passed. Exact commands are recorded in [quality-checks.txt](quality-checks.txt).
- Sidebar JavaScript parses, `git diff --check` and strict UTF-8/relative-link checks pass. Full documentation-site build was not run because its installed dependencies are absent.

## Changed file groups and deliberate contracts

- Retrieval/backend: `retrieval/dense.py`, `profiles.py`, `services.py`; `postgres/postgres.py`, `postgres_dense.py`, `postgres_profiles.py`; `persistence/models.py`; `embedding/embedding_adapters.py`, `embedding_capacity.py`; `api/application.py`, `projection.py`; `contracts/schemas.py`, published `api/openapi.json` and shared `testing/persistence.py`.
- Backend verification: dense route, dense model smoke, dense PostgreSQL and dense evaluator tests; existing HTTP-contract assertions and validator registry/validation tests adjusted for additive approved constructor sockets.
- Frontend: shared API contracts/decoding, graph catalog/templates/types/validation, approved execution, discovery, live result/session hooks and displays, profile settings/pipeline views, exact accompanying unit tests and `scripts/dense-search-smoke.js`.
- Operations/evidence: `scripts/workbench_dense_serve.py`, `workbench_dense_evaluate.py`; selected `.gitignore` evidence entries; this task/evidence, API/web/validator READMEs, project map/engineering/runtime/profile/embedding documentation, new Live Dense runbook/sidebar and one user-facing release note.

The additive contract intentionally introduces dense profile capability/provenance and real dense stage timings while retaining the strict four-field request and default lexical startup. No applied migrations, model assets, main source data or existing vectors were rewritten. Ordinary rollback retires the dense rollout and starts the lexical service while preserving vectors. Repair uses existing backfill and explicit current-generation profile qualification. Future ANN/production authentication/abstention/independent corpus evaluation retain their separate contracts.

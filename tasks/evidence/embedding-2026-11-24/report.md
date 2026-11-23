# Durable embedding ingestion and measured retrieval acceptance — 2026-11-24

**Status:** COMPLETE for EMBED-002's scoped durable-ingestion, single-owner admission and objective-evaluation gates. The actual ten-minute run passed its predeclared steady-window rule. Whole-run completed utilization was **91.992753788%**, explicitly below an exact 92%; the broader TPM-001 task remains IN PROGRESS.

**Inspected base:** `4d3292f81e55aa66cda4df97831b7eefe7b1f858` plus this task's working-tree changes. Completed INDEX-001/PROFILE-001/EMBED-001 remain the source of persisted generation, immutable policy and qualified local model behavior.

## Scope and source reuse

The deliverable adds durable leased embedding jobs, immutable tenant-local cache/mappings, complete semantic generations, measured shared query/document admission and CLI diagnostics. Lexical publication and its null-embedding guard remain intact. Dense HTTP, ANN, hybrid retrieval, answer generation and an LLM judge are outside scope.

Donor commit `955fd049949d3fc462d555be14774e4b255aa15c` was actually inspected through pinned source reads. No donor implementation is copied.

| Inspected source | Git blob | Recipient decision |
| --- | --- | --- |
| `semantic_embedding_preparation.py` | `42d8dce6970eb3d0ff9df7896a432ece55e3363b` | Independently implement cache partition/current-input/paid-result scenarios through existing PostgreSQL and neutral provider owners |
| `embedding_execution.py` | `2ebfe78d3b3785708eb0584e1fc7e282f7f036e5` | Independently bound async execution and ownership; no copied ThreadPool/Qdrant runtime |
| `test_semantic_restore_delta_lifecycle.py` | `9a9ea7696a43ef1bada638b187f2f62e19d49515` | Recipient scenarios cover restoration, source/model changes and compatible reuse; donor tests are not recipient execution proof |

The old qualification owner remains a separate explicit bootstrap mode and shares the deployment lease boundary with the measured owner. It is not another production quota. Existing tokenizer assets, profile fingerprint, PostgreSQL/RLS, lexical publisher and runtime attestation are reused. The previous task's accepted startup/model artifacts are not relabeled as this task's backfill or throughput results.

## Objective quality contract

The fixed oracle has 102 eligible active chunks, 12 historical-version sentinels, 12 foreign-workspace chunks and 52 queries. It includes true cross-language cases requiring English-only sources, code, graded direct/support evidence, hard negatives and no-answer cases. Original source SHA-256 and exact chunk character spans bind the ground truth.

The implementation agent authored the fixed synthetic sources and labels during this session. They are explicit reproducible test expectations, not independently human-reviewed relevance judgments or a production-domain benchmark. No external expert-labeled quality dataset was supplied.

Actual query embeddings must use the shared governed runtime; ranking must read actual persisted vectors with exact cosine SQL. Every returned hit is audited for original bytes/hash, tenant, active version, input hash, profile and one generation before scoring. Recall/MRR/nDCG@1/5/10 and primary-evidence recall are reported by language/cohort. No-answer forced neighbors are explicit; no cosine-to-truth conversion, answer generator, Ollama dependency or model judge is used.

Pure scorer/provenance tests pass 24 cases, including known metric values, wrong original/version/tenant/profile/generation, redaction, no-answer semantics, actual runtime seam composition and refusal to relabel tokenizer-proxy usage as provider usage. Final PostgreSQL/GPU quality before and after the ten-minute workload passes the integrity gate; relevance metrics are reported without a fabricated production threshold.

The preserved [initial actual quality run](acceptance-quality-initial.json) measured all 52 queries against 102 persisted active vectors: source/tenant/version/profile/generation integrity passed, primary-evidence Recall@1 was 0.673913, Recall@5 was 0.934783, primary-evidence Recall@5 was 0.956522 and MRR@10 was 0.942029. All six no-answer queries returned forced nearest neighbors and one answerable query ranked a hard negative first. These initial results precede the source-policy cache-key correction and fresh upload/edit preparation; they are retained as initial evidence and will not substitute for the final before/after-load runs. Workbench has no TPM dashboard; current telemetry is CLI/JSON only.

The fresh `r2` [preparation](acceptance-preparation.json) passed the actual application upload path: multipart POST returned 201 and produced 50 chunks, with the eight seeded chunks giving 58/58 ready vectors. A guarded multipart source replacement returned 200, generated exactly **one** changed input and reused **49** unchanged chunk vectors; coverage returned to 58/58. The separate quality fixture generated 102 initial main inputs and 12 foreign-workspace inputs. Replacing four fixture sources generated four changed inputs and reused eight unchanged same-tenant chunks. Superseded occurrence mappings remain retained history and are fenced out of active retrieval.

The fresh [before-load quality result](acceptance-quality-before.json) audits 52 actual governed queries against generation 38, with integrity PASS and 2312 provider-reported query tokens. It reports:

| Metric | @1 | @5 | @10 |
| --- | ---: | ---: | ---: |
| Recall | 0.445652 | 0.934783 | 1.000000 |
| Primary-evidence recall | 0.673913 | 0.956522 | 1.000000 |
| MRR | 0.891304 | 0.942029 | 0.942029 |
| nDCG | 0.704969 | 0.845519 | 0.863413 |

Among the 12 cross-language cases, Recall@5 is 0.958333 and primary-evidence Recall@5 is 1.0. The four-case code cohort is weaker: primary-evidence Recall@1 is 0.5 and @5 is 0.75; @10 reaches 1.0. These small synthetic groups do not establish general multilingual or code retrieval accuracy.

The [after-load quality result](acceptance-quality-after.json) passes original-source/tenant/version/profile/generation integrity and has identical aggregate relevance metrics to the before-load run. The same explicit limitations remain: six no-answer cases have forced neighbors, abstention is unimplemented and one answerable hard negative ranks first. These are measured fixed-fixture results with no production quality threshold. The [implementation SHA-256 manifest](implementation-hashes.json) freezes 19 runtime/adapter/governor/worker/SQL/fixture/operator files; the [after-run verification](implementation-hashes-verified.json) confirms all 19 remain unchanged.

An independent [preflight](acceptance-preflight.json) verified the unchanged profile/calibration denominator and implementation hashes, actual HTTP delta gate, 2200 unique 4096-token inputs and the bounded 8/8/8/4-item packet cycle before authorizing the final 600-second run.

## Measured capacity and main-corpus backfill

The [actual calibration](capacity-calibration.json) binds profile revision `qwen3-4b-capacity-32k-r1`, fingerprint `5e3513dc019d264f3009f81febe768b0121d65a3eb9c26c3d304bc7550318354`, to the observed dedicated deployment. Vectors remain 2560-dimensional; each input is capped at 8192 tokens and each batch at 32768 tokens/eight items. The measured denominator is 622592 tokens/minute: the highest sustainable result among the declared tested candidates under observed shared-GPU conditions, not a globally proven GPU maximum. The configured 0.92 operating target is 572784.64 tokens/minute, and the separate 0.95 hard reservation budget is 591462 tokens per rolling minute. These are an expiring endpoint observation and admission settings, not proof of sustained 92% completion or globally exclusive GPU capacity.

The [dry run](main-dry-run.json) identified 44 eligible active chunks without provider inference. The [real main backfill](main-backfill.json) reached 44/44 ready vectors, 15 completed jobs, zero failed jobs and generation 1. Its 16 governed provider batches reported 12307 tokens. A [reopened status read](main-reopened-status.json) retained the same checkpoint with zero provider calls. A second [actual no-op CLI backfill](main-noop-backfill.json) enqueued no work, took zero worker steps and sent zero provider attempts.

## Migration, actual server restart and compatibility

Parent-controlled migration `0005` was applied after an owned local database backup; the original 15 sources, 17 versions, 55 chunks and 44 active chunks were preserved. No credential-bearing backup or DSN is published here.

The [actual PostgreSQL container restart](database-restart.json) retained its container identity and volume. [Before](main-before-server-restart.json) and [after](main-after-server-restart.json) snapshots match: 44 full 2560-dimensional vectors/mappings, identical stored-vector-content and chunk-hash digests, and zero embeddings injected into lexical chunk rows. Both TEI process start times remained unchanged. The [real HTTP readiness result](api-after-server-restart.json) advertises only `postgres-fts-baseline`; an [HTTP lexical lookup](lexical-after-server-restart.json) returned the expected `demo-identifiers-chunk-1` after restart with zero provider calls.

A separate [actual API process restart](api-restart.json), performed through the root launcher after vectors were persisted, changed the owned API process identity while retaining all 44 vectors and the identical vector-content digest. Real HTTP readiness and the expected rank-one lexical result passed again; the dedicated TEI process was reused without inference.

## Actual ten-minute single-owner capacity result

The [executed acceptance report](acceptance-report.json) and [raw capacity events/windows](acceptance-capacity.json) record **600.969 seconds** with the fixed 622592-token/minute denominator, continuously eligible demand and **zero** provider errors, unknown usage or hard-admission breaches. The predeclared rule was: at least 600 seconds, at least 99% ready backlog, no errors/hard breaches, at least 90% of steady windows in the 90–95% band and steady median at least 0.92. The result passes that rule; its definition was not changed after execution.

| Actual metric | Result |
| --- | ---: |
| Provider-reported tokens completed inside the measurement interval | 5736645 |
| Whole-run completed TPM | 572739.525666 |
| Whole-run utilization | **91.992753788% — BELOW exact 92%** |
| Steady eligible windows | 55 |
| Steady utilization p10 / median / p90 | 92.137708162% / 92.141081157% / 92.144293534% |
| Steady windows in 90–95% band | 53/55 (96.363636%) |
| Ready-backlog fraction | 100% |
| Independent peak held-plus-rolling reservation charge | 573696 / 591462 hard budget |
| Concurrent governed query latency p95 | 2047 ms |
| Queue wait p95 / post-send wall latency p95 | 469 ms / 2875 ms |
| Shared-device sampled peak memory / device total | 23156 / 24564 MiB |

The whole-run result is **0.007246212 percentage points below** an exact 92%; it is not rounded into exact target achievement. Request quantization and finite interval boundaries remain explicit. The worker sent 200 real document packets: 150 at 32768 tokens and 50 at 16384 tokens. It committed **1400 unique 2560-dimensional vectors**, split 468/468/464 across the three load workspaces, with zero cache reuse and zero failed jobs. The 2200-input demand corpus intentionally remained partially covered and **NOT_READY** (800 chunks still pending), demonstrating continuous backlog without falsely publishing a complete generation.

There were 51 concurrent real quality-query attempts and 251/251 successful model calls in this controlled runtime. One 49-token query completed after the measurement endpoint and was drained safely; its completion is excluded from the interval's token/TPM totals. The separate full 52-query before/after evaluations verify the controlled fixture's unchanged relevance metrics and provenance. Model assets were fully rehashed successfully, and the owned disposable acceptance database was removed. The main application database was not modified by this experiment.

The independently written [PowerShell replay](independent-capacity-audit.ps1) imports neither the Python governor nor evaluator. Its [audit](independent-capacity-audit.json) reproduces the exact 5736645-token/600.969-second totals, verifies every held-plus-rolling admission/send against the hard ceiling and finds zero breaches. An additional **541** one-second-step 60-second completion windows have median 92.141241776% and 97.41219963% in the 90–95% band. This overlapping-window analysis is an extra diagnostic; it does not replace the original acceptance rule.

The final independent [integrity audit](final-integrity-audit.json) matches 1400 generated/processed inputs to 1400 actual persisted mappings and 1400 unique actual provider inputs. It verifies unchanged 52-query aggregate metrics, successful private test-database removal and ready main API. The frozen implementation's 19 file hashes remain unchanged after measurement.

The sanitized [completion receipt](acceptance-completion.json) records observed CLI exit 0/PASS only after final full rehash of all nine source/cache assets, normal runtime-context exit and owned-marker cleanup. An independent read-only `pg_database` check confirms the disposable database is absent. The receipt preserves whole-run `BELOW_TARGET` separately from the passing steady-window gate.

Only the measured single-owner TPM prerequisite required by EMBED-002 is accepted. TPM-001 remains IN PROGRESS for its broader unrun 30-minute and wider concurrency matrix. The denominator remains the highest sustainable tested candidate under the observed shared-GPU conditions, not an absolute GPU maximum or a global quota for other projects.

## Checks and execution scope

The [full application suite](full-tests.xml), with real disposable PostgreSQL fixtures and GPU smoke opt-in unset, passed **1279 tests**, with **2 skipped**, in 296.39 seconds. It ran through `hatch run workbench-api:test --override-ini addopts='' --junitxml=tasks/evidence/embedding-2026-11-24/full-tests.xml` after loading the existing development environment into test-only DSN variables. Later focused [worker checks](worker-tests.xml) and [final stable-reuse regressions](stable-reuse-tests.xml) cover the bounded-page, expired-capacity and policy-key corrections; [94 capacity checks](capacity-unit-tests.xml) exercise measured admission. The pure [evaluation checks](evaluation-tests.xml) pass 24 cases. Final combined Ruff, formatting and mypy gates passed **129 Python files**, covering the API and all five new operator scripts. The [acceptance guard tests](acceptance-guard-tests.xml) verify the controlled experiment's safety/measurement boundaries.

The offline evaluator command `hatch run workbench-api:python -m scripts.workbench_embedding_evaluate` returned `FIXTURE_VALIDATED` without `--run`. Sidebar JavaScript parsing, release-note backtick validation, strict UTF-8 and relative file links for this runbook/report pass. A full documentation-site build was not run because its `node_modules` are absent; the frontend was not changed.

The separate [storage benchmark](storage-benchmark.json) and its [executed test](storage-benchmark-tests.xml) pass with 100000 initial mappings across ten 10000-chunk workspaces. A compatible 10000-chunk source-version change produced 110000 retained mappings with the same ten tenant-local synthetic cache vectors. Total wall time was 465.875 seconds; pool-close/reopen counts and full coverage matched. The independent [actual server-restart benchmark](storage-server-restart.json) and [test](storage-server-restart-tests.xml) preserved 10000 mappings across the observed PostgreSQL postmaster restart, then reached 20000 mappings with one compatible cache vector. Its 90.781 seconds include operator synchronization time. The [guard/small-dataset checks](storage-benchmark-guards.xml) pass 14 tests. Both large runs use synthetic **32-dimensional** vectors and **zero model/provider calls**; they establish storage/recovery behavior, not GPU throughput or full-2560 storage sizing. Owned disposable fixtures were cleaned afterward.

The actual ten-minute run, objective quality before/after, fixture replacement/foreign-cache proof, real 50-chunk upload/edit and storage/recovery gates above all have execution artifacts. Final command results are collected in the [quality record](quality-checks.txt). No browser/UI checks were run because the frontend and its HTTP DTO contract were unchanged; actual API/FTS HTTP and restart checks cover the preserved runtime boundary.

## Remaining boundaries

An independent review found a worker compatibility bug: a new per-heading 2048-character cap could reject Markdown that the existing chunker correctly accepts under its six-component/8192-canonical-UTF-8-byte aggregate heading policy. The worker now reuses that existing aggregate bound. Focused worker tests cover this correction; no new heading policy was imposed on lexical publication.

A second review found a cache-reuse bug: the initial digest included source-bound processing/chunking fingerprints containing the whole-source SHA and span structure. Any file edit therefore missed the cache for unchanged chunks. `durable-document-input-r2` now binds stable parser/chunker/admission policy and the exact sent-input SHA, while source identities and spans remain occurrence provenance. The model profile and measured capacity are unchanged. Existing 44 `r1` main-corpus vector values/mappings remain correct and preserved; new `r2` work uses an intentionally distinct cache namespace rather than an unreviewed SQL rekey.

The correction passed [19 focused tests](stable-reuse-tests.xml): 17 worker cases and two actual `IngestionService` regressions. A real source edit changes the source SHA and source-bound fingerprints while identical chunks retain the same reusable processing digest. Changing split length or native `max_tokens` invalidates that digest; changing only a YAML comment/configuration provenance does not. Ruff, formatting and mypy passed for this change. Fresh live preparation independently passed the actual multipart HTTP source edit/reuse gate before the ten-minute run.

The physical GPU is shared. Measured endpoint capacity expires and is not a globally assigned GPU quota. Production tenant authorization, executable Dense HTTP and generated-answer truth require their own contracts. Routine rollback disables/stops the worker while preserving lexical data and existing vectors; no destructive schema rollback is part of ordinary recovery.

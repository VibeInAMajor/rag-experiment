# TASK-RAG-RERANK-001 local qualification

- **Date** 2026-11-28 (Europe/Kyiv)
- **Baseline repository revision** `cce197a`
- **Scope** Frozen cleaned exact OPEN candidates and the existing loopback reranker.
- **Decision** NO-GO for this reranker on the measured Dense arms. Retain exact Dense. Hybrid and the full independent semantic gate remain open.

## Model and runtime

The operator-specified container `9e683389d384b7c286225cd4f696db8913552f7f145b72b1d43e8916782891e9` was healthy as `rag-workbench-reranker-1`. It served `Qwen/Qwen3-Reranker-0.6B` on `127.0.0.1:8083` via vLLM 0.34.0. The image digest was `sha256:cf5b2fdd087eb4f6d261736967cc5cde974bd22ff4df50365f8fa419b6b4c484`. The model's source revision is `e61197ed45024b0ed8a2d74b80b4d909f1255473`, licensed Apache-2.0. [Pinned Qwen model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B/tree/e61197ed45024b0ed8a2d74b80b4d909f1255473)

| Mounted asset | Observed SHA-256 |
| --- | --- |
| model.safetensors | `27cd75a405b9c1b46b59abfd88aaa209e6fed2a1972cde9b70e7659537c5e65b` |
| tokenizer.json | `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4` |
| tokenizer_config.json | `253153d0738ceb4c668d2eff957714dd2bea0b56de772a9fdccd96cbf517e6a0` |
| chat_template.jinja | `6f682162495ec5b39fd9005c01b6aa2a74669379fe967039f1e2cbbe8752369d` |
| config.json | `d479c427a9ca5295218063d4f9aca4f297ab4ac27487cca7af42c84643d51ef0` |

The read-only mount and fixed server template provide the model's instruction, query and document formatting. The server uses the original Qwen yes/no classifier, float16 and one scheduled sequence. The deployment accepts at most 4,096 tokens per formatted pair. The experiment sends up to 16 original documents per HTTP batch and at most 50 per query, with one in-flight ranking, a 15-second batch deadline and 90-second query deadline. Truncation is disabled and score ties preserve the original order. Scores order candidate relevance. They do not establish answerability or calibrated correctness. The runtime rejected a 5,000-token synthetic pair. Request-content logging is disabled by default and the running container does not set the enable flag. [vLLM scoring](https://docs.vllm.ai/en/stable/models/pooling_models/scoring/) · [vLLM 0.34.0 request logging](https://docs.vllm.ai/en/v0.34.0/cli/serve/#-enable-log-requests-disable-log-requests)

## Frozen experiment

The cleaned `ui-comparison-2026-11-25/after` OPEN V2 capture has 306 queries across 102 families and 15,300 exact candidate occurrences. There are 261 answerable queries, 45 no-answer variants and 634 active source chunks. The replay rechecked source/version/body identity and SQL order evidence for all occurrences. The immutable capture SHA-256 is `70dee6855eeae7fe6ac929333551141315a44d779c4318194733d00770c373e9`. The ingestion SHA-256 is `1c31c301697b60157cdf03be65dd990bf1b457a68cdff143ed1a75b899f7ecc4`. The exact profile fingerprint is `5e3513dc019d264f3009f81febe768b0121d65a3eb9c26c3d304bc7550318354`. [Matched cleaned Dense baseline](../quality-2026-11-25/report.md)

Each reordered arm uses only its original depth-specific 10, 20 or 50 candidates. The top-five evaluation and the whole-chunk 2,048-token context from the first 10 results use the same cutoffs on both orders. No-answer cases are excluded from known-fact denominators. The predeclared gain is at least +5 percentage points in any-complete-fact@1, with zero decrease in all-facts@5 or within the fixed token budget. Intervals resample query families. Known source facts do not replace independent relevance labels.

| Candidate depth | Oracle with at least one complete fact in a single candidate | Oracle with all required facts across the pool |
| ---: | ---: | ---: |
| 10 | 255/261 | 246/261 |
| 20 | 258/261 | 251/261 |
| 50 | 258/261 | 255/261 |

The hybrid arm remains unavailable because HYBRID-001 has no qualified candidate list for the cleaned corpus. Full OPEN qrels remain provisional. The eligible v8 evidence only covers 37 candidate occurrences across three families and nine variants. Unseen candidates remain unknown. [HYBRID-001](../../quality/TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) · [DATASET-002](../../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md)

## Actual OPEN results

The pinned container ranked all 306 queries, 15,300 pairs and 1,224 HTTP batches. The replay observed zero errors, incomplete permutations, source or version mismatches, and zero changes to candidate membership. The capture SHA-256 is `aa02e22d8787029d288975b186212c82d3c5f1e9f5d078c3d04b906b90989a39`. The frozen run manifest SHA-256 is `27676b41aabdd2d9ee787248aa9492dc12866e1683b1ccb630ecfdcbf4597d2f`.

| Order | At least one complete fact at rank 1 | At least one complete fact in top 5 | All required facts in top 5 | All required facts within 2,048 tokens |
| --- | ---: | ---: | ---: | ---: |
| Exact Dense | 194/261 (74.3%) | 255/261 (97.7%) | 237/261 (90.8%) | 240/261 (92.0%) |
| Reranked K10 | 194/261 (74.3%) | 252/261 (96.6%) | 234/261 (89.7%) | 235/261 (90.0%) |
| Reranked K20 | 190/261 (72.8%) | 251/261 (96.2%) | 235/261 (90.0%) | 238/261 (91.2%) |
| Reranked K50 | 189/261 (72.4%) | 248/261 (95.0%) | 236/261 (90.4%) | 237/261 (90.8%) |

The paired rank-one differences were 0.00, −1.53 and −1.92 percentage points. Family-clustered 95% intervals using 2,000 draws were [−7.28, +6.90], [−8.81, +5.75] and [−9.20, +5.36]. All three arms missed the +5 point threshold and lost all-fact coverage at both fixed cutoffs. They reduced explicitly annotated negative-only rank-one hits from 4/261 to zero. None of the 45 no-answer cases triggered that narrow negative-only annotation at rank one in either order. This count does not measure rejection of unanswerable questions.

At K50, Kubernetes improved all-facts@5 by 7.0 points and fixed-budget coverage by 5.3 points. Literature lost 6.7 and 8.3 points respectively. The Russian cohort lost 4.6 points at rank one, and the Ukrainian cohort lost 4.6 points within the fixed context budget. These are cohort point estimates from the same paired run.

| K50 latency measurement | Samples | p50 / p95 / p99, ms |
| --- | ---: | ---: |
| Rerank stage per query | 306 | 1,141 / 1,453 / 1,531 |
| Rerank HTTP batch | 1,224 | 328 / 484 / 516 |
| Historical exact observer, including SQL and source checks | 306 | 870 / 1,037 / 1,099 |
| Modeled sequential sum per query | 306 | 2,026 / 2,341 / 2,445 |

Rerank throughput was 42.9 pairs/s by summed rank timings. The modeled sum was 2.26× the historical observer p95. It combines measurements from separate runs. The identical-load Dense end-to-end gate remains unmeasured. The owned disposable database passed the read-only fence for 634 eligible vectors, the original corpus revision and generation. Its measured TEI admission policy expired on 2026-11-25 at 23:43 UTC. The existing finite TEI probe does not renew that policy. Given the quality NO-GO, no additional capacity calibration was run.

Across 339 complete GPU samples during the OPEN replay, peak used memory was 23,189 MiB and the minimum device-reported free memory was 950 MiB. The same reranker container remained healthy with zero automatic restarts. Main Workbench readiness returned HTTP 200 after the experiment.

## Independent v8 overlap

The overlap runner matched all nine variants by original query digest, candidate/source/version lineage and body hash. The table reports direct-support precision as position counts. Ranges reflect unknown labels and are worst-to-best bounds rather than sampling intervals.

| Candidate cap | Reviewed top-1 / top-5 / top-10 positions | Direct-support top-1 / top-5 / top-10 counts |
| --- | --- | --- |
| Exact Dense | 9/9, 45/45, 90/90 | 5/9, 11/45, 12/90 |
| K10 rerank | 9/9, 45/45, 90/90 | 4/9, 12/45, 12/90 |
| K20 rerank | 8/9, 42/45, 73/90 | 4–5/9, 11–14/45, 12–29/90 |
| K50 rerank | 8/9, 33/45, 57/90 | 4–5/9, 9–21/45, 12–45/90 |

At K10, the irrelevant counts at ranks 1/5/10 remained 0/0/2. Wrong-scope counts moved from 0/8/19 to 1/6/19. At K50, the irrelevant count bounds were 0–1/9, 0–12/45 and 0–33/90. Wrong-scope bounds were 1–2/9, 4–16/45 and 10–43/90. In EXT-ART-003, the Russian variant lost its complete fact at rank one across all three depths. EXT-LIT-001 retained a useful first result in all three variants. In EXT-NA-003, the K50 top five had no useful result among all 15 reviewed positions and one fewer wrong-scope result. No new judgment requests were sent. Full OPEN strict precision, recall, graded nDCG and semantic GO remain open.

## Context budget sensitivity

An offline follow-up reconstructed all 15,300 query-document pairs with the mounted Qwen template and tokenizer, matching the asset digests above. Pair input was 429 tokens at p50, 610 at p95 and 707 at maximum. Zero pairs exceeded the deployment's 4,096-token limit. The original run sent whole pairs with truncation disabled.

The follow-up repacked the saved orders using the same top-ten whole-chunk prefix and context token counter. It counted queries for which the selected context contained all required facts. The 2,048-token row reproduces the original experiment.

| Context budget | Exact Dense | Reranked K10 | Reranked K20 | Reranked K50 | Mean context tokens used by exact Dense |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2,048 | 240/261 | 235/261 | 238/261 | 237/261 | 1,811 |
| 3,072 | 244/261 | 243/261 | 243/261 | 242/261 | 2,571 |
| 4,096 | 246/261 | 246/261 | 244/261 | 244/261 | 2,902 |
| 6,144 | 246/261 | 246/261 | 246/261 | 244/261 | 2,960 |
| 8,192 | 246/261 | 246/261 | 246/261 | 244/261 | 2,960 |

For exact Dense, 3,072 recovered four complete contexts at 42% more context tokens on average. At 4,096, the total gain was six contexts at 60% more tokens. Higher budgets had the same fact coverage with the ten-chunk cutoff. Equal-budget reranking never exceeded exact Dense on this measure. The fixed rank-one and top-five results remain the original observations. This analysis made zero inference requests and measured evidence coverage only.

### Exact Dense 4,096 confirmation

The repeat uses 4,096 source-content tokens for exact Dense and the original 2,048-token control. It repacks the same frozen original-only top-ten orders using the existing whole-chunk prefix. The 306-query OPEN V2 replay has 261 answerable variants and 45 no-answer variants. The exact capture SHA-256 remained `70dee6855eeae7fe6ac929333551141315a44d779c4318194733d00770c373e9`. The dataset digest is `38ad2c628a7a578445998f14d05277d22e0f7ea79ec79839764e2ecd59a7ce9d`.

| Measure | 2,048 control | 4,096 exact Dense |
| --- | ---: | ---: |
| Answerable queries with all required facts in context | 240/261 (91.95%) | 246/261 (94.25%) |
| Mean source-content tokens per answerable query | 1,811.2 | 2,901.6 |
| Mean selected whole chunks | 6.697 | 9.866 |

Six queries across three families improved, 255 had the same all-facts outcome and zero worsened. Literature accounted for four gains and mathematics for two. Gains by language were EN +2, RU +1 and UK +3. The paired gain was +2.30 percentage points, with a family-clustered 95% interval of [0.00, +5.36] over 87 answerable families. For the 221 answerable queries with added chunks, the larger packs extended their original prefixes. All packs respected the cap, with an observed maximum of 4,086 tokens. Coverage reached the original top-ten ceiling of 246/261, two cases below the 95% target. Ranked positions and source identities stayed fixed. This was a repeat on the original data and measured source-fact coverage.

The main Workbench search contract returns ranked hits. The 4,096 budget belongs to the local evidence replay. The existing reranker advertised `max_model_len=4096`, remained healthy on the original container ID and had zero restarts. This repeat used zero inference requests.

From the checkout root in PowerShell, using the protected OPEN evaluator:

```powershell
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + (Resolve-Path '.local/evaluation-holdout/quality-check').Path
hatch -e workbench-api run python -m rag_quality.ranking.exact_dense_context_replay --run exact-dense-context-4096-v1
```

The exclusive run directory has an aggregate `summary.json` (SHA-256 `95354e8988cf0be5b468ee49f30c58e95ca28e27679a8b091b7dc86aaf2a411f`) and protected paired records in `paired-contexts.json` (SHA-256 `2107314200d4fd41adaac27c6a10690e77974fb98703e5f34987d7091a1d5159`). A repeated invocation uses a new run name. All 35 targeted retrieval and reranker tests and seven local replay tests passed. An independent read-only calculation reproduced the same counts and family interval.

## Synthetic runtime and shared resources

Each depth used four isolated controls in English, Russian, Ukrainian and code, repeated three times. The authored primary passage ranked first in all 12 executions at each depth.

| Depth | Pairs | Query p50 / p95 / p99, ms | HTTP batch p95 / p99, ms | Pairs/s |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 120 | 211 / 344 / 344 | 344 / 344 | 44.7 |
| 20 | 240 | 375 / 484 / 484 | 375 / 406 | 51.0 |
| 50 | 600 | 961 / 1,078 / 1,078 | 375 / 391 | 51.7 |

Per-pair amortized latency was 22.4, 19.6 and 19.3 ms at depths 10, 20 and 50. These numbers include batch overhead. The existing finite qualification governor admitted 36 synthetic TEI requests, 1,206 estimated and provider-reported tokens, with no failed or uncertain sends. At 12 samples per condition, TEI alone had p50/p95 453/1,078 ms. Sequential TEI plus K10 reranking had 640/750 ms. Simultaneous TEI and reranking completed in 469/672 ms. These small samples do not qualify sustained shared throughput or the actual Dense end-to-end 1.20× gate.

Observed RTX 4090 device usage ranged from 19,343 to 23,045 MiB against 24,564 MiB total (123 samples). Across 18 Docker samples, the reranker reached 2,726 MiB of container memory and 106.56% CPU, in Docker's per-core percentage units. TEI reached 4,538 MiB and 88.19% CPU. Device VRAM is shared and the observed high-water mark includes TEI and other local activity.

## Reproduction and checks

From the checkout root in PowerShell, using the running pinned service and the separately authorized local OPEN checkout:

```powershell
hatch --version
hatch run workbench-api:python -m scripts.workbench_reranker_probe --container-id 9e683389d384b7c286225cd4f696db8913552f7f145b72b1d43e8916782891e9 --output .cache/reranker/rerank-001-runtime.json
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + (Resolve-Path '.local/evaluation-holdout/quality-check').Path
hatch -e workbench-api run python -m rag_quality.ranking.rerank_replay prepare --run rerank-open-v1 --sample all --candidate-cap 50 --max-seconds 1200
hatch -e workbench-api run python -m rag_quality.ranking.rerank_replay capture --run rerank-open-v1
hatch -e workbench-api run python -m rag_quality.ranking.rerank_replay score --run rerank-open-v1
hatch -e workbench-api run python -m rag_quality.ranking.rerank_pilot_overlap --run rerank-open-v1
```

Each run and output path is exclusive. A new reproduction uses a new path and run name. The immutable historical captures, original source files and old pilot verdicts stay in their original directories. Raw ranks, payload-derived identifiers and detailed telemetry stay in the ignored local workspace. Git contains the diagnostic adapter, its 22 tests, the synthetic probe and this sanitized report. The protected checkout owns the replay, v8 overlap scorer and their four focused tests.

`hatch run workbench-api:check`, `hatch run workbench-api:types`, and scoped Ruff/mypy for the synthetic probe passed. The scoped Workbench adapter and retrieval suite returned 63 passed and two configured database skips. Four local replay and overlap tests also passed. Adapter and replay cases cover stable permutations, prefix isolation, untrusted score/index data, exact runtime identity, request limits, deadlines, cancellation, redirect and retry refusal, and safe failure classification. The existing TEI service ran only the finite governed synthetic requests described above. Production search profiles stayed outside the experiment. OpenAI request count was zero.

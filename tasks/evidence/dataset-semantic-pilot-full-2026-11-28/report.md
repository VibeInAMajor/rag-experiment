# DATASET-002 full-input Semantic Judge pilot — 2026-11-28

**Decision.** Runtime 0.3.1 completed the three-family pilot on the full saved inputs. All 37 passages and nine ordered context packs received validated verdicts. This clears the measured pilot capacity blocker. The 102-family OPEN audit remains pending.

## Scope and admission

This replay uses the first pilot's nine independently derived and reviewed references and all saved evidence for EXT-LIT-001, EXT-NA-003, and EXT-ART-003. The questions, frozen retrieval ranks, and input source bytes are the same as in the first pilot. This isolates wider intake. The whole OPEN audit remains a separate stage. [First pilot](../dataset-semantic-pilot-2026-11-27/report.md) · [Owning task](../../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md)

| Input bound | Prior pilot | Runtime 0.3.1 | Largest saved request used here |
| --- | ---: | ---: | ---: |
| CLI envelope, UTF-8 bytes | 8,192 | 16,384 | 10,476 |
| Semantic-review admission units | 8,192 | 16,384 | 15,431 |
| Fragments in a judge_context pack | 8 | 12 | 10 |

The offline CLI admitted all 46 complete requests with zero provider calls. All 56 context positions kept their exact fragment text, identity, source offsets, hashes, and order. The direct Responses adapter runs with truncation disabled. Authored boundary tests covered 12 accepted fragments, 13 rejected fragments, the exact CLI byte ceiling and one byte over it. In the new live 12-fragment control, the two required facts were supported by exact quotes from the last two fragments.

Both replay revisions use semantic-review with gpt-6.1-sol, medium reasoning and the v6 prompts and output schemas. All 10 development controls and the 32 frozen qualification cases for v7 and v8 passed, including 16 critical controls and 3 exact repeats in each qualification. [MAF runtime limits](../../../apps/maf/README.md#execution-limits-and-estimated-spend) · [Live qualification record](../../maf/TASK-MAF-002-semantic-judge-agent.md#bounded-intake-amendment--2026-11-28)

## First full-input attempt

Runtime 0.3.0 sent all 46 whole inputs. It returned 37/37 valid passage verdicts and 8/9 valid context verdicts. The English Ruskin context reached the provider with all six fragments intact. It returned INCOMPLETE_OUTPUT at exactly 2,048 generated tokens, including 305 reasoning tokens. The other eight packs yielded five sufficient and three insufficient verdicts. The first attempt recorded zero provider retries and estimated USD 0.551188 before credits.

The v7 qualification fingerprint is f06974b1279c752f8c16f070ea1a6db2eb09ebf2240784e598d84e0ec58c5423. Its replay plan is 414361bae9062ddd0a8fc8f5b26eaee2874bdccda1b5326db214bebfb965e90b. Detailed inputs, checkpointed results and scorer output live under the ignored local evaluation owner at .local/evaluation-holdout/quality-check/runs/semantic-judge-pilot-full-2026-11-28/.

## Output-cap retest

Runtime 0.3.1 raises the profile output cap to 4,096 generated tokens. The v8 preflight independently matched all whole request bodies to the v7 plan, including all ordered context slots. The maximum reserve is USD 0.090112 per request and USD 4.145152 for the 46 pilot requests. The new qualification fingerprint is eb6faa0198320869f3f6f8f73336ed653a78d9e5ef2fc84dea17ddb1cbd8dfe3 and the replay plan is a33ac9c4091ed2aa44a1cef0ff398cd342f6725c76a36f14587a51efe68b7995. The output-cap retest uses the separate local evidence directory .local/evaluation-holdout/quality-check/runs/semantic-judge-pilot-full-v8-2026-11-28/. [Amendment](../../maf/TASK-MAF-002-semantic-judge-agent.md#output-cap-amendment--2026-11-28)

| Family | Whole passages | Full context, EN / RU / UK | Evidence checked |
| --- | ---: | --- | --- |
| EXT-LIT-001, Austen | 13/13 | Sufficient / sufficient / sufficient | Opening scene supports Bingley's tenancy and the reported annual income. The chapter 4 passage directly supports the same original tenancy. |
| EXT-ART-003, Ruskin | 12/12 | Sufficient / sufficient / sufficient | All four required facts, including the tracing-paper comparison and correction before inking. The recovered English context used 1,849 generated tokens, including 218 reasoning tokens. |
| EXT-NA-003, Azure | 12/12 | Insufficient / insufficient / insufficient | All 12 passages scored zero. The saved sources address Azure services and contain no exact monthly EUR total for the named storage account. |

The existing deterministic scorer covered all 90 saved top-10 positions and all 56 selected context positions. It counted 12 useful context positions, including 11 direct. The audit independently verified 57 whole-passage and 120 context quote occurrences against the frozen originals. Compared with the historical grades, five passages moved from 1 to 0 and one moved from 0 to 1. The other 31 stayed unchanged. The v7 and v8 passes gave identical grades to all 37 passages. One grade-0 Ruskin fragment changed category from topically related to wrong scope. These changes reflect how the same saved retrieval was judged. The pilot does not measure generated-answer quality or support a release decision for the full OPEN pool.

The v8 replay made 46 provider requests with 46 valid responses, no errors, no retries, and no unresolved semantic labels. It recorded 89,152 input tokens and 27,873 output tokens, including 7,971 reasoning tokens. Estimated cost before credits was USD 0.551771 for the final replay and USD 1.65724625 across both replays, both qualifications, and the development run reported here. The final repository checks passed 110 MAF tests, 49 ranking and evidence coverage tests, Ruff, strict mypy, and the standalone wheel build.

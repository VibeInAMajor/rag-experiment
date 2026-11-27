# DATASET-002 Semantic Judge pilot — 2026-11-27

**Decision.** The three-family pilot ran. The reference and targeted source checks passed. Full audit with the qualified v6 admission and CLI limits is **NO_GO**. Whole-passage outcomes exist for 14 of 37 pooled occurrences and whole-context outcomes for zero of nine saved packs. The full OPEN audit remains pending. [Task](../../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md) · [MAF v6 qualification](../../maf/TASK-MAF-002-semantic-judge-agent.md)

## Inputs and sequence

1. Froze the three reported families, all nine existing EN/RU/UK questions, original public corpus and saved post-cleanup results. The pool has 37 distinct family–occurrence pairs across 90 top-10 positions. The nine saved ordered context packs contain 56 positions and 25 distinct family–occurrence pairs. Each context slot maps back to its frozen projection and source. The saved context budget is 2048 source-content tokens using o200k_base.
2. Confirmed the deployed judge matches v6 and ran nine authored development controls. Semantic Judge then derived each reference independently from original text. The requests excluded retrieval results, ranks, historical labels and authored answers. Froze all outputs, rechecked exact quotes, then compared with the original, the latest local reference and the source-checked candidate. The frozen questions are equivalent within each language family.
3. Ran rank-hidden family-level evidence judgments using the verified common semantics and exact occurrence identity. Ran context assessment separately over the longest admitted ordered prefix where available. Eight further checks used exact, short windows within saved occurrences and were evaluated separately. Old grades were withheld from all provider calls and joined afterward by frozen occurrence identity.
4. Reused the existing deterministic ranking scorer, including its sparse-label guards. The historical revision, saved results and original questions were preserved. No retrieval or generation was run. Only public OPEN excerpts went to the provider. The R2/ANSWER holdout stayed out of the pilot.

The public source snapshot is cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5. The local historical ranking revision is a87a8e7c1fef975111acb59d6579e125c2c8c2a5d7eb74c16e29f97c5827d6a4. The approved Rag key used semantic-review with gpt-6.1-sol, medium reasoning and the v6 prompt and output schema. [Source notices](../../quality/dataset/EXTERNAL_SOURCE_NOTICES.md) · [Historical comparison](../dataset-ranking-full-open-2026-11-26/report.md)

## What the three cases established

| Case and original anchor | Historical label or reference | Live finding and disposition |
| --- | --- | --- |
| Austen, chapter 1, lines 16–17 and 32–46 | Latest local reference identified Mr. Bingley and reported four or five thousand pounds a year. | All three independent references found Bingley and four or five thousand annually. The dialogue omits the currency name. The pilot requires the reported annual figure and keeps currency as historical context. The window at lines 32–46 scored direct 3 for both facts. |
| Austen, chapter 4, lines 473–482 | The later occurrence had grade 3 for the tenant. | The exact later window independently scored direct 3 for Bingley taking the same property and supplied no income. The later dialogue explicitly recounts the original event. The full historical occurrence exceeded admission. |
| Austen, chapter 1, lines 100–105 inside the saved lines 94–121 occurrence | The full occurrence had grade 1. | The whole occurrence and the exact window both scored 0, topically related. The four thousand a year refers to hypothetical future neighbors. This confirms a provisional whole-passage correction from 1 to 0. |
| Azure Storage redundancy, lines 8–11 | The local reference recorded no account-specific amount. All 12 old pooled occurrences had grade 0. | The exact generic cost window scored 0, topically related, in EN, RU and UK. Nine whole occurrences scored 0 and three could not be admitted. All 31 eligible originals were searched for the distinctive invoice identifier and returned zero matches. The judge asserted absence only for the supplied excerpts. The caller's verified absence is scoped to the frozen OPEN corpus. |
| Ruskin, Exercise II, lines 185–198 | The early published reference omitted tracing and comparison. The latest local reference and new authored candidate already include tracing, comparison and correction. | All independent references recovered the missing-in-V1 step. The window at lines 191–198 scored direct 3 for tracing the original, comparing it with the pencil copy and correcting the faults. Actual inking at lines 200–204 is context after the requested pre-ink sequence. The full historical primary occurrence exceeded admission. |
| Ruskin, outline discussion at lines 440–450 and the separate Turner exercise at lines 217–226 | Both saved occurrences had supporting grade 1. | The first whole occurrence scored 0, topically related. Drawing delicate tree contours does not support the pre-ink copying procedure. The Turner window also scored 0. It belongs to a different exercise, and the full Turner occurrence exceeded admission. |

Source anchors appear in the pinned [Austen chapters](../../quality/dataset/corpus/literature/austen-chapters-01-05.md), [Azure guide](../../quality/dataset/corpus/azure/storage-redundancy.md) and [Ruskin exercises](../../quality/dataset/corpus/art/ruskin-first-practice.md). The latter Turner excerpt is in [Ruskin, Sketching from Nature](../../quality/dataset/corpus/art/ruskin-sketching-nature.md).

## Admission, coverage and metric eligibility

| Family | References | Whole candidate verdicts | Saved context fragments assessed as an ordered prefix, EN / RU / UK |
| --- | ---: | ---: | --- |
| EXT-LIT-001 | 3/3 | 2/13 | 1/4 sufficient, 1/4 sufficient, 1/4 sufficient |
| EXT-NA-003 | 3/3 | 9/12 | 2/9 insufficient, 1/9 insufficient, 1/10 insufficient |
| EXT-ART-003 | 3/3 | 3/12 | 0/6 blocked, 0/5 blocked, 1/5 insufficient |

All nine full context requests exceed the 8192-byte wire limit with the admitted reference. The exact encoded sizes were 8662–10476 bytes. The three Azure packs also exceed the mode's eight-fragment limit. The 23 other whole-passage requests were rejected by the offline MAF profile admission check before provider egress. A preceding zero-egress check also rejected the initial Azure derivation window. Its smaller exact source window was recorded as an additive input amendment before the three Azure source calls.

Of the 14 admitted whole passages, 12 kept grade 0 and two changed from 1 to 0. The 23 unresolved whole labels had previous grades 0 (15), 1 (4) and 3 (4). Judged-position coverage at top 10 was 32/90. Whole-passage assessments cover 25/56 saved context slots. Both denominators include positions with unresolved labels. The eight short-window results and seven prefix verdicts were excluded from whole-occurrence grade and whole-pack sufficiency metrics. Full-pack sufficiency, the revised pooled Recall and nDCG, complete useful-chunk precision, and revised release thresholds remain not evaluable on this coverage. Generation and abstention accuracy were not evaluated from retrieved text.

Before the full audit, qualify a bounded MAF intake that can process the exact saved passages and complete ordered context packs, then replay the unresolved pilot inputs against the same frozen data. Implementation and requalification belong to the MAF owner. No runtime policy or qualified judge revision changed during the pilot.

## Execution record

| Stage | Real provider calls | Validated responses |
| --- | ---: | ---: |
| Authored development controls | 9 | 9 |
| Independent source derivation | 9 | 9 |
| Whole candidate grading | 14 | 14 |
| Ordered context prefix assessment | 7 | 7 |
| Source-window diagnostics | 8 | 8 |
| Total | 47 | 47 |

All eight source-window expectations matched. We independently rechecked 95 exact quote occurrences across the four live pilot stages (30 reference, 12 whole candidates, 33 context prefixes and 20 diagnostic windows). The observed counts were 61,737 input tokens, 21,809 output tokens including 5,685 reasoning tokens, and zero cached input tokens. There were zero provider retries and zero provider errors on submitted inputs. Under openai-standard-2026-11-27, the estimated total before credits was **USD 0.40967575**.

The local owner is .local/evaluation-holdout/quality-check. Detailed data, UTF-8 CLI checkpoints and provenance are in runs/semantic-judge-pilot-2026-11-27/ under that owner. The canonical assessment plan fingerprint is fe77a4c1d79af0b5d56202371ed940d30d6bed1b4e728b4ca7e827ea48ae5090. The historical input export has file SHA-256 e2044249901cacca63f7a5e509bfe2acce8e09352440902bbe6613cce54198ed. The final detailed metrics have file SHA-256 c3f772a83ca6c9000a8a8546017958f25d9ee50c6f6c0d9dacd59064dd015608. Detailed provider outputs and credentials stay outside Git.

Verification passed 106 standalone MAF tests and 49 local ranking and evidence coverage tests. Offline preflight demonstrated zero provider calls on unadmitted inputs. The bridge was also checked for UTF-8 transport, idempotent checkpoint reuse and redacted correlation metadata.


# OPEN Golden Reference Answer Set — V1

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** SOURCE_CHECKED_CANDIDATE — complete authored answer coverage; independent MAF Semantic Review not run.  
**Dataset scope:** existing public external OPEN questions; 31 pinned source files.  
**Source snapshot:** `cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5`  
**Owner:** [DATASET-002](../../TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md)

## Purpose and delivered files

The golden reference set describes what a correct answer should contain, derived directly from the original documents rather than the retrieval results. It is an independent-of-retrieval candidate reference, not a claim of human-reviewed or independently judge-qualified gold. The previous published answer keys were used to locate candidate original passages; the original text was read and answers were authored in all three question languages. Historical answers, questions, captures and metric reports remain unchanged.

| Domain | Question families | Localized answers |
| --- | ---: | ---: |
| Kubernetes | 19 | 57 |
| Azure | 12 | 36 |
| C# | 14 | 42 |
| Mathematics | 14 | 42 |
| Art | 8 | 24 |
| Literature | 20 | 60 |
| No-answer | 15 | 45 |
| Total | 102 | 306 |

The three files contain actual reference answers, not a task plan. Each row maps an unchanged query ID to a localized reference answer, expected answerability, original source evidence (or an absence scope) and the required semantic facts. English, Russian and Ukrainian variants share the same family facts. Correct equivalent formulations are acceptable; exact string equality is not a semantic metric. The expected source-language constraint remains binding for questions that explicitly request a Russian/Ukrainian article.

## Frozen input and answer manifest

Git blob identities below are version identifiers, not independent semantic-validation certificates.

| Question file | Original question blob | Reference file | Reference blob | Families | Rows |
| --- | --- | --- | --- | ---: | ---: |
| [TECHNICAL_V1.md](../questions/TECHNICAL_V1.md) | `ca2f0703daefcee78e472bea0f8200c951a04a5c` | [TECHNICAL_REFERENCE_ANSWERS_V1.md](TECHNICAL_REFERENCE_ANSWERS_V1.md) | `88b96aa126e805612696da72c3d8c9d3d8a1d35e` | 45 | 135 |
| [MATHEMATICS_ART_LITERATURE_V1.md](../questions/MATHEMATICS_ART_LITERATURE_V1.md) | `0962d19aea0ed4b969f7dab8c0dd70ed9e0f041b` | [MATHEMATICS_ART_LITERATURE_REFERENCE_ANSWERS_V1.md](MATHEMATICS_ART_LITERATURE_REFERENCE_ANSWERS_V1.md) | `cff2d1af2e1b35ffcd01095fa5826999daa7da29` | 42 | 126 |
| [NO_ANSWER_V1.md](../questions/NO_ANSWER_V1.md) | `6d6dd2d1324a8ce44714202aa8c24e58a8f3d89c` | [NO_ANSWER_REFERENCE_ANSWERS_V1.md](NO_ANSWER_REFERENCE_ANSWERS_V1.md) | `ce7d31ac28dcc28e3eaa63b3a0c8435de8ea92cf` | 15 | 45 |

## Source snapshot and absence check

The 31 original files below were fetched from the pinned source commit. Authoring checked the answer-bearing ranges against the original text, extending several prior anchors when needed. A literal distinctive-identifier/theorem-name search across all 31 originals and inspection of the included literary chapter/section headings returned no matches for the requested missing records in the 15 no-answer families. This is limited source-scope evidence. It does not replace the subsequent semantic check of corpus-relative absence; an incomplete source scope must be marked UNKNOWN.

| Original file | Git blob |
| --- | --- |
| [corpus/art/ruskin-color-composition.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/art/ruskin-color-composition.md) | `3b43aa0b194f5c2eee874c700e4e58276c274d67` |
| [corpus/art/ruskin-first-practice.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/art/ruskin-first-practice.md) | `6b7f26d92c3d7a409474602440bf1e7c83a1b737` |
| [corpus/art/ruskin-sketching-nature.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/art/ruskin-sketching-nature.md) | `c494df61ce9488b71ab8b6ebf38334bccc7803e3` |
| [corpus/azure/rbac.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/azure/rbac.md) | `a66b8bef64f2a376d265aacefd70ee100215fad2` |
| [corpus/azure/resource-manager.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/azure/resource-manager.md) | `7a4fc2e5dadce85b0364fec2675f4e20486bb979` |
| [corpus/azure/storage-redundancy.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/azure/storage-redundancy.md) | `07a8145f5269a0be0e523cf8f1c33ec233b5986f` |
| [corpus/azure/virtual-network.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/azure/virtual-network.md) | `8ca9106f153d5b4a4d357c7bcb7ee2883a77c953` |
| [corpus/csharp/async.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/async.md) | `b4115c4e0fa2b11e37e29dadaf5eca8781b0873d` |
| [corpus/csharp/await.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/await.md) | `b10704c179bea408c9062cba8e64f38a95922a06` |
| [corpus/csharp/exceptions.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/exceptions.md) | `9dd4c9ae3d517873d8e9286694240db32fe9333d` |
| [corpus/csharp/generics.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/generics.md) | `548e11567839ff43205ffe2ca068311911a68231` |
| [corpus/csharp/linq.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/linq.md) | `6ff126633c54f27ed397e0468c28799dadc5a0d7` |
| [corpus/csharp/records.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/csharp/records.md) | `93e217939ca6d7551f7da4ba963abeece9ab7e3d` |
| [corpus/kubernetes/configmaps-uk.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/configmaps-uk.md) | `c189ef5485a78f837e610272f5a85e8c9924f7d2` |
| [corpus/kubernetes/configmaps.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/configmaps.md) | `88b9f621e1feb7910c6ce899a66ffdb9cfb7a380` |
| [corpus/kubernetes/deployments.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/deployments.md) | `19e7e6bc33c32f50914cc9f7cee76caa55419be1` |
| [corpus/kubernetes/pods-ru.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/pods-ru.md) | `b17a727ea66b6e14e4f3a51bc0a84632273b0463` |
| [corpus/kubernetes/pods.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/pods.md) | `b2694779d49ebfb08e198a4c822256d4899154cb` |
| [corpus/kubernetes/probes.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/probes.md) | `2942d8d17920339d5cd091fef1407fab05b52854` |
| [corpus/kubernetes/services.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/kubernetes/services.md) | `da96ca511b72138e502dad6794bf4b8233ce402a` |
| [corpus/literature/abbott-flatland-sections-01-03.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/abbott-flatland-sections-01-03.md) | `5548698400b23f4544306bf3b3b4bd567a5e3de7` |
| [corpus/literature/abbott-flatland-sections-13-16.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/abbott-flatland-sections-13-16.md) | `dd7f89203db84c19af9c30aa9f0b217bf0012cc4` |
| [corpus/literature/abbott-flatland-sections-17-19.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/abbott-flatland-sections-17-19.md) | `1193ccc5c5ffe4eaed8e747a7557933d88babe44` |
| [corpus/literature/austen-chapters-01-05.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/austen-chapters-01-05.md) | `2507f8d5b4deadacdcedde007d95b99c2fb53fdc` |
| [corpus/literature/austen-chapters-06-10.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/austen-chapters-06-10.md) | `db3956e75b877c0f3eba02196f98c578e5cf6921` |
| [corpus/literature/austen-chapters-34-36.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/literature/austen-chapters-34-36.md) | `f5c5ae6fce4ff7ecbd202ff044df2db02fb52ce8` |
| [corpus/mathematics/calculus-differentiation.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/mathematics/calculus-differentiation.md) | `076a9df88154c48ef381cab88103488d13413a94` |
| [corpus/mathematics/calculus-integration.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/mathematics/calculus-integration.md) | `8906baa1348862fca278e908fbec9e82bab54c2a` |
| [corpus/mathematics/calculus-maxima-minima.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/mathematics/calculus-maxima-minima.md) | `a826c5c89dc850eba7d16e88309246aa22228570` |
| [corpus/mathematics/calculus-successive-derivatives.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/mathematics/calculus-successive-derivatives.md) | `c32e1f5cec8afcdd83c9903e14cfe4ff54cfe118` |
| [corpus/mathematics/calculus-symbols-relative-growth.md](https://github.com/VibeInAMajor/rag-experiment/blob/cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5/tasks/quality/dataset/corpus/mathematics/calculus-symbols-relative-growth.md) | `6f9ae3532eef3dcec6d2ad27b8f08c82cd7a0a57` |

For absence checks, the distinctive terms were orchard-north-73, checkout-mist-71, invoice-birch-902, Granite Reader 94 / granite-sub-94, cobalt-vm-812, InvoiceQuartz782, LedgerMoss214, Atiyah / Singer index theorem, matrix-amber-927, Evening Orchard 1978, Mira Vale 2034 / Glass Coast, Chapter 59, Section 22, North Quill 518, and Birch Operator 661. The scan used case-insensitive patterns, including flexible separator matching for hyphenated identifiers. All 15 checks returned no matches in the checked-in corpus. Austen excerpts contain chapters 1–10 and 34–36; Flatland excerpts contain sections 1–3 and 13–19. No private records, runtime telemetry, external sources or missing chapters were consulted.

## Regression controls and notable corrections

- EXT-LIT-001: require the initial Netherfield rental event, Bingley and the reported income of four or five thousand annually, grounded in Chapter 1. A later passage is acceptable only if it explicitly supports the same event.
- EXT-NA-003: explicitly abstain on the exact monthly invoice amount in EUR. Storage redundancy material is not billing evidence.
- EXT-ART-003: the reference now includes tracing the original on tracing paper, comparing it with the pencil drawing, and correcting detected errors before ink. This was omitted from the earlier published reference; it is mandatory in the new fact checklist.
- EXT-K8S-018: the source range includes the actual YAML example and the distinction between environment variable name and the original ConfigMap key.
- EXT-LIT-010: the expanded original passage establishes Elizabeth's self-recognized vanity and prejudice, rather than a bare summary of her self-knowledge.

## Semantic Review handoff

1. Implement and qualify [MAF-001](../../../maf/TASK-MAF-001-standalone-agent-runtime.md) and [MAF-002](../../../maf/TASK-MAF-002-semantic-judge-agent.md).
2. The caller supplies the unchanged question and authorized original source material to `derive_reference`. Do not supply the candidate answer files, old labels, retrieved passages or ranking information during that pass. Record source scope and exact quotes; freeze the independent derivation.
3. Compare the judge-derived facts against this authored reference. Verify quoted original text, source identity, event/time/section scope, numbers/units, translation equivalence, and missing or unsupported facts. Resolve disagreements against originals or retain UNKNOWN; judge agreement alone is not proof. Start with the three reported regression families.
4. Admit a new immutable semantic-reviewed reference revision only after evidence validation. Keep this authored V1 and earlier historical artifacts unchanged. Then use `judge_evidence` and `judge_context` against saved actual candidate/context captures and compute metrics in the existing deterministic evaluator. Do not rerun retrieval merely to repair labels.
5. Preserve all 306 rows; unresolved cases remain explicit. Use the qualified judge version and approved data egress policy. R2/ANSWER holdout is excluded from this authoring and tuning scope.

The entire golden_set directory is evaluation-only and MUST NOT be ingested, embedded or supplied to production retrieval/reranking/generation. Only authorized original corpus files are ingestion inputs. No separate reviewer accounts or human approval prerequisite.

## Verification performed

- Re-read all three answer files after committing.
- Checked one-to-one equality of the original and new query ID sets: 306 expected, 306 actual, 306 unique, zero missing or unexpected IDs.
- Checked 45 + 42 + 15 families and all three language suffixes.
- All 261 answerable rows contain pinned original-file line references; all 45 no-answer rows contain a checked corpus scope. Path, commit and line-range ordering were checked; no unknown corpus path or invalid reference syntax was found.
- Source text was consulted for every answerable family and 31 originals scanned for absence markers. This is source-backed authoring, not a separate exhaustive semantic verification of all claims or all translations.
- No runtime retrieval, embedding, tests, MAF/API calls or semantic judge execution were performed by this delivery. The newer ignored local gold files and holdout were not accessible or used. Do not report this reference as approved or use it for final quality GO before Semantic Review.

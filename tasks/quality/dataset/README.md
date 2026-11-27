# External multidisciplinary retrieval dataset V1

**Created:** 2026-11-24  
**Updated:** 2026-11-27  
**Status:** COLLECTED / SOURCE-ANCHORED DRAFT — actual documents and multilingual question/answer keys present; agent source verification, real ingestion and retrieval evaluation not yet executed. This is separate from [repository-specific seed](RETRIEVAL_EVALUATION_SEED_V1.md), not a replacement for it.

## Source-checked Golden Reference Answer Set

The additive [OPEN Golden Reference Answer Set V1](golden_set/README.md) contains **306 actual reference answers** for the unchanged questions, with source locators and required facts in EN/RU/UK. This is the candidate reference for independent MAF Semantic Review, not already validated gold. The original V1 answer keys remain historical; do not overwrite them. Exclude the entire golden_set directory and all question/answer keys from ingestion. See the [actual local dataset report](../../evidence/dataset-2026-11-24/report.md) for later runtime evidence; the historical collection status above describes the initial delivery.

## Corpus and purpose

The corpus consists of **31 locally stored Markdown files** from external, pinned internet sources rather than the RAG project's documentation. The 17 technical files cover Kubernetes (including upstream Russian and Ukrainian localized pages), Azure and C#. Four public-domain books contribute 14 mathematics, art and literature files. The corpus totals 789,122 UTF-8 bytes and 120,675 whitespace-separated units (not model tokens), roughly 400 illustrative page-equivalents at 300 such units per page; Markdown has no fixed pagination and actual printed page count is not claimed. Each file is less than 61,000 bytes. This workload fits current per-file and byte limits; actual parser output/chunk count must be verified under the current 10,000 active-chunk / 50 MiB limits before real tests.

| Domain | Documents | Answerable families | Answerable language cases |
| --- | ---: | ---: | ---: |
| Kubernetes | 7 | 19 | 57 |
| Azure | 4 | 12 | 36 |
| C# | 6 | 14 | 42 |
| Mathematics | 5 | 14 | 42 |
| Art | 3 | 8 | 24 |
| Literature | 6 | 20 | 60 |
| Total | 31 | 87 | 261 |

An additional 15 no-answer families (45 language cases) produce **102 families and 306 total query cases**, exactly 102 per EN/RU/UK. Three translations of one question are correlated and never three independent gold cases. Candidate answer keys include full localized answers, original local file line ranges, mandatory evidence facets and explicit alternative source treatment. The 87 answerable families have 115 source-range/anchor checks. No-answer labels remain candidates until corpus-wide agent verification. The corpus is independent of our project documentation, but questions and initial gold candidates are assistant-authored and visible: **not yet source-verified gold or a held-out split**. Do not claim production generalization from this open dataset.

## What to ingest / what not to ingest

Only recursively ingest the Markdown files under `corpus/` into an owned disposable authorized workspace. Do not ingest this README, manifests, license notices, questions, answers, review notes, task documents or prior project seed. No network is needed at search time. Corpus files are source text adaptations, not invented summaries. External page assets, Hugo/Microsoft includes and original illustrations are excluded; do not evaluate image-only or linked-only information. Formula-bearing text remains Markdown with TeX notation. Actual parser acceptance is a gate; if a source needs bounded normalization or a split, preserve original source/line mapping and increment corpus revision, never fabricate evidence.

| Resource | Location |
| --- | --- |
| Actual technical source files and hashes | [Technical manifest](EXTERNAL_TECHNICAL_MANIFEST.md) |
| Actual book excerpts and hashes | [Books manifest](EXTERNAL_BOOKS_MANIFEST.md) |
| Source rights and change notices | [Attribution](EXTERNAL_SOURCE_NOTICES.md) |
| Technical questions | [Questions](questions/TECHNICAL_V1.md) |
| Technical answer key | [Answers](answers/TECHNICAL_V1.md) |
| Mathematics, art and literature questions | [Questions](questions/MATHEMATICS_ART_LITERATURE_V1.md) |
| Mathematics, art and literature answer key | [Answers](answers/MATHEMATICS_ART_LITERATURE_V1.md) |
| Candidate no-answer questions | [Questions](questions/NO_ANSWER_V1.md) |
| Candidate no-answer answer key | [Answers](answers/NO_ANSWER_V1.md) |
| Evaluation contract | [External evaluation protocol](EXTERNAL_EVALUATION_PROTOCOL_V1.md) |

## Quality gate

Use this dataset as a **separate external-domain generalization diagnostic**, in addition to the original synthetic regression and repository-specific dataset. The [DATASET-001](../TASK-RAG-DATASET-001-independent-evidence-gold-set.md) task owns review and fixture admission; [QUALITY-001](../TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md) owns baseline/tuning; [QUALITY-002](../TASK-RAG-QUALITY-002-retrieval-release-gate-and-regression.md) owns independent retrieval gate; [QUALITY-003](../TASK-RAG-QUALITY-003-grounded-answer-correctness-evaluation.md) owns later answer correctness. Run actual current small-document ingestion and governed model embedding, FTS/exact Dense and qualified RRF/reranker/context paths on the same frozen corpus and query/facet labels. Keep external and internal datasets separate in reports. No physical ANN, large-file ingestion or production tenant rollout required. No runtime metrics are asserted by this corpus collection.

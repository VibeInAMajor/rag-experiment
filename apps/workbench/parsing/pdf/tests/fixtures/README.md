# Reproducible PDF qualification fixtures

`scripts/workbench_pdf_fixtures.py` generates non-sensitive PDF inputs with ReportLab, using a local Unicode font. Tests generate their own bytes rather than committing platform-dependent PDF binaries. `scripts/workbench_pdf_qualification.py` writes the full corpus, independent row/cell truth checks and labelled queries to the selected evidence directory.

| Case | Pages | Expected text-layer behavior |
| --- | ---: | --- |
| text-one / text-five / text-twenty | 1 / 5 / 20 | Exact page-labelled text |
| two-columns | 1 | Parser r2 retains all 24 sentences, including both final `11` values, as verified text columns |
| numeric-units | 1 | Eight three-column numeric body rows |
| long-table | 1 | Thirty body rows, whole-row child partitioning |
| cross-page-table | 2 | Eight body rows per page, repeated observed headers |
| caption-table | 1 | Fifteen body rows with observed caption |
| russian / ukrainian | 1 each | Unicode text retained; no automatic locale inference |
| mixed-figure | 1 | Verified text plus one unprocessed visual region |
| scanned-negative | 1 | `NO_EXTRACTABLE_TEXT`; no silent success |
| encrypted-negative | 1 | `PDF_ENCRYPTED` |
| corrupt-negative | invalid | `PDF_CORRUPT` |

Security tests additionally construct active content, unsupported rotations, strict page limits, actual child CPU/wall-time exhaustion, cell gaps/overlaps, misleading continuation headers and resource tightening. Missing runtime assets disable capability independently from ordinary text ingestion.

Generated positive fixtures are **not live real-source proof**. The separate running-server probe uses actual public California WARN report content and preserves original corpus rows. See the [qualification record](../../../../../../docs-website/docs/tasks/pdf-layout-qualification-2026-11-23.md).

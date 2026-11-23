---
title: Two-column PDF numeric integrity, 2026-11-23
---

# Two-column PDF numeric integrity

The previously refused two-column fixture is fixed in `docling-pdf-r2`. This is a specific qualified layout, not universal support for arbitrary multi-column PDFs.

## Reproduced cause

On the original input SHA256 `196191c63a2e1d0d455125a42a8db943c6b3bb62a01c82b8ec568b8f839bdc2e`, Docling classified the two sentence columns as one table. Its default cell matching emitted `Right section observation` instead of the full final sentence ending in `11.`. The independent source-text check correctly refused publication with `PDF_NUMERIC_COVERAGE_MISMATCH`.

The [documented cell-matching option](https://docling-project.github.io/docling/usage/advanced_options/#control-pdf-table-extraction-options) restores the missing suffix for this case. A global switch was rejected after it lost dates in the unrelated real WARN table. The deployed policy preserves the original mode and permits at most one recovery attempt only after a numeric mismatch in a candidate two-column block.

Recovery uses the same offline Docling worker and existing CPU/memory/wall-time limits. Replacement requires matching table identity, page and detected outer box, plus two non-overlapping columns of complete sentences. Only those columns replace the primary blocks; unrelated blocks remain unchanged. Complete sentences are published as text with explicit geometric-order/recovery warnings. No fake column headers, second parser, OCR or model downloads were introduced.

The guard also compares complete numerical-token occurrences, not just a bag of digit characters. Negative tests reject changed groupings such as `12, 34` becoming `13, 24`, moved decimal positions, and missing repeated `11` values. This checks numerical completeness; it does not by itself prove every semantic association in an arbitrary table.

## Live successful verification

The same originally refused fixture was sent over real HTTP to `127.0.0.1:8011`, using the existing ingestion/jobs and PostgreSQL publication. No mocked API or persistence was used. This input is an explicitly identified reproducible fixture, not a claimed public document.

| Check | Original PDF | Stored original excerpts |
| --- | ---: | ---: |
| Numerical occurrences | 26 | 26 |
| Digit characters | 30 | 30 |
| Distinct numerical tokens | 12 | 12 |
| Complete source sentences | 24 | 24 |
| Missing / extra numbers | — | 0 / 0 |

The counts are: `0` twice, `1` four times, and each integer `2` through `11` twice. The two extra occurrences of `1` are the observed heading and page marker. Comparisons use original excerpts, excluding repeated retrieval heading context. Both final `11` values are present.

Five actual chunks reference page 1. Query `Right observation 11` returns the correct source/page. HTTP chunk IDs/content hashes match read-only app-role SQL snapshots. Idempotency replay retains version identity. Re-ingestion of the probe source exercised the selective recovery path; document details explicitly report `PDF_NATIVE_CELL_RECOVERY`. All unrelated corpus rows and prior chunks were preserved.

Source ID: `5f4ae6f05bef4a56ac3b28eb5caa6ceb`. Local evidence is under `tasks/evidence/pdf-layout-2026-11-23/selective-two-columns-live/`, particularly `successful-numeric-completeness.json` and `selective-path-confirmed.json`.

## Regression scope

Fresh extraction of all 11 qualification inputs passed with the final selective policy. Independent table truth checks retained all 69 audited fixture body rows/columns. The real public WARN first-page regression retained **259 identical cells** (37 rows including header, seven columns) and passed the stronger numeric guard. The tested two-column input now has zero published tables and two observed text columns.

The controlled 25-query comparison is saved under `tasks/evidence/pdf-layout-2026-11-23/selective-column-recovery/`. The selected 768/0 policy has 190 children, Recall@5 0.60 and Recall@10 0.88; plain recursive has 13 children, 0.56/0.80. These remain lexical fixture metrics, not general semantic QA claims.

225 targeted parser/ingestion tests passed during qualification; the final selective policy passed seven focused real parser/HTTP and numeric-negative tests. Ruff and mypy pass. Earlier full-suite/UI results remain historical; no frontend code changed in this fix. An additional complex public scientific two-column excerpt remained safely refused by numeric/layout validation and is not qualified by this fixture's success. OCR, visual semantics and original evidence storage remain outside this fix.

Reproduction uses Hatch. `scripts/workbench_pdf_columns_probe.py` uploads the exact earlier input, compares independent PDF text to actual stored excerpts and SQL, and records numeric counters. Its optional `--source-id`, `--expected-version` and separate `--output-dir` support guarded re-ingestion of an existing probe without overwriting unrelated sources. Do not reuse a completed idempotency key when testing a new parser execution.

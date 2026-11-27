# ANSWERABILITY-001 Phase A — saved-pilot diagnostic replay

**Date** 2026-11-28

**Result.** The offline projection passed on all nine saved EN/RU/UK contexts from three families. Six contexts support verified answers. The three Azure variants represent expected no-answer in one verified corpus scope. [Task and truth table](../../quality/TASK-RAG-ANSWERABILITY-001-insufficient-evidence-and-abstention.md#two-phase-execution-and-diagnostic-classification--2026-11-28) · [Recorded context pilot](../dataset-semantic-pilot-full-2026-11-28/report.md)

| Family | Variants | Reviewed corpus reference | Raw context verdict | Diagnostic result |
| --- | ---: | --- | --- | --- |
| Austen, EXT-LIT-001 | 3 | Answerable | sufficient | Answer supported, 3/3 |
| Ruskin, EXT-ART-003 | 3 | Answerable | sufficient | Answer supported, 3/3 |
| Azure invoice, EXT-NA-003 | 3 | No answer in the verified corpus | insufficient | Expected no answer, 3/3 |

No rows had retrieval misses, partial or conflicting evidence, unexpected answer support, unknowns, operational errors or unevaluated results. The denominators are six variants across two answerable families and three variants of one no-answer family. Translations share a family.

## Source scope and recorded judgments

The Azure derivation reported `not_found_in_supplied_excerpt`. The caller established `not_found_in_complete_eligible_scope` separately. The replay enumerated all 31 eligible public OPEN originals at snapshot `cbb2c98047d4dfe2bb5dd1ed23ceb6d08332ebb5`, verified each file digest and reran the case-insensitive search for the distinctive invoice identifier. The search found zero matches. The corpus-scope classification applies to that pinned source set, and the raw context verdict remains `insufficient`. [Original scope evidence](../dataset-semantic-pilot-2026-11-27/report.md#what-the-three-cases-established)

The local projection uses the preserved MAF 0.3.1 v8 envelopes, verified independent reference artifacts and exact public original-source bytes. It keeps the raw context verdict, independently derived reference answerability, corpus-scoped reference, scope proof and original operational reason in separate fields. Its revision is `answerability-diagnostic/v1`. The frozen input plan fingerprint is `a33ac9c4091ed2aa44a1cef0ff398cd342f6725c76a36f14587a51efe68b7995`.

## Verification

The replay uses the existing local ranking artifact reader, hash verifier and evidence writer. The new projector, source-proof loader, report adapter and focused tests live under the ignored `.local/evaluation-holdout/quality-check/` owner. The detailed additive projection is `.local/evaluation-holdout/quality-check/runs/answerability-diagnostic-2026-11-28/phase-a-projection.json` with file SHA-256 `b2dfdfc9d686bce5d19103d5b030b187f0723c230ecc47dbb3fb63b154fd189b`. A second replay reproduced the same artifact byte for byte.

All 137 focused and regression tests passed under Hatch 1.18.2, including 88 Phase A checks and 49 existing ranking and evidence-coverage checks. Ruff lint and format checks passed. Strict mypy passed on the three new implementation modules with a scoped exception for typed calls into the frozen legacy artifact reader. Tests cover all 25 reference and admitted-context combinations, provenance mismatches, missing coverage, conflicts, independently verified unexpected support, timeout, invalid output, cancellation and budget rejection.

Run the replay from the repository root in PowerShell.

```powershell
$qualityRoot = Join-Path (Get-Location).Path '.local/evaluation-holdout/quality-check'
$env:PYTHONPATH = (Get-Location).Path + [IO.Path]::PathSeparator + $qualityRoot
hatch -e workbench-api run python -m rag_quality.ranking.answerability_report
```

The replay used zero provider calls and zero retrieval or generation calls. The full OPEN audit, runtime abstention policy, false-acceptance and false-abstention rates, and holdout qualification are outside this evidence.

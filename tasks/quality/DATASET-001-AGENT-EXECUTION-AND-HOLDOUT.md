# DATASET-001 — Local holdout and reference answers

**Created:** 2026-11-24  
**Updated:** 2026-11-25  
**Status:** PROPOSED — local execution instructions; dataset not yet generated  
**Parent:** [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md)

## A. Title

Prepare and validate a local held-out RAG evaluation set automatically.

## B. Context / Problem

We need to measure retrieval and answer quality during local development without tuning on the same questions used for final evaluation. This is not an enterprise certification or independent security audit.

## C. Current Repository State

[External dataset V1](dataset/README.md) contains 31 source documents and 306 candidate query/answer rows (102 families across EN/RU/UK). These are visible diagnostic data. [Embedding evaluator](../../scripts/workbench_embedding_evaluate.py) owns existing fixture validation/scoring; [dense evaluator](../../scripts/workbench_dense_evaluate.py) owns actual HTTP and SQL checks. The legacy fixture has a 100-query limit and fixed chunk labels; preserve it and reuse the existing bounded adapter work in the parent task. See the parent for repository evidence and [engineering rules](../../AGENTS.md).

## D. Goal

The coding agent produces a usable, source-grounded local holdout with questions, complete reference answers and evidence, runs applicable validation and reports results. No user-authored answers or manual review required.

## E. Scope

Source selection, question/answer generation, evidence validation, split checks, local versioning and evaluator handoff.

## F. Non-Goals

No independent reviewer appointments, human approval workflow, separate service accounts, secrets, encryption, vault, isolated infrastructure, external certification, new agent framework or second evaluator.

## G. Architecture / Boundaries

One coding agent and the existing evaluation scripts are sufficient. Keep corpus originals separate from questions and expected answers. Use ordinary local files. The holdout is excluded from tuning by convention and evaluator input separation, not by a claimed security boundary.

## H. Contracts / Interfaces / Data Model

Create the following Markdown files under `tasks/quality/holdout/`:

- `CORPUS_MANIFEST.md` — source paths, version/hash, scope and source families.
- `QUESTIONS.md` — query ID, language, family and question.
- `REFERENCE_ANSWERS.md` — matching query ID, complete expected answer, required facts, acceptable alternatives and source locators; expected abstention for no-answer cases.
- `VALIDATION.md` — dataset revision, counts, checks, exclusions and SHA-256 file digests.

Reuse the parent schema and evaluator formats; derive machine-readable inputs only when required. No new runtime API.

## I. Repository Files / Components Impacted

The local holdout directory, the parent dataset task and existing evaluation scripts/tests if needed for the parent adapter. Add a narrow local ignore rule if the holdout is kept untracked; never place label files into ingestion. Preserve the existing 52-case fixture and open external dataset.

## J. Implementation Requirements

1. Read the existing corpus, question/answer files, parent task and applicable evaluator code. Verify available sources and original locators.
2. Generate new questions from real source content, including multi-facet, code, exact numbers, cross-language and no-answer cases. Do not merely translate or paraphrase open questions into the holdout. Keep correlated translations and source/question families grouped; prefer new source families where practical and disclose overlap.
3. Generate complete expected answers directly from originals, not from candidate RAG outputs. Check each answer again against source text in a separate pass. Use a fresh agent context if readily available, but no additional agent deployment or reviewer account is required. Reject ambiguous or unsupported cases.
4. Use the parent dataset targets as planning guidance; report actual accepted family/case counts and missing cohorts. Start with available valid cases rather than blocking local development on sample-size or organizational prerequisites. Preserve existing per-file and corpus limits.
5. Store the local files listed in H. Freeze their version and hashes before tuning; exclude them from tuning inputs and avoid inspecting them while optimizing. Git ignore is optional housekeeping, not security. The agent that authored them knows their contents; describe this accurately as a local held-out split, not a genuinely blind independent benchmark.
6. For final evaluation, feed only question text and authorized source corpus to the RAG pipeline. Compare actual outputs to reference answers afterward using existing evaluation ownership. Check evidence, required facts, correctness, completeness, citations and abstention as applicable. Report retrieval and generation separately.
7. Never tune using final holdout feedback. When detailed failures are used to improve the system, retain that set as regression evidence and prepare fresh questions for the next local holdout run. Do not silently change expected answers to match model output.
8. Execute all available steps autonomously. If a model/database is unavailable, complete the dataset preparation and record the specific runtime check as not run; do not require the user to recruit reviewers or provision security infrastructure.

## K. Security / Governance / Observability

Retain existing workspace, version and source checks. Use authorized source text only; keep credentials out of artifacts. Exclude labels, reports and questions from indexing. Ordinary local access is sufficient. Record safe execution status, source hashes and error categories. Enterprise custody and formal independent review are deferred and are not local prerequisites.

## L. Testing / Evaluation / Runtime Verification

Check unique IDs, one-to-one answer joins, exact source anchors, hashes, family leakage, no-answer verification, label exclusion from ingestion and legacy fixture compatibility. Run applicable configured Hatch checks (start with `hatch --version`) and actual local evaluator where available. Report commands, counts, exit codes and unavailable checks. Do not report mock or unexecuted tests as runtime evidence.

## M. Acceptance Criteria

- [ ] Agent generates local questions and matching complete reference answers.
- [ ] Every accepted answer is supported by original evidence; no-answer cases have a documented corpus check.
- [ ] Holdout files and digest exist, with no duplicate query families across tuning and holdout.
- [ ] Reference answers are excluded from runtime prompts, indexing and tuning.
- [ ] Validation results and actual local metrics (when executable) are recorded; no human approval or special infrastructure is required.

## N. Documentation / Migration / Compatibility / Rollback

Keep earlier dataset revisions and existing fixtures unchanged. If the holdout is used for tuning, version it as regression data and generate a new holdout. No migration, production change or new service.

## O. Mandatory Completion Checklist

- [ ] Inspect current owners and reuse existing logic.
- [ ] Generate and verify questions, answers and source references.
- [ ] Freeze and validate local holdout files.
- [ ] Run applicable existing tests/evaluation or record why not run.
- [ ] Record changed files, counts and limitations.

Execute this contract as part of the parent task. Do not stop at another plan: produce actual local data and run the available checks.

# TASK-GOV-001 — Establish contract consistency and review-before-change rules

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** PLANNED  
**Priority:** P1  
**Repository snapshot inspected:** `dc4b1cd45fb48b7154fdafcdd712a2536ee5da47`  
**Related tasks:** [MAF-002](maf/TASK-MAF-002-semantic-judge-agent.md), [DATASET-002](quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md), [QUALITY-003](quality/TASK-RAG-QUALITY-003-grounded-answer-correctness-evaluation.md)

## A. Title

Document repository-wide conflict resolution, stale-finding review and evaluation integrity.

## B. Context / Problem

A historical Semantic Judge review identified an apparent abstention/validation contradiction and category-repeatability failure. The v6 qualification resolved both observed failures without relaxing the gates. Future agents must reconcile current repository evidence and intended contracts before making changes, rather than repeating fixes or weakening acceptance rules.

## C. Current Repository State

- [Root instructions](../AGENTS.md) already route agents to [engineering conventions](../docs-website/ENGINEERING.md), including reuse-first and scoped verification guidance. The specific conflict-resolution procedure is missing.
- The [Semantic Judge contract](../apps/maf/SEMANTIC_JUDGE.md), scoped MAF instructions, `instructions.py`, `contracts.py`, `validation.py`, `calibration/controls.py` and `calibration/scoring.py` establish the current provider-neutral semantics and deterministic admission rules.
- MAF-002 records v6 PASS (32/32 admitted verdicts, three exact repeats, 106 offline tests). The old abstention failure was reproduced as `complete_without_required_facts`; the new prompt uses `not_applicable` and empty claims for pure abstention. The category rubric was clarified without changing the exact repeat gate. These are reported results, not newly executed tests.
- Some cross-field abstention invariants and explicit per-citation expected statuses are not fully enforced by the current validator/scorer. Answer claims currently resolve against the union of context and original excerpts. Do not claim these gaps were repaired by v6 or this documentation change.
- DATASET-002 owns the retrieval/reference audit; QUALITY-003 already owns Faithfulness-Plus and answer-quality evaluation. Neither requires reopening the qualified judge for this documentation-only task.
- Existing task directories were inspected; no dedicated governance task for these three instruction amendments was found.

## D. Goal

Publish one concise root routing rule and two scoped English policy sections, with valid relative links and explicit separation of current verified behavior, future requirements and historical results.

## E. Scope

Add the review-before-change rule to root AGENTS.md, the general conflict-resolution policy to ENGINEERING.md, and component-specific semantic/qualification clarification to SEMANTIC_JUDGE.md.

## F. Non-Goals

No runtime changes, prompt/schema revisions, new metrics, calibration modifications, live provider calls, task reopening, or changes to existing qualification results, datasets or acceptance thresholds.

## G. Architecture / Boundaries

Documentation and governance only. Root instructions route to engineering policy; the Semantic Judge document owns component-specific clarification. The caller continues to own RAG evaluation, scope coverage and final scoring. Keep MAF and Workbench/Haystack independent and provider-neutral. Domain, application, ports, adapters, persistence, retrieval, runtime, observability implementation and infrastructure are unchanged.

## H. Contracts / Interfaces / Data Model

No executable contract changes. Document existing pure-abstention semantics, factual verdict invariants, evidence categories, distinct unknown/error states and current frozen exact repeatability. Future mixed/cited-abstention semantics, per-citation expectations and separate faithfulness checks require explicit contract/protocol work before answer-quality qualification; they are not current guarantees.

## I. Repository Files / Components Impacted

- `AGENTS.md`: one short routing rule.
- `docs-website/ENGINEERING.md`: general policy, following reuse-first guidance.
- `apps/maf/SEMANTIC_JUDGE.md`: clarification after quote and scope validation.
- This A–O task: scope and completion evidence.

All source code, test fixtures, scoring, prompt/schema fingerprints, other task files and historical evidence MUST remain unchanged.

## J. Implementation Requirements

- MUST inspect current files and scoped guidance before editing and preserve existing content.
- MUST classify findings by current evidence and identify the normative owner and conflicting rules before changing behavior.
- MUST require explicit resolution of ambiguous requirements and preserve security, frozen qualification gates and historical decisions.
- MUST distinguish structural validation from semantic correctness and distinguish future hardening from already implemented behavior.
- MUST use existing documentation owners, English prose, relative Markdown links and semantic naming; do not add another competing policy document or provider-specific core rules.
- MUST document future changes through the owning A–O task before expanding scope.

## K. Security / Governance / Observability

Do not weaken authorization, workspace isolation, trust boundaries or deterministic validation. Preserve safe diagnostic identifiers, redaction, evidence provenance and historical records. No credentials, private payloads, new retention, egress or authorization mechanisms are introduced. No operational events change.

## L. Testing / Evaluation / Runtime Verification

Verify the documentation diff is limited to the four authorized Markdown paths; inspect inserted headings and relative links, preserve all original text, confirm the A–O sections and dates, and verify no runtime, calibration or historical files changed. Python/unit/integration/runtime/AI/CI execution: N/A — documentation-only, no executable or evaluation protocol changes. Do not claim newly executed calibration or tests.

## M. Acceptance Criteria

- [ ] Root rule links to the exact engineering heading.
- [ ] Engineering policy covers stale findings, normative ownership, minimal counterexamples, conflict resolution, regression verification and frozen evaluation integrity.
- [ ] Judge clarification preserves qualified behavior and explicitly distinguishes future hardening and caller responsibilities.
- [ ] Diff contains only the three instruction documents and this A–O task; original content and qualification history preserved.
- [ ] All new relative links and headings verified; no new runtime or live qualification claim.

## N. Documentation / Migration / Compatibility / Rollback

Additive Markdown-only change. No schema, index, config, API or provider migration. Preserve historical evidence. Roll back the documentation change with a scoped Git revert; no runtime rollback required. Future behavior changes must be separately specified and qualified.

## O. Mandatory Completion Checklist

- [ ] Inspect current repository and scoped guidance.
- [ ] Insert agreed English instructions without altering existing behavior.
- [ ] Verify scoped diff, links and A–O structure.
- [ ] Record checks run/not run and remaining limitations.

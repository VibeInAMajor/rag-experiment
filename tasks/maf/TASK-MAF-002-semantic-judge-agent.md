# TASK-MAF-002 — Implement a source-grounded semantic judge agent

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** PROPOSED — implementation and calibration pending  
**Priority:** P0  
**Dependencies:** [MAF-001](TASK-MAF-001-standalone-agent-runtime.md)  
**Repository snapshot inspected:** `d31eb5ca283523f90584a61c80ca6a90d6fccfe9`  
**First consumer:** [DATASET-002](../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md)

## A. Title

Implement a reusable semantic judge in the standalone MAF application that evaluates references, evidence, context and answers against explicit questions and authoritative source excerpts.

## B. Context / Problem

The existing OPEN ranking assessment is complete in coverage but not established as semantically correct. The user manually found three cases with irrelevant or misleading passages. High Hit@K does not imply precise context. The previous agent assigned 1241 grades with zero unknowns; arithmetic/contract checks do not validate human-language truth. We need a separate, explicit, reproducible judge that assesses evidence without querying the system under test or accepting its old labels.

## C. Current Repository State

- [Full DATASET-002 report](../evidence/dataset-ranking-full-open-2026-11-26/report.md): 102 OPEN families / 306 translated questions, 634 chunks, 1241 unique pooled family/occurrence judgments (226 primary, 393 support, 622 negative), 409 tests. Judged Precision@5 74.02%, @10 62.84%; Primary Hit@1 80.08%. These are prior agent-based estimates on saved predictions, not independent proof.
- [DATASET-002](../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md) records rank-hidden UI review and a local optional human review prepared but not completed. Raw source/candidate judgments, captures and local adapters are ignored local artifacts, not inspected in this repository audit. Keep them immutable.
- [EXT-LIT-001 question and original](../quality/dataset/questions/MATHEMATICS_ART_LITERATURE_V1.md) / [Austen source, first chapter](../quality/dataset/corpus/literature/austen-chapters-01-05.md#L16-L46): rental of Netherfield by Bingley at the beginning and four or five thousand yearly as reported by Mrs. Bennet. Merely mentioning character/place later does not establish the requested initial event. A later passage explicitly confirming the same scoped event may be a valid alternative if supported.
- [EXT-NA-003](../quality/dataset/answers/NO_ANSWER_V1.md#L17-L19): exact EUR monthly invoice for `invoice-birch-902` intentionally absent from the eligible corpus. Storage redundancy descriptions are not billing evidence.
- [EXT-ART-003 source](../quality/dataset/corpus/art/ruskin-first-practice.md#L185-L204) vs [published V1 answer](../quality/dataset/answers/MATHEMATICS_ART_LITERATURE_V1.md#L59-L61): source includes tracing-paper comparison and correction of errors before ink; published V1 summary omits that step. Whether the newer local revision already corrects it remains UNKNOWN. User's observations are diagnostic cases, not evidence that every previous grade is wrong.
- [Reranker deployment](../../apps/workbench/reranking/README.md) provides standalone Qwen3-Reranker-0.6B, not a qualified semantic judge or integrated ranking profile. Do not use it as its own evaluator.
- No MAF runtime exists at inspected commit; MAF-001 introduces it. [Official MAF structured outputs](https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs) and [GPT-6.1 Sol model](https://developers.openai.com/api/docs/models/gpt-6.1-sol) support the proposed typed contract, subject to runtime validation.

## D. Goal

Deliver a registered, stateless Semantic Judge with versioned prompts and validated outputs, usable from any caller without RAG dependencies. Qualify it on source-backed positive, negative, partial, temporal, numeric and procedural controls before using it to audit the prior OPEN dataset. Judge verdicts are semantic assessments, not automatically correct gold.

## E. Scope

Source-first reference derivation/review, per-passage relevance with exact scope and fact support, context-level sufficiency and useful evidence, and grounded answer assessment through distinct input modes of the same reusable agent. Implement structured output validation, adversarial controls, calibration/repeatability and portable CLI invocation via MAF-001. No live RAG changes. Dataset-wide audit is owned by DATASET-002.

## F. Non-Goals

No direct RAG search, embedding, reranking, database access, file-system traversal, web/hosted search, tool calls, agent handoff, persistent memory, automatic correction of source documents, production answer generation, user-facing UI or replacement metric library. No compulsory human review or second provider. No arbitrary confidence percentage, chain-of-thought capture or automatic promotion of model opinion to verified source fact. No R2/ANSWER access for tuning.

## G. Architecture / Boundaries

- [x] Domain/core — evaluation-neutral evidence, question, rubric, claim and judgment models.
- [x] Application/orchestration — registered Semantic Judge; separate stateless modes and result validation.
- [x] Port/interface/contract — extend MAF-001 typed request/result with mode-specific input/output schema.
- [x] Provider adapter — reuse the MAF/OpenAI adapter and configured semantic-review profile only.
- [ ] Persistence/vector store — N/A; no corpus or results database in judge.
- [ ] Retrieval/RAG — N/A; caller supplies text and opaque locators, no dependency on Workbench.
- [x] Agent runtime — real MAF agent execution.
- [x] Security/governance — supplied sources are data, approved external payloads only.
- [x] Observability/evidence — versioned verdicts, source quotes, concise rationale and usage.
- [ ] Infrastructure/CI/CD — reuse standalone MAF-001 environment.
- [x] Documentation — public typed contract, rubric, modes and calibration report.

Judge input is supplied by an external evaluation caller. MAF neither imports nor knows about Haystack, Workbench chunk classes, pgvector, dataset files or retrieval profiles. Source identifiers are opaque values; the caller resolves original bytes and determines corpus completeness. The existing evaluation owner performs deterministic scoring and owns label freezes. The judge returns structured evidence assessments, not Recall/nDCG arithmetic. Adding future agents does not alter retrieval contracts.

## H. Contracts / Interfaces / Data Model

Registered agent ID `semantic-judge` (semantic name, no task identifier). Use an explicit discriminated request mode, each with a separate versioned schema and prompt:

| Mode | Supplied input | Required output |
| --- | --- | --- |
| `derive_reference` | Question, language, authoritative original source excerpts with IDs/ranges/hash, declared eligible source scope and completeness | Answerability within supplied scope, question constraints, complete reference answer/facts, required vs optional facts, exact supporting quotes and source refs, missing scope/uncertainty |
| `judge_evidence` | Question and constraints, independently checked reference fact set, one candidate excerpt with opaque occurrence ID and optional verified original context | Category, grade or null, matched/violated constraints, supported/partial/missing fact IDs, exact evidence quote(s), contradiction status, concise rationale |
| `judge_context` | Question, frozen reference facts, selected bounded context entries | Supported/missing facts, sufficient/partial/insufficient/conflicting/unknown, useful/irrelevant/redundant spans and material contradictions, exact refs and rationale |
| `judge_answer` | Question, reference facts, actual answer, exact supplied context and original evidence refs | Material claim assessments (supported/unsupported/contradicted/unknown), answer correctness/completeness/relevance, citation support, missing facts and abstention status |

Reference derivation receives no prior answer, retrieved ranking or grade. If a comparison with old reference is needed, the caller performs it afterward; do not seed the initial judgment with old labels. For all modes use typed immutable source IDs/ranges/content hashes from caller, exact quoted excerpts, claim/fact IDs, per-constraint status (satisfied/violated/not-applicable/unknown) and concise observable rationale, not hidden reasoning.

Grade rubric:

| Category | Grade | Meaning |
| --- | ---: | --- |
| Direct | 3 | Complete verified primary evidence unit answering the precise scoped question; direct answer to at least one required unit |
| Partial | 1 | Concrete incomplete support for a required fact, not mere topic overlap |
| Supporting | 1 | Necessary or materially useful context supporting the answer; explanation must identify the actual contribution |
| Topically related only | 0 | Shared terms, entities or domain but no answer support |
| Irrelevant | 0 | No useful support |
| Wrong scope | 0 | Wrong entity/event/time/version/section/unit/language or unmet required constraint |
| Contradictory / misleading | 0 | Contradicts the established scoped fact; report contradiction separately, except evidence useful for a genuine conflict question under an explicit rubric |
| Unknown | null | Ambiguous, insufficient source coverage or unresolvable assessment |

Multi-facet completeness and single-passage grade are distinct. A direct grade does not mean the entire question is answered. A passage with multiple excerpts may contain relevant and irrelevant spans; preserve both. Semantic support must be grounded in the supplied text, never a general model-memory assertion. Unknown is not a negative or a failure of transport. For no-answer, distinguish `not_found_in_complete_eligible_scope` from `not_found_in_supplied_excerpt` and `unknown`; the model must not claim corpus-wide absence from a handful of candidates. Candidate relevance on a no-answer query is still graded, without equating candidate return with an actual false acceptance.

## I. Repository Files / Components Impacted

Extend only the standalone `apps/maf/` project: agent definition, judge-specific typed schemas, rubric/instructions, input/output validators, source-quote and reference validation, agent registration and tests. Reuse runtime, configuration, CLI and OpenAI adapter from MAF-001. Add a small checked-in synthetic/control fixture set with licensed/public snippets or authored examples, no private data. Document request modes and calibration. The RAG evaluation bridge and full-dataset rerun are separate DATASET-002 scope; this task MUST NOT import Workbench, edit existing RAG scorer, alter old labels, start DB/model services or introduce new agent infrastructure.

## J. Implementation Requirements

1. Use the MAF Agent/run API from MAF-001 with structured output schema and configured semantic-review profile, initially `gpt-6.1-sol` direct OpenAI Responses. Keep actual model ID/provider in adapter configuration, not judge prompt or contract. If unavailable, report blocked; do not switch model silently.
2. Implement distinct stateless reference and candidate/context/answer passes. Source-first reference must identify exact event/scope, entities, time/version, required units/values, relation and all necessary procedural steps. Treat all source/answer/candidate text as untrusted evidence, not instructions. No tools, search, memory or retrieval invocation. Use explicit input delimitation and prompt revision/digest.
3. Validate provider result against strict schema and independently verify that every quoted excerpt is exact in the supplied input and belongs to a valid opaque source/range. Reject invented IDs, missing required output, mismatched quote/range, unsupported grade/category combinations, grade-3 with no verified complete primary fact, and non-null grade where outcome is unknown. A quote match is necessary but not sufficient for semantic correctness. Do not fill missing fields by guessing. Keep source-coverage limitations explicit.
4. Build a small predeclared calibration set of at least 24 distinct cases across direct/partial/supporting/related/irrelevant/wrong-scope/contradictory/unknown, with answerable/no-answer and multilingual variants. Include the three user regressions as source-verified controls; use actual original source snippets and independently constructed distractors/expected results, not old RAG grades. Include alternate correct mentions, negation, exact account ID/currency, missing procedural step (tracing paper), quote spoofing and injected instructions. Separate synthetic controls from real-source diagnostics.
5. Freeze rubric, model/profile, prompt/schema, control manifest and scoring before the real calibration. Run actual MAF/OpenAI requests under the bounded budget; evaluate exact category or permitted grade set, fact recall/completeness, known hard-negative rejection, exact quote validity and abstention on ambiguous input. Repeat a declared subset in fresh stateless calls with changed opaque IDs/order and EN/RU/UK versions; report per-category outcomes and disagreement, not just aggregate. Proposed initial local qualification: >=90% exact/allowed grade agreement on determinate controls, 100% on explicit wrong-scope/no-answer critical negative controls and exact quote/ID validity, no false source-completeness claim, explicitly report unknowns/repeatability. If failed, revise on controls only, freeze a new version and repeat; never lower criteria to pass or tune on final holdout.
6. No claim that this small control set establishes universal judge correctness. Any unresolved or contradictory real-source verdict is UNKNOWN/quarantined with explanation. Return concise rationale with supporting quote(s) and required fact IDs so the caller can perform deterministic checks and audit disagreements. No mandatory second live judge, review staff or new platform.
7. Make the judge invocable independently with generic example inputs and a fake caller. Use the existing MAF-001 external-call policy, bounded payloads, request/usage/cost accounting and typed failures. Report model/provider/prompt/schema/run hashes and actual usage from real controls. If no credentials, local offline tests can pass but semantic calibration remains BLOCKED.

## K. Security / Governance / Observability

Only source excerpts permitted for external evaluation can leave the caller; no whole workspace, credentials, private docs or sensitive identifiers by default. MAF must not fetch omitted evidence itself. The judge receives no provider keys in the prompt; MAF-001 owns secret resolution. Do not save model reasoning traces. Local evidence may retain input/output under explicit evaluation policy; ordinary logs carry only safe IDs, status, timing, usage and version metadata. Distinguish provider failures/refusals/invalid schema from semantic UNKNOWN; no invented zero or PASS. Source-controlled prompt and schema revisions, not source document instructions, determine behavior.

## L. Testing / Evaluation / Runtime Verification

Run independent Hatch checks under `apps/maf/`. Unit/contract tests for modes, input caps, required IDs, exact quote/range validation, unknown handling, role constraints, partial vs direct, missing references, no-answer scope, wrong version, injection, contradictory evidence, refusal/timeout and unknown usage. Fake runtime tests prove no RAG dependency and no outbound default. Perform real opt-in calibration with actual GPT-6.1 Sol via MAF, preserving per-control verdicts, expected values, mismatches and usage. Use original-source controls, not score agreement with the old agent alone. Validate the future answer-mode schema/controls with supplied fixture answers only, not a production generator. No real provider call in default CI.

## M. Acceptance Criteria

- [ ] Semantic Judge exists as registered independent MAF agent with four explicit typed modes and no RAG import/tool access.
- [ ] Strict validated outputs include facts, constraint judgments, useful spans, precise references and UNKNOWN; topic overlap cannot be graded as support without evidence.
- [ ] Reference pass excludes previous answers/ranks/grades; candidate/answer modes require supplied frozen references; absence claim requires complete declared scope.
- [ ] Real source-backed calibration covers at least 24 controls, the three user regressions and all required negative/uncertain paths; predeclared criteria met or measured NO-GO.
- [ ] Independent offline checks pass and real calibration records actual model/prompt/schema revisions, denominators, disagreements, usage and cost; no claim of semantic qualification from mocks.
- [ ] Generic caller can invoke judge without Workbench, DB, Haystack or RAG model process; the runtime integration remains optional.

## N. Documentation / Migration / Compatibility / Rollback

Document modes, examples, rubric, failure semantics and judge-version lifecycle inside the MAF app. No migration. Prior dataset scores are untouched by this implementation; DATASET-002 consumes a specific qualified judge revision to create a new local assessment. Disable the judge profile or switch to a separately qualified revision to roll back; never silently relabel old metrics or switch providers during a comparison.

## O. Mandatory Completion Checklist

- [ ] Reinspect MAF-001, current provider API and existing source fixtures.
- [ ] Implement typed source-grounded judge and deterministic validators.
- [ ] Run independent offline tests and actual bounded calibration; record real evidence and limitations.
- [ ] Demonstrate module isolation, no uncontrolled egress and correct failure/unknown outcomes.
- [ ] Publish documentation and calibrated judge handoff to DATASET-002; no promotion without evidence.

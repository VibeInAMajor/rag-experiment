# TASK-MAF-002 — Implement a source-grounded semantic judge agent

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** Implemented. The initial live calibration measured `NO_GO`. Evidence prompt revision 3 is in live qualification.

**Priority:** P0  
**Dependencies:** [MAF-001](TASK-MAF-001-standalone-agent-runtime.md)  
**Repository snapshot inspected:** `d31eb5ca283523f90584a61c80ca6a90d6fccfe9`  
**First consumer:** [DATASET-002](../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md)  
**Architecture:** [MAF module boundary](MAF_ARCHITECTURE.md)

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

### Judge qualification clarification — 2026-11-27

Retain the four named request modes in H. Split prompt-development examples from frozen qualification controls; the three reported families are mandatory regression controls, not a hidden independent test. Add unseen synthetic contrasts and public source cases to qualification. Record binary answer-support agreement separately from coarse grade/class agreement (proposed >=95% binary agreement on determinate qualification controls, >=90% grade agreement); count operational errors and UNKNOWN separately and disclose coverage, not selective denominator improvement. No positive grade without a validated exact quote and contribution to a requested fact; for multi-span claims distinguish individual partial support from sufficient union. Use caller-verified Unicode offsets, reject invented IDs and ambiguous ranges unless explicitly disambiguated. Reference derivation must not see old references, and caller compares saved source-first output afterward. Preserve uncertainty and independent source evidence when resolving old/new disagreements. Do not award usefulness solely for co-occurring entities or a passage being in the right chapter. Initial `gpt-6.1-sol` remains configurable; alternate models, including `gpt-6.2-sol`, require separate qualification. No hard-coded fixture answers in general instructions.

## K. Security / Governance / Observability

Only source excerpts permitted for external evaluation can leave the caller; no whole workspace, credentials, private docs or sensitive identifiers by default. MAF must not fetch omitted evidence itself. The judge receives no provider keys in the prompt; MAF-001 owns secret resolution. Do not save model reasoning traces. Local evidence may retain input/output under explicit evaluation policy; ordinary logs carry only safe IDs, status, timing, usage and version metadata. Distinguish provider failures/refusals/invalid schema from semantic UNKNOWN; no invented zero or PASS. Source-controlled prompt and schema revisions, not source document instructions, determine behavior.

## L. Testing / Evaluation / Runtime Verification

Run independent Hatch checks under `apps/maf/`. Unit/contract tests for modes, input caps, required IDs, exact quote/range validation, unknown handling, role constraints, partial vs direct, missing references, no-answer scope, wrong version, injection, contradictory evidence, refusal/timeout and unknown usage. Fake runtime tests prove no RAG dependency and no outbound default. Perform real opt-in calibration with actual GPT-6.1 Sol via MAF, preserving per-control verdicts, expected values, mismatches and usage. Use original-source controls, not score agreement with the old agent alone. Validate the future answer-mode schema/controls with supplied fixture answers only, not a production generator. No real provider call in default CI.

### Verification record — 2026-11-27

The standalone `semantic-judge` reuses the MAF-001 admission path, OpenAI Responses adapter and version 1 JSON envelope. Each mode has its own input, strict output and versioned prompt. Deterministic validators check excerpt digests, Unicode intervals, source roles, exact IDs, coverage claims, quoted support and rubric consistency. Semantic assessments still need qualification. [Judge contract](../../apps/maf/SEMANTIC_JUDGE.md)

| Verification | Result |
| --- | --- |
| Hatch 1.18.2 on Windows with Python 3.12.1 | `hatch run check`, `hatch run types` and `hatch run test` passed. 101 tests passed, including 34 focused validation tests. |
| Standalone Linux container with `--network none` and Python 3.12.15 | Ruff, strict mypy and all 101 tests passed in a copy of the MAF project. |
| Standalone CLI and module | Subprocess tests verify import isolation, explicit egress opt-in, a bounded JSON result, quote normalization and the distinct `UNKNOWN` and invalid-output paths. |
| `hatch build --target wheel` | Built `rag_maf_agent_runtime-0.2.0-py3-none-any.whl`. |
| `hatch run calibrate --check` | Passed for 29 distinct controls and 3 stateless repeats. The separate development set contains three cases. |
| Public-source provenance | Verified 13 excerpt occurrences against the exact Unicode slices of the LF-normalized Austen, Ruskin and Azure originals. SHA-256 checks passed for all supplied snippets. |

The frozen qualification control manifest SHA-256 is `caa72c9408c4ab4a2066671524be825824addebbc5491b94fead1597c4b606cf`. Each calibration fixes the model profile `semantic-review` (`gpt-6.1-sol`, `medium`), prompt/schema revisions and digests, scoring thresholds, concurrency of one, a 420-second deadline, zero retries and a maximum estimated run cost of USD 1.441792. Determinate controls remain in their denominators when a result is missing, ambiguous or operationally invalid. [Controls](../../apps/maf/calibration/controls.py) · [Runner](../../apps/maf/calibration/run.py) · [Scoring](../../apps/maf/calibration/scoring.py)

The built-in controls use Austen's beginning-of-novel rental and income report, Azure storage redundancy with no invoice data, and Ruskin's tracing-paper step. They include separate reference, evidence, context and answer cases, plus EN/RU/UK repeats. The source shards and distractors are local to the MAF control manifest. The dataset audit remains caller-owned.

#### Initial live qualification

The operator ran `hatch run calibrate --allow-external --report calibration/live-report-rag.jsonl` using the existing project credential. The run used implementation `bf1267a` and calibration fingerprint `e0d6b1bab9798b40e116f8e45ac6688aa217a7fc54340536a8fd38f0de87be9b`. The reused editable Hatch environment reported distribution metadata `0.1.0`. The recorded mode and manifest fingerprints identify the running judge source. Recreating the standalone Hatch environment installed distribution metadata `0.2.0` for the follow-up.

| Measure | Initial run |
| --- | --- |
| Validated verdicts and actual provider model | 32/32, `gpt-6.1-sol` |
| Determinate grade agreement and binary support | 16/16 for each |
| Non-evidence mode agreement | 12/12 |
| Critical controls and expected `unknown` | 15/16 and 0/1 |
| Repeatability and original-source diagnostics | 3/3 repeats, all 9 original-source controls plus both original-source repeats |
| Fact and required-quote checks | 30/30 and 3/3 |
| Provider usage | 37,400 input tokens, 12,177 output including 2,471 reasoning, 0 cached input |
| Provider attempts and estimated Standard usage cost | 32 attempts, 0 retries, USD 0.236797 |

`billing-ambiguous-row` produced `partial` with grade 1 even though the candidate explicitly left the amount's account attribution unresolved. The frozen control requires `unknown` with a null grade. This failed the critical and unknown gates. All responses met the structural and quote validators and none overclaimed complete source coverage. The initial result is `NO_GO`.

#### Evidence prompt revision 2

`judge_evidence/2` requires the quoted contribution to be attributable to the requested entity, event or record. When competing attributions are explicitly unresolved and there is no independently attributable contribution, the expected result is `unknown`. A separate authored development probe assesses the same rule with an unassigned equipment reading. The revised qualification fingerprint is `08f3a44a620f8f9430b3b3298f956e56e98bd422bffe9fa2fb05295f8d2356ff`. The 32 qualification requests and gate thresholds are from the same frozen control manifest.

The live development run matched 2 of 4 probes. `dev-reference-sensor-model` ended in `PROVIDER_FAILURE` without returned model or usage metadata. `dev-evidence-unassigned-sensor-reading` returned usage and then failed with `INVALID_OUTPUT`. The frozen qualification run was held at the development gate.

#### Evidence prompt revision 3

`judge_evidence/3` specifies the structured representation for ambiguity. An unassignable fact uses `unknown` and an empty quote list. Spans may be empty when the candidate supplies no attributable evidence. The runner also records a bounded operational failure stage in the local report. The public invocation schema and qualification controls are unchanged.

The revised development fingerprint is `69a127152bba4d67e383bd220c69bab613c0e98688d5672f881b170e39c5e9f4`. All four development probes passed with `gpt-6.1-sol`, four requests, zero retries and estimated usage cost of USD 0.01954975. The qualification fingerprint is `1e42c13277cbf8bdfb3570e300fe5a03365dbbc5f2578703bd4645049d77f83a`.

## M. Acceptance Criteria

- [x] Semantic Judge registers four independent typed modes and runs without RAG dependencies or tools.
- [x] Strict results include facts, constraints, useful spans, exact references and `unknown`. A positive grade requires a quoted contribution to a required fact.
- [x] Reference derivation accepts original excerpts and declared scope. The other modes require a frozen reference. A complete-scope absence requires declared complete coverage.
- [x] The initial real calibration covered 29 controls, the three original regressions and the declared repeats. The gates measured `NO_GO` for an ambiguity error.
- [x] Offline checks passed. The live report captures actual model, prompt/schema revisions, disagreements and usage for the initial run.
- [x] A generic caller invokes the judge through the standalone version 1 JSON CLI.

## N. Documentation / Migration / Compatibility / Rollback

Document modes, examples, rubric, failure semantics and judge-version lifecycle inside the MAF app. No migration. Prior dataset scores are untouched by this implementation; DATASET-002 consumes a specific qualified judge revision to create a new local assessment. Disable the judge profile or switch to a separately qualified revision to roll back; never silently relabel old metrics or switch providers during a comparison.

## O. Mandatory Completion Checklist

- [x] Reinspect MAF-001, the released provider API and source fixtures.
- [x] Implement typed source-grounded judge and deterministic validators.
- [ ] Run independent offline tests and actual bounded calibration; record real evidence and limitations.
- [x] Verify package isolation, default egress denial and distinct failure and `unknown` outcomes.
- [ ] Publish documentation and calibrated judge handoff to DATASET-002; no promotion without evidence.

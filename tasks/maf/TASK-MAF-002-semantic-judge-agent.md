# TASK-MAF-002 — Implement a source-grounded semantic judge agent

**Created:** 2026-11-27  
**Updated:** 2026-11-28

**Status:** REOPENED for bounded output-cap and prompt-cache qualification. Runtime 0.3.1 passed v8; the 32,000-token candidate is checked in but not yet qualified. Prompt caching, cache-write accounting and measured cache reuse remain to be implemented and verified. Historical v8 evidence remains valid for 0.3.1.

**Priority:** P0  
**Dependencies:** [MAF-001](TASK-MAF-001-standalone-agent-runtime.md)  
**Repository snapshot inspected:** `d31eb5ca283523f90584a61c80ca6a90d6fccfe9` (original baseline); `7709a24187e3c1f2845015678bd76042447bccf4` (cache amendment, 2026-11-28).  
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

### Current cache evidence — 2026-11-28

- [Current adapter](../../apps/maf/src/agent_runtime/adapters/maf_openai.py): `MafOpenAIRuntime.invoke` sets explicit caching and 30-minute TTL; its `_ResponsesTransport._guarded_request` admits one user JSON text block and top-level instructions with an exact allowlisted wire structure. No cache breakpoint or routing key is emitted. Current OpenAI explicit-only semantics require a breakpoint; without one the request neither reads nor writes a prompt cache. The existing wire test checks options and zero cached tokens, not real cache reuse.
- [Usage contract](../../apps/maf/src/agent_runtime/contracts.py) and adapter `_reported_usage` expose cached reads but not cache-write counts; [configuration](../../apps/maf/src/agent_runtime/configuration.py) estimates all non-read input at the write rate. This is a conservative estimate, not exact per-category accounting. [Calibration runner](../../apps/maf/calibration/run.py) already fingerprints controls, schemas and limits and checkpoints JSONL; it does not freeze cache policy or summarize cache efficiency.
- The recorded initial/v4/v6 runs have zero cached input tokens. The published full-input pilot does not disclose cache read/write totals. Do not infer its hit rate. The existing 0.3.2 ceiling amendment is not yet verified. The 16 KiB request cap remains an independent admission limit, not a provider context window.
- Enterprise source inspected at commit `955fd049949d3fc462d555be14774e4b255aa15c`; reusable components and limitations are documented in J. Operator-local settings, retained provider traces and live cache performance are not available in this review.

## D. Goal

Deliver a registered, stateless Semantic Judge with versioned prompts and validated outputs, usable from any caller without RAG dependencies. Qualify it on source-backed positive, negative, partial, temporal, numeric and procedural controls before using it to audit the prior OPEN dataset. Judge verdicts are semantic assessments, not automatically correct gold.

## E. Scope

Source-first reference derivation/review, per-passage relevance with exact scope and fact support, context-level sufficiency and useful evidence, and grounded answer assessment through distinct input modes of the same reusable agent. Implement structured output validation, adversarial controls, calibration/repeatability and portable CLI invocation via MAF-001. No live RAG changes. Dataset-wide audit is owned by DATASET-002.

The 2026-11-28 amendment adds native prompt-prefix caching, validated read/write usage accounting and bounded comparative cache qualification before the full OPEN audit. Keep the 32,000 output-token profile candidate and its already-defined reserve; do not silently expand other limits.

## F. Non-Goals

No direct RAG search, embedding, reranking, database access, file-system traversal, web/hosted search, tool calls, agent handoff, persistent memory, automatic correction of source documents, production answer generation, user-facing UI or replacement metric library. No compulsory human review or second provider. No arbitrary confidence percentage, chain-of-thought capture or automatic promotion of model opinion to verified source fact. No R2/ANSWER access for tuning.

No Redis, cache server, vector index, session restoration, workflow graph, autonomous retry/recovery loop, imported Enterprise web application or mandatory Langfuse dependency. No reuse of a prior judge verdict in calibration, repeats or cold/warm comparisons. Corpus-specific result checkpoints remain caller-owned.

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

Cache transport hints are adapter-owned; core contracts remain provider-neutral. Preserve the four mode input/output shapes, grades, quote offsets, source hashes, and one-shot fresh inference. Extend only the existing usage/metadata contract as needed for nullable cache-write counts and versioned accounting; explicitly decide compatible envelope evolution (strict older consumers reject extra fields). Test legacy JSONL replay with missing fields, and update the affected CLI consumers before emitting an incompatible shape. No silent reinterpretation of historic estimated costs.

## I. Repository Files / Components Impacted

Extend only the standalone `apps/maf/` project: agent definition, judge-specific typed schemas, rubric/instructions, input/output validators, source-quote and reference validation, agent registration and tests. Reuse runtime, configuration, CLI and OpenAI adapter from MAF-001. Add a small checked-in synthetic/control fixture set with licensed/public snippets or authored examples, no private data. Document request modes and calibration. The RAG evaluation bridge and full-dataset rerun are separate DATASET-002 scope; this task MUST NOT import Workbench, edit existing RAG scorer, alter old labels, start DB/model services or introduce new agent infrastructure.

Cache amendment: inspect and extend the existing adapter, runtime admission, configuration/pricing, Usage contract, calibration runner, and current adapter/runtime/calibration tests under `apps/maf/`. Update package/release metadata, README, SEMANTIC_JUDGE.md and MAF_ARCHITECTURE.md as needed. Use a single cache-policy owner inside the adapter; introduce a helper only for a distinct tested responsibility. The existing caller may need a compatibility update to decode new metadata and record safe batch statistics; this belongs to DATASET-002's existing owner, not a new evaluator. Do not edit hidden local files by assumption or alter the frozen controls/gates.

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

### Prompt caching and Enterprise reuse amendment — 2026-11-28

Implement the following bounded substeps before the next full audit. Use the [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) and [pricing](https://developers.openai.com/api/docs/pricing), verified on 2026-11-28. Use the actual installed MAF/OpenAI SDK wire behavior as evidence, not an assumed SDK field mapping.

1. **Stable prompt composition.** Keep explicit-only caching and 30-minute TTL for the qualified direct Responses model. Put the unchanged trusted mode instructions in an initial developer message with an explicit content-block breakpoint. Keep the complete validated JSON as user data, not developer instructions; never duplicate it in the prefix. Measure whether the actual reusable visible prefix meets the 1,024-token eligibility threshold, including schema only if provider diagnostics establish its placement/eligibility. Do not pad the prompt to manufacture eligibility. If needed, evaluate a second breakpoint within a deterministic serialization of the user data for repeated question/reference pairs (especially judge_evidence): concatenate the text blocks to the same validated JSON and preserve field values, source order, scope and trust level. Qualify the changed framing and only enable this optimization for explicitly approved, safely scoped reusable data. All unique candidate/context/answer content remains after the last breakpoint. If the SDK cannot faithfully encode it or the prefix is too short, report that limitation and use the separately qualified no-cache path; do not claim savings.
2. **Cache identity and guard.** Adapt the stable digest/anchor approach, not session history. Use stable opaque keys where needed, bound to provider/model/profile, mode, prompt/schema fingerprints, prefix layout revision and authorized isolation scope. A shared static public rubric may use a static scope; never share user/reference-specific keys across unrelated security scopes, or derive them solely from request/trace IDs. Do not place raw identifiers, keys, private source text or secrets in a cache key. Recheck egress and source authorization for every physical request; cache identity is not authorization. Extend the exact wire guard to allow only the intended developer/user roles, content, breakpoints, key and options. Reject unexpected fields/roles, duplicated instructions, unauthorized hints, changed source bytes or stateful provider continuation. Preserve store=false, no tools, no hidden reasoning retention, no background, no truncation, one request, zero retries. Confirm cache retention is allowed by the project's egress/data policy.
3. **Usage and pricing.** Extend the existing provider-neutral Usage metadata for nullable cache-write input tokens; map the actual Responses `input_tokens_details.cached_tokens` and `cache_write_tokens` fields and verify against real responses. Validate nonnegative integer counts, reads+writes <= input, reasoning <= output. Missing or inconsistent usage is unknown, not zero; invalid accounting must not silently produce a discounted cost or invalidate an otherwise valid semantic verdict without a documented reason. Compute ordinary input = total input - read - write when known. For GPT-6.1 Sol Standard short context, verify tariff at execution (currently USD 2 ordinary, 0.10 read, 2.50 30m write, 10 output per million). Apply the existing conservative regional allowance separately and identify it as an estimate; do not present estimated charges as invoice-reconciled amounts. Reasoning is included in output. Preserve worst-case pre-egress reserve without assuming hits; distinguish exact-category estimated cost, conservative upper estimate and unknown cost, with versioned tariff and accounting evidence. Do not retroactively reprice old reports.
4. **Measured cache diagnostics.** Reuse the runner's fingerprints and JSONL; add cache policy/layout/key-scope revision, wire bytes, estimated prefix and suffix tokens (not billed counts), physical request count, actual usage categories, cache-read token share (sum reads/sum input on known rows), request hit rate (read-positive/eligible observed calls), write/read totals, elapsed time, estimated cost and savings versus same observed token usage at ordinary input price. Report missing telemetry coverage, cold/warm rows, per-mode counts and output/reasoning independently. No prompt bodies or reasoning traces in telemetry. Group independent cases by mode and identical authorized reference only when this does not alter frozen test order/holdout isolation; run separate cache probes if regrouping is required.
5. **Controlled qualification.** First record offline capacity checks for the 0.3.2 configuration. Freeze a no-breakpoint baseline and cache-enabled candidate with identical model, reasoning, input semantics, 32,000-token ceiling, schema, rubric and source fixtures. Run a small separate synthetic/public cache probe before final qualification: predeclare at most eight total physical calls (including baseline, first write and repeated calls with distinct suffixes), reserve at most USD 3.20 at the current worst-case per-call rate, no extra warmups or retries; use a distinct report and explicit egress opt-in. Measure at least two independent warm requests with nonzero provider-reported cached reads after a qualifying write, and ensure an altered prefix/key-scope or no-breakpoint control is distinguishable; do not assume the first request is cold without evidence. Use a fresh opaque experiment scope when isolation is required. No invented universal hit-rate target; if no eligible prefix/hit is measured or savings are nonpositive on representative repeated traffic, record NO_GO/NOT_EVALUABLE for cache adoption, investigate or keep cache disabled. Independently run the unchanged 32-case semantic qualification and exact saved 46-request full-input pilot replay on the final candidate with separate approved aggregate reservations. Retain previous gates, report all differences including semantic disagreement, quote validity, operational errors and latency. Do not declare the cache effective solely from mock transport. Do not claim a semantic PASS from a cache hit.
6. **Separation of responsibilities.** Cache computation reuse is not result reuse. MAF must execute fresh provider inference for every qualification and repeatability case. DATASET-002 can reuse admitted identical verdicts only for interrupted-run resume under its existing checkpoint rules and source/profile/prompt/schema/runtime fingerprints. A stale, failed, partial or changed-input result cannot be a cache hit; retain failed attempt accounting. No hidden second call, automatic model switch or automatic enlargement of budgets.

#### Reuse inventory and ownership decisions

The following is a source inspection, not a claim that the Enterprise runtime or its local production performance was executed here. All links pin the inspected commit.

| Enterprise source | Reuse decision for Semantic Judge |
| --- | --- |
| [maf_prompt_cache.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/engineering/maf_prompt_cache.py), [azure_prompt_cache.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/runtime/azure_prompt_cache.py), [test_maf_prompt_cache.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/tests/pipeline/test_maf_prompt_cache.py) | NOW: adapt breakpoint, stable scope digest, capability admission and actual SDK mock-wire assertions. Enterprise uses implicit mode plus explicit anchors for multi-turn Azure roles; keep explicit-only for this one-shot judge. Do not copy session mutation or Azure deployment-SKU rules. |
| [native_chat_accounting.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/runtime/native_chat_accounting.py), [token_pricing.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/configuration/token_pricing.py) | NOW: adapt usage-subset invariants, explicit unknown costs, tariff fingerprint and non-invoice estimate. Reuse our existing Usage/configuration owner; do not import the Enterprise pricing catalog or apply Azure rates. |
| [maf_input_measurement.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/observability/maf_input_measurement.py) | NOW: adapt redacted measurements after SDK serialization, separate instructions/schema/reference/candidate and control overhead, label token estimates non-billable and potentially non-additive. This helps locate input-cap and cache-prefix bottlenecks without logging text. |
| [native_output_budget.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/observability/native_output_budget.py), [azure_request_admission.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/runtime/azure_request_admission.py) | LATER IF MEASURED, caller-owned: aggregate reservations, provider RPM/TPM header-aware pacing and bounded resume. The 32,000 cap may affect quota independently of actual billed output. Existing one-shot MAF admission and serial runner remain authoritative now; do not import Azure transport or introduce auto-retries/dynamic cap reduction. Keep rate-limit errors visible and record observed quota/Retry-After safely when available. |
| [candidate_validation_cache.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/src/enterprise_ai_pipeline/validation/candidate_validation_cache.py), [maf_evaluation_attestation.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/engineering/maf_evaluation_attestation.py) | DATASET-002: adapt exact input/current-policy binding and physical producer receipt checks to existing checkpoint/replay, including scope, model, request and verdict digest, not a second database or security workflow. Reverify provenance on consumption. No checkpoint result reuse for calibration or repeats. |
| [maf_diagnostics.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/observability/maf_diagnostics.py), [maf_langfuse.py](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/observability/maf_langfuse.py) | NOW: use safe correlation and one record per physical call in existing local metadata/JSONL. OPTIONAL LATER under observability owner: project sanitized events to Langfuse without double-counting SDK spans and journal exports. Do not enable full-payload telemetry, session persistence or an external tracing dependency for this task. |

The immediate reusable scope is cache policy and wire verification, accounting, redacted component measurement and provenance fields already owned by the runtime. Caller pacing/checkpoint enhancements are recommendations for existing owners, not hidden prerequisites or new implementation tasks. No Enterprise runtime modules are imported.

## K. Security / Governance / Observability

Only source excerpts permitted for external evaluation can leave the caller; no whole workspace, credentials, private docs or sensitive identifiers by default. MAF must not fetch omitted evidence itself. The judge receives no provider keys in the prompt; MAF-001 owns secret resolution. Do not save model reasoning traces. Local evidence may retain input/output under explicit evaluation policy; ordinary logs carry only safe IDs, status, timing, usage and version metadata. Distinguish provider failures/refusals/invalid schema from semantic UNKNOWN; no invented zero or PASS. Source-controlled prompt and schema revisions, not source document instructions, determine behavior.

Cache keys and breakpoints cannot grant source access, modify scope or elevate supplied data to developer authority. Keep 30-minute retention within approved public/synthetic egress; unknown retention policy blocks the affected caching mode. Avoid cache-hit probing across security scopes. Preserve safe IDs and hashes; never persist raw reasoning or credentials. Observability must not expose raw prompt contents or secret keys.

## L. Testing / Evaluation / Runtime Verification

Run independent Hatch checks under `apps/maf/`. Unit/contract tests for modes, input caps, required IDs, exact quote/range validation, unknown handling, role constraints, partial vs direct, missing references, no-answer scope, wrong version, injection, contradictory evidence, refusal/timeout and unknown usage. Fake runtime tests prove no RAG dependency and no outbound default. Perform real opt-in calibration with actual GPT-6.1 Sol via MAF, preserving per-control verdicts, expected values, mismatches and usage. Use original-source controls, not score agreement with the old agent alone. Validate the future answer-mode schema/controls with supplied fixture answers only, not a production generator. No real provider call in default CI.

For the cache amendment run `hatch run check`, `hatch run types`, `hatch run test`, both offline calibration preflights and the wheel build. Extend actual SDK mock transport tests for developer/user separation, exact reconstruction of all input values, stable prefix across changed suffix, mode/schema/profile/scope invalidation, no-breakpoint baseline, unexpected field rejection, admission caps after serialization, missing/malformed/read+write-overflow usage, cost formula and reasoning subset, and replay of old envelopes. Test each mode, zero-egress default and one physical call. Preserve the recorded 32-case manifest and acceptance gates. Execute the bounded cold/warm probe and final qualification/replay specified in J only with authorized real provider access and distinct reports; record actual requests, costs, checks, failures and stop reasons. Offline tests are not cache-hit evidence.

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

The qualification returned 31 validated verdicts from 32 requests, with 16/16 grade and support agreements, 1/1 expected `unknown`, 3/3 repeats and zero coverage overclaims. `answer-unsupported-citation` returned `INVALID_OUTPUT` at `evidence_validation`. The failed request still reported usage. The run's total was 38,730 input tokens and 11,685 output tokens, including 1,831 reasoning tokens. Estimated cost was USD 0.23504250. The critical and error gates gave `NO_GO`.

#### Answer prompt revision 2

`judge_answer/2` makes grounded completeness explicit. Every covered required fact must appear in a supported claim and have a supported fact assessment. A citation must use its supplied ID and quote only its cited excerpt. A separate development control uses an authored first-edition date and a citation that contradicts the answer. The development and qualification fingerprints are `28bbc82f8e7ba5ed74b7c7317c8e2c457dcd4046c3c80fe05e6cceb16372b3a8` and `3d69e0aa37d985681f28c1b9e918eed2f8b90e5cc30713f5c56299cabac986e2`. The qualification case manifest and gates remain fixed.

The final candidate is implementation `1b22301`, runtime `0.2.0` and `semantic-review` with `gpt-6.1-sol` at medium reasoning. It uses `derive_reference/1`, `judge_evidence/3`, `judge_context/1`, and `judge_answer/2` prompts, each with schema revision 1. All five development probes passed. In the frozen qualification run, the previous ambiguous attribution returned `unknown` and the incorrect invoice answer returned `incorrect`, `incomplete`, and an `unsupported` citation.

| Measure | Final qualification run |
| --- | --- |
| Validated verdicts and actual provider model | 31/32, `gpt-6.1-sol` |
| Determinate grade agreement and binary support | 16/16 for each |
| Non-evidence mode agreement | 11/12 |
| Critical controls and expected `unknown` | 16/16 and 1/1 |
| Repeatability | 2/3 exact category matches. All three repeat grades agreed. |
| Fact and required-quote checks | 30/30 and 3/3. All 31 accepted verdicts passed local quote and ID verification. |
| Coverage overclaims | 0 |
| Provider usage | 38,802 input tokens, 11,759 output including 1,943 reasoning, 0 cached input |
| Provider attempts and estimated Standard cost | 32 attempts, 0 retries, USD 0.23605450 before credits |

Two gates failed. `azure-answer-abstains` returned `INVALID_OUTPUT` at `evidence_validation`. The report retains its phase and usage without retaining the rejected model text. The English `azure-no-invoice-in-redundancy` and Ukrainian repeat both returned grade 0, with categories `irrelevant` and `topically_related` respectively. Both categories were allowed for that control. The declared exact-repeat gate still failed. Replaying the 32 saved envelopes offline reproduced the full scoring summary and independently rechecked all 31 accepted verdicts.

The v4 per-control verdicts, expected outcomes, exact-source quotes, and reported usage are saved locally in `apps/maf/calibration/live-report-rag-v4.jsonl`. That qualification decision was `NO_GO`. [Evaluation order](../quality/IMPLEMENTATION_ORDER.md)

#### Follow-up calibration for abstention and category repeatability

The local calibration report records a fixed `failure_reason` when an evidence validation rule rejects a verdict. The original v4 rejected JSON remains unavailable. A diagnostic replay on `judge_answer/2` reproduced the abstention failure in two of three calls with `complete_without_required_facts`. The rejected verdict claimed complete coverage even though the reference had no required facts. Its report records the code and usage with `output: null`. The EN and UK cases both returned `topically_related`, grade 0 in the old-prompt replay, so the earlier category difference did not recur on every call. The diagnostic replay is saved locally as `apps/maf/calibration/diagnostic-report-abstention-category.jsonl`.

`judge_answer/3` represents a pure abstention with `not_applicable` correctness and completeness, plus a separate abstention verdict. `judge_evidence/4` applies the same zero-grade rubric across languages. A candidate on the same subject with no answer support earns `topically_related`. An unrelated subject earns `irrelevant`. The separate development set includes an authored abstention and an EN/UK pair. The 32-case qualification manifest and gates remain fixed. The development fingerprint is `2e37b05854fba4e6bdbbc5f93da280a3fe3f14ebd058bd4eebb04b3d0152d85a`. The v5 qualification fingerprint is `915611533dcf56e5ed54d2f47356d56e0991a9a4d22d8fd63e60b7b8c6941cbe`.

All eight development probes passed. The live v5 run gave `azure-answer-abstains` an `appropriate` abstention with `not_applicable` factual completeness and correctness. The English and Ukrainian Azure controls both returned `topically_related`, grade 0. Exact repeatability was 3/3. One other control, `ruskin-reference-tracing-paper`, returned `INVALID_OUTPUT` at `output_schema`, which left the run at `NO_GO`. The v5 checkpoint recorded only the stage for schema errors. The local report is `apps/maf/calibration/live-report-rag-v5.jsonl`.

The v5 run accepted 31/32 verdicts, matched 15/16 critical controls and matched 16/16 determinate grades and support judgments. It made 32 requests with zero retries and recorded 39,531 input tokens and 11,611 output tokens, including 1,932 reasoning tokens. The estimated cost was USD 0.23643125 before credits.

Schema rejections now record a fixed reason and the declared top-level output field when available. A three-request diagnostic replay of the Ruskin control reproduced the failure once with `text_too_long` on `reference_answer`. The replay is saved locally as `apps/maf/calibration/diagnostic-report-ruskin-schema.jsonl`. The new derivation prompt keeps the reference summary concise and puts ordered procedural detail in the facts. Its new provider schema exposes the existing 600-character local bound through a supported string pattern. [Structured Outputs schema constraints](https://developers.openai.com/api/docs/guides/structured-outputs#supported-schemas)

The v6 development fingerprint is `1cb6f8a2d79037042d4aba927920d130777a98e9f68a3d9ad77305e8705256e7`. The v6 qualification fingerprint is `5cb5d0fb484c68117fbc290b3ad39dc806d7a31c363d567af892326e38613f4c`. The new derivation prompt and output schema are `derive_reference/2`.

#### v6 result and handoff

All nine development probes and all 32 frozen qualification requests passed with `gpt-6.1-sol`. The EN/UK pair matched on `topically_related`, grade 0. The scope-limited Azure refusal returned `appropriate`, `not_applicable` correctness and `not_applicable` completeness. The Ruskin reference summary used 348 characters and retained the tracing-paper and correction steps in its required facts.

| Measure | v6 qualification |
| --- | --- |
| Validated verdicts and all expected checks | 32/32 |
| Determinate grade and binary support agreement | 16/16 for each |
| Non-evidence mode agreement | 12/12 |
| Critical controls and expected `unknown` | 16/16 and 1/1 |
| Exact repeatability and complete-scope overclaims | 3/3 and 0 |
| Fact checks and required quote checks | 30/30 and 3/3 |
| Provider attempts and operational errors | 32 requests, 0 retries, 0 errors |
| Provider usage | 39,647 input tokens, 11,861 output including 2,519 reasoning, 0 cached input |
| Estimated cost | USD 0.23950025 before credits |

Ruff, strict mypy and all 106 offline tests passed on Windows and in a standalone Linux container with networking disabled. The `0.2.0` wheel built. Offline replay independently validated the 32 returned envelopes, checked the verifier output and reproduced the frozen scoring summary. The report with per-case results is saved locally as `apps/maf/calibration/live-report-rag-v6.jsonl`.

The qualified prompt revisions for DATASET-002 are `derive_reference/2`, `judge_evidence/4`, `judge_context/1`, and `judge_answer/3`. The output schema revision is 2 for derivation and 1 for the other modes. Use `semantic-review`, `gpt-6.1-sol`, and medium reasoning. This result qualifies the standalone judge on the frozen controls. DATASET-002 owns the three-family pilot and the OPEN audit. [Evaluation order](../quality/IMPLEMENTATION_ORDER.md)

### Bounded intake amendment — 2026-11-28

The first DATASET-002 pilot established a conflict between exact saved-input review and the v6 executable intake. Its 37 whole passages and nine ordered contexts need at most 10,476 CLI bytes, 15,431 admission units, and 10 context fragments. The full saved Ukrainian Azure context is a positive case for the new bounded intake. A thirteenth fragment and a request one byte over the transport ceiling remain negative boundary cases. [First pilot](../evidence/dataset-semantic-pilot-2026-11-27/report.md)

Runtime 0.3.0 widens the version 1 CLI ceiling to 16 KiB and the `semantic-review` input cap to 16,384. Only `judge_context` admits up to 12 fragments. The per-excerpt bounds, prompt and output schema revisions, semantic gates, validators, model, output caps, timeout, direct egress and zero retries are preserved. The explicit per-call budget must allow the new USD 0.067584 reserve. The calibration runner raises its reserve ceiling to USD 2.50, enough for all 36 allowed cases under the new input cap. The 32 frozen controls therefore reserve USD 2.162688. The historical v6 evidence is preserved.

Requalify on the identical 32 frozen controls and verify admitted and rejected intake boundaries before live pilot review. The replay binds the nine previously admitted independent references and submits all 37 saved pooled passages and all nine full ordered contexts with the same bytes and membership. The replay has a separate manifest and results. Reusing these references isolates the intake change from another reference derivation.

**Observed v7 qualification.** The frozen control hash remains `caa72c9408c4ab4a2066671524be825824addebbc5491b94fead1597c4b606cf`. The v7 calibration fingerprint is `f06974b1279c752f8c16f070ea1a6db2eb09ebf2240784e598d84e0ec58c5423`. All 10 development controls passed, including the full 12-fragment case that requires exact evidence from the final two entries. Qualification passed 32/32 validated cases, 16/16 critical controls, 3/3 exact repeats, and 30/30 fact checks. Both runs used `gpt-6.1-sol` with medium reasoning and recorded zero provider errors or retries. Estimated before-credit cost was USD 0.07311975 for development and USD 0.23895025 for qualification. The local reports are `apps/maf/calibration/development-report-rag-v7.jsonl` and `apps/maf/calibration/live-report-rag-v7.jsonl`.

### Output-cap amendment — 2026-11-28

The first full-input replay on v7 submitted the exact saved English Ruskin context and reached the provider. The provider returned `INCOMPLETE_OUTPUT` at exactly 2,048 reported output tokens. This exposes a second capacity boundary. The runtime accepted the entire input and lacked enough output allowance to finish the structured assessment. Preserve that attempt and its results.

Runtime 0.3.1 gives `semantic-review` a 4,096-token output cap with a USD 0.090112 per-call reserve. The CLI and input limits introduced in 0.3.0, 12-fragment context schema, prompts, output format, quote validation, default maximum spend, alternate profile, provider and retry policy are preserved. The frozen 32-case requalification reserves USD 2.883584 under a USD 3.25 runner ceiling, which covers the existing maximum of 36 controls. Requalify on the same controls and rerun the whole pilot under the amended cap with a fresh manifest. The saved English Ruskin context must complete at the new cap. Above-cap output remains a local budget error.

**Observed v8 qualification.** The v8 fingerprint is `eb6faa0198320869f3f6f8f73336ed653a78d9e5ef2fc84dea17ddb1cbd8dfe3`. The preserved 32-case manifest passed 32/32, with 16/16 critical controls, 3/3 exact repeats and 30/30 fact checks. Provider errors, retries and overclaims remained at zero. Estimated cost before credits was USD 0.24221725. The report is `apps/maf/calibration/live-report-rag-v8.jsonl`. [Full-input pilot](../evidence/dataset-semantic-pilot-full-2026-11-28/report.md)

### Output-cap alignment with Lead Engineer — 2026-11-28

User requests alignment with the working Lead Engineer ceiling in the earlier Enterprise AI Development Pipeline. The checked-in [workspace defaults at 955fd04](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/configuration/workspace.defaults.json#L25-L27) set `production_agent_output_tokens: 32000`. [Runtime execution selection](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/configuration/runtime_execution_selection.py#L64-L78) exposes that ceiling for cloud production execution. [NativeModelComposition](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/runtime/maf_model_composition.py) takes this value into the role options as `max_tokens`. The separate 16,000-token constraint is for Ollama local execution, not the cloud production setting; the non-production cloud default is 2,000. Its [native output budget](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/webapp/observability/native_output_budget.py) further constrains actual allowance by remaining ledger and tariff. Reuse the cloud numeric upper bound and admission principle, not that project's Azure client, role machinery or ledger. Operator-local overrides and actual long-output usage were not inspected.

Current runtime at `64087f2c63791d542016428a2592cb0c828909a4` uses `_REVIEW_MAX_OUTPUT_TOKENS = 4_096` in `apps/maf/src/agent_runtime/configuration.py`, `RunPolicy.max_cost_usd = 0.10`, calibration aggregate reserve ceiling 3.25, and existing wire/usage guards. v7 hit INCOMPLETE_OUTPUT at 2,048; v8 passed at 4,096. A 32,000 cap is preventive capacity, not evidence that v8 is broken.

Scope: change only the existing semantic-review profile to 32,000 output tokens including reasoning; keep alternate profile, 16,384 input admission units, CLI envelope, 128 KiB response limit, 45-second deadline, egress, retry and prompt/schema/rubric controls unchanged. Recalculate reserve using existing pricing: USD 0.397056 per call, USD 12.705792 for 32 controls, USD 14.294016 for the maximum 36. Amend the default per-invocation budget to USD 0.40 and runner ceiling to USD 15.00 (explicit live opt-in remains required; hard USD 1 per invocation unchanged). These are reservation ceilings, not expected actual spend; callers passing old explicit budgets must update or fail closed. Bump runtime package to 0.3.2. Keep bounded byte/time errors independent; do not promise arbitrary long responses or raise other limits without evidence. Preserve all historical reports.

Update existing configuration, calibration runner, package metadata, README, judge document, architecture notes, focused tests and release-note metadata. Test wire propagation and reported usage above 4,096, at 32,000 and above 32,000; reject insufficient reserve before egress and confirm frozen manifest/gates. Execute Hatch offline checks, new bounded live qualification on unchanged controls and replay identical full pilot with fresh manifests before adopting. No claim of PASS without actual evidence. If credentials/runner are unavailable, record qualification pending. The report projection belongs to ANSWERABILITY-001 Phase A; no change to MAF semantic states.

### Implementation record — 2026-11-28

The 0.3.2 candidate changes the existing `semantic-review` profile ceiling, the default invocation reserve and aggregate calibration reserve; the alternate profile, prompt/schema, existing frozen manifest controls and acceptance thresholds are unchanged. Tests now cover a full ordered wire request above the previous 4,096 output-token limit, usage at/over the new cap and pre-egress rejection at the old explicit spend ceiling. Offline and live checks, provider acceptance and a fresh full-input pilot remain pending; no new qualification is claimed. The caller must not adopt this configuration for full OPEN until it passes. Phase A diagnostic reporting remains assigned to ANSWERABILITY-001.

## M. Acceptance Criteria

- [ ] Cache policy and prefix layout are versioned and verified on the actual MAF SDK wire for all modes; no unauthorized role/data changes, no duplicate prompt or lost evidence.
- [ ] Cache-read/write/ordinary and output accounting distinguishes missing/invalid usage, preserves conservative reservations and does not double-bill reasoning.
- [ ] Bounded real probe demonstrates at least two warm reads on eligible stable prefixes, positive measured savings for the representative repeated workload, and separately reports the uncached baseline, cache writes, latency, coverage and semantic results; otherwise record cache NO_GO/NOT_EVALUABLE and qualify a no-cache configuration.
- [ ] Final candidate passes unchanged semantic gates and full-input replay, with cache/accounting/prefix fingerprints, actual usage and separate historical reports; no result-cache substitution.
- [ ] Legacy report/CLI compatibility, privacy, scope isolation and safe diagnostics verified. Reused Enterprise patterns and deliberate exclusions documented without introducing new services.


- [ ] 32,000-token ceiling, updated bounded reserves and unchanged independent guards verified by offline tests; alternate profile unchanged.
- [ ] New runtime fingerprint passes frozen live qualification and identical full-input pilot replay before adoption.


- [x] Semantic Judge registers four independent typed modes and runs without RAG dependencies or tools.
- [x] Strict results include facts, constraints, useful spans, exact references and `unknown`. A positive grade requires a quoted contribution to a required fact.
- [x] Reference derivation accepts original excerpts and declared scope. The other modes require a frozen reference. A complete-scope absence requires declared complete coverage.
- [x] The final revision passed the frozen calibration on 29 distinct controls and three declared repeats, including the three original regression families.
- [x] Offline checks passed. Live reports capture the actual model, prompt/schema revisions, denominators, disagreements, usage and cost.
- [x] A generic caller invokes the judge through the standalone version 1 JSON CLI.

## N. Documentation / Migration / Compatibility / Rollback

Document modes, examples, rubric, failure semantics and judge-version lifecycle inside the MAF app. No migration. Prior dataset scores are untouched by this implementation; DATASET-002 consumes a specific qualified judge revision to create a new local assessment. Disable the judge profile or switch to a separately qualified revision to roll back; never silently relabel old metrics or switch providers during a comparison.

For this amendment version the runtime and cache layout/accounting policy independently from semantic rubric changes; update strict consumer compatibility where required. Preserve the no-breakpoint configuration as a separately identifiable rollback candidate; requalify the chosen final configuration before adoption. Keep old reports and price revisions immutable. No cache purge service or persistent storage migration is required.

## O. Mandatory Completion Checklist

- [ ] Implement and verify the cache amendment, measured probe, accounting, wire/metadata compatibility, and final live qualification. Report cache adoption decision independently of semantic qualification.


- [ ] Complete output-cap amendment tests, fresh qualification and pilot replay; retain historical v8 result.

- [x] Reinspect MAF-001, the released provider API and source fixtures.
- [x] Implement typed source-grounded judge and deterministic validators.
- [x] Run independent offline tests and bounded live calibration. Record the measured result and limitations.
- [x] Verify package isolation, default egress denial and distinct failure and `unknown` outcomes.
- [x] Publish the contract, rubric, verification record and handoff conditions.
- [x] Qualify and record the judge revision for the DATASET-002 pilot.

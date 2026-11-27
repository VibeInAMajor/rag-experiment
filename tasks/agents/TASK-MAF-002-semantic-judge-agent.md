# TASK-MAF-002 — Source-grounded Semantic Judge Agent

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** PROPOSED — judge specification; no model qualified  
**Priority:** P0  
**Dependencies:** [MAF-001](TASK-MAF-001-independent-agent-runtime.md); source-grounded public/synthetic control cases from the existing evaluation corpus.  
**Repository snapshot inspected:** `d31eb5ca283523f90584a61c80ca6a90d6fccfe9`  
**Target:** `tasks/agents/TASK-MAF-002-semantic-judge-agent.md`  
**Architecture:** [MAF module boundary](MAF_ARCHITECTURE.md)

## A. Title

Implement and qualify a reusable MAF Semantic Judge Agent with structured source-first, reference, candidate and evidence-pack assessments, independent of retrieval infrastructure.

## B. Context / Problem

High Hit@K may coexist with many irrelevant chunks. In [DATASET-002 full report](../evidence/dataset-ranking-full-open-2026-11-26/report.md), judged precision@5 is 74.02%, @10 62.84%; 393 of 1241 pooled occurrences are labeled support, 622 negative, 226 primary. All positions were assessed by an agent, but 409 passing arithmetic/contract tests do not demonstrate correctness of every semantic grade. Manual review reported irrelevant or wrong-scope material for three queries. The public seed reference for Ruskin omits the tracing-paper check. A distinct evaluation model must verify actual question constraints and evidence, not just topical similarity or old labels. Do not claim all old judgments are wrong before re-audit.

## C. Current Repository State

- [DATASET-002](../quality/TASK-RAG-DATASET-002-source-grounded-ranking-judgments.md) preserves full OPEN pooled grades and immutable captures, with local raw source/candidate judgments and existing review UI. No qualified reusable semantic judge exists in the checked-in tree.
- [Existing full report](../evidence/dataset-ranking-full-open-2026-11-26/report.md): 102 families, 306 EN/RU/UK questions, 31 original documents, 634 chunks; no generation or sufficiency decisions. Exhaustive Recall/nDCG remain not evaluable.
- [Literature questions and references](../quality/dataset/answers/MATHEMATICS_ART_LITERATURE_V1.md): EXT-LIT-001 requires the initial Netherfield rental and reported annual income; verify against [Austen original](../quality/dataset/corpus/literature/austen-chapters-01-05.md#L16-L46), not every mention of Bingley. A later passage can be useful if it actually proves the initial event; chapter number alone is not a relevance rule.
- EXT-NA-003 in [no-answer reference](../quality/dataset/answers/NO_ANSWER_V1.md#L17-L19): no exact invoice-birch-902 monthly EUR amount in frozen corpus. Storage redundancy is not supporting evidence for a bill.
- EXT-ART-003 in [seed reference](../quality/dataset/answers/MATHEMATICS_ART_LITERATURE_V1.md#L59-L61): compare the [original procedure](../quality/dataset/corpus/art/ruskin-first-practice.md#L185-L204), including tracing-paper comparison and correction, with the seed answer. Latest ignored local reference may differ; verify it instead of presuming the omission persists.
- [Reranking README](../../apps/workbench/reranking/README.md): standalone Qwen3-Reranker-0.6B is deployed by config, not integrated/qualified. It ranks candidates; cannot be its own sole judge.
- Official [MAF Responses client](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/openai), [structured outputs](https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs), [OpenAI Sol model](https://developers.openai.com/api/docs/models/gpt-6.2-sol). Runtime versions and actual model access are qualified in MAF-001.

## D. Goal

Return reproducible, validated semantic verdicts with direct evidence quotes, explicit constraint checks, fact support and unknown/error states. Demonstrate that the judge distinguishes direct answers from related-but-useless content, detects omitted reference facts and respects no-answer scope. Use the same generic agent contract for future consumers, without any RAG dependency.

## E. Scope

One reusable semantic judge with separate stateless assessment modes; versioned typed prompts/results; deterministic validation of supplied source/candidate quotes and identifiers; controlled model quality qualification; optional future answer-mode contract (no fabricated generation measurements).

## F. Non-Goals

No retriever, reranker, search tool, database access, document crawler, gold mutation, corpus management, metric aggregator, Workbench import, new UI/server, persistent sessions, autonomous loop, extra agents or manual-reviewer prerequisite. Do not use judge as runtime answerability policy here. No full OPEN audit in this task; DATASET-002 owns that orchestration.

## G. Architecture / Boundaries

- [x] Domain / core — provider-neutral rubric, schemas and validation.
- [x] Application / orchestration — independent judge modes through runtime port.
- [x] Port / interface / contract — typed semantic judgment payload and result.
- [x] Provider adapter — reuse MAF-001; no direct SDK calls in judge.
- [ ] Persistence / vector store — N/A; caller owns storage.
- [ ] Retrieval / RAG — N/A; caller supplies evidence.
- [x] Agent runtime — one MAF agent definition with stateless invocations.
- [x] Security / governance — authorized inputs only, no tool instructions.
- [x] Observability / evidence — versioned verdicts, rationale and usage metadata.
- [ ] Infrastructure / CI/CD — N/A beyond independent MAF checks.
- [x] Documentation — rubric, contracts and qualification report.

Application receives bounded text units with opaque IDs and supplied locators. It does not know Workbench query ID conventions, filesystem paths, source DB records, ranking profile, provider identity or model name. Generic semantics (entity, requested value, time/event, version, procedure, comparison, scope) are extensible, not domain-specific runtime routing.

## H. Contracts / Interfaces / Data Model

Use MAF-001 envelope and a versioned `SemanticJudgeRequest` discriminated by mode. Proposed modes:

| Mode | Input | Output |
| --- | --- | --- |
| source_assessment | question, language, authorized source text units, caller-verified coverage declaration | answerability (answerable / no_evidence_in_supplied_scope / ambiguous / incomplete_scope), required atomic facts, exact evidence references, constraints, qualified reference answer, uncertainties |
| reference_audit | independently derived source assessment, original supporting source units, old reference facts/answer | supported/missing/unsupported/contradicted facts, required corrections and evidence references |
| candidate_assessment | question, verified facts/constraints, candidate text, optional authorized source context clearly distinguished | relevance class, supported fact IDs, constraint outcomes, exact candidate quotes, contradiction flags, concise rationale |
| context_assessment | question, verified facts/constraints, actual selected evidence units | sufficient/partial/insufficient/conflicting/unknown, supported/missing fact IDs, useful and irrelevant ranges, conflict details, precise evidence references |
| answer_assessment (future consumer) | actual generated answer, question, exact context, original evidence and verified facts | claim-level correctness/faithfulness, required facts, unsupported claims, citation support; only score actual answers |

EvidenceRef contains opaque input unit ID and exact quote, plus validated local range (Unicode code point half-open interval if unique/explicit). Caller maps to original source version/line/hash. The model cannot invent IDs or locators. Quote matching and schema validation are deterministic; repeated ambiguous quotes require disambiguation or UNKNOWN. Mark inferred or disputed propositions, not as observed. Each material claim/constraint is independently classified as supported, contradicted, missing, not_applicable or unknown. Rationale is concise and evidence-based, not hidden chain-of-thought.

Candidate relevance taxonomy (keep distinct even when mapped to the same numeric grade):
- DIRECT: explicitly supports at least one complete required fact in correct question scope, grade 3.
- PARTIAL / NECESSARY_SUPPORT: demonstrably contributes a required sub-fact or essential relation; grade 1. Do not award support for broad background or topical overlap.
- TOPICAL_ONLY / IRRELEVANT / WRONG_SCOPE: grade 0; wrong entity, temporal event, amount/currency/unit, version, chapter scope, negation or requested relation recorded as reason.
- CONTRADICTORY: grade 0 for misleading evidence against established scoped fact; record separately. Actual conflicting authorities relevant to a conflict question are judged under its declared rubric, not automatically discarded.
- UNKNOWN: no grade; unresolved, not a negative.

A multi-span unit can require a union. Do not award complete single-chunk credit for a fact established only by other supplied units; candidate quotes must support the candidate's own contribution. Context usefulness refers to selected text, not the gold union. Do not equate model confidence with probability or report false acceptance from raw candidate presence. Errors/refusal/incomplete source scope must be separate from semantic negative/no-answer.

## I. Repository Files / Components Impacted

Create within `apps/maf/src/maf_runtime/agents/semantic_judge/` the minimum contracts, versioned instructions and agent composition needed; reuse runtime and adapter from MAF-001. Add module-local tests and small public/synthetic controls, README/architecture links. Do not copy RAG evaluator or source loaders into MAF. Existing ignored local evaluation runner is extended only in DATASET-002. No changes to production Workbench, retrieval API, PG schema, embedding or reranking configuration.

## J. Implementation Requirements

1. Implement typed modes with strict native structured outputs and local Pydantic validation. Use explicitly pinned prompt/rubric and schema revisions. All modes use fresh context/session and no tools; do not feed previous candidate grades, ranks, model scores, arm identity or previous judge answer to a source-first call. Reference audit sees old reference only after independent source assessment is saved. Candidate/context passes receive verified reference facts and question constraints; no external knowledge as evidence.
2. Extract question intent and explicit constraints, including requested object/entity, relation, time/event, version, numeric value/unit/currency, negative qualifier, requested procedure and all multi-part requirements. Return exact evidence and atomic facts. Reject reference omission, unsupported additions and false scope matches. If a whole authorized corpus cannot be sent, caller supplies deterministic verified source windows/coverage; model marks incomplete scope instead of claiming universal absence. For no-answer decisions distinguish missing evidence from technical failure.
3. Validate every verdict: known IDs, valid quote/range within provided text, fact/constraint references, class/grade consistency, no direct grade for incomplete or wrong-scope claim, no source-supported claim based solely on old reference or candidate. Reject malformed/inconsistent output; bounded retry only under configured policy, otherwise UNKNOWN/error. Positive evidence must be auditable; schema-valid JSON alone is not semantic proof.
4. Build frozen qualification controls before model runs, using original excerpts and deterministic synthetic contrasts. Include all three reported question families and translations, tracing-paper omission, wrong annual income, same actor wrong event, late passage with explicit retrospective proof, same-term wrong entity, storage redundancy distractors, wrong invoice/currency, true no-answer, incomplete source scope, negation, unit mismatch, procedure order, partial/multi-span evidence and prompt injection embedded in text. Include correct/incorrect candidate variants, short/long text, plausible but irrelevant context, and real conflicts. Do not use the target retrieval system to author reference truth. No hard-coded fixture IDs or answers in production prompt.
5. Start with proposed 36+ distinct control scenarios across classes (translations tracked as correlated), predeclare actual sample and acceptance before calls. Use disjoint prompt-development and qualification controls; run real configured model against frozen controls and a bounded repeat subset in fresh contexts with order shuffled. Report exact class/grade agreement, direct/support false-positive counts, missed evidence, constraint error rate, source-quote validation rate, repeated agreement and UNKNOWN/error coverage. Initial proposed acceptance: >=90% exact coarse grade/class agreement on assessed controls, >=95% binary answer-support agreement, zero falsely accepted mandatory wrong-scope/invoice/negation controls, zero invalid positive evidence references, all three anchor cases correctly explained. Report denominators including refusal/unknown; incomplete or unsupported gate is NO-GO/NOT_EVALUATED. These are local starting gates, not universal judge accuracy guarantees. Ratify before run, not after seeing output.
6. If disagreement persists, record error examples, improve rubric on development controls only and requalify on new held-back controls. Optionally compare a separately configured stronger model on contested cases; never assert a second call is independent human truth. A disagreement stays unresolved until supported by source evidence. Retain historical decisions rather than silently relabeling. Model profile default proposed `gpt-6.2-sol`, medium reasoning if available; record actual provider/model, settings, prompt hash, input/output schema and usage. No assumption of deterministic outputs even if configuration fixed.
7. Actual OPEN audit is a separate DATASET-002 run after judge qualification. Output proposals only: the caller validates original locator and chooses revision admission. Judge never updates gold, metrics, files, ranking profile or calls RAG. Existing local UI/runner remains the only integration caller; no additional service required.

## K. Security / Governance / Observability

Reuse MAF-001 egress, explicit live budget and credential rules. First calls use public licensed or synthetic material only; user-described invoice is a synthetic identifier, do not send real billing data. Treat excerpts/questions as untrusted; never follow embedded instructions or call tools. No internet search, index access, shell, network fetch or persistent conversation through agent. Log only safe identifiers/status/revisions/usage/time; store detailed outputs in ignored local artifacts. No model reasoning traces, customer payload logging or automatic promotion. Provider storage/retention caveat remains explicit.

## L. Testing / Evaluation / Runtime Verification

Module-local Hatch check/test/types. Unit and contract tests with fake runtime for every mode, grade mapping, required-fact and quote mapping, duplicate/unknown IDs, wrong scope, incomplete sources, refusal, malformed output, prompt injection and no tools/SDK import in judge. Verify fixed envelope cross-process with no RAG installed. Run actual opt-in MAF/OpenAI controlled qualification, repeat subset and report confusion matrix, cost, failure categories and model identity. Keep local source-controlled fixture content permitted; full OPEN run is outside this task. No external reviewer requirement or mock-as-live claim.

## M. Acceptance Criteria

- [ ] One independent semantic judge runs via MAF runtime JSON contract, with source/reference/candidate/context modes.
- [ ] Separate typed verdicts, evidence quotes, constraints and UNKNOWN/error semantics validated; no old ranking or gold leakage into source pass.
- [ ] Three reported cases and contrast controls pass declared qualification; real model accuracy, repeatability and failures recorded, or explicit NO-GO.
- [ ] Provider profile is configurable, no retrieval/RAG access or direct imports; fake and real adapter share contract.
- [ ] All applicable tests pass and actual API smoke/qualification evidence linked before downstream use; no quality claim if model/credential/budget unavailable.

## N. Documentation / Migration / Compatibility / Rollback

Version rubric/prompt/result schema; keep prior revisions and evidence. No DB migration. Disable external judge or use offline fake for tests without affecting RAG; downstream metrics retain provisional status if judge unavailable. Future answer assessment builds on same contract, no separate engine.

## O. Mandatory Completion Checklist

- [ ] Reinspect actual MAF-001 implementation and existing evaluation artifacts.
- [ ] Implement schemas, instructions, validations and standalone invocation.
- [ ] Freeze controls and run actual bounded model qualification.
- [ ] Record tests, usage, model settings, limitations and GO/NO-GO.
- [ ] Hand validated contract to DATASET-002; never mark COMPLETE/live-qualified without evidence.

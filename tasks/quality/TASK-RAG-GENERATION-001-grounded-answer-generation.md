# TASK-RAG-GENERATION-001 — Implement grounded answer generation over qualified evidence context

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** BLOCKED — retrieval quality GO required  
**Priority:** P1  
**Dependencies:** [QUALITY-002](TASK-RAG-QUALITY-002-retrieval-release-gate-and-regression.md) GO, [EVIDENCE-002](TASK-RAG-EVIDENCE-002-bounded-context-and-required-facet-coverage.md), [ANSWERABILITY-001](TASK-RAG-ANSWERABILITY-001-insufficient-evidence-and-abstention.md); separately qualify local generation model and shared hardware budget.  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-GENERATION-001-grounded-answer-generation.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Implement grounded answer generation over qualified evidence context

## B. Context / Problem

Finding evidence is necessary but does not prove that a model can synthesize a complete correct answer. Generation should consume only qualified context and abstain when insufficient.

## C. Current Repository State

[actual Dense evidence](../../tasks/evidence/dense-2026-11-24/report.md) explicitly excludes answer generation; [API contracts](../../apps/workbench/contracts/schemas.py) and [projection](../../apps/workbench/api/projection.py) return search results, not answers. [haystack/components/rankers/llm_ranker.py](../../haystack/components/rankers/llm_ranker.py) is not a generation runtime. Existing TEI capacity is embedding-only; no generation throughput qualification established.

## D. Goal

Provide a separate approved grounded-answer composition with factual citations, bounded context/output and explicit no-answer behavior.

## E. Scope

Provider-neutral generation port/profile, locally qualified model adapter (Ollama candidate subject to actual model/runtime test), grounded prompt, source citation validation, bounded API/Live view and error semantics.

## F. Non-Goals

No internet retrieval, agentic tools, fabricated citations, general model authority, silent fallback, new vector store or enterprise scale.

## G. Architecture / Boundaries

Application consumes EVIDENCE-002 pack and ANSWERABILITY decision; model adapter owns inference. Server validates citations against authorized context; evidence text remains untrusted. Keep retrieval endpoint compatible.

## H. Contracts / Interfaces / Data Model

Versioned generation policy/model, prompt revision, tokenizer/context/output budget, answer status, cited evidence IDs, request/trace IDs and stage timing. Citation validation proves existence/identity, not factual support (QUALITY-003).

## I. Repository Files / Components Impacted

Inspect current Haystack chat generator interfaces and existing API/app ownership; use existing profile, boundary, projection and UI patterns. Add minimal logical generation module and contract, no upstream framework modifications.

## J. Implementation Requirements

1. Qualify pinned local generation model and actual context tokenizer/capacity on shared RTX 4090 with embedding/reranker resources; do not assume embedding TPM covers generation. Measure actual context/output and contention, explicit stop conditions.
2. Use only authorized bounded context. Insufficient/conflicting evidence produces explicit abstention or qualified conflict explanation; transport failures remain typed errors. Grounded instructions require citations for factual claims and admit missing facets, not use model memory as source.
3. Validate citation IDs against actual context and source/version; reject fabricated citations or unsafe output. No document instruction changes tool/authorization. Enforce deadlines/cancellation and no automatic cross-provider fallback.
4. Integrate separate approved answer capability with actual model and UI trace, preserve raw retrieval as independent feature; only activate after QUALITY-003 release gate, not just model smoke.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

No untrusted content in system role; no external calls or secrets, sanitize UI output and citations.

## L. Testing / Evaluation / Runtime Verification

Real local model smoke, citation ID validation, multi-facet and no-answer, prompt injection, conflict, missing/invalid evidence, GPU contention/cancellation and retrieval regression.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] Pinned local model and bounded resource proof.
- [ ] Actual answer composition, valid source citations and explicit abstention/error behavior.
- [ ] No claim of factual correctness from citation-ID check; release blocked until QUALITY-003 GO.

## N. Documentation / Migration / Compatibility / Rollback

Additive answer capability and profile; disable without changing retrieval, corpus or vectors.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.


## QUALITY-001 failure-localization evidence

QUALITY-001 OPEN V2 handoff (2026-11-25): generation and answer correctness are NOT_EVALUATED. The eight arms measure sparse reviewed source-facet coverage, not generated answer accuracy or hallucination rate. Preserve separate Primary Evidence Hit NOT_EVALUABLE when no separately judged primary label exists, and do not turn no-answer neighbors into fabricated generation failures.

Evidence: [V2 report](../evidence/quality-2026-11-25/report.md). Raw per-query IDs, locators, alternative sets and next probes remain in the ignored existing V2 run; sanitized counts are in metrics.json → failure_localization.
## QUALITY-001 UI completion evidence — 2026-11-26

The measured Markdown pair provides all reviewed source facets in the fixed context on 226 → 240/261. Treat the remaining gaps and automatic sparse gold as explicit generation inputs/limits; no generated-answer accuracy or faithfulness measurement exists. Generation remains NOT_EVALUATED.

Evidence: [completed UI comparison](../evidence/quality-2026-11-25/report.md); metrics.json → ui_completion. Raw case details remain ignored locally.

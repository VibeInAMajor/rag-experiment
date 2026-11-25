# TASK-RAG-GENERATION-001 — Implement grounded answer generation over qualified evidence context

**Created:** 2026-11-24  
**Updated:** 2026-11-26  
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

### Structured source-grounded answer input/output — 2026-11-26

Adapt the [quality/content plan](RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md) evidence formatting concept: stable evidence IDs, source/version/locator and observed/inferred status in bounded context, material claim citations returned as structured IDs resolved by backend. Never require model-generated URLs or source positions, expose reasoning traces, or cap all answers to an arbitrary three sentences. Preserve sufficient/partial/conflict behavior and validate IDs. Save exact context/prompt/model revision and output safely for QUALITY-003's Faithfulness-Plus, claim-chain and NAG scoring. Reuse existing model-neutral adapter ownership.

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

- [ ] Actual answer context and citation IDs are reproducible, bounded and verified; no generated URL or fabricated locator; QUALITY-003 inputs retained.

## N. Documentation / Migration / Compatibility / Rollback

Additive answer capability and profile; disable without changing retrieval, corpus or vectors.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

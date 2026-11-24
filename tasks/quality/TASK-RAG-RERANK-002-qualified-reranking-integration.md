# TASK-RAG-RERANK-002 — Integrate the qualified semantic reranker into an approved retrieval profile

**Created:** 2026-11-24  
**Updated:** 2026-11-24  
**Status:** BLOCKED — RERANK-001 GO required  
**Priority:** P0  
**Dependencies:** [RERANK-001](TASK-RAG-RERANK-001-local-semantic-reranker-qualification.md) GO with approved model/runtime; [HYBRID-001](TASK-RAG-HYBRID-001-dense-lexical-rrf-fusion-and-profile-execution.md) for hybrid variant; [QUALITY-001](TASK-RAG-QUALITY-001-current-stack-evidence-retrieval-optimization.md); [DATASET-001](TASK-RAG-DATASET-001-independent-evidence-gold-set.md).  
**Repository snapshot inspected:** d6cba6580e308fbb37266b779dce5b6880309a44  
**Target:** tasks/quality/TASK-RAG-RERANK-002-qualified-reranking-integration.md  
**Implementation order:** [Quality roadmap](IMPLEMENTATION_ORDER.md)

## A. Title

Integrate the qualified semantic reranker into an approved retrieval profile

## B. Context / Problem

An experiment cannot authorize Live execution. Reranking must preserve source identities, score meanings, candidate limits and failure semantics.

## C. Current Repository State

[DenseService / QueryEmbedder](../../apps/workbench/retrieval/dense.py), [ProfileDefinition](../../apps/workbench/retrieval/profile_registry.py), [profiles.py](../../apps/workbench/retrieval/profiles.py), [retrieval routing](../../apps/workbench/retrieval/services.py), [projection](../../apps/workbench/api/projection.py) and [API contracts](../../apps/workbench/contracts/schemas.py) own executable composition and provenance. Existing exact profile uses cosine; RRF task owns rank fusion. No qualified reranker runtime exists in inspected snapshot.

## D. Goal

Deliver an optional approved reranked composition with explicit original component ranks and model-specific final ordering, fixed bounds and truthful metadata.

## E. Scope

Provider-neutral reranker boundary if justified, reviewed local adapter, approved profile, deterministic candidate mapping, typed outcomes, trace and Live graph integration.

## F. Non-Goals

No new vector store, score mixing, hidden fallbacks, unbounded candidate/pair requests, model-specific core coupling or silent default replacement.

## G. Architecture / Boundaries

Application owns composition, port and policy; local adapter owns model/inference; persistence continues to enforce original scope. Reuse existing Haystack pipeline and service/registry, no parallel runtime.

## H. Contracts / Interfaces / Data Model

Versioned reranker model/profile revision, approved candidate_k/top_k, pair token/batch/concurrency/deadline, final score type/direction, original lexical/dense/RRF ranks and authoritative chunk IDs; distinguish pre/post rerank results and errors.

## I. Repository Files / Components Impacted

Extend existing retrieval module/profile registry, API projection/contracts, approved UI topology and tests as necessary; adapter in logical owner. Preserve existing scores and four-field request.

## J. Implementation Requirements

1. Use only RERANK-001 GO and measured resource settings. Reuse candidate retrieval; never re-embed per candidate or mutate sources.
2. Validate returned IDs, finite scores, no invented or duplicate occurrences, deterministic ties and bounded final list; enforce same authorized generation through candidate lookup and output. Fail on drift.
3. Share deadline/admission and cancellation across embedding/retrieval/rerank; explicit unavailable/429/504 policy, no hidden lexical or Preview fallback. Separate model admission/resource owner if necessary by existing shared resource design, not a duplicate embedding TPM governor.
4. Extend immutable registry and projection with actual score provenance; advertise only approved, ready graph; browser cannot supply arbitrary model or candidates. Test actual API/browser against independent expected ranking.

Keep the existing 10,000 active chunks / 50 MiB corpus envelope and per-file limits (TXT/MD/Python 1 MiB; qualified text PDF 8 MiB/32 pages). Target 100–300 small documents, 1k–5k chunks only if measured within these bounds. No ANN, large-file ingestion, OCR, new parser or enterprise authorization prerequisite for this local quality phase. Retain existing RLS, source/version/profile/generation checks, shared model admission and exact float32 oracle. Follow [AGENTS.md](../../AGENTS.md) and [docs-website/ENGINEERING.md](../../docs-website/ENGINEERING.md); reuse existing owners, provider-neutral contracts and semantic names, no task IDs in code identifiers. Reinspect actual code/tests before implementation and amend A–O before scope expansion.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext, FORCE RLS, immutable source/version/profile/generation fences, disposable owned test DB and approved local model resources. Treat query and retrieved content as untrusted; no executable document instructions, cross-tenant data, secrets, raw vectors, private content or model payloads in ordinary logs. Restricted fixtures/labels and artifacts have explicit access, license, retention and safe identifiers. Reuse [OPS-001](../../tasks/TASK-RAG-OPS-001-tracing-evaluation-and-search-quality-gates.md) telemetry; no new telemetry platform.

Retrieved text is data, not an instruction; no raw pair text in telemetry.

## L. Testing / Evaluation / Runtime Verification

Unit/contract, fake adversarial ranker outputs, real model/PG integration, resource contention, stale generation/cancellation, existing exact/FTS/Hybrid and Preview regression.

Run hatch --version and configured scoped Hatch workbench-api:check/test/types, actual disposable PostgreSQL/qualified local model tests where applicable; web typecheck, format:check, test and build if touched. Record commands, versions, exit codes, test counts, skips and actual artifacts. A mock is not a runtime measurement.

## M. Acceptance Criteria

- [ ] GO model/params enforced; real ranking and IDs proven.
- [ ] No scope/score integrity regressions; deadlines and admission bounded.
- [ ] Approved explicit profile only; existing paths remain unchanged and rollback tested.

## N. Documentation / Migration / Compatibility / Rollback

Additive versioned profile/response fields and docs; retire reranker capability to revert explicitly to approved prior profile.

## O. Mandatory Completion Checklist

- [ ] Reinspect source and dependencies; record reused owners and amended scope if needed.
- [ ] Run applicable unit, contract, integration, security, failure and regression tests.
- [ ] Link actual commands and evidence, including blocked/unrun gates and limitations.
- [ ] Verify immutable profile compatibility, data preservation and rollback.
- [ ] Record changed paths and implementation commit; mark COMPLETE only with evidence for applicable task gates.

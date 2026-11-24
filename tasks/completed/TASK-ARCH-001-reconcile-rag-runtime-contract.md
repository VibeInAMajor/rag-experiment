# TASK-ARCH-001-reconcile-rag-runtime-contract

**Created:** 2026-11-20  
**Updated:** 2026-11-24  
**Status:** COMPLETE  
**Priority:** P0 · prerequisite  
**Dependencies:** None  
**Repository snapshot reviewed:** `5e7086364f62d4f15b7370e55767a8f84ed4dc14`

## A. Title

Reconcile the canonical RAG runtime choices and integration contract

## B. Context / Problem

The reference architecture and the Workbench README describe incompatible storage and embedding choices. Integrating the UI by simply mapping its visual `component` strings to Python classes would create provider-coupled code and false runtime behavior. A single source of truth is required before durable adapters are implemented.

## C. Current Repository State

Current working-tree evidence inspected on 2026-11-20 (the reviewed commit above plus the earlier validation-only implementation):
- The original architecture selected OpenSearch + PostgreSQL + Ollama embeddings. It is now retained as an explicitly superseded historical appendix in the dated plan; its current section points to the canonical contract.
- `apps/workbench/web/README.md` points to the canonical PostgreSQL+pgvector/TEI contract and separates preview, construction validation and planned live retrieval.
- `apps/workbench/web/src/domain/catalog.ts` contains `OpenAITextEmbedder`, `OpenAIDocumentEmbedder`, `InMemoryBM25Retriever` and `PgvectorEmbeddingRetriever` display labels in simulated graphs; labels do not select providers.
- `apps/workbench/web/src/domain/graph.ts` serializes *Workbench* JSON (`schemaVersion: 1`), not an executable Haystack pipeline. `graph.test.ts` covers round-trip fidelity, incomplete drafts, strict fields, invalid imports and preview-only restrictions.
- `apps/workbench/validator/registry.py`, `validator.py` and `README.md` implement a real construction/connection/input validation boundary, without execution. A general claim that no backend or API client exists is no longer accurate. No RAG execution, ingestion or persistent registry API exists.
- Haystack's in-memory store/retriever source confirms BM25L, raw score semantics, lexical tokenization and instance-local stores. The current splitter defaults to tiktoken `o200k_base`, not a qualified Qwen tokenizer.

## D. Goal

Publish a reviewed, implementation-oriented single contract that distinguishes the immediate BM25-only integration slice from decisions for durable indexing, embeddings, and future generation.

## E. Scope

1. Record the canonical storage backend and a separate metadata/version registry choice.
2. Record the embedding transport (Ollama, TEI, or adapter-enabled alternatives), model profile, expected dimension, tokenizer strategy and which facts require a live probe.
3. Specify the minimum API v1 request/response/error schemas, supported capability profiles, and when the UI must reject a graph.
4. Record exact meanings of a live run, a preview run, source identity, scores, stage timing, run IDs and trace IDs.
5. Update the existing plan and Workbench README for consistency without losing historical architecture decisions.

## F. Non-Goals

Do not install databases, invoke an embedding model, implement routes, port Delta Detector/TPM controller, or introduce an arbitrary graph interpreter. Do not silently change the agreed model runtime merely to match existing UI labels.

## G. Architecture / Boundaries

Affected: Documentation; Port/interface/contract; Application/orchestration; Provider-adapter capability decisions; Security/governance; Observability/evidence. Core/domain and external providers remain unchanged. Dependencies must point from future adapters toward app-owned neutral interfaces, not from the application core to provider SDKs. Add abstractions only for actual substitution/test seams.

## H. Contracts / Interfaces / Data Model

Define a versioned, provider-neutral API contract for:
- `GET /api/v1/health/live`, `GET /api/v1/health/ready`, `GET /api/v1/capabilities`.
- `GET /api/v1/workspaces`, `GET /api/v1/workspaces/{workspace_id}/documents`.
- `POST /api/v1/workspaces/{workspace_id}/search` with `query`, `top_k`, `profile_id` and a typed response with `run_id`, `trace_id`, `status`, `duration_ms`, `results[]` (`chunk_id`, `source_id`, `title`, `page?`, `content`, `rank`, `score`, `score_type`).
- Errors with stable code, user-safe message, `trace_id`, retryability and HTTP status.
- Capabilities listing only executable approved profiles, their parameters/limits, and backend revision. `profile_id` identifies a backend-approved execution profile, not a provider/model name.
No client-provided graph JSON may be executed as raw Python/YAML deserialization.

## I. Repository Files / Components Impacted

Expected: `docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md`, `apps/workbench/web/README.md`, a small new decision/contract `.md` file under `docs-website/docs/`, and `docs-website/sidebars.js` if navigation is needed. Must NOT modify `haystack/`, frontend component implementations, or unrelated documentation in this task. Keep `AGENTS.md` concise, linking rather than embedding the detailed rules.

## J. Implementation Requirements

MUST cite actual existing files and identify contradictions explicitly. MUST separate confirmed observations from pending runtime measurements. MUST define one real BM25-only first slice and defer unsupported templates. MUST keep a portable profile interface for eventual providers. MUST NOT introduce task-number prefixes in production variable, type, function or method names. MUST reuse graph validation and existing domain structures rather than duplicate them.

## K. Security / Governance / Observability

Secrets are never in schema examples, tasks, logs or traces. API contracts must state that workspace identity and data access are decided server-side, not from user-edited UI Settings or filters. `source_id`, version and permissions must remain authoritative server state. Define logging redaction, request/trace IDs and retention policy responsibility. Document that the initial single-workspace dev slice is **not** production multi-tenant security.

## L. Testing / Evaluation / Runtime Verification

Review current `apps/workbench/web/src/domain/graph.test.ts` to preserve graph import/export behavior; add a schema/contract validation check to the eventual API task. Check every referenced path and link. No runtime pass can be reported from documentation-only analysis. Repo-level Python verification remains Hatch-based; commands for future code must be repo-path-correct, not blindly copied from a generic `src tests` layout.

## M. Acceptance Criteria

- [x] One canonical decision record explicitly resolves or records as *open* the search backend, embedding endpoint, tokenizer and vector size; no contradictory present-tense claims remain in active docs.
- [x] API contract defines at least five concrete read/health/search endpoints with types and errors.
- [x] Exactly which UI graph/profile runs live in the first slice is documented; unsupported graphs are rejected.
- [x] No runtime results are claimed as measured without a logged run.
- [x] No provider SDK imports or hard-coded vendor/model identifiers are mandated inside application-core contracts.

## N. Documentation / Migration / Compatibility / Rollback

Documentation-only change. The current visual fixture graph format remains `schemaVersion: 1`; no migration required. Keep an explicit deferred decision log for the selected persistent backend if probing remains necessary. Rollback is reverting the documentation/contract change; downstream implementation tasks MUST be updated first if the contract changes.

## O. Mandatory Completion Checklist

- [x] Section C cites current files and actual observed conditions.
- [x] Implementation contract and architecture boundaries reviewed.
- [x] Measurable acceptance points verified and evidence linked.
- [x] Relevant docs/README aligned, with unresolved items marked.
- [x] No change outside the declared documentation scope.
- [x] Status changed to COMPLETE **only** after all applicable gates and review evidence are recorded.

### Completion evidence — 2026-11-20

Deliverables:
- [Canonical runtime/API contract](../../docs-website/docs/architecture/rag-runtime-contract.md): six endpoints, strict request and typed response/error definitions, capabilities/revision handshake, exact `bm25-v1` graph eligibility, score/provenance/run/timing semantics, server-owned authorization, redaction and retention responsibilities.
- [Dated plan](../../docs-website/docs/tasks/RAG_MVP_Architecture_Implementation_Plan_EN_2026-11-19.md): active reconciliation plus preserved historical v1.1 appendix. PostgreSQL owns the corpus from the first live slice; true BM25 is transient derived state. TEI/2560, tokenizer qualification and generation deferral are explicit.
- [Workbench README](../../apps/workbench/web/README.md): current runnable behavior remains preview/validation only; planned live search is separate. Graph schema version 1 is unchanged.
- Documentation navigation in `docs-website/sidebars.js`; narrow RAG boundary corrections in [engineering guidance](../../docs-website/ENGINEERING.md) and [project map](../../docs-website/PROJECT_MAP.md) prevent those routers from denying the existing validation-only API/client.

Reuse reviewed: existing graph import/export and structural checks; catalog node/parameter/handle definitions; constructor validator and its separate capability revision; core BM25 store/retriever and public Pipeline APIs. No duplicate graph parser, runtime interpreter or provider interface code was added.

Independent agent review covered runtime/source accuracy, Workbench compatibility, API/security completeness and documentation consistency. Corrections incorporated: `results.limit` must equal BM25 `topK`, discovery-to-execution profile revision handshake, deterministic chunk-ID load order for BM25 ties, and PostgreSQL-backed corpus ownership before first live search.

Verification passed: MDX compilation with GFM for six Markdown files, 31 local Markdown links, six TypeScript/JSON fenced examples, sidebar ID/path consistency, README Prettier and Git whitespace checks. The check script and temporary verification dependencies live outside the repository under the operating-system temporary directory. No new production/test dependencies were added.

Not run: full Docusaurus build (site dependencies are not installed), Python/frontend runtime suites, database setup, provider/model calls or performance tests. Existing graph tests were inspected; no executable code changed in this task. Earlier validation-task results are not presented as runtime evidence for this contract.

Open decisions are recorded in the canonical qualification gates: concrete package/image pins, TEI served model/tokenizer/usage and output qualification, pgvector halfvec adapter/index compatibility, scalable genuine BM25, production isolation and deployment retention. These are implementation gates, not hidden claims of measured readiness. Rollback and downstream contract-change obligations are explicit.

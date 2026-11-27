# TASK-MAF-001 — Independent Microsoft Agent Framework runtime

**Created:** 2026-11-27  
**Updated:** 2026-11-27  
**Status:** PROPOSED — implementation specification; no runtime qualification  
**Priority:** P0  
**Dependencies:** Existing repository engineering conventions only; no RAG, retrieval, database or embedding prerequisites.  
**Repository snapshot inspected:** `d31eb5ca283523f90584a61c80ca6a90d6fccfe9`  
**Target:** `tasks/agents/TASK-MAF-001-independent-agent-runtime.md`  
**Architecture:** [MAF module boundary](MAF_ARCHITECTURE.md)

## A. Title

Establish an independently installable, executable and testable agent module using Microsoft Agent Framework (MAF), initially with a direct OpenAI Responses API adapter.

## B. Context / Problem

The user requires a reusable agent runtime separate from RAG Workbench. The first consumer is semantic evaluation, but subsequent agents must not require importing the retrieval system, loading an index or sharing its dependencies. Coupling Workbench and agent orchestration would prevent separate deployment and provider substitution.

## C. Current Repository State

The inspected complete recursive tree has `apps/workbench/` but no MAF/agent/judge application module. [AGENTS.md](../../AGENTS.md), [engineering conventions](../../docs-website/ENGINEERING.md) and [project map](../../docs-website/PROJECT_MAP.md) require reuse-first, meaningful naming, Hatch and explicit ownership. [Root pyproject.toml](../../pyproject.toml), blob `82be58e32fa89d40e408816f953986917e33b5eb`, packages upstream `haystack` and already defines a scoped `workbench-api` environment. Do not put MAF into the Haystack distribution or Workbench dependencies. Workbench embedding/reranker admission concerns local GPU inference; the remote judge has different API limits and no GPU dependency. [DATASET-002 report](../evidence/dataset-ranking-full-open-2026-11-26/report.md) describes local agent judgments, not a reusable API-based judge. Existing local review artifacts are ignored and not available for this static audit.

Current official reference: [MAF OpenAI provider](https://learn.microsoft.com/en-us/agent-framework/integrations/by-component/model-providers/openai) documents Python `Agent` with `OpenAIChatClient` for Responses API; [structured outputs](https://learn.microsoft.com/en-us/agent-framework/agents/structured-outputs) documents typed response formats. [OpenAI model catalog](https://developers.openai.com/api/docs/models) and [Sol model](https://developers.openai.com/api/docs/models/gpt-6.2-sol) list `gpt-6.2-sol` as a structured-output-compatible model. These docs are not proof of installed package or account entitlement.

## D. Goal

Deliver a standalone module with a small validated execution contract, one MAF/OpenAI adapter, independent environment, a deterministic fake for tests and a real opt-in structured-output smoke run. It can execute without Workbench, PostgreSQL, Haystack, TEI, reranker or Ollama.

## E. Scope

Module layout, own Hatch project/environment and pinned compatible dependencies, provider-neutral profiles/capability validation, agent execution boundary, config and secret resolution, local CLI JSON protocol, bounded lifecycle/error/cost telemetry, tests and operator README.

## F. Non-Goals

No RAG imports or changes to its production pipeline; no judge rubric implementation here (MAF-002 owns it), autonomous tools, multi-agent orchestration, new database, cloud deployment, external monitoring, extra user accounts, separate microservice or mandatory HTTP listener. No speculative registry/factory hierarchy. Do not activate paid calls on import/startup.

## G. Architecture / Boundaries

- [x] Domain / core — neutral typed contracts; no SDK imports.
- [x] Application / orchestration — generic run entry point and explicitly registered agent definitions.
- [x] Port / interface / contract — async agent execution and JSON wire envelope.
- [x] Provider adapter — MAF/OpenAI implementation, fake for tests.
- [ ] Persistence / vector store — N/A; no database.
- [ ] Retrieval / RAG — N/A; strict independent module.
- [x] Agent runtime — MAF behind adapter; no upstream Haystack changes.
- [x] Security / governance — explicit data egress, credential boundary.
- [x] Observability / evidence — bounded usage/status and revision data.
- [x] Infrastructure / CI/CD — independent Hatch dependency/test environment; no new required service.
- [x] Documentation — module README, project map and boundary.

Dependency direction: CLI/composition -> application/contracts <- adapters. Future agents depend on neutral contracts, not directly on OpenAI or Workbench. Inter-process JSON is the initial integration boundary. Do not import across `apps/maf` and `apps/workbench` in either direction. A caller can invoke the module without sharing its Python environment; a future HTTP transport may wrap the same contract, but is not needed now.

## H. Contracts / Interfaces / Data Model

Proposed independently versioned JSON envelope: `schema_version, request_id, agent_id, profile_id, payload`; result: `request_id, agent_id, status, result, error, run_metadata`. Agent-specific payload/result schemas are owned by that agent. Validate IDs, schemas, lengths and capabilities before calling the provider. Status distinguishes success, invalid_request, unsupported_profile, budget_exceeded, provider_error, timeout, cancelled and invalid_output. Unknown optional usage is null, never invented.

Neutral `AgentRuntime` protocol accepts typed run data and expected output schema; use only a necessary port for SDK isolation/testing. `ModelProfile` requires structured output and optional reasoning control, input/output bounds; composition maps profile to provider/model. Initial configurable profile `semantic-judge`: direct OpenAI, `gpt-6.2-sol`, medium reasoning if supported. Resolve actual model and supported options during qualification, record requested and returned model identity. No silent model fallback, Azure fallback, ChatGPT/Codex subscription assumption or hard-coded vendor names in agent logic.

## I. Repository Files / Components Impacted

Create independent `apps/maf/pyproject.toml`, `README.md`, scoped `AGENTS.md`, `.env.example` (variable names only), `src/maf_runtime/contracts.py`, `runtime.py`, `configuration.py`, `adapters/maf_openai.py`, `cli.py`, package init files and colocated `tests/`. Layout may be simplified without violating boundary. Create local ignore entries for MAF secrets/artifacts, not broad rules that hide source. Update project map and link boundary doc. Do not change Workbench/TEI/reranker runtime, Haystack package dependencies, database schema, main startup script or existing evaluation artifacts. If a shared dependency lock conflicts, update this specification before changing unrelated components.

## J. Implementation Requirements

1. Inspect compatible released MAF distribution/imports, OpenAI SDK, Python and Pydantic versions. Pin the tested dependency set within the standalone project. Use Hatch; verify `hatch --version`, then enter the module directory and run its own commands. Test installation in a clean environment without installing repository root or Workbench. Record versions and license.
2. Implement explicit composition using the current supported MAF `Agent` and Responses client (`OpenAIChatClient` in current official docs). Keep all MAF/OpenAI SDK types inside adapter/composition. Use native structured response format and strict local schema validation; verify actual pinned SDK API, not pseudo-code. For each execution create fresh isolated context/session; no cross-case memory, persistent conversation or inherited tools. No agent tool registration by default.
3. Provide a standalone CLI `python -m maf_runtime` through a Hatch script with commands for validate/describe, run and explicit live smoke. Use versioned JSON stdin/stdout or explicit input/output files; no secrets in argv. Diagnostics go to stderr; machine output stays parseable. Never read arbitrary paths supplied inside model payload. Reject malformed/oversized input and unknown agent/profile IDs without network access. Keep the first contract small and reusable.
4. Configure model/profile, API limits, timeouts, bounded retry with backoff for transient errors, concurrency, maximum cases/input/output tokens and per-run spending cap. Require explicit live flag and budget before remote calls; default offline/fake. Use provider-reported usage and configured current rates for measured/estimated cost, including retries; unknown usage flagged. Stop on budget exhaustion, resume only missing case digests; no automatic retries of refusals or auth/invalid-schema errors. Support cancellation and close clients cleanly. No separate cloud queue.
5. Resolve the existing operator-supplied OpenAI API credential at adapter boundary from environment or ignored local config; no key values persisted. Explicitly route to intended OpenAI API; forbid accidental provider fallback. Verify provider storage option `store=false` on actual outgoing request, no conversation/background/hosted tools; if pinned adapter cannot implement required data handling, fail qualification. Explain that disabling response storage does not imply zero provider retention. Restrict first live smoke to harmless synthetic data, then approved corpus only.
6. Demonstrate a trivial typed test agent or fake invocation without Workbench. No MAF SDK imports in neutral core and no imports of Workbench/Haystack/retrieval modules anywhere in MAF. Check that existing Workbench installation works with MAF absent and does not call it. Publish actual smoke result or explicit configuration blocker; do not invent success.

## K. Security / Governance / Observability

Provider credentials never enter payloads, output, logs, fixtures or Git. Egress off by default; require explicit per-run approval for permitted non-sensitive/public data. Do not send private invoices, customer data, internal secrets or unapproved corpus. Validate outbound data classification, minimize payload, disable content telemetry and retain only local ignored artifacts. OpenAI's [data controls](https://developers.openai.com/api/docs/guides/your-data) describe retention; record actual settings, not assumed ZDR. Inputs (documents, retrieved text, model output) are untrusted data, never instructions or tool permissions. Log request IDs, safe status, model/profile/revision, latency, usage and cost only; no hidden reasoning traces. No new reviewers or enterprise governance.

## L. Testing / Evaluation / Runtime Verification

Use module-local Hatch test/check/types scripts; configure Ruff and pytest for src/tests. Tests: fresh install, module import graph, SDK isolation, fake runtime, invalid schema/model/profile, structured output parse/validation, refusal/429/5xx/timeout/cancellation, budget/resume, redaction, missing secret, no call on import, no implicit tool/session/storage, mocked outbound envelope with store=false. Real opt-in smoke on small harmless structured-output task, record model, request outcome, usage, actual elapsed time and versions. Verify RAG can start/test separately using its existing Hatch checks, and standalone MAF can run in absence of RAG. No live key in normal CI.

## M. Acceptance Criteria

- [ ] Independently installed MAF module runs/tests without Workbench or Haystack; Workbench does not depend on MAF.
- [ ] Provider-neutral validated wire contract; actual MAF adapter supports native structured output and a fake uses identical contract.
- [ ] Model/profile switch via config; no silent fallback; real smoke or explicit blocker recorded (live qualification requires actual successful call).
- [ ] Egress/budget/redaction/failure tests pass; no tools or persistent conversation.
- [ ] README and project map document separate commands, ownership and extension seam for future agents.

## N. Documentation / Migration / Compatibility / Rollback

Additive standalone project only, no DB migration or existing runtime dependency change. Keep OpenAI API setup optional and separate from RAG startup. Remove/disable module or use fake without affecting Workbench. Version JSON envelope and agent-specific schema. Future HTTP or agent-to-agent orchestration must be separate task if needed.

## O. Mandatory Completion Checklist

- [ ] Reinspect current tree and package APIs, record pinned versions.
- [ ] Implement independent module and execute import/dependency isolation tests.
- [ ] Execute actual structured-output smoke if credential/budget configured; record blocker otherwise without marking live acceptance passed.
- [ ] Record test commands, outcomes, changed files and rollback; do not mark COMPLETE before applicable acceptance.

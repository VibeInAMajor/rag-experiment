# TASK-RAG-EVIDENCE-001 — Connect original PDF/image/Mermaid evidence to the Live Workbench UI

**Created:** 2026-11-23  
**Updated:** 2026-11-23  
**Status:** PROPOSED — implementation blueprint, not implemented  
**Priority:** P1 after verified evidence resolver  
**Dependencies:** CONTENT-001 and CONTENT-005; completed UI-001/UI-002; CONTENT-002/003/004 add format-specific providers  
**Repository snapshot inspected:** 1aa9b2654df0f490781b2a09a5809e111c1f6651  
**Target:** tasks/TASK-RAG-EVIDENCE-001-live-original-evidence-and-diagram-viewer.md

## A. Title

Connect original PDF/image/Mermaid evidence to the Live Workbench UI

## B. Context / Problem

CONTENT-001 will persist original assets and derived representations, and CONTENT-005 will provide authorized evidence resolution; but the present web UI primarily displays text results and its DocumentsView is fixture-based. Without a secure viewer, operators cannot examine the original PDF page, diagram, chart or Mermaid source supporting a retrieved chunk. The UI must consume the existing evidence contract, not create a second storage system.

## C. Current Repository State

[DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx) currently consumes PreviewDocument[]; [ResultsPanel.tsx](../apps/workbench/web/src/components/ResultsPanel.tsx) and [RunsView.tsx](../apps/workbench/web/src/views/RunsView.tsx) show session search results. [local_sources.py](../apps/workbench/api/local_sources.py) offers host-local original reveal for a registered source, **not** a general authenticated PDF/image asset endpoint. [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) and [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) are existing PROPOSED specs and must be implemented before UI promises original evidence.

**Evidence rule:** this source audit is not proof that the proposed new feature is working. Re-read code and tests at task start.

## D. Goal

A Live search result can open a secure evidence pane with exact original page/crop or Mermaid source, verified source/version/element references and visible inferred-versus-observed status. Missing/stale/unauthorized evidence is clearly unavailable, never substituted by Preview data.

## E. Scope

Typed evidence API client, modal/side pane, original page/figure/Mermaid source viewing with safe MIME, line/page/bbox citations, error states, workspace/cancellation cache hygiene, provider/capability gates and browser E2E.

## F. Non-Goals

No new binary store or EvidenceResolver API implementation, no arbitrary Markdown/SVG/HTML script execution, no unauthenticated direct blob URL, no automatic VLM, no fabricated original pages, no localStorage of private assets.

## G. Architecture / Boundaries

React Live ResultsPanel -> shared typed client -> CONTENT-005 secured evidence API -> CONTENT-001 assets and relations. Server authorizes workspace/source version on every request. Browser displays source type/processor trust but cannot promote inferred descriptions to facts.

Provider neutrality and source/tenant ownership are mandatory. Do not create empty Manager/Factory wrappers without demonstrated need.

## H. Contracts / Interfaces / Data Model

EvidencePanelState{source_id,source_version_id,evidence_id,kind,content_type,hash,page?,bbox?,line_range?,provenance_kind,verification_status,body_state idle/loading/available/incomplete/error}; any original bytes fetched by safe bounded route with Content-Disposition and Cache-Control policy. Render Mermaid as escaped text, not script; images as verified Blob object URLs revoked on unmount; PDF viewer stays isolated.

## I. Repository Files / Components Impacted

MODIFY web src/api typed client (existing UI-001), [ResultsPanel.tsx](../apps/workbench/web/src/components/ResultsPanel.tsx), [RunsView.tsx](../apps/workbench/web/src/views/RunsView.tsx), optional [DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx); CREATE web src/components/EvidencePanel.tsx, tests and scripts/live-evidence-smoke.js. REUSE CONTENT-005 routes; MUST NOT copy asset server or execute user Mermaid directly.

MUST NOT modify historical migration 0001/0002, framework haystack/ or unrelated Preview/validator implementations as a shortcut.

## J. Implementation Requirements — ordered blueprint

1. J1 — Inspect actual CONTENT-005 API and schema, not merely the blueprint; validate that source version, evidence status, Content-Type and byte caps are explicit.
2. J2 — Extend shared typed API client with getEvidence/getOriginal bounded requests and safe error/abort handling. Fetch only server-generated opaque evidence IDs, never raw storage refs or filesystem paths.
3. J3 — Implement accessible panel with exact page/line/crop/diagram source, verified/inferred indicator and original hash. Render Markdown/Mermaid as inert text; prevent executable SVG/HTML and stale evidence after model-generated result.
4. J4 — Use server-approved workspace and per-run source_version context; cancel old requests, revoke object URLs and purge bytes on switching workspace/mode/logout.
5. J5 — Test real PDF table/crop, a diagram asset and Mermaid source when respective producers qualify. Upstream unavailable must show Not available, not example image.
6. J6 — Run browser E2E HTTP/source hash parity, adversarial media types, 404/409/503, slow network, RLS and existing Preview/validator/Live regression tests; document privacy and operator rollout.

## K. Security / Governance / Observability

Use server-derived WorkspaceContext and FORCE RLS across all source, asset and index paths. Keep private source bytes, vectors, prompts, credentials, user identifiers and arbitrary URLs out of logs and public evidence. Treat source/model text as untrusted data. Enforce bounded CPU/GPU/DB/network requests, cancellation, timeout, retention, auditing and safe error codes with trace/job/run IDs. Test cross-workspace and provider outage negative cases.

## L. Testing / Evaluation / Runtime Verification

UI contract tests safe content type, oversized asset, invalid hash, wrong workspace/source version, stale request, missing bbox, script-like Mermaid, broken image, API 404/503, explicit Preview-only run. Real E2E for >=3 source types after upstream producer qualifies; do not report mock as real evidence.

Execute existing Hatch workbench-api:check/test/types, explicit disposable PostgreSQL integration; when UI changes run npm typecheck/test/build and Preview/validator smoke. Attach real command outcomes and mark unrun tests NOT TESTED.

## M. Acceptance Criteria

- [ ] Every displayed source asset comes from actual scoped EvidenceResolver response
- [ ] PDF crop/page and Mermaid original hash/reference match active or pinned source version
- [ ] No cross-workspace original bytes or stale object URLs retained
- [ ] Model-inferred/OCR data visibly distinguished from original/verified evidence
- [ ] Unsupported producer or missing original yields honest Not available
- [ ] SVG/HTML/Mermaid cannot execute scripts or follow external links
- [ ] >=3 qualified source types pass real HTTP/browser E2E
- [ ] Existing Preview/Live search and API error handling unchanged

## N. Documentation / Migration / Compatibility / Rollback

Feature gate evidence pane; disable it when resolver unavailable but preserve textual Live search. No SQL migration from frontend. Never delete originals on UI rollback; invalidate caches/object URLs on workspace changes.

## O. Mandatory Completion Checklist

- [ ] Reinspect current source and completed tasks.
- [ ] Confirm API/schema/architecture owners and no duplicated services.
- [ ] Error/status/authorization contracts validated and documented.
- [ ] Original source/version and all relevant profiles preserved.
- [ ] Negative, stress/restart/recovery and security tests actually executed.
- [ ] Real metrics/cost/quality or source-evidence fidelity recorded.
- [ ] CI/Hatch/frontend regression gates passed with logs.
- [ ] New capabilities reflect true current readiness, not planned behavior.
- [ ] Safe non-destructive rollback and operator actions documented.
- [ ] Mark COMPLETE only with linked evidence proving acceptance criteria.

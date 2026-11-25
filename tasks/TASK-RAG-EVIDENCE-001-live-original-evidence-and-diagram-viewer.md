# TASK-RAG-EVIDENCE-001 — Connect original PDF/image/Mermaid evidence to the Live Workbench UI

**Created:** 2026-11-23  
**Updated:** 2026-11-26  
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

[DocumentsView.tsx](../apps/workbench/web/src/views/DocumentsView.tsx) currently consumes PreviewDocument[]; [ResultsPanel.tsx](../apps/workbench/web/src/components/ResultsPanel.tsx) and [RunsView.tsx](../apps/workbench/web/src/views/RunsView.tsx) show session search results. [local_sources.py](../apps/workbench/sources/local_sources.py) offers host-local original reveal for a registered source, **not** a general authenticated PDF/image asset endpoint. [CONTENT-001](TASK-RAG-CONTENT-001-structured-elements-representations-and-original-evidence.md) and [CONTENT-005](TASK-RAG-CONTENT-005-original-evidence-resolution-and-grounding.md) are existing PROPOSED specs and must be implemented before UI promises original evidence.

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

### I.1. Verified implementation map, symbol ownership and test references

| Existing real source file | Role / reason to reuse |
| --- | --- |
| [`apps/workbench/sources/local_sources.py`](../apps/workbench/sources/local_sources.py) | guarded registered original local Windows file reveal; NOT general asset serving |
| [`apps/workbench/sources/source_registration.py`](../apps/workbench/sources/source_registration.py) | source registration/version identity |
| [`apps/workbench/contracts/schemas.py`](../apps/workbench/contracts/schemas.py) | current source metadata and API response |
| [`apps/workbench/api/application.py`](../apps/workbench/api/application.py) | readiness/capabilities and route owner |
| [`apps/workbench/web/src/api/client.ts`](../apps/workbench/web/src/api/client.ts) | typed HTTP client and abort path |
| [`apps/workbench/web/src/components/ResultsPanel.tsx`](../apps/workbench/web/src/components/ResultsPanel.tsx) | Live versus Preview result presentation |
| [`apps/workbench/web/src/components/LiveRunDetails.tsx`](../apps/workbench/web/src/components/LiveRunDetails.tsx) | live provenance/run IDs and score metadata |
| [`apps/workbench/web/src/views/DocumentsView.tsx`](../apps/workbench/web/src/views/DocumentsView.tsx) | current fixture-only documents list and tabs |
| [`apps/workbench/api/tests/test_local_sources.py`](../apps/workbench/api/tests/test_local_sources.py) | existing local-source security tests |

**Related project (pinned source snapshot) for design/test comparison, never a blind code transplant:** [`docs/67-decision-grounding-and-provenance.md`](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/docs/67-decision-grounding-and-provenance.md); [license](https://github.com/VibeInAMajor/enterprise-ai-development-pipeline/blob/955fd049949d3fc462d555be14774e4b255aa15c/LICENSE.md).

## J. Implementation Requirements — ordered blueprint

1. J1 — Inspect actual CONTENT-005 API and schema, not merely the blueprint; validate that source version, evidence status, Content-Type and byte caps are explicit.
2. J2 — Extend shared typed API client with getEvidence/getOriginal bounded requests and safe error/abort handling. Fetch only server-generated opaque evidence IDs, never raw storage refs or filesystem paths.
3. J3 — Implement accessible panel with exact page/line/crop/diagram source, verified/inferred indicator and original hash. Render Markdown/Mermaid as inert text; prevent executable SVG/HTML and stale evidence after model-generated result.
4. J4 — Use server-approved workspace and per-run source_version context; cancel old requests, revoke object URLs and purge bytes on switching workspace/mode/logout.
5. J5 — Test real PDF table/crop, a diagram asset and Mermaid source when respective producers qualify. Upstream unavailable must show Not available, not example image.
6. J6 — Run browser E2E HTTP/source hash parity, adversarial media types, 404/409/503, slow network, RLS and existing Preview/validator/Live regression tests; document privacy and operator rollout.

### J7–J13. Concrete implementation handoff and component changes

**J7.** Require real CONTENT-001 asset store and CONTENT-005 evidence resolver APIs; do not implement a frontend viewer against spec-only endpoints or fabricate pdf/source URI.

**J8.** Extend single API client with typed evidence metadata/bounded original fetch. Validate workspace, source_version_id, asset sha and server-provided content types; no arbitrary URL fetch.

**J9.** Build inert EvidencePanel for safe PDF page/crop, plain text Mermaid source and non-executable diagram image. Render model-derived graph and OCR confidence as **derived/unverified**, not original truth.

**J10.** Attach evidence_id on actual SearchResult from backend after hydration/authorization; user clicking a chunk finds the correct immutable source page/version, not latest document by default.

**J11.** Bound browser bytes, revoke Blob URLs, avoid localStorage/cache, cancel stale fetch when workspace/Run selection changes and never allow remote use of host-local Explorer reveal.

**J12.** Exercise forged evidence ID, foreign workspace, missing asset, wrong hash, SVG/HTML/Mermaid XSS, 404/409/503; show explicit not available without Preview fallback.

**J13.** Test at least 3 truly qualified source types with exact original SHA and source/page/line provenance, plus existing Live, Preview and validation regression.

**Cross-cutting constraints:** Original assets and EvidenceResolver are separate BACKEND prerequisites, not existing sources merely because a UI link exists.

### Original evidence navigation — 2026-11-26

Adapt the evidence-navigation interaction from the [pinned Azure sample UI](https://github.com/Azure-Samples/azure-ai-search-with-content-understanding-python/blob/82ade360894b5b7959ef546cbfe96f0ff9e1cc81/nodejs/video-search-app/app/page.tsx) through existing Workbench components: select a result/citation and open exact original PDF page/crop, Markdown section or code span when supported; show derived/observed/unverified state and failed links. Never parse model-generated URLs or timestamps as evidence. Only backend-resolved IDs/locators are authoritative. Future media timestamps remain conditional on qualified transcript/media support, not a new local prerequisite. See [quality/content plan](quality/RAG_QUALITY_AND_CONTENT_UNDERSTANDING_PLAN_2026-11-26.md).

## K. Security / Governance / Observability

Use server-derived WorkspaceContext and FORCE RLS across all source, asset and index paths. Keep private source bytes, vectors, prompts, credentials, user identifiers and arbitrary URLs out of logs and public evidence. Treat source/model text as untrusted data. Enforce bounded CPU/GPU/DB/network requests, cancellation, timeout, retention, auditing and safe error codes with trace/job/run IDs. Test cross-workspace and provider outage negative cases.

## L. Testing / Evaluation / Runtime Verification

UI contract tests safe content type, oversized asset, invalid hash, wrong workspace/source version, stale request, missing bbox, script-like Mermaid, broken image, API 404/503, explicit Preview-only run. Real E2E for >=3 source types after upstream producer qualifies; do not report mock as real evidence.

Execute existing Hatch workbench-api:check/test/types, explicit disposable PostgreSQL integration; when UI changes run npm typecheck/test/build and Preview/validator smoke. Attach real command outcomes and mark unrun tests NOT TESTED.

### L.1. Task-specific reproducible test vectors

- [ ] Hash and exact original PDF/Mermaid byte parity through API; page/bbox/source-version consistency after restart.
- [ ] Frontend security: no HTML/JS execution, private Blob URL cleanup, safe content type and size ceilings, cross-tenant denial.
- [ ] Browser active source version changes while evidence modal open; must not show new version under old ID.

Capture actual executed Hatch/SQL/browser commands, source and model/index SHA, actual traces, regression suite results, and failure reason codes in a test evidence artifact. If a provider is missing, mark NOT TESTED or BLOCKED, not PASS.

## M. Acceptance Criteria

- [ ] Every displayed source asset comes from actual scoped EvidenceResolver response
- [ ] PDF crop/page and Mermaid original hash/reference match active or pinned source version
- [ ] No cross-workspace original bytes or stale object URLs retained
- [ ] Model-inferred/OCR data visibly distinguished from original/verified evidence
- [ ] Unsupported producer or missing original yields honest Not available
- [ ] SVG/HTML/Mermaid cannot execute scripts or follow external links
- [ ] >=3 qualified source types pass real HTTP/browser E2E
- [ ] Existing Preview/Live search and API error handling unchanged

- [ ] Browser smoke demonstrates navigation from actual result/citation to the verified original locator, and explicit unavailable/inferred states; no new UI framework or direct model URL.

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

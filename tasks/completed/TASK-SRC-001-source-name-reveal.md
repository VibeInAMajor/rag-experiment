# TASK-SRC-001 — Click source name to reveal its local original

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** COMPLETE — implemented and verified on 2026-11-21  
**Inspected base:** `1d082e043a7d7c8f89d7623cac321d7b83218f23`, plus the existing uncommitted, verified UI-002 implementation. Preserve those changes.

## A. Goal

A real source's name is clickable and opens Windows Explorer with its registered original selected. Demo/synthetic/unregistered sources remain plain text. No extra action button, icon, menu or file picker is added to the interface.

## B. Existing owners

Source/version/chunk identities and arbitrary metadata already live in PostgreSQL under forced workspace RLS. `source_versions.metadata` is version-bound; `PostgresPersistence` owns scoped transactions and source publication locks. Search results contain source/version IDs but no file locations. `LiveRunDetails` renders source provenance, and the shared typed API client owns all execution HTTP. Original files and ingestion are not implemented yet.

## C. Boundaries

Reuse the current registry, client, presentation and error envelopes. Do not change retrieval algorithms, profile identities, graph serialization, core Haystack, existing seed/Preview values or SQL schema. No arbitrary path from browser, shell command, file execution, HTTP path registration, upload or ingestion workflow. Windows same-machine local development only; a remote server cannot reveal a browser client's filesystem.

## D. Registration

An explicit trusted CLI binds an existing active non-demo source/version to a file beneath `WORKBENCH_LOCAL_SOURCE_ROOT`. Store `local_original = {relative_path, sha256}` in existing version metadata; original byte hash is distinct from parsed-content hash. Preserve other metadata. Refuse demo/synthetic provenance, foreign scope, missing/inactive versions and conflicting registrations. Identical registration is idempotent. No startup seeding or registration.

## E. HTTP contract

- `GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file`: correlated metadata plus safe display name and reveal availability; no filesystem paths.
- `POST .../local-file/reveal`: empty JSON object; IDs in path only; an allowed explicit browser Origin is required. Success means Explorer dispatch was accepted, not that the user read the document.
- Existing error envelopes and X-Request-ID correlation apply. Unknown/foreign identifiers and unavailable originals fail safely without path disclosure.
- Additive API routes/DTOs; search response/profile and `rag-api-v1.0` remain unchanged. Update published OpenAPI and canonical documentation.

## F. Local native boundary

Configured root is explicit and optional; absent configuration or unsupported host disables reveal. Reject absolute/parent/UNC/device/ADS registrations, traversal and resolved symlink/junction escape. Check regular-file existence and containment; before POST additionally verify SHA256 and current scoped version metadata. Reveal via the native Windows Shell selection API using typed arguments, not shell-string interpolation. Inject the native launcher in automated tests. Native calls must not block the ASGI event loop; errors are sanitized.

## G. UI

Replace only the Source value with a reusable source-name component. Use filename returned by the server for registered originals. An available name is a keyboard-accessible text link; unavailable/demo values remain noninteractive. No invented file path or clickable demo fixture. Prevent double dispatch and stale updates; bound/deduplicate metadata lookups in transient memory. Display a concise safe error only after a failed click. Preview remains entirely noninteractive for source files.

## H. Security and provenance

Workspace resolution and RLS precede file lookup. Server resolves the registered path independently on each reveal; browser flags are hints only. Names/content render as React text, not HTML. No path/DSN/document bodies in error messages or logs. Origin/host/body/method protections prevent drive-by native actions. Registration changes existing corpus fingerprint/cursor validity because version metadata is fingerprinted; document this intentional effect.

## I. Ownership

Persistence/registration agent: registry methods, trusted CLI, disposable PostgreSQL tests. Native/API agent: configuration, local service, two routes, boundary, DTO/OpenAPI and API tests. Frontend agent: shared client additions, source-name component and presentation/tests. Root: task/contract docs, release note, integration/browser verification and review.

## J. Verification

Run Hatch version first and use the dedicated workbench-api environment. Run focused native/registry/API tests plus existing API regression suite. Run frontend typecheck, format, tests, production build and real browser demo-unavailable assertion. Positive integration uses an isolated real non-demo record and temporary original, not mutation of main demo seeds. Inject native calls in automated tests; identify any actual Explorer check separately. Retain existing Preview/validator/Live behavior.

## K. Acceptance

- [x] Available real source name alone is clickable, keyboard-operable and dispatches reveal once.
- [x] Demo/synthetic/unregistered sources have no clickable element.
- [x] Trusted registration persists across API restart without schema migration; scope and active version are checked.
- [x] Browser never sends or receives an absolute path.
- [x] Traversal, external Origin, arbitrary body/path, unknown/foreign/demo/inactive/missing/changed file fail closed.
- [x] Source ID/version are rechecked at click; no fabricated successful reveal.
- [x] Python/frontend checks and browser evidence captured.
- [x] Existing main seed/corpus and prior UI-002 changes preserved.

## L. Compatibility

New API operations are independent of lexical search. Existing clients ignore the new routes. No graph/DB migration. Real ingestion can populate the same registration metadata later. Existing unavailable files remain plain text; storage readiness does not imply a native desktop capability.

## M. Rollback

Remove source-name integration and the new local-file routes/CLI; preserve corpus, versions, files and database volume. Optional registration metadata does not require destructive cleanup.

## N. Limits

No real ingestion or remote desktop bridge is introduced. Current main corpus contains only synthetic records and intentionally has no clickable originals. Same-machine Windows/interactive Explorer and an explicitly configured allowed root are required for real reveal.

## O. Completion record

Implemented with three agents over the preserved UI-002 working tree. Reused existing PostgreSQL version metadata/RLS, publication locks, typed transport and Live result/session presentation. Added trusted registration, native guarded API operations and only a clickable filename; demo stays plain text. All 259 frontend and 199 API tests passed, along with typecheck/format/build/Ruff/mypy and actual browser/native/legacy regressions. A controlled React Flow measurement correction prevents fast Run from hiding nodes without changing graph serialization. The actual isolated real-file browser click dispatched Windows Explorer; the main8-source corpus remains unchanged, and the owned fixture database/listener were cleaned. See [verification and evidence](evidence/source-name-verification-2026-11-21.md) and [operating guide](../docs-website/docs/architecture/local-source-reveal.md) for exact commands, files, limits and unrun checks. Search contracts/profile, schema/fixtures and Haystack core are unchanged; the new routes and original-registration metadata are the intentional additive contract.

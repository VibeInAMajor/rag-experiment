---
title: Local source originals
---

# Local source originals

Workbench can make a registered local source's filename clickable in Live results and session details. The click selects the original in Windows Explorer on the API host. Demo/synthetic sources and unavailable originals remain ordinary text. There is no extra action button, menu or file picker.

This is a same-machine Windows development capability. A remote API or a service without an interactive desktop cannot open the browser client's Explorer. Native dispatch uses [SHOpenFolderAndSelectItems](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems); it selects the file rather than executing its contents.

## Configure and register

Use the existing PostgreSQL [setup/runbook](postgresql-foundation.md). In the API terminal, explicitly choose a local root containing the originals, then start the API:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
$env:WORKBENCH_LOCAL_SOURCE_ROOT = 'C:\Documents\Sources'
hatch run workbench-api:serve
```

From a separate terminal with the same database/root configuration, register an **already existing real active source version**:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
$env:WORKBENCH_LOCAL_SOURCE_ROOT = 'C:\Documents\Sources'
hatch run workbench-api:source-register --source-id report --version-id report-v1 --file 'C:\Documents\Sources\report.pdf'
```

The IDs/file above are examples; this command does not create sources, parse documents or ingest files. It refuses unknown/inactive versions, demo markers, reserved demo IDs and files outside the trusted root. Ingestion remains a separate workflow. The current eight-source development corpus deliberately has no clickable original.

Registration stores `source_versions.metadata.local_original = {relative_path, sha256}` using the existing RLS registry and publication locks. The application requires the current [corpus-generation migration](persisted-index-generations.md); registration adds no separate original-file schema. The SHA identifies original bytes and is separate from the parsed-content fingerprint. Exact retry is idempotent; a different registration for the same version is refused. A replacement document needs its own version/publication workflow. Changed registration advances the persisted corpus generation atomically and expires old corpus-bound cursors; exact retry preserves the generation. It does not rewrite chunks or seed data. Reopening the API preserves registration in PostgreSQL.

## Browser protocol

The shared typed client uses two additional routes, with the existing `rag-api-v1.0`, `request_id`, `trace_id`, error envelope and X-Request-ID rules:

| Method / route suffix                                                                        | Meaning                                                                       |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `GET /api/v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version_id}/local-file` | Returns `name`, `can_reveal`, optional `reason`; no filesystem path           |
| `POST .../local-file/reveal`                                                                 | Empty JSON object `{}`; requests native selection for the registered identity |

For example, a demo GET returns `name: null`, `can_reveal: false`, `reason: "demo_source"`. Other unavailable reasons are `not_registered`, `root_unconfigured`, `file_unavailable` and `host_unavailable`. Registered but unavailable names can remain readable without becoming clickable. Available names are keyboard-accessible text links. Four concurrent metadata lookups are allowed in the browser, with transient in-flight deduplication and cancellation; metadata is not stored persistently.

A reveal POST requires an explicit allowed Origin, loopback Host and JSON content type; it accepts no browser path, query string or extra JSON fields. Its body limit is 1 KiB. Workspace scope and active source/version are resolved independently on each operation. Success is `{status: "revealed", ...meta}`: native selection dispatch was accepted, without claiming the user opened/read the document.

| Failure                                               | HTTP / code                                            |
| ----------------------------------------------------- | ------------------------------------------------------ |
| Unknown or inactive source version                    | 404 `SOURCE_NOT_FOUND`                                 |
| Foreign workspace                                     | 404 `WORKSPACE_NOT_FOUND`                              |
| Unregistered/demo/missing/changed/disallowed original | 409 `SOURCE_FILE_UNAVAILABLE`                          |
| Native dispatch unavailable/fails                     | 503 `FILE_REVEAL_FAILED`                               |
| Missing/external Origin or untrusted Host             | 403 `FORBIDDEN`                                        |
| Extra fields/invalid body/query                       | 400 `INVALID_REQUEST` or `INVALID_JSON`                |
| Wrong media type / oversized body                     | 415 `UNSUPPORTED_MEDIA_TYPE` / 413 `PAYLOAD_TOO_LARGE` |

The server rejects traversal, UNC/device/ADS paths, symbolic links and reparse points (including junctions), and originals on network drives. Files must be regular local files no larger than 512 MiB. Before dispatch it verifies byte SHA, file identity, containment and current version again. Byte verification has a five-second deadline and occurs outside the event loop; a canceled/timed-out hash worker cannot launch Explorer afterward. A native request already dispatched is not revocable. The client does not retry reveals automatically. Failures show concise safe feedback after a click; successful clicks add no new controls or messages.

## Verification

From the repository root, load the existing test DB environment and run the targeted API checks through Hatch; see the [API README](../../../apps/workbench/api/README.md). From `apps/workbench/web`, run typecheck, format, tests and build as documented in its [README](../../../apps/workbench/web/README.md).

The supervised `scripts/workbench_source_reveal_fixture.py` harness creates its own disposable `rag_test_*` database, registers a real temporary original and serves the actual API on port 8014 with native Explorer enabled. It requires explicit local administrator/application environment from `use-dev-env.ps1 -IncludeAdmin`. It never resets the main corpus. Stop it with Ctrl+C after the browser scenario and verify the source_fixture_cleaned marker. Normal cleanup removes only its owned database and retains the temporary original used by Explorer. Abrupt console/process termination can bypass finally; any fallback must verify the exact owned database identity printed by the harness, never reset the main database.

The separate `scripts/source-name-smoke.js` scenario first proves current demo names are noninteractive against the main API, then directs its browser-only API traffic to the isolated harness and performs a real keyboard filename click through PostgreSQL/API/native dispatch. Its final failure response is deliberately injected and labeled in evidence. No main demo record is converted into a fake original.

# Workbench execution discovery — verification record

Date: 2026-11-21 (Europe/Kiev). Inspected base: `6639ccb2d01f6c0a2396ee43022bfd2edd5e1a77`. Implementation is the working-tree change relative to that base.

## Result and boundaries

The UI defaults to Preview. Explicit Live selection performs four GET discovery operations through one runtime-validated RAG API client. Readiness requires a running service, ready database, search support, matching readiness/profile revisions and a server-returned workspace authorized by the supported profile. Live Run is disabled with an explicit explanation. Live Documents and Runs display placeholders instead of Preview fixtures. The display-name preference never becomes an authorization identifier.

No backend, PostgreSQL migration, existing corpus/Preview fixtures, graph serialization or constructor-validator protocol changed. Search and document-list DTOs are declared for subsequent tasks; their operations are not invoked. No ingestion, model inference, production authentication or arbitrary graph execution is introduced.

## Checks

| Check                                      | Evidence / outcome                                                                                                                                                                                                                      |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TypeScript                                 | [Output](ui-discovery-typecheck-2026-11-21.txt), passed                                                                                                                                                                                 |
| Prettier (all frontend src/scripts/README) | [Output](ui-discovery-format-2026-11-21.txt), passed                                                                                                                                                                                    |
| Vitest                                     | [Output](ui-discovery-tests-2026-11-21.txt), [JUnit](ui-discovery-tests-2026-11-21.xml): 96 passed; 46 transport, 21 discovery, 21 graph and 8 validator-client tests                                                                   |
| Production build                           | [Output](ui-discovery-build-2026-11-21.txt), passed; existing third-party module-directive warnings remain nonfatal                                                                                                                     |
| Preview browser regression                 | [Output](ui-discovery-preview-smoke-2026-11-21.txt), passed against production preview4173: editing, undo/redo, graph import/export, branching/cycle restriction, output, document chunks, run history and simulated failure            |
| Constructor-validator browser regression   | [Output](ui-discovery-validation-smoke-2026-11-21.txt), passed against production4173 and real validator8010, including independent unavailable state                                                                                   |
| Discovery browser                          | [Structured result](ui-discovery-browser-2026-11-21.json): real healthy API8011, actual unconfigured API8012 response replay, keyboard/focus, navigation, offline/no fallback, workspace conflict, stale responses and Preview recovery |
| Actual HTTP discovery                      | [Responses](ui-discovery-http-2026-11-21.json): primary API ready200; separate no-DSN API live200 / ready503 / capabilities200 with profiles[]; original request/trace IDs retained                                                     |
| Visual inspection                          | [Ready1440](workbench-live-ready-1440.png), [Ready1100](workbench-live-ready-1100.png), [Not ready1440](workbench-live-not-ready-1440.png): no horizontal overflow; native radio keyboard selection has visible focus                   |

Healthy standalone HTTP capabilities request ID: `fd179626c07c4fc0b780bfb8a069b32b`. Workspaces request ID: `493d416b5f744e54affa6b522e539a4a`. Unconfigured readiness503 request ID: `481bd0caf16e4d4c9a415e32fa63df3b`. Browser observations have their own genuine request/trace IDs in the structured result.

The second API was started without `WORKBENCH_DB_DSN` on8012, without stopping or modifying the primary database. Its actual safe payloads were obtained over HTTP and replayed through the browser route to test UI rendering. Offline, conflicting-workspace and out-of-order responses were deliberately injected browser scenarios. These injected failures are not claimed as independently observed production incidents.

## Ownership and reuse

- `src/api/`: wire DTOs, decoders, correlation/errors, bounded request deadlines and discovery GET transport. Published OpenAPI discriminator/limit assumptions are tested.
- `src/domain/backendDiscovery.ts`, `src/hooks/useBackendDiscovery.ts`: one discovery state machine, bounded pagination, cancellation generations and server-owned selection. This follows the existing validation client's stale-request pattern while keeping its separate service/protocol unchanged.
- `App.tsx`, `ExecutionControls.tsx`, `SettingsView.tsx`, `PipelineEditor.tsx` and existing CSS: reuse the shell, session state, Preview hook, graph history, validator hook and established typography/palette. Live hides fixture provenance rather than changing fixture content.
- `vite.config.ts`: adds a non-overlapping `/api/v1` proxy to8011 for dev and preview, retaining validation8010.
- Workbench README, project map, engineering guide and canonical contract status text now reflect discovery integration. API v1 and graph schemaVersion1 are unchanged. A release note describes the user-visible behavior.

## Limits and checks intentionally not run

No full upstream Haystack Python suite or documentation-site build was run: server/core behavior is unchanged. Existing targeted validator browser checks and published-OpenAPI frontend tests cover the affected boundaries. No new package dependencies were needed; the existing node_modules installation was used.

Connection status is a point-in-time check with a last-checked timestamp; Refresh obtains a new snapshot. Availability can change after discovery, so later execution tasks must revalidate. Discovery is bounded to ten workspace pages of50 and has a15-second overall deadline with5-second request deadlines. Cross-origin/static deployments require explicit proxy/CORS configuration. Browser response-size validation currently applies after buffering the response; server-controlled local discovery bodies are bounded, but streaming body limits remain a possible future hardening measure.

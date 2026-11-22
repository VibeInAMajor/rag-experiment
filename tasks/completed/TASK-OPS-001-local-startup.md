# TASK-OPS-001 — Local Workbench startup

**Created:** 2026-11-21  
**Updated:** 2026-11-21  
**Status:** COMPLETE — implemented and verified on 2026-11-21

## A. Goal

Run the existing local site, API and PostgreSQL from one root PowerShell command, `./start.ps1`.

## B. Existing owners

Reuse `apps/workbench/postgres/compose.yaml`, its ignored `.env`, `use-dev-env.ps1`, the `workbench-api:serve` Hatch command, the constructor validator module, and the frontend build/Vite preview. Health contracts and proxy destinations already exist.

## C. Scope

Windows local development, PostgreSQL 55432, API 8011, validator 8010 and website 4173. Start stopped services and reuse healthy listeners. No application or database API changes.

## D. Preconditions

Hatch must report its version; Node.js >=22.12, npm, Docker Desktop/Compose and the existing initialized database configuration are required. Dependency installation uses the existing lockfile if Vite is absent.

## E. Database lifecycle

Inspect only the existing Workbench Compose postgres service. Start Docker Desktop if its engine is unavailable; start/wait for the service if needed. Preserve credentials and named volumes. Never bootstrap, migrate, seed, reset or regenerate credentials automatically.

## F. Process lifecycle

Launch hidden workers with independent per-service logs. Build the frontend before a cold site launch. Wait for expected service health, then verify API readiness through the website proxy. Report failures with log locations.

## G. Idempotency

A per-checkout startup mutex prevents concurrent duplicate launchers. Existing healthy services retain their PIDs. A foreign or unhealthy occupied port fails without terminating its owner.

## H. Security

Bind the services to loopback using their existing contracts. Load only the application DB credential into the API worker; clear DB secrets from other workers. Preserve optional local-source configuration. No credentials in command lines or launcher output.

## I. Ownership

Root launcher owns orchestration; existing service entry points retain setup, runtime and health behavior. No duplicate backend/frontend configuration subsystem.

## J. Verification

Parse the script, run against healthy services and confirm unchanged PIDs; stop only verified Workbench processes/container and test cold restart; repeat startup. Check all health endpoints, proxy and unchanged document corpus. Do not stop Docker Desktop or unrelated containers to test an optional branch.

## K. Acceptance

- Root `start.ps1` starts the local application with one command.
- Stopped PostgreSQL is started and awaited before services.
- Healthy service listeners are reused without duplicates.
- Cold site startup builds current sources.
- Readiness is checked through the same proxy used by the UI.
- Logs and setup/failure guidance are documented.
- Existing corpus, credentials and database volume are preserved.

## L. Compatibility

Windows PowerShell 5.1 syntax and PowerShell 7; existing manual commands remain usable. This starts a local production build preview, not a production deployment.

## M. Rollback

Remove the launcher and its documentation. Existing services, database schema, credentials and volumes are unchanged. Running child processes have an independent lifetime.

## N. Limits

First-time database provisioning is explicit in the API README. Docker Desktop must be installed at its standard location for automatic engine startup. No stop/restart manager, migration runner, model service or remote deployment is introduced.

## O. Completion record

Added root `start.ps1`, startup instructions in the web/API READMEs, a project-map owner entry and a scoped release note. Reused existing Compose, credentials helper, Hatch service commands, validator and frontend build/proxies. No runtime API, database schema or UI design changes.

Passed syntax parsing, actual Windows PowerShell 5.1 cold startup after stopping the three owned service processes and the Workbench PostgreSQL container, and PowerShell 7 repeated startup with unchanged PIDs. HTTP liveness, readiness, validator, website and website-to-API proxy checks returned 200. All eight documents and their corpus revision survived unchanged. Concurrent startup and an occupied unrecognized port are refused without replacing its listener. Frontend typecheck, format, all 259 tests and the production build passed; the build retained existing dependency directive warnings.

See [runtime evidence](evidence/local-startup-2026-11-21.json) and [verification scope](evidence/local-startup-verification-2026-11-21.md). Docker Desktop engine startup and first-install dependency downloads were not exercised; the existing engine/dependencies were available. Python unit/integration suites and browser automation were not rerun for this orchestration-only change. Services are running after verification.

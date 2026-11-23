# Approved profile registry qualification — 2026-11-23

Base commit: `44866bb7e7dc01993bbaefefdec1ab1985951cc7`, with the preceding uncommitted INDEX-001 work preserved. This task adds immutable retrieval policy definitions and workspace rollout governance to the existing local application. It does not qualify a model, ANN, RRF, BM25 or production authentication.

## Implemented ownership and compatibility

`profile_registry.py` owns frozen provider-neutral definitions, canonical policy hashes and strict bounded YAML decoding. It reuses the existing document-processing YAML node decoder; parser/chunker configuration, resources and source fingerprints remain in their existing owners. `postgres_profiles.py` and additive migration `0004` own immutable revision rows, scoped rollout state, append-only audit events and explicit administrator commands. `sync` publishes definitions without activating them. Atomic `promote`/`rollback` uses the existing workspace lock, actual corpus/index qualification and compare-and-set rollout version; a failed activation retains the prior binding and audit history.

The application reuses its persistence port, source-generation manifest, SQL active-version/RLS rules and reviewed Haystack FTS composition. Unknown catalog identities/revisions reject before persistence. Known stale/draft/retired state uses bounded metadata SQL and rejects before retrieval/embedding work. Actual rollout and policy admission are rechecked before candidate SQL inside the same REPEATABLE READ transaction as the corpus and hits. Projection refuses absent or mismatched policy provenance.

The baseline `postgres-fts-baseline` / `postgres-fts-baseline-r1` descriptor and search-response wire keys are frozen by a real HTTP regression. The request remains the four existing fields. Existing descriptor fields admit other approved lexical IDs/revisions and tighter validated limits; regenerated OpenAPI and typed client decoders agree. `corpus_revision` retains the persisted source-generation identity. Internal profile revision, policy hash and numeric index-generation metadata are traced without inventing an externally calibrated score. All executable responses retain raw `postgres_ts_rank_cd`.

## Real PostgreSQL lifecycle and HTTP checks

The [focused route artifact](profile-routes.xml) records **24 passing tests** in 18.44 seconds. These cover pure preflight, request and profile bounds, workspace denial, baseline byte-compatible keys, draft/qualified/active/retired transitions, revision swap/rollback, stale rollout inside SQL admission, source growth after application admission, missing dependencies despite a forged active flag, atomic activation rollback and wrong/missing result provenance. The source-growth race observes actual asynchronous SQL execution and proves zero ranking statements before its 503 refusal. The activation fault injects a real PostgreSQL trigger failure, preserving the old rollout and event count.

The [combined focused artifact](profile-regressions.xml) records **54 passed, zero skips**: 30 registry model/configuration/migration tests plus the 24 route cases. These exercise invalid dimensions, score direction, missing model/capacity/RRF dependencies, unsafe YAML and duplicate identities, immutable definition drift, upgrade/backfill and the 64-binding guard. The guard refuses the 65th ordinary binding before writing rather than allowing a valid administrator action to disable the existing baseline through an oversized runtime read. Focused and final whole-suite artifacts distinguish executed PostgreSQL tests from skipped native-model qualification.

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1 -IncludeAdmin
$env:WORKBENCH_TEST_ADMIN_DSN = $env:WORKBENCH_DB_ADMIN_DSN
$env:WORKBENCH_TEST_APP_DSN = $env:WORKBENCH_DB_DSN
hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_profile_routes.py --tb=short --junitxml=tasks/evidence/profile-2026-11-23/profile-routes.xml
```

## Actual API, lifecycle and restart

[The HTTP artifact](http-rollout.json) records an owned UUID-named disposable database, two real lexical profiles, actual administrator retirement/reactivation and independent application-role SQL parity. The focused profile is `postgres-fts-focused` / `focused-r1`, with top-K ceiling 3. A request to its actually retired revision returns 409 `PROFILE_NOT_AVAILABLE` with a safe trace ID and no results.

The harness restarts a real API process on loopback port 8021. Both active profiles retain the same source-generation token, source/version/chunk IDs and raw scores before and after restart; each response is compared to independently executed SQL. Its state file contains only owned database/process identities and the public registry configuration; credentials remain in inherited environment references. The owned API and database were removed after verification. Shared API 8011 and main application data were preserved by this harness.

```powershell
hatch run workbench-api:python -m scripts.workbench_profile_smoke prepare
hatch run workbench-api:python -m scripts.workbench_profile_smoke start
hatch run workbench-api:python -m scripts.workbench_profile_smoke verify
hatch run workbench-api:python -m scripts.workbench_profile_smoke retire
hatch run workbench-api:python -m scripts.workbench_profile_smoke activate
hatch run workbench-api:python -m scripts.workbench_profile_smoke restart
hatch run workbench-api:python -m scripts.workbench_profile_smoke verify
hatch run workbench-api:python -m scripts.workbench_profile_smoke cleanup
```

## Actual browser verification

[The sanitized browser report](browser-smoke.json) records Playwright over the isolated API and a temporary Vite proxy, with the normal Preview and constructor validator boundaries preserved. The focused profile was explicitly selected, submitted through the exact four-field request and returned one real FTS hit with its actual profile revision and score type. There was no horizontal overflow at viewport widths 1440 and 1100.

After actual administrator retirement, discovery entered `awaiting_profile` / `PROFILE_NOT_AVAILABLE`, left selection empty, disabled Run and hid the prior profile's results. It did not silently substitute the baseline or fixtures. An explicit baseline selection restored readiness. The existing Live smoke additionally passed three real queries, nine injected failure scenarios, local Stop/late-response checks and layout checks, with the source registry unchanged. Existing Preview and validator browser smokes passed as separately identified scenarios.

- [Focused selection at 1440](profile-selected-1440.png)
- [Focused selection at 1100](profile-selected-1100.png)
- [Explicit baseline recovery](profile-recovered-1440.png)

Frontend typecheck, format check, build and **350 tests in 18 files** passed. The regenerated OpenAPI/client-focused selection additionally passed 97 tests. These client checks do not qualify unsupported semantic modes.

## Bugs addressed and operational limits

Review fixed the distinction between definition identity and mutable lifecycle, a non-atomic rollout/rollback window, stale rollout admission, corpus growth between application and SQL checks, missing result attribution and a binding-budget failure that could otherwise hide all profiles. Definition immutability and audit protection remain distinct from operator qualification; an active flag never proves capability evidence.

Current public profile execution requires migration `0004`. The explicit legacy corpus read switch does not bypass governance. Editing a registry YAML file requires an API restart to update its allowlist; subsequent durable lifecycle changes are read live. Keep the current revision in configuration while publishing a replacement, load both revisions before promotion, and use explicit compare-and-set promotion/rollback. Retired bindings count toward the 64-ID workspace budget; history deletion/retention is not silently introduced. Processing pins and semantic/capacity/index requirements remain unavailable until their actual owners can attest compatibility.

## Final whole-suite and quality result

```powershell
hatch run workbench-api:check
hatch run workbench-api:types
hatch run workbench-api:test --tb=short --junitxml=tasks/evidence/profile-2026-11-23/full-tests.xml
```

[Final JUnit](full-tests.xml): **984 passed, 16 skipped, zero failures/errors** in 253.44 seconds. Every profile and PostgreSQL test executed. All 16 skips are native Qwen tokenizer counting/provisioning cases requiring absent `WORKBENCH_TEST_QWEN_TOKENIZER_DIR`; they do not represent model qualification. The lexical golden property records 10/10 exact targets in top five and the same three known paraphrase misses. Existing HTTP 400/404/409/429/503/504, cancellation, source-version, RLS and independent SQL identity/score cases passed.

[Quality output](quality-checks.txt) records Ruff check/format and mypy passing across 100 API source files. Focused Ruff/format and mypy for the new smoke script and route suite passed separately. Documentation relative-link targets across nine changed guides/task/report files, strict UTF-8/final newlines, unique sidebar ID, `node --check docs-website/sidebars.js`, the release-note backticks check and `git diff --check` passed. Evidence text/JSON/XML was scanned for the actual configured database DSNs/passwords without exposing their values.

Docusaurus full build was not run because `docs-website/node_modules` is absent; no dependencies were downloaded. Haystack core checks were not run because framework code is unchanged. Actual frontend and browser checks are recorded above. No production deployment or performance improvement is inferred from this profile task.

## Existing local database migration and API readiness

[The deployment artifact](deployment.json) records the actual local `0003` → `0004` upgrade after the verified old API process was stopped. Backup `workbench-before-0004-20261123-210904.dump` is 103,984 bytes and its custom archive was checked with `pg_restore --list`; its SHA-256 is retained in the artifact. The existing volume and credentials were preserved.

Counts and full-record SHA-256 signatures matched across all nine preceding tables: the six original corpus/job/profile tables plus `corpus_index_state`, `corpus_source_state` and `index_generations`. The manifest remained consistent at generation 1, with 15 active sources and 44 active chunks; the database retains 55 total chunks and 17 versions including history. No new main-corpus aliases or synthetic documents were seeded. Source/vector data and prior generation history were unchanged.

The restarted actual API on port 8011 returned readiness 200 and advertised the qualified baseline. A real PostgreSQL query returned three results whose source/version/chunk identities and raw scores matched an independent SQL query. The safe trace ID is `8991171fa702478ab512d8e3a8cf1df1`. The deployed corpus revision remains `corpus-138b2a8f620aed19d324da8c8046dd2f251d7e7e957c724665c9f45252e04b10`.

Result: **COMPLETE for PROFILE-001**. The code, actual local schema and API are aligned. Unsupported semantic retrieval and processing/model qualification remain explicit future gates, rather than executable capabilities inferred from a stored definition.

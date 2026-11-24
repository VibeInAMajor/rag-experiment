---
title: Live lexical acceptance — 2026-11-22
description: Evidence and reproducible checks for the Workbench UI, Haystack and PostgreSQL lexical path.
---

# Live lexical acceptance — 2026-11-22

**Status:** COMPLETE — local Live lexical acceptance gates passed on 2026-11-22.\
**Task:** [TASK-EVAL-001](../../../tasks/completed/TASK-EVAL-001-prove-vertical-slice.md)\
**Inspected base:** `deb9fb63dde97f68db6dd856d1fc2a13a2af2255`, with existing working-tree parser/chunker changes preserved. No new implementation commit is claimed.

This report evaluates the existing **browser Live → FastAPI → Haystack Pipeline → persisted PostgreSQL FTS** path on this **local Windows workstation**, using loopback services at `127.0.0.1:4173` and `127.0.0.1:8011`. It does not qualify a remote deployment, ingestion, embeddings, semantic retrieval or generated answers. Preview and constructor validation are independent regressions. The [runtime contract](../architecture/rag-runtime-contract.md), [lexical guide](../architecture/postgres-lexical-search.md) and [PostgreSQL operations guide](../architecture/postgresql-foundation.md) own the behavior being tested.

## Evidence lanes and current gate state

| Gate | Evidence lane | Current observation |
| --- | --- | --- |
| Ten exact plus three diagnostic browser attempts | Real browser/API/PostgreSQL | PASS in baseline, after-API and after-database phases: 10/10 exact, 0/3 diagnostic hits, all attempts retained |
| DOM/JSON identity, rank, score and timing parity | Real browser and captured HTTP | PASS for 39 canonical cases plus three explicit no-match requests |
| Persisted SQL ranking/source parity | Real read-only HTTP/SQL and existing integration tests | PASS: 13/13 canonical cases per phase, 39 total; 38 backend tests pass, zero skips |
| API/database outages and explicit recovery | Real stopped services/browser | PASS: API proxy 502 without invented server IDs; database 503 with actual correlation; neither falls back to fixtures |
| API restart and PostgreSQL restart on the same volume | Real services and persisted identities | PASS: API process changed, database container/volume preserved, corpus/registry and SQL parity unchanged |
| Safe 400/404/409 outcomes and zero-hit response | Real service, with clearly labeled invalid request arrangements | PASS: actual errors, nested codes/correlation and visible UI parity |
| 429/503/504, malformed success, network error, races and local Stop | Mock fault injection, separate from real ranking/latency | PASS: nine injected error shapes, local interruption, query/mode late responses and inert markup |
| Existing Preview and constructor validator | Independent regression smokes | PASS independently |
| Backend/frontend quality commands | Actual captured command output | PASS: 38 backend tests, 259 frontend tests, typecheck, format/build, probe static checks and runner failure-preservation check |

The generated [acceptance summary](../../../tasks/evidence/eval-vertical-2026-11-22/acceptance-summary.json), [artifact audit](../../../tasks/evidence/eval-vertical-2026-11-22/evidence-audit.json) and [source/build manifest](../../../tasks/evidence/eval-vertical-2026-11-22/source-build-manifest.json) identify current observations. Source inspection, historical results and mocked responses are not substitutes for real-service gates. The existing evidence ignore policy keeps machine artifacts local; reusable harnesses and this Markdown report are reviewable repository source. Previous 2026-11-21 evidence remains historical and untouched.

## Corpus and metric method

Use the existing [gold fixture](../../../apps/workbench/retrieval/fixtures/lexical-evaluation.json) and [eight-source synthetic corpus fixture](../../../apps/workbench/postgres/fixtures/development-corpus.json). Do not create another corpus, edit labels to hide misses or reseed a populated database. The expected fixture identity is `development-corpus-v1`; actual source/version/chunk counts, corpus revision, schema/image/backend/UI versions and timestamp must be captured during execution.

The intended profile is `postgres-fts-baseline` with raw score type `postgres_ts_rank_cd`; the browser obtains the actual approved revision/workspace from capabilities. Native PostgreSQL `simple` FTS with `ts_rank_cd` is neither BM25 nor a probability. These small synthetic-source labels are a regression gate, not a production relevance or semantic-quality claim.

Each question labels one relevant source:

- `hit@5 = 1` when its expected source occurs at rank 1–5, otherwise 0. Report this as **expected-source-hit-rate@5**, with “Recall@5” only in the single-relevant-source sense.
- `RR@5 = 1 / first_expected_source_rank` inside ranks 1–5, otherwise 0. Repeated chunks of one source do not earn extra credit.
- Aggregate exact cases over all **10 attempts** and diagnostic paraphrases over all **3 attempts**, separately. Misses, HTTP errors, timeouts and missing attempts remain in each denominator. The exact gate requires at least 9/10 hits and all ten real attempts; diagnostics are reported even when all miss.
- Successful-empty rate uses successful HTTP 200 search responses as its denominator. HTTP/transport failure rates are separate; a failed request is not a successful empty search.
- Sort each named latency sample series and use **nearest rank**, `x[ceil(p × n) - 1]`, for p50/p95. State `n`, inclusion rules and startup/warm state. Do not remove inconvenient slow samples or insert zero for an absent duration.
- Keep server `duration_ms`, server stage durations and independently observed browser request elapsed time separate. The harness's combined query sample includes one additional explicit no-match request (**n=14** when all succeed); retain exact **n=10** and diagnostic **n=3** subgroups. The extra no-match does not alter relevance denominators. Mock faults, real invalid-request cases and restart probes do not join those query latency series. Browser elapsed time is measured by Playwright request timing through `responseEnd`, separately from server-only duration.

| Group | Attempted / required | Hit@5 | MRR@5 | Successful empty / successful 200 | Server p50/p95, n | Browser elapsed p50/p95, n |
| --- | --- | --- | --- | --- | --- | --- |
| Exact/identifier, baseline | 10 / 10 | 10/10 = 1.0 | 1.0 | 0 / 10 | 15.000 / 31.000 ms, n=10 | 18.186 / 29.578 ms, n=10 |
| Diagnostic paraphrase, baseline | 3 / 3 | 0/3 = 0.0 | 0.0 | 3 / 3 | 16.000 / 16.000 ms, n=3 | 18.771 / 20.136 ms, n=3 |

The exact result exceeds the 9/10 gate. The three diagnostic misses remain misses, not excluded samples or semantic successes. All 13 canonical attempts succeeded at HTTP level in every phase; each extra no-match request returned successful empty output. Baseline, after-API and after-database phases together contain **39 canonical attempts and 3 explicit no-match attempts**, with no relevance denominator pooled across different query groups.

| Phase | Exact hit@5 / MRR@5 | Paraphrase hit@5 / MRR@5 | All-query server p50/p95, n | All-query browser p50/p95, n |
| --- | --- | --- | --- | --- |
| Baseline | 10/10 / 1.0 | 0/3 / 0.0 | 15.000 / 31.000 ms, n=14 | 18.186 / 29.578 ms, n=14 |
| After API restart | 10/10 / 1.0 | 0/3 / 0.0 | 16.000 / 94.000 ms, n=14 | 19.209 / 95.902 ms, n=14 |
| After database restart | 10/10 / 1.0 | 0/3 / 0.0 | 16.000 / 31.000 ms, n=14 | 19.113 / 24.120 ms, n=14 |

Displayed durations are rounded to three decimals; raw values remain in each phase JSON. These are sequential warm-service samples with a fresh browser page and no cache reset, not cold-start/production SLO measurements. Some observed server totals/stages are **0 ms** on the Windows clock; they are retained genuine readings, not missing values filled with zero. Independent coarse server and browser clocks can produce small apparent inversions; their times are never subtracted or treated as interchangeable.

## Per-question observations

Labels come from the canonical fixture; actual baseline values below come from fresh Live browser requests. Every returned source is rank 1 for the exact cases, giving RR=1. The other two real phases return the same source/version/chunk ordering and raw scores.

| Group | Synthetic query label | Expected source | Actual ordered sources / first expected rank | Outcome / hit / RR |
| --- | --- | --- | --- | --- |
| Exact | `superseded` | `demo-publication` | `demo-publication` / 1 | HTTP 200 / 1 / 1 |
| Exact | `retention` | `demo-backup` | `demo-backup` / 1 | HTTP 200 / 1 / 1 |
| Exact | `GIN` | `demo-search` | `demo-search` / 1 | HTTP 200 / 1 / 1 |
| Exact | `postgres_ts_rank_cd` | `demo-search` | `demo-search` / 1 | HTTP 200 / 1 / 1 |
| Exact | `cosine` | `demo-vectors` | `demo-vectors` / 1 | HTTP 200 / 1 / 1 |
| Exact | `Composite foreign keys` | `demo-scope` | `demo-scope` / 1 | HTTP 200 / 1 / 1 |
| Exact | `Liveness` | `demo-health` | `demo-health` / 1 | HTTP 200 / 1 / 1 |
| Exact | `RAG_MVP_2026` | `demo-identifiers` | `demo-identifiers` / 1 | HTTP 200 / 1 / 1 |
| Exact | `документация` | `demo-identifiers` | `demo-identifiers` / 1 | HTTP 200 / 1 / 1 |
| Exact | `credentials` | `demo-security` | `demo-security` / 1 | HTTP 200 / 1 / 1 |
| Diagnostic | `How do I undo a bad release?` | `demo-publication` | `[]` / unavailable | HTTP 200 / 0 / 0 |
| Diagnostic | `Can I restore lost data?` | `demo-backup` | `[]` / unavailable | HTTP 200 / 0 / 0 |
| Diagnostic | `Чи можна знайти український документ?` | `demo-identifiers` | `[]` / unavailable | HTTP 200 / 0 / 0 |

Each [baseline](../../../tasks/evidence/eval-vertical-2026-11-22/baseline-browser.json), [after-API](../../../tasks/evidence/eval-vertical-2026-11-22/after-api-browser.json) and [after-database](../../../tasks/evidence/eval-vertical-2026-11-22/after-database-browser.json) artifact preserves per-attempt IDs, source/version/chunk identities, rank/raw score, content hash, stages, profile/corpus revision and independent durations. The audit matches **39/39 canonical browser/HTTP/SQL cases** and **three additional browser/HTTP empty responses**; those extra no-match probes were not separately queried through the SQL adapter. **45 request IDs and 45 trace IDs** are unique across browser successes/real request errors, and **42 successful search run IDs** are unique.

For example, baseline `exact-01` returned `demo-publication-v1` / `demo-publication-chunk-1`, rank 1, raw score **0.10000000149011612** of type `postgres_ts_rank_cd`. Request `b321669109704f4bbc8b252181ea61f5`, trace `e42501bc36264259b440ac7d4018a90f`, and run `6f7c729afba54945bc63dd377afce2a3` were verified in UI details/JSON at capture; later reloads clear session history. Its actual stages were corpus load **16.00000000325963 ms**, retrieval **0 ms**, projection **0 ms**, matching raw response attributes; missing physical page remained “Page unavailable.” Retrieved text was compared in memory and recorded as SHA256, not exported as a second corpus.

## Observed backend baseline

These independently observed backend checks corroborate the completed browser evaluation:

- `backend-lexical-tests.xml` / `.log`: **38 passed**, zero skips; test fixtures own/clean fresh guarded disposable `rag_test_...` databases rather than mutate the main corpus.
- `backend-http-durability.json`, baseline phase: all ten exact targets found, all three diagnostic paraphrases miss, explicit no-match query returns HTTP 200 with no results; **8 sources, 8 chunks, 1,808 content bytes**. Empty input remains an invalid request.
- `backend-sql-baseline.json`: **13/13** canonical HTTP/SQL comparisons agree on source/version/chunk IDs, rank, raw score and content SHA256 through read-only `PostgresPersistence` calls.
- Corpus revision: `corpus-b30ac0b84585409663a73375da38f9e1b74d5ca288c6b2139c69c6975c1b21ac`. PostgreSQL **17.10**, pgvector **0.8.2**, schema **0001**; existing named volume `rag-workbench_postgres_data`.
- Pinned image digest: `feb68f4f15446397d8cac7f4fe48fe4586de83160d1fc48b46283312d1a33966`. Runtime versions: Python **3.12.1**, Haystack **3.5.0**, FastAPI **0.165.0**, Starlette **1.10.0**, psycopg **3.3.9**, pool **3.3.3**, httpx **0.28.1**.

Artifacts are in `tasks/evidence/eval-vertical-2026-11-22/`. The separate [historical lexical HTTP](../../../tasks/evidence/postgres-lexical-http-2026-11-21.json), [backend test](../../../tasks/evidence/postgres-lexical-tests-2026-11-21.xml) and [database restart](../../../tasks/evidence/postgresql-restart-2026-11-21.json) records remain unchanged, not recast as current execution.

## Actual outages, recovery and independent faults

| Lane / scenario | Observed HTTP / code | Correlation and UI behavior |
| --- | --- | --- |
| Real invalid body | 400 / `INVALID_REQUEST` | Actual request/trace IDs, no server run ID expected, visible error parity; no fixture results |
| Real unknown workspace | 404 / `WORKSPACE_NOT_FOUND` | Actual request/trace IDs and no foreign data; no fixture results |
| Real stale profile | 409 / `PROFILE_NOT_AVAILABLE` | Actual request/trace IDs, explicit refresh and no automatic search retry |
| Real stopped API | Proxy 502 / `INVALID_GATEWAY_RESPONSE` | No server request/trace/run ID invented; mode remains Live; refresh shows Offline |
| Real stopped database | 503 / `DEPENDENCY_UNAVAILABLE` | Actual request/trace/run IDs; mode remains Live; refresh shows Not ready |
| Mock fault injection | 400/404/409/429/503/504/502, network rejection, malformed 200 | Nine separately labeled injected error cases; safe visible outcomes, no fabricated Live success |

[API recovery](../../../tasks/evidence/eval-vertical-2026-11-22/api-recovery.json) replaced verified API process **32840 → 35724**. [Database recovery](../../../tasks/evidence/eval-vertical-2026-11-22/database-recovery.json) stopped/started the same container `b4483d166afe280b94615c5fac700a03f2dd464e31a70864b53e23b3c11363a0` on the same `rag-workbench_postgres_data` volume; `started_at` changed from `2026-11-21T14:48:11.920076956Z` to `2026-11-22T11:57:19.614428225Z`. Neither recovery seeded, migrated or recreated the data. All three snapshots retain 8/8 sources/chunks, 1,808 content bytes, active versions/content hashes, ledger/image and corpus revision.

The [strengthened race evidence](../../../tasks/evidence/eval-vertical-2026-11-22/mock-races-browser.json) verifies delayed query/mode responses while the mock transport ignores abort. Active output and Runs history retain one legitimate completion plus the expected locally interrupted runs; the late server run ID never commits. Stop remains **InterruptedLocally**, not proof of server cancellation. Injected markup/instructions remain inert. Existing frontend tests additionally cover context invalidation; this browser result does not claim a second selectable production workspace.

## Non-destructive real-service runbook

Run from the repository root unless a command explicitly changes directory. Use the existing local environment and container/volume; do not delete volumes, reset the database, migrate or seed as part of acceptance.

1. Record Hatch/Node/npm/Docker versions and the source/build reference. Inspect existing readiness/capabilities/document metadata before starting anything; preserve current source/version/chunk IDs and corpus revision. If corpus identity differs from the canonical eight-source synthetic fixture, stop the gold comparison and report the mismatch rather than overwriting data.
2. Load existing app-only credentials in the service terminal with `. ./apps/workbench/postgres/use-dev-env.ps1`; never print/export the environment or DSN. Start `hatch run workbench-api:serve` only if the existing service is not already running. The complete `start.ps1` launcher reuses healthy services and does not migrate/seed; ensure the browser's served build matches the inspected source.
3. Confirm real readiness 200, the approved profile/revision and server-authorized development workspace. Run Vite preview/dev with its existing `/api/v1` proxy to 8011. The constructor validator on 8010 is independent and needed only for its regression smoke.
4. Open explicit Live mode, create the approved three-node Keyword search graph, and run each canonical query with `top_k=5`. Capture actual outgoing four-field requests and incoming responses; no response interception is permitted for success/quality cases. Match rendered order/identity/raw scores, JSON, page availability, stages and correlation to those responses.
5. Exercise discriminating `retention`/`GIN` and a safe zero-hit term. Arrange real invalid-body/profile/workspace requests explicitly and verify the actual 400/409/404 envelopes; label any request mutation as a negative test arrangement. A raw API probe alone does not establish a UI-visible error.
6. Perform a real API outage using only the verified task-owned service process. Observe Live transport failure without automatic Preview/fixture fallback. Restart the same application configuration and re-query; IDs/revision must match, while fresh request/run/trace IDs should differ.
7. Use the supervised recovery runner below to stop/start only the verified existing PostgreSQL container. It checks project/service labels and the baseline volume, restores the service in `finally`, waits for qualification and repeats browser/SQL comparisons. Start pagination afresh if its cursor expired; never reseed to recover.
8. Run the targeted real backend/SQL baseline and existing Preview/validation smokes. Capture each exact command, exit status, counts and skips. The backend integration tests use their explicit disposable test-database contour, not privileged writes to the main corpus.

The executed operator path uses the repository runners, which load the canonical fixture and inject configuration rather than run an unconfigured browser function. From the repository root:

```powershell
. ./apps/workbench/postgres/use-dev-env.ps1
hatch run workbench-api:python -m scripts.workbench_evaluation_probe baseline
Push-Location apps/workbench/web
npx --yes --package @playwright/cli playwright-cli -s=eval20261122 open http://127.0.0.1:4173
Pop-Location
./scripts/run_workbench_live_evaluation.ps1 -Phase baseline
./scripts/run_workbench_recovery_evaluation.ps1 -Service api
./scripts/run_workbench_recovery_evaluation.ps1 -Service database
./scripts/run_workbench_live_evaluation.ps1 -Phase mock-races -Harness resilience
```

The recovery runner requires the baseline SQL artifact and the opened `eval20261122` browser session. It verifies the API listener process command before stopping it, and invokes browser phases in fresh PowerShell processes. The phase runner loads the fixture once, records its SHA256, generates a wrapper under ignored `output/playwright/`, and preserves a sanitized failed report if a harness throws. Actual phase names are `baseline`, `after-api`, `after-database`, with separate outage/reconnect and mock phases. Returned browser data is also stored as `window.__workbenchEvaluationReport`.

## Separate mock-fault lane

After real captures, the original `live-search-smoke.js` supplied nine well-formed/malformed/network error cases and a delayed local Stop. The new resilience harness supplied query/mode races and inert markup. [Sanitized legacy smoke output](../../../tasks/evidence/eval-vertical-2026-11-22/live-regression-cli.txt) and the race artifact label these arrangements separately. They do not prove actual backend saturation/deadlines; those server boundaries are covered by the 38 real backend integration tests.

No mock response contributes to real hit-rate/MRR/latency. Real outage assertions and all injected fault observations contain **zero fixture fallback/false Live completion**. Independent [Preview](../../../tasks/evidence/eval-vertical-2026-11-22/preview-browser.txt) and [validator](../../../tasks/evidence/eval-vertical-2026-11-22/validator-browser.txt) smokes passed, preserving their distinct fixture versus constructor-only meanings.

## Execution log, environment and limitations

| Executed check | Actual result / artifact |
| --- | --- |
| `hatch --version` | 1.18.2 |
| `hatch run workbench-api:python -m pytest -q apps/workbench/api/tests/test_lexical_routes.py --junitxml=tasks/evidence/eval-vertical-2026-11-22/backend-lexical-tests.xml` | 38 passed, zero skips; explicit test DSNs and fresh guarded disposable databases |
| `npm run typecheck` | PASS, `frontend-typecheck.txt` |
| `npm run format:check` | PASS, `frontend-format.txt` |
| `npm test -- --reporter=default --reporter=junit --outputFile.junit=../../../tasks/evidence/eval-vertical-2026-11-22/frontend-tests.xml` | 259 passed; text/JUnit artifacts |
| `npm run build` | PASS, `frontend-build.txt` |
| Probe Ruff, Ruff format and mypy; browser JS `node --check` | PASS; final checks rerun |
| Existing Preview, validation and Live regression browser smokes | PASS independently; real and injected lanes identified |
| Runner failure-preservation negative probe | Expected failing harness retained; [meta-test PASS](../../../tasks/evidence/eval-vertical-2026-11-22/runner-failure-preservation-test.json) |

The host is Windows, with Node **v24.15.0**, npm **11.2.0**, and Headless Chrome **157.0.8103.80**. The [manifest](../../../tasks/evidence/eval-vertical-2026-11-22/source-build-manifest.json) records the inspected base plus dirty source hashes, **121 source files** and **73 build files**; the four served HTML/JS/CSS checks match the built `dist` bytes. Baseline screenshots at [1440 px](../../../output/playwright/workbench-live-evaluation-baseline-1440.png) and [1100 px](../../../output/playwright/workbench-live-evaluation-baseline-1100.png) are local artifacts.

Two evidence weaknesses were corrected, without changing application code: the race proof now checks Runs history for a late commit, and the PowerShell wrapper retains sanitized failure JSON when a harness throws. The deliberate unsupported-phase failure is a runner meta-test, not a product outage or a removed gold-query failure. The [automation incident record](../../../tasks/evidence/eval-vertical-2026-11-22/automation-incidents.json) retains initially empty CLI output after a hosted-shell/Hatch sequence; the service was restored, browser execution isolated in a fresh child PowerShell, and the entire recovery gate rerun successfully.

After the mock lane, the browser was restored to a real, unmocked Live `retention` search: HTTP 200, `demo-backup`, unchanged corpus. This [final restoration](../../../tasks/evidence/eval-vertical-2026-11-22/final-live-browser.json) is excluded from all qualification metrics. Its first one-off cleanup attempt omitted the Pipelines navigation and failed before searching; that selector incident is retained, then the corrected cleanup passed. Neither automation incident is represented as a product defect or erased query observation.

The read-only artifact audit found no configured credential values or full synthetic passage bodies in collected artifacts; hashes retain content parity without duplicating the corpus. Machine evidence remains local/ignored under the existing policy, not uploaded or represented as a remote-server run. Historical evidence and unrelated parser/chunker work remain preserved. Docusaurus build and the full upstream Haystack suite were not run; neither changes the scoped application acceptance result.

This pass qualifies only the tested local eight-source synthetic lexical slice. It does not establish production relevance/latency, semantic recall, ingestion, embeddings, generation, remote deployment, production authorization or persisted server-side run history. Evidence retention/access for future non-synthetic content needs its own reviewed policy.

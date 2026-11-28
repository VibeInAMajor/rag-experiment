# TASK-UI-005 verification

- **Date** 2026-11-28 (Europe/Kyiv)
- **Baseline** `e20568b`, including the shared Sol capacity from `997e694`
- **Status** Implemented and verified locally. Live provider and joint qualification gates remain open.

## Configured profiles

| Model | Profile | Input admission units | Generated tokens | Eligible evidence |
| --- | --- | ---: | ---: | --- |
| GPT-6.1 Sol | `semantic-review` | 16,384 | 32,000 | Operator-approved historical v8 pass on runtime 0.3.1 |
| GPT-6.2 Sol | `semantic-review-6.2` | 16,384 | 32,000 | Offline capacity checks only. Model selection is disabled. |

Both profiles also expose the current 16 KiB request envelope, 128 KiB response limit, 45-second deadline and 30-minute explicit cache policy. The real catalog returned both profiles through the Workbench API. The eligibility projection carries the v8 fingerprint and timestamp for the primary profile. [Historical pilot](../dataset-semantic-pilot-full-2026-11-28/report.md) · [MAF qualification record](../../maf/TASK-MAF-002-semantic-judge-agent.md)

On 2026-11-28 in Kyiv, the OpenAI Standard short-context table listed both models at $2.00 ordinary input, $0.10 cache reads, $2.50 30-minute cache writes and $10.00 output per million tokens. The runtime's existing conservative estimator applies the 30-minute write rate to input outside reported cache reads and includes its configured regional allowance. Historical and current estimates are before any account credits. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

## Verification levels

| Level | Execution and result |
| --- | --- |
| Standalone MAF | From `apps/maf`: `hatch run check`, `hatch run types`, `hatch run test` (116 passed), `hatch run calibrate --check` (32 frozen cases), and `hatch build` (sdist and wheel). |
| Workbench API | From the root: `hatch run workbench-api:check`, `hatch run workbench-api:types` and 53 focused HTTP and configuration tests, including schemas, decimal accounting, charged failures, duplicate records, retention, scope, symlink rejection, and revision-checked selection. |
| Workbench web | From `apps/workbench/web`: `npm run typecheck`, `npm run format:check`, `npm test` (399 passed) and `npm run build`. The navigation test covers the URL remount and the unsaved Configuration guard. |
| Actual MAF to HTTP | An unpinned synthetic Judge input entered the installed CLI with `--use-operations-selection --data-classification synthetic`. The CLI froze the same default revision published by the API, recorded `EGRESS_DISABLED` with zero provider requests, and served the complete lifecycle with no cost or usage from both history endpoints. |
| Actual DATASET-002 caller | Reused the 46 saved v8 checkpoints through the existing local caller on the pinned runtime 0.3.1 identity. The verification disabled the provider-call and key-loading functions. The HTTP projection returned 46 reused cases, 0 physical requests, and a null estimated cost. Checkpoint and audit payloads remained with the evaluator. |

## Browser verification

The [Playwright smoke script](../../../apps/workbench/web/scripts/agents-smoke.js) drove local Chrome against the real Workbench API and Vite frontend on isolated loopback ports 8123 and 8124. The catalog came from the installed MAF CLI. The smoke appended controlled, labeled usage events in an isolated journal and read them through real HTTP. It checked navigation, eligibility, limits, rates, pending reserve, physical requests, reuse, history filtering, reload, disconnect, recovery and persistent selection with a simulated eligible alternate profile.

The cost fixture uses one physical request per completed call, with 100 input tokens including 20 cache-read tokens and 10 output tokens including 3 reasoning tokens. The expected estimate per request is USD 0.0003322, using the existing regional allowance. The checkpoint reuse event adds one case and zero physical requests. The browser did not send a provider request.

Across 30 completed-call observations, event commit to matching activity row took **1,036 ms p95** using the nearest-rank calculation (635–1,037 ms sample range). The terminal display matched the fixture's 30 physical requests, one reused checkpoint, 3,300 total tokens and USD 0.0099660. The check timed a healthy local connection and recorded browser DOM updates, without provider latency.

## Scope and open gates

- MAF terminal metadata currently reports cache-read counts. Ordinary input and cache-write counts remain unavailable unless a provider measurement explicitly supplies them. The browser does not derive either from the remaining input count.
- Provider traffic was disabled during verification. Real-provider post-call telemetry for this UI and a jointly qualified GPT-6.2 Sol arm remain unverified. The prior v8 proof remains historical.
- `hatch run workbench-api:test --tb=short` returned 1,184 passed, 225 skipped and the same two failures seen on the baseline. The baseline capability expectation omits `upload_folders`, and the Markdown test expects revision `r1` while the configured parser reports `r3`. The six new agent route tests passed.
- The implementation commit containing this report includes the Workbench UI, API, schema, release note, project map and MAF catalog/operations support. The existing protected DATASET-002 caller changes live in the two ignored paths documented in the task's section I.4.

[Operator setup and rollback](../../../apps/workbench/api/README.md#local-agent-operations) · [TASK-UI-005](../../TASK-UI-005-agent-operations-model-selection-and-live-usage.md)

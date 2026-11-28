# Standalone MAF agent runtime

`apps/maf` is an independent Hatch application that runs registered Python agents through Microsoft Agent Framework and OpenAI Responses. It ships a synthetic smoke agent and a Semantic Judge with four typed modes. The judge evaluates only text supplied by the caller. [Semantic Judge contract and calibration](SEMANTIC_JUDGE.md)

## Setup and offline checks

Run from `apps/maf/` or the root of its standalone copy.

```sh
hatch --version
hatch run check
hatch run test
hatch run types
```

Hatch creates a Python 3.12 environment. The first setup may need package-index access. The application and tests do not need OpenAI credentials to start, and tests use local fakes for provider calls. [Dependency manifest](pyproject.toml)

| Runtime dependency | Version | License |
| --- | --- | --- |
| `agent-framework-core` | [1.26.0](https://pypi.org/project/agent-framework-core/1.26.0/) | MIT |
| `agent-framework-openai` | [1.18.2](https://pypi.org/project/agent-framework-openai/1.18.2/) | MIT |
| `openai` | [3.60.0](https://pypi.org/project/openai/3.60.0/) | Apache-2.0 |
| `httpx2` | [2.16.2](https://pypi.org/project/httpx2/2.16.2/) | BSD-3-Clause |
| `pydantic` | [2.14.4](https://pypi.org/project/pydantic/2.14.4/) | MIT |

## Run the live smoke

Provision `OPENAI_API_KEY` in the launching process's environment. The app reads it only for an invocation that passes local admission. `apps/maf/.env` is ignored by Git. A local launcher can export the key from that file into its own process. [Environment variable example](.env.example)

```sh
hatch run smoke --allow-external
```

This submits the built-in synthetic input `The synthetic marker is cobalt.` using `structured-smoke` and `semantic-review`. A successful smoke returns `{"marker":"cobalt"}` and provider-reported model and usage data when available. Missing credentials or model entitlement block live qualification. The app makes a single attempt.

| Profile | Model | Qualification |
| --- | --- | --- |
| `semantic-review` | `gpt-6.1-sol` | Default. Existing v8 live evidence. |
| `semantic-review-6.2` | `gpt-6.2-sol` | Selectable. Verified offline for the shared limits. |

Both Sol models use the same application limits and the same four Semantic Judge modes through direct OpenAI Responses. Supported reasoning levels are `low`, `medium`, `high`, `xhigh` and `max`. The base profile IDs above use `MAF_OPENAI_REASONING_EFFORT` (default `medium`). The loader also registers effort-specific variants for the other levels, such as `semantic-review-high`, `semantic-review-max` and `semantic-review-6.2-low`. These are real runtime profiles with the same resource caps, not frontend-only options. The operations catalog exports all five levels per model. [Shared limits and verification](../../tasks/maf/TASK-MAF-002-semantic-judge-agent.md#shared-sol-limits-only--operator-decision) · [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) · [Model capabilities](https://developers.openai.com/api/docs/models)

Provider support and agent qualification are separate. Historical v8 evidence applies only to the original GPT-6.1 Sol Medium default. Additional levels are discoverable but cannot be activated through qualified Workbench selection until their qualification is recorded; they do not inherit the Medium evidence. Explicit CLI invocations still require the existing caller-owned egress, classification, budget and evaluation checks.

## JSON invocation contract v1

Supply one UTF-8 JSON object on stdin and close the input stream. The installed `maf-agent` entry point and `hatch run python -m agent_runtime` use the same contract. Each JSON invocation writes one result envelope to stdout. Save the following synthetic example to `request.json`.

```json
{
  "schema_version": 1,
  "request_id": "marker-001",
  "agent_id": "structured-smoke",
  "profile_id": "semantic-review",
  "input": {"text": "The synthetic marker is cobalt."}
}
```

```sh
hatch run run --allow-external --data-classification synthetic < request.json
```

```powershell
Get-Content -Raw -Encoding UTF8 request.json | hatch run run --allow-external --data-classification synthetic
```

Use opaque IDs of up to 64 ASCII characters and select an agent and profile from the local registry. IDs start with a letter or digit and may also contain `_`, `.`, `:`, or `-`. The parser rejects IDs that start with `sk-` or `bearer`, extra request fields, and duplicate JSON keys. The smoke agent accepts `input.text` of 1–2,048 characters and returns a `marker` of 1–40 lowercase ASCII letters. External execution requires both `--allow-external` and a caller-asserted `--data-classification synthetic` or `--data-classification public`. The smoke command supplies the synthetic classification for its own fixture. [Transport DTOs](src/agent_runtime/contracts.py) · [Smoke fixture and schemas](src/agent_runtime/agents/structured_smoke.py)

The result contains `schema_version`, `request_id`, `agent_id`, `profile_id`, `outcome`, `output`, `error`, and `metadata`. An `ok` outcome carries the typed `output`. An `error` outcome carries an `error.code` and a null `output`. IDs may be null when a request cannot be decoded. Metadata contains the provider, requested and returned model IDs, runtime/prompt/output schema revisions, timing, correlation ID, usage, request and retry counts, and versioned cost estimates. Cost estimates use decimal strings. Unavailable provider model or usage information is `null`. Input, output, reasoning, and cached input token counts reflect provider reports when present.

## Agent operations

`hatch run run --operations-catalog` returns only the versioned local catalog. It reports the shared Semantic Judge limits and the published OpenAI Standard rates. GPT-6.1 Sol is the default with operator-approved historical v8 evidence. GPT-6.2 Sol has matching offline-tested limits and requires its own qualifying evidence for selection. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)

After the [Workbench operator setup](../workbench/api/README.md#local-agent-operations), use `hatch run run --use-operations-selection` with a version 1 Semantic Judge request that omits `profile_id`. The CLI reads the persisted selection at admission, binds its revision and emits the usual single terminal invocation result. Use `--record-operations` for an invocation with an explicitly pinned profile. Both modes retain the normal external-access and classification gates.

The checkout launcher initializes `.local/workbench-agent-operations` with `hatch run run --operations-catalog-to <absolute directory>`. The checkout calibration runner and recorded CLI invocations discover the initialized journal even from another terminal. A standalone installation can use `WORKBENCH_AGENT_OPERATIONS_DIR` to point to an existing journal. Calibration retains its pinned profile and report format. A recorded operation includes lifecycle, measured usage, estimated cost, safe failure codes and opaque IDs. Prompt text, evidence, verdict payloads and credentials stay outside the journal.

The CLI returns exit code `0` on success, `130` on cancellation, and `1` for other error envelopes. CLI option errors use argparse's exit code `2` and stderr. For a credential-free transport check, pipe the sample through `hatch run run` with no options. It emits `EGRESS_DISABLED` and reports zero provider requests.

| Error code | Condition |
| --- | --- |
| `INVALID_INPUT` | Malformed, unsupported, or oversized request |
| `UNKNOWN_AGENT`, `UNKNOWN_PROFILE` | Requested entry is absent from the local registry |
| `UNSUPPORTED_CAPABILITY`, `CONFIGURATION_ERROR` | Profile lacks an agent requirement or local settings are invalid |
| `EGRESS_DISABLED`, `MISSING_CREDENTIALS`, `PRIVACY_POLICY` | External execution was not authorized, the API key is unavailable, or a privacy check failed |
| `BUDGET_EXCEEDED` | The run budget is below the preflight estimate or provider-reported usage exceeds a token cap |
| `TIMEOUT`, `CANCELLED` | The invocation exceeded its deadline or was interrupted |
| `RATE_LIMITED`, `PROVIDER_FAILURE` | Provider rate limit or another upstream failure |
| `REFUSAL`, `INCOMPLETE_OUTPUT`, `INVALID_OUTPUT`, `RESPONSE_TOO_LARGE` | The response was refused, incomplete, schema-invalid, or over the response byte limit |

## Execution limits and estimated spend

| Limit | Per invocation |
| --- | --- |
| Stdin | 16,384 UTF-8 bytes (16 KiB) |
| Estimated input ceiling | 16,384 including framing reserve for either Sol profile |
| Provider-generated tokens, including reasoning | 32,000 for either Sol profile |
| Provider response body | 128 KiB |
| Provider execution deadline | 45 seconds after local admission |
| Provider requests / concurrency / retries | 1 / 1 / 0 |
| Estimated spend | USD 0.40 by default, configurable through `--max-cost-usd` up to USD 1 |

The standalone runtime reads the complete JSON envelope within the stdin limit. Profile admission separately adds the UTF-8 sizes of the validated input, instructions and output schema, and a 1,024-unit framing reserve. It checks this conservative estimate before external execution and checks reported usage after the call.

Maximum spend uses the full profile input and output caps, the Standard short-context cache-write input rate and a regional allowance. Runtime 0.3.3 reserves USD 0.397056 per call for either configured Sol profile. Use the USD 0.40 default budget or set `--max-cost-usd` at or above the reserve. The independent response-body ceiling is 128 KiB and the execution deadline is 45 seconds. The reserve is a ceiling. A separate usage estimate requires a matching returned model and reported input and output counts. Actual billing can differ. Callers running multiple processes own their combined budget and concurrency. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) · [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

## Data handling

Use only synthetic input or material approved for external evaluation. Keep credentials, internal paths, private documents and private identifiers out of requests. The runtime treats submitted text as data and starts a fresh agent invocation with no tools, retrieval access, web search, or conversation carry-over. The provider adapter verifies `store=false` on the wire and allows only the fixed OpenAI Responses endpoint. It selects Standard processing and explicit prompt caching with no breakpoints. OpenAI's separate abuse-monitoring and data retention policies still apply. [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)

The CLI keeps provider diagnostics, raw payloads, credentials and reasoning traces out of logs. Structured output is returned to the caller over stdout. The caller owns the handling of both the input it submits and the output it receives.

## Qualification

Disconnect the caller or remove the standalone app to roll back. Workbench startup and RAG data require no migration. [Offline checks and live smoke status](../../tasks/maf/TASK-MAF-001-standalone-agent-runtime.md)

# Standalone MAF agent runtime

`apps/maf` runs registered Python agents through Microsoft Agent Framework and OpenAI Responses. The built-in synthetic agent exercises structured output. The application runs from this directory or an independent copy with its own Hatch environment. It needs no Workbench server, Haystack installation, database, corpus, or local inference service. The Semantic Judge is planned separately. [Semantic Judge task](../../tasks/maf/TASK-MAF-002-semantic-judge-agent.md)

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

Provision `OPENAI_API_KEY` in the launching process's environment through your secret manager. The app reads it only for an invocation that passes local admission. Configuration comes from the process environment. [Environment variable example](.env.example)

```sh
hatch run smoke --allow-external
```

This submits the built-in synthetic input `The synthetic marker is cobalt.` using `structured-smoke` and `semantic-review`. A successful smoke returns `{"marker":"cobalt"}` and provider-reported model and usage data when available. Missing credentials or model entitlement block live qualification. The app makes a single attempt.

| Profile | Model | Qualification |
| --- | --- | --- |
| `semantic-review` | `gpt-6.1-sol` | Used by the live smoke. Account access is checked by that run |
| `semantic-review-6.2` | `gpt-6.2-sol` | Requires separate live qualification |

Both profiles use direct OpenAI Responses. Set `MAF_OPENAI_REASONING_EFFORT` to `low`, `medium`, `high`, or `xhigh`. The default is `medium`. Model selection is explicit through `profile_id`. [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) · [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)

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
| Stdin | 8,192 UTF-8 bytes |
| Estimated input tokens | 8,192, including framing reserve |
| Provider-generated tokens | 2,048, including reasoning |
| Provider response body | 128 KiB |
| Provider execution deadline | 45 seconds after local admission |
| Provider requests / concurrency / retries | 1 / 1 / 0 |
| Estimated spend | USD 0.10 by default, configurable through `--max-cost-usd` up to USD 1 |

Admission estimates input size from UTF-8 bytes plus a framing reserve. Maximum spend reserves the full profile input and output caps using the Standard short-context cache-write input rate and a regional allowance. The current profiles each reserve USD 0.045056. A usage-based estimate requires a matching returned model and reported input and output counts. Actual billing can differ. Callers running multiple processes own their combined budget and concurrency. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) · [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

## Data handling

Use only synthetic input or material approved for external evaluation. Keep credentials, internal paths, private documents and private identifiers out of requests. The runtime treats submitted text as data and starts a fresh agent invocation with no tools, retrieval access, web search, or conversation carry-over. The provider adapter verifies `store=false` on the wire and allows only the fixed OpenAI Responses endpoint. It selects Standard processing and explicit prompt caching with no breakpoints. OpenAI's separate abuse-monitoring and data retention policies still apply. [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)

The CLI keeps provider diagnostics, raw payloads, credentials and reasoning traces out of logs. Structured output is returned to the caller over stdout. The caller owns the handling of both the input it submits and the output it receives.

## Qualification

Disconnect the caller or remove the standalone app to roll back. Workbench startup and RAG data require no migration. [Offline checks and live smoke status](../../tasks/maf/TASK-MAF-001-standalone-agent-runtime.md)

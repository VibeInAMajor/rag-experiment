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
| `semantic-review` | `gpt-6.1-sol` | Synthetic live smoke passed on 2026-11-27 |
| `semantic-review-6.2` | `gpt-6.2-sol` | Pending shared Sol policy and joint qualification (see below) |

The [planned shared Sol policy](../../tasks/maf/TASK-MAF-002-semantic-judge-agent.md#shared-sol-runtime-policy-and-joint-qualification--2026-11-28) requires identical application limits (16,384 estimated input units and 32,000 output tokens) and one joint qualification protocol with evidence for both model arms. The current checked-in limits below are not yet aligned. Prices remain model-specific. Both profiles use direct OpenAI Responses. Set `MAF_OPENAI_REASONING_EFFORT` to `low`, `medium`, `high`, or `xhigh`. The default is `medium`. Model selection is explicit through `profile_id`. [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) · [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol)

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
| Stdin | 16,384 UTF-8 bytes (16 KiB) |
| Estimated input ceiling | 16,384 with `semantic-review` and 8,192 with `semantic-review-6.2`, including framing reserve |
| Provider-generated tokens, including reasoning | 32,000 with `semantic-review` and 2,048 with `semantic-review-6.2` |
| Provider response body | 128 KiB |
| Provider execution deadline | 45 seconds after local admission |
| Provider requests / concurrency / retries | 1 / 1 / 0 |
| Estimated spend | USD 0.40 by default, configurable through `--max-cost-usd` up to USD 1 |

The standalone runtime reads the complete JSON envelope within the stdin limit. Profile admission separately adds the UTF-8 sizes of the validated input, instructions and output schema, and a 1,024-unit framing reserve. It checks this conservative estimate before external execution and checks reported usage after the call.

Maximum spend uses the full profile input and output caps, the Standard short-context cache-write input rate and a regional allowance. The `semantic-review` profile reserves USD 0.397056 per call and `semantic-review-6.2` reserves USD 0.045056. Use the default budget or set `--max-cost-usd` at or above the reserve for the selected profile. The 0.3.2 ceiling is a capacity candidate pending fresh qualification; the last measured v8 PASS used 0.3.1 at 4,096 output tokens. The independent 128 KiB response-body cap and 45-second execution deadline remain unchanged. A higher token ceiling does not guarantee completion or imply actual spend. A usage-based estimate requires a matching returned model and reported input and output counts. Actual billing can differ. Callers running multiple processes own their combined budget and concurrency. [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) · [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

## Data handling

Use only synthetic input or material approved for external evaluation. Keep credentials, internal paths, private documents and private identifiers out of requests. The runtime treats submitted text as data and starts a fresh agent invocation with no tools, retrieval access, web search, or conversation carry-over. The provider adapter verifies `store=false` on the wire and allows only the fixed OpenAI Responses endpoint. It selects Standard processing and explicit prompt caching with no breakpoints. OpenAI's separate abuse-monitoring and data retention policies still apply. [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)

The CLI keeps provider diagnostics, raw payloads, credentials and reasoning traces out of logs. Structured output is returned to the caller over stdout. The caller owns the handling of both the input it submits and the output it receives.

## Qualification

Disconnect the caller or remove the standalone app to roll back. Workbench startup and RAG data require no migration. [Offline checks and live smoke status](../../tasks/maf/TASK-MAF-001-standalone-agent-runtime.md)

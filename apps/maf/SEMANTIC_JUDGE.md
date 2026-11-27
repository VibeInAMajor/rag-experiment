# Semantic Judge

`semantic-judge` is a standalone MAF agent for evaluating supplied evidence. Select the `semantic-review` profile and one of four modes. Each invocation starts fresh and returns its prompt and output schema revisions. The caller supplies authorized text and owns reference approval, corpus coverage, and downstream scoring. [Runtime transport and limits](README.md)

## Invoke the judge

Save this authored example as `judge-request.json` in `apps/maf`.

```json
{
  "schema_version": 1,
  "request_id": "valve-reference",
  "agent_id": "semantic-judge",
  "profile_id": "semantic-review",
  "input": {
    "mode": "derive_reference",
    "question": "At what pressure does the valve open?",
    "language": "en",
    "scope": {"description": "The valve specification excerpt", "complete": false},
    "sources": [
      {
        "id": "valve-spec",
        "start": 0,
        "end": 25,
        "sha256": "f17dd8f5a18a185538f243ccb751afaee5e057112540ea019f477d6ac7375174",
        "text": "The valve opens at 3 bar."
      }
    ]
  }
}
```

```sh
hatch run run --allow-external --data-classification synthetic < judge-request.json
```

```powershell
Get-Content -Raw -Encoding UTF8 judge-request.json | hatch run run --allow-external --data-classification synthetic
```

A successful response has `outcome: "ok"` and a typed `output` containing `mode`, `answerability`, the scoped reference answer, separate facts, and exact evidence. For this example the reference should identify **3 bar** as a required fact. Each object uses a strict schema and rejects extra fields. Set `language` to `en`, `ru`, or `uk`. Quotes preserve the source's original language and characters. For a credential-free transport check, omit the opt-in flags. The sample returns `EGRESS_DISABLED` and records zero provider requests. [Contract DTOs](src/agent_runtime/agents/semantic_judge/contracts.py)

## Modes

| `input.mode` | Mode-specific input | Evaluation output |
| --- | --- | --- |
| `derive_reference` | `scope` with `description` and `complete`, plus original `sources` | `answerability`, nullable `reference_answer`, constraints, individually quoted required and optional facts, and `coverage_gaps` |
| `judge_evidence` | Frozen `reference`, one `candidate` and optional original context in `sources` | `category`, `grade`, `contradiction`, candidate spans, constraint and fact assessments |
| `judge_context` | Frozen `reference` and selected `context` | `sufficiency`, useful, irrelevant, redundant and contradictory spans, constraint and fact assessments |
| `judge_answer` | Frozen `reference`, actual `answer`, selected `context`, original `sources`, and `citations` | Claim and citation assessments, correctness, completeness, relevance, abstention, constraint and fact assessments |

All modes take a question and language. Set `scope.complete` only if the caller can establish completeness of the declared eligible scope. Derivation accepts original sources and question constraints inferred from the question. The caller can compare the resulting reference with prior labels after the invocation.

Review and freeze the reference before the three downstream modes. Supply `reference` with an opaque `revision`, the derived `answerability`, `constraints` containing `id` and `description`, and `facts` containing `id`, `statement`, and `required`. Keep the original quotations from the derivation in the caller's reference record. Downstream evidence and citations resolve against the excerpts supplied for that invocation. Provide an empty list for an allowed empty `sources` or `citations` field. Answer citations use `id` and the corresponding `source_id`.

### Evidence rubric

| Category | Grade | Evidence requirement |
| --- | ---: | --- |
| `direct` | 3 | Candidate text establishes at least one complete required fact within the requested scope. |
| `partial` | 1 | Candidate text gives concrete, incomplete support for a required fact. |
| `supporting` | 1 | Candidate text contributes materially useful context for a required fact. The rationale identifies the contribution. |
| `topically_related` | 0 | Shared terms, entities or subject with no answer support. |
| `irrelevant` | 0 | Candidate lacks useful evidence for the question. |
| `wrong_scope` | 0 | Candidate pertains to a different entity, event, time, edition, unit or other question constraint. |
| `contradictory` | 0 | Candidate directly conflicts with a scoped reference fact. |
| `unknown` | `null` | The available evidence leaves the assessment ambiguous. |

Passage grade measures the passage's contribution. Context sufficiency measures coverage of all required facts and applicable constraints across the selected pack. A directly supported fact can coexist with other missing facts, irrelevant spans, or conflicting evidence.

### Quote and scope validation

Every excerpt contains `id`, `start`, `end`, `sha256`, and `text`. IDs are opaque and unique across the supplied excerpts. Ranges are half-open Unicode code-point offsets in the source. Hash the UTF-8 bytes of the exact excerpt text, preserving whitespace. Every quote includes `source_id`, `text`, `start`, and `end`. The validator checks supplied numeric offsets against the text. When both quote offsets are null, the validator can resolve a unique exact match to its source coordinates. A repeated quote requires explicit matching offsets or a longer exact quote that is unique. Positive candidate grades require a quote from the candidate linked to a required fact. [Evidence validators](src/agent_runtime/agents/semantic_judge/validation.py)

`not_found_in_complete_eligible_scope` requires complete declared scope. `not_found_in_supplied_excerpt` records absence within an incomplete excerpt set. `partially_answerable` retains supported facts and records missing coverage. An unresolved semantic `unknown` verdict is a valid typed result. Provider refusal, invalid quote or ID, malformed output, and timeout use the runtime error envelope.

## Calibration and versioning

Run the control preflight from `apps/maf`. It validates the manifest and the planned request bounds without provider calls.

```sh
hatch run calibrate --check
```

With the approved project key in the launching process's `OPENAI_API_KEY`, run the frozen qualification cases.

```sh
hatch run calibrate --allow-external --report calibration/live-report.jsonl
```

The runner submits authored cases and public original-source excerpts through `semantic-review`. It checks predeclared outcomes and repeats a subset across languages or opaque IDs. Use `--development` and a separate report path to run authored development probes. Check the qualification report and its gate results before using a revision to audit a dataset. An inconclusive or disputed case remains unresolved for that dataset's caller. [Calibration task and verification](../../tasks/maf/TASK-MAF-002-semantic-judge-agent.md)

Bump the corresponding mode revision when its prompt, output contract, or rubric changes. Preserve the exact prompt and schema fingerprints together with the model/profile, control manifest digest, per-case verdicts, and observed usage. Qualify any changed revision with the same gates before adopting it. [Versioned prompts](src/agent_runtime/agents/semantic_judge/instructions.py)

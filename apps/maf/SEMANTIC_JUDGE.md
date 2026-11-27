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

`derive_reference` returns a concise `reference_answer` of at most 600 characters. The provider schema and local validator enforce the same bound. The ordered facts retain the supporting quotations and procedural detail.

Review and freeze the reference before the three downstream modes. Supply `reference` with an opaque `revision`, the derived `answerability`, `constraints` containing `id` and `description`, and `facts` containing `id`, `statement`, and `required`. Keep the original quotations from the derivation in the caller's reference record. Downstream evidence and citations resolve against the excerpts supplied for that invocation. Provide an empty list for an allowed empty `sources` or `citations` field. Answer citations use `id` and the corresponding `source_id`.

Answer completeness measures coverage of required facts by supported claims. When an answer solely declines to provide the requested answer, use `not_applicable` for factual correctness and completeness, an empty `claims` list, and a separate abstention verdict. A citation is assessed against the particular excerpt it points to. Exact quotations can demonstrate either support or contradiction.

### Evidence rubric

| Category | Grade | Evidence requirement |
| --- | ---: | --- |
| `direct` | 3 | Candidate text establishes at least one complete required fact within the requested scope. |
| `partial` | 1 | Candidate text gives concrete, incomplete support for a required fact. |
| `supporting` | 1 | Candidate text contributes materially useful context for a required fact. The rationale identifies the contribution. |
| `topically_related` | 0 | The candidate discusses the same product, service, entity or subject but supplies no answer support. |
| `irrelevant` | 0 | The candidate discusses a different subject with no meaningful overlap. |
| `wrong_scope` | 0 | Candidate pertains to a different entity, event, time, edition, unit or other question constraint. |
| `contradictory` | 0 | Candidate directly conflicts with a scoped reference fact. |
| `unknown` | `null` | The available evidence leaves the assessment ambiguous. |

Passage grade measures the passage's contribution. Context sufficiency measures coverage of all required facts and applicable constraints across the selected pack. A directly supported fact can coexist with other missing facts, irrelevant spans, or conflicting evidence.

Attribute a quoted value to the entity, event or record asked about before awarding credit. When the text leaves that attribution unresolved and establishes no separate required fact, the judge returns `unknown` with a null grade.

### Quote and scope validation

Every excerpt contains `id`, `start`, `end`, `sha256`, and `text`. IDs are opaque and unique across the supplied excerpts. Ranges are half-open Unicode code-point offsets in the source. Hash the UTF-8 bytes of the exact excerpt text, preserving whitespace. Every quote includes `source_id`, `text`, `start`, and `end`. The validator checks supplied numeric offsets against the text. When both quote offsets are null, the validator can resolve a unique exact match to its source coordinates. A repeated quote requires explicit matching offsets or a longer exact quote that is unique. Positive candidate grades require a quote from the candidate linked to a required fact. [Evidence validators](src/agent_runtime/agents/semantic_judge/validation.py)

`not_found_in_complete_eligible_scope` requires complete declared scope. `not_found_in_supplied_excerpt` records absence within an incomplete excerpt set. `partially_answerable` retains supported facts and records missing coverage. An unresolved semantic `unknown` verdict is a valid typed result. Provider refusal, invalid quote or ID, malformed output, and timeout use the runtime error envelope.

### Semantic states and qualification boundaries

Follow the repository-wide [contract consistency and review-before-change rules](../../docs-website/ENGINEERING.md#contract-consistency-and-review-before-change) before modifying the judge. The following describes qualified semantics and requirements for future evaluation work; it does not introduce a new executable contract or change the frozen v6 qualification.

A pure abstention from asserting the requested answer uses `correctness: not_applicable`, `completeness: not_applicable`, `claims: []`, and a separately assessed `abstention` verdict. This is not an operational failure and does not require fictitious material facts. Statements about what supplied excerpts cover must stay within that evidence scope; do not claim unverified corpus-wide absence. Do not hide substantive factual claims as pure abstention. Mixed answers containing substantive claims require assessment of those claims. Continue to assess supplied constraints and facts. Where mixed or cited abstention is not unambiguously represented by the current contract, define and qualify an explicit representation before extending it.

A `complete` factual verdict requires declared required facts, supported fact assessments and grounded claims covering them; a `correct` factual verdict requires grounded material claims. Do not weaken either invariant to admit pure abstention. `unknown`, `not_applicable`, and runtime `INVALID_OUTPUT` are distinct; do not map them to factual success or grade zero by default. The current prompt and regression test establish the pure-abstention representation, not exhaustive deterministic enforcement of every cross-field combination. Add positive and negative cross-field controls before qualifying new answer-evaluation behavior.

Distinguish `topically_related` (same subject without answer support) from `irrelevant` (different subject without meaningful overlap) consistently across languages. Maintain exact category repeatability under the current frozen qualification protocol. A future semantic-decision consistency metric may supplement, but must not silently replace, that gate. Define any equivalence policy before a new run and preserve material distinctions such as `wrong_scope` and `contradictory`.

When qualifying citation-support behavior for future answer-quality evaluation, explicitly check the expected status of each citation; quote, ID and offset validity alone cannot establish semantic support. The current calibration does not assert every expected citation status independently. Under [QUALITY-003](../../tasks/quality/TASK-RAG-QUALITY-003-grounded-answer-correctness-evaluation.md), distinguish original-source correctness, support in the exact generator-visible context, and context-to-original fidelity (Faithfulness-Plus). The current answer validator resolves evidence against supplied context and original sources together; that is not proof of separate faithfulness. A source the generator never received cannot establish generator-context support. Missing generator inputs or unverified coverage remain unresolved or not evaluated, as appropriate. The caller owns source coverage, generator-context capture, independent reference approval and deterministic final scoring.

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

On a failure, the local calibration checkpoint can include a bounded `failure_stage` such as `transport`, `output_schema`, or `evidence_validation`. Verdict rejections also record a fixed `failure_reason` such as `complete_without_required_facts`, `quote_not_found`, or `quote_offsets_unpaired`. For schema failures, `failure_field` may identify a declared top-level field. The public JSON envelope carries the same error codes. The report omits rejected response text, unrecognized field names and exception messages.

Bump the corresponding mode revision when its prompt, output contract, or rubric changes. Preserve the exact prompt and schema fingerprints together with the model/profile, control manifest digest, per-case verdicts, and observed usage. Qualify any changed revision with the same gates before adopting it. [Versioned prompts](src/agent_runtime/agents/semantic_judge/instructions.py)

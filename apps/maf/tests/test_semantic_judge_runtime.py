import asyncio
import json
from hashlib import sha256
from unittest.mock import AsyncMock

import pytest
from pydantic import JsonValue

from agent_runtime.agents.semantic_judge.contracts import DeriveReferenceResult
from agent_runtime.configuration import SEMANTIC_REVIEW_PROFILE, RunPolicy, load_profiles
from agent_runtime.contracts import ErrorCode, InvocationRequest
from agent_runtime.runtime import AgentApplication, AgentRuntime, ProviderObservation

_KEY = "test-only-credential"
_SOURCE = "Ship launches in July."
_QUOTE = "in July"
_INPUT: dict[str, JsonValue] = {
    "mode": "derive_reference",
    "question": "When does the ship launch?",
    "language": "en",
    "scope": {"description": "Authorized log excerpt", "complete": False},
    "sources": [
        {
            "id": "log",
            "start": 140,
            "end": 140 + len(_SOURCE),
            "sha256": sha256(_SOURCE.encode()).hexdigest(),
            "text": _SOURCE,
        }
    ],
}


def _request(*, profile: str = SEMANTIC_REVIEW_PROFILE, **overrides: JsonValue) -> InvocationRequest:
    return InvocationRequest(
        schema_version=1,
        request_id="derived",
        agent_id="semantic-judge",
        profile_id=profile,
        input={**_INPUT, **overrides},
    )


@pytest.mark.parametrize(
    ("overrides", "profile", "code"),
    [
        ({"mode": "review_old_labels"}, SEMANTIC_REVIEW_PROFILE, ErrorCode.INVALID_INPUT),
        ({"mode": ["derive_reference"]}, SEMANTIC_REVIEW_PROFILE, ErrorCode.INVALID_INPUT),
        ({"old_reference": "June"}, SEMANTIC_REVIEW_PROFILE, ErrorCode.INVALID_INPUT),
        ({}, "semantic-review-6.2", ErrorCode.EGRESS_DISABLED),
        ({}, SEMANTIC_REVIEW_PROFILE, ErrorCode.EGRESS_DISABLED),
    ],
)
def test_rejected_judge_request_skips_adapter(overrides: dict[str, JsonValue], profile: str, code: ErrorCode) -> None:
    def no_runtime() -> AgentRuntime:
        pytest.fail("Rejected request constructed a provider runtime")

    app = AgentApplication(no_runtime, load_profiles({}))
    result = asyncio.run(app.invoke(_request(profile=profile, **overrides), policy=RunPolicy(), environ={}))

    assert result.error is not None
    assert result.error.code == code
    assert result.metadata.requests == 0


@pytest.mark.parametrize(("count", "code"), [(12, ErrorCode.EGRESS_DISABLED), (13, ErrorCode.INVALID_INPUT)])
def test_context_fragment_limit_is_enforced_before_provider_access(count: int, code: ErrorCode) -> None:
    def no_runtime() -> AgentRuntime:
        pytest.fail("Offline request constructed a provider runtime")

    fragments = [
        {
            "id": f"log-{index}",
            "start": 0,
            "end": len(_SOURCE),
            "sha256": sha256(_SOURCE.encode()).hexdigest(),
            "text": _SOURCE,
        }
        for index in range(count)
    ]
    request = InvocationRequest(
        schema_version=1,
        request_id="context-limit",
        agent_id="semantic-judge",
        profile_id=SEMANTIC_REVIEW_PROFILE,
        input={
            "mode": "judge_context",
            "question": "Where does the ship dock?",
            "language": "en",
            "reference": {"revision": "fixture", "answerability": "unknown", "constraints": [], "facts": []},
            "context": fragments,
        },
    )
    app = AgentApplication(no_runtime, load_profiles({}))
    result = asyncio.run(app.invoke(request, policy=RunPolicy(), environ={}))

    assert result.error is not None and result.error.code == code
    assert result.metadata.requests == 0


@pytest.mark.parametrize(
    ("text", "end", "stage", "reason", "field"),
    [
        (_QUOTE, None, None, None, None),
        ("in June", None, "evidence_validation", "quote_not_found", None),
        (_QUOTE, 99, "output_schema", "quote_offsets_unpaired", "facts"),
    ],
)
def test_application_validates_and_locates_returned_quote(
    text: str, end: int | None, stage: str | None, reason: str | None, field: str | None
) -> None:
    reply = {
        "mode": "derive_reference",
        "rationale": "The log gives the launch month.",
        "answerability": "answerable",
        "reference_answer": "July",
        "constraints": [],
        "facts": [
            {
                "id": "month",
                "statement": "Launches in July",
                "required": True,
                "quotes": [{"source_id": "log", "start": None, "end": end, "text": text}],
            }
        ],
        "coverage_gaps": [],
    }
    port = AsyncMock(spec=AgentRuntime)
    port.invoke.return_value = json.dumps(reply)
    app = AgentApplication(lambda: port, load_profiles({}))
    observation = ProviderObservation()
    result = asyncio.run(
        app.invoke(
            _request(),
            policy=RunPolicy(allow_external=True, data_classification="synthetic"),
            environ={"OPENAI_API_KEY": _KEY},
            observation=observation,
        )
    )

    assert port.invoke.call_args.kwargs["output_schema"] is DeriveReferenceResult
    assert json.loads(port.invoke.call_args.kwargs["input_json"]) == _INPUT
    assert result.metadata.prompt_revision == "derive_reference/2"
    assert result.metadata.output_schema_revision == "derive_reference/2"
    assert observation.failure_stage == stage
    assert observation.failure_reason == reason
    assert observation.failure_field == field
    if stage is None:
        verdict = DeriveReferenceResult.model_validate(result.output)
        assert verdict.facts[0].quotes[0].start == 140 + _SOURCE.index(_QUOTE)
    else:
        assert result.error is not None
        assert result.error.code == ErrorCode.INVALID_OUTPUT
        assert text not in result.model_dump_json()
        assert result.output is None

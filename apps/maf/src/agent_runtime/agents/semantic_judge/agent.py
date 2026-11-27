"""Register the four independent Semantic Judge modes."""

from pydantic import BaseModel

from agent_runtime.agents.registration import AgentDefinition
from agent_runtime.agents.semantic_judge.contracts import (
    DeriveReferenceInput,
    DeriveReferenceResult,
    JudgeAnswerInput,
    JudgeAnswerResult,
    JudgeContextInput,
    JudgeContextResult,
    JudgeEvidenceInput,
    JudgeEvidenceResult,
)
from agent_runtime.agents.semantic_judge.instructions import INSTRUCTIONS
from agent_runtime.agents.semantic_judge.validation import validate_verdict
from agent_runtime.configuration import SEMANTIC_REVIEW_PROFILE

AGENT_ID = "semantic-judge"

_MODE_SCHEMAS: dict[str, tuple[type[BaseModel], type[BaseModel]]] = {
    "derive_reference": (DeriveReferenceInput, DeriveReferenceResult),
    "judge_evidence": (JudgeEvidenceInput, JudgeEvidenceResult),
    "judge_context": (JudgeContextInput, JudgeContextResult),
    "judge_answer": (JudgeAnswerInput, JudgeAnswerResult),
}

JUDGE_MODES = {
    mode: AgentDefinition(
        input_schema=input_schema,
        output_schema=output_schema,
        instructions=INSTRUCTIONS[mode].text,
        prompt_revision=INSTRUCTIONS[mode].revision,
        output_schema_revision=f"{mode}/1",
        allowed_profiles=frozenset({SEMANTIC_REVIEW_PROFILE}),
        validate_output=validate_verdict,
    )
    for mode, (input_schema, output_schema) in _MODE_SCHEMAS.items()
}

"""Strict request and response objects for the four semantic judge modes."""

from collections.abc import Iterable
from hashlib import sha256
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator


def _opaque_id(value: str) -> str:
    if value.lower().startswith(("sk-", "bearer")):
        raise ValueError("Use an opaque identifier")
    return value


def _text(value: str) -> str:
    if not value.strip() or len(value) > 600:
        raise ValueError("Text must be nonblank and at most 600 characters")
    return value


def _quote_text(value: str) -> str:
    if not value.strip() or len(value) > 1_024:
        raise ValueError("A quote must be nonblank and at most 1024 characters")
    return value


type _Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$"), AfterValidator(_opaque_id)]
type _ShortText = Annotated[str, AfterValidator(_text)]
type _Offset = Annotated[int, Field(ge=0, le=2**53 - 1)]
type _IdList = Annotated[list[_Id], Field(max_length=16)]
type _Language = Literal["en", "ru", "uk"]
type _ConstraintStatus = Literal["satisfied", "violated", "not_applicable", "unknown"]
type _FactStatus = Literal["supported", "partial", "missing", "contradicted", "unknown"]
type _Answerability = Literal[
    "answerable",
    "partially_answerable",
    "not_found_in_complete_eligible_scope",
    "not_found_in_supplied_excerpt",
    "unknown",
]
type _EvidenceCategory = Literal[
    "direct", "partial", "supporting", "topically_related", "irrelevant", "wrong_scope", "contradictory", "unknown"
]

ANSWERABLE = frozenset({"answerable", "partially_answerable"})


def require_unique(values: Iterable[str]) -> None:
    """Reject repeated identifiers within one locator or assessment namespace."""
    identifiers = list(values)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate identifiers")


class _JudgeModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)


class Excerpt(_JudgeModel):
    """Caller-supplied text fragment with absolute Unicode offsets and its UTF-8 digest."""

    id: _Id
    start: _Offset
    end: _Offset
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    text: Annotated[str, StringConstraints(min_length=1, max_length=4_096)]

    @model_validator(mode="after")
    def _verify_integrity(self) -> Self:
        if not self.text.strip() or self.end - self.start != len(self.text):
            raise ValueError("Invalid excerpt interval")
        if self.sha256 != sha256(self.text.encode("utf-8")).hexdigest():
            raise ValueError("Excerpt digest mismatch")
        return self


class Quote(_JudgeModel):
    """Exact quote. Null coordinates request resolution of a unique occurrence."""

    source_id: _Id
    start: _Offset | None
    end: _Offset | None
    text: Annotated[str, AfterValidator(_quote_text)]

    @model_validator(mode="after")
    def _check_interval(self) -> Self:
        if (self.start is None) != (self.end is None):
            raise ValueError("Supply both quote offsets or neither")
        if self.start is not None and self.end is not None and self.end - self.start != len(self.text):
            raise ValueError("Invalid quote interval")
        return self


type _Fragments = Annotated[list[Excerpt], Field(max_length=8)]
type _Quotes = Annotated[list[Quote], Field(max_length=4)]


class Scope(_JudgeModel):
    description: _ShortText
    complete: bool


class Constraint(_JudgeModel):
    id: _Id
    description: _ShortText


class ReferenceFact(_JudgeModel):
    id: _Id
    statement: _ShortText
    required: bool


class FrozenReference(_JudgeModel):
    """Caller-reviewed benchmark reference identified by an immutable revision."""

    revision: _Id
    answerability: _Answerability
    constraints: Annotated[list[Constraint], Field(max_length=12)]
    facts: Annotated[list[ReferenceFact], Field(max_length=16)]

    @model_validator(mode="after")
    def _validate_reference(self) -> Self:
        require_unique(item.id for item in self.constraints)
        require_unique(item.id for item in self.facts)
        if self.answerability in ANSWERABLE:
            if not any(fact.required for fact in self.facts):
                raise ValueError("Answerable reference requires at least one required fact")
        elif self.facts:
            raise ValueError("Unanswerable reference cannot supply asserted answer facts")
        return self


class Citation(_JudgeModel):
    id: _Id
    source_id: _Id


class _JudgeInput(_JudgeModel):
    question: _ShortText
    language: _Language


class DeriveReferenceInput(_JudgeInput):
    mode: Literal["derive_reference"]
    scope: Scope
    sources: Annotated[list[Excerpt], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def _validate_sources(self) -> Self:
        require_unique(excerpt.id for excerpt in self.sources)
        return self


class _ReferenceInput(_JudgeInput):
    reference: FrozenReference


class JudgeEvidenceInput(_ReferenceInput):
    mode: Literal["judge_evidence"]
    candidate: Excerpt
    sources: _Fragments

    @model_validator(mode="after")
    def _validate_sources(self) -> Self:
        require_unique(excerpt.id for excerpt in [self.candidate, *self.sources])
        return self


class JudgeContextInput(_ReferenceInput):
    mode: Literal["judge_context"]
    context: _Fragments

    @model_validator(mode="after")
    def _validate_context(self) -> Self:
        require_unique(excerpt.id for excerpt in self.context)
        return self


class JudgeAnswerInput(_ReferenceInput):
    mode: Literal["judge_answer"]
    answer: Annotated[str, StringConstraints(min_length=1, max_length=2_500)]
    context: _Fragments
    sources: _Fragments
    citations: Annotated[list[Citation], Field(max_length=12)]

    @model_validator(mode="after")
    def _validate_sources(self) -> Self:
        if not self.answer.strip():
            raise ValueError("Answer must contain text")
        excerpt_ids = [excerpt.id for excerpt in [*self.context, *self.sources]]
        require_unique(excerpt_ids)
        require_unique(citation.id for citation in self.citations)
        if any(citation.source_id not in excerpt_ids for citation in self.citations):
            raise ValueError("Citation refers to an unknown excerpt")
        return self


class DerivedConstraint(Constraint):
    status: _ConstraintStatus


class DerivedFact(ReferenceFact):
    quotes: _Quotes


class DeriveReferenceResult(_JudgeModel):
    mode: Literal["derive_reference"]
    rationale: _ShortText
    answerability: _Answerability
    reference_answer: _ShortText | None
    constraints: Annotated[list[DerivedConstraint], Field(max_length=12)]
    facts: Annotated[list[DerivedFact], Field(max_length=16)]
    coverage_gaps: Annotated[list[_ShortText], Field(max_length=8)]


class ConstraintAssessment(_JudgeModel):
    constraint_id: _Id
    status: _ConstraintStatus


class FactAssessment(_JudgeModel):
    fact_id: _Id
    status: _FactStatus
    quotes: _Quotes


class SpanAssessment(_JudgeModel):
    kind: Literal["useful", "irrelevant", "redundant", "contradictory"]
    quote: Quote


class _ReferenceResult(_JudgeModel):
    rationale: _ShortText
    constraint_assessments: Annotated[list[ConstraintAssessment], Field(max_length=12)]
    fact_assessments: Annotated[list[FactAssessment], Field(max_length=16)]


class JudgeEvidenceResult(_ReferenceResult):
    mode: Literal["judge_evidence"]
    category: _EvidenceCategory
    grade: int | None
    contradiction: bool
    spans: Annotated[list[SpanAssessment], Field(max_length=12)]


class JudgeContextResult(_ReferenceResult):
    mode: Literal["judge_context"]
    sufficiency: Literal["sufficient", "partial", "insufficient", "conflicting", "unknown"]
    spans: Annotated[list[SpanAssessment], Field(max_length=12)]


class ClaimAssessment(_JudgeModel):
    id: _Id
    text: Annotated[str, AfterValidator(_quote_text)]
    status: Literal["supported", "unsupported", "contradicted", "unknown"]
    fact_ids: _IdList
    quotes: _Quotes


class CitationAssessment(_JudgeModel):
    citation_id: _Id
    status: Literal["supported", "unsupported", "unknown"]
    claim_ids: _IdList
    quotes: _Quotes


class JudgeAnswerResult(_ReferenceResult):
    mode: Literal["judge_answer"]
    correctness: Literal["correct", "partially_correct", "incorrect", "unknown", "not_applicable"]
    completeness: Literal["complete", "partial", "incomplete", "unknown", "not_applicable"]
    relevance: Literal["relevant", "partially_relevant", "irrelevant", "unknown", "not_applicable"]
    abstention: Literal["not_abstained", "appropriate", "inappropriate", "unknown"]
    claims: Annotated[list[ClaimAssessment], Field(max_length=16)]
    citations: Annotated[list[CitationAssessment], Field(max_length=12)]

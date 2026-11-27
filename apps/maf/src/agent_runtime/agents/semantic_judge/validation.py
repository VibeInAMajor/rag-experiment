"""Check model judgments against the caller's evidence and normalize exact quote offsets."""

from collections.abc import Iterable, Mapping

from pydantic import BaseModel

from agent_runtime.agents.registration import VerdictRejected
from agent_runtime.agents.semantic_judge.contracts import (
    ANSWERABLE,
    CitationAssessment,
    ClaimAssessment,
    DeriveReferenceInput,
    DeriveReferenceResult,
    Excerpt,
    FactAssessment,
    FrozenReference,
    JudgeAnswerInput,
    JudgeAnswerResult,
    JudgeContextInput,
    JudgeContextResult,
    JudgeEvidenceInput,
    JudgeEvidenceResult,
    Quote,
    SpanAssessment,
    require_unique,
)
from agent_runtime.agents.semantic_judge.violations import VerdictRule

_GRADES = {
    "direct": 3,
    "partial": 1,
    "supporting": 1,
    "topically_related": 0,
    "irrelevant": 0,
    "wrong_scope": 0,
    "contradictory": 0,
    "unknown": None,
}
_QUOTED_FACT_STATUS = frozenset({"supported", "partial", "contradicted"})


def validate_verdict(request: BaseModel, verdict: BaseModel) -> BaseModel:
    """Return the checked verdict with absolute quote offsets.

    :raises ValueError: On mismatched modes, unsupported claims of completeness, inconsistent
        rubric values, invalid identifiers, or quotes that cannot be located exactly.
    """
    if isinstance(request, DeriveReferenceInput) and isinstance(verdict, DeriveReferenceResult):
        return _validate_reference(request, verdict)
    if isinstance(request, JudgeEvidenceInput) and isinstance(verdict, JudgeEvidenceResult):
        return _validate_evidence(request, verdict)
    if isinstance(request, JudgeContextInput) and isinstance(verdict, JudgeContextResult):
        return _validate_context(request, verdict)
    if isinstance(request, JudgeAnswerInput) and isinstance(verdict, JudgeAnswerResult):
        return _validate_answer(request, verdict)
    raise VerdictRejected(VerdictRule.MODE_MISMATCH, message="Judgment mode does not match the request")


def _validate_reference(request: DeriveReferenceInput, verdict: DeriveReferenceResult) -> DeriveReferenceResult:
    require_unique(constraint.id for constraint in verdict.constraints)
    require_unique(fact.id for fact in verdict.facts)
    if verdict.answerability == "not_found_in_complete_eligible_scope" and not request.scope.complete:
        raise VerdictRejected(
            VerdictRule.COMPLETE_SCOPE_REQUIRED,
            message="A complete-scope absence needs caller-declared complete coverage",
        )
    if verdict.answerability in {"partially_answerable", "not_found_in_supplied_excerpt"} and not verdict.coverage_gaps:
        raise VerdictRejected(
            VerdictRule.COVERAGE_GAP_REQUIRED, message="Report the incomplete answer or source coverage"
        )
    if verdict.answerability in ANSWERABLE:
        if verdict.reference_answer is None or not any(fact.required for fact in verdict.facts):
            raise VerdictRejected(
                VerdictRule.REFERENCE_ANSWER_REQUIRED,
                message="An answerable judgment needs a reference answer and required facts",
            )
    elif verdict.reference_answer is not None or verdict.facts:
        raise VerdictRejected(
            VerdictRule.UNRESOLVED_REFERENCE_ASSERTS_FACTS,
            message="An unresolved question cannot assert an answer or answer facts",
        )

    sources = _excerpt_index(request.sources)
    facts = []
    for fact in verdict.facts:
        if not fact.quotes:
            raise VerdictRejected(
                VerdictRule.REFERENCE_QUOTE_REQUIRED, message="Each reference fact needs exact original evidence"
            )
        facts.append(fact.model_copy(update={"quotes": _resolve_quotes(fact.quotes, sources)}))
    return verdict.model_copy(update={"facts": facts})


def _validate_evidence(request: JudgeEvidenceInput, verdict: JudgeEvidenceResult) -> JudgeEvidenceResult:
    if verdict.grade != _GRADES[verdict.category]:
        raise VerdictRejected(VerdictRule.GRADE_CATEGORY_MISMATCH, message="Grade does not match the evidence category")
    _validate_assessment_ids(request.reference, verdict)
    sources = _excerpt_index([request.candidate, *request.sources])
    facts = _resolve_facts(verdict.fact_assessments, sources)
    spans = _resolve_spans(verdict.spans, {request.candidate.id: request.candidate})

    candidate_facts = [fact for fact in facts if fact.status in _QUOTED_FACT_STATUS]
    if any(not any(quote.source_id == request.candidate.id for quote in fact.quotes) for fact in candidate_facts):
        raise VerdictRejected(
            VerdictRule.CANDIDATE_QUOTE_REQUIRED, message="Candidate assessments must quote the candidate"
        )
    required = _required_fact_ids(request.reference)
    if verdict.grade in {1, 3}:
        needed_status = "supported" if verdict.grade == 3 else "partial"
        if not any(fact.fact_id in required and fact.status == needed_status for fact in candidate_facts):
            raise VerdictRejected(
                VerdictRule.POSITIVE_GRADE_REQUIRES_FACT_SUPPORT,
                message="A positive grade needs a quoted contribution to a required fact",
            )
        if verdict.grade == 3 and any(constraint.status == "violated" for constraint in verdict.constraint_assessments):
            raise VerdictRejected(
                VerdictRule.DIRECT_EVIDENCE_VIOLATES_SCOPE, message="Direct evidence must satisfy the stated scope"
            )
    elif any(span.kind == "useful" for span in spans):
        raise VerdictRejected(
            VerdictRule.NONPOSITIVE_SPAN_MARKED_USEFUL,
            message="An ungraded or negative candidate cannot mark evidence useful",
        )
    if verdict.category in {"topically_related", "irrelevant", "unknown"} and any(
        fact.fact_id in required and fact.status in {"supported", "partial"} for fact in candidate_facts
    ):
        raise VerdictRejected(
            VerdictRule.CATEGORY_CONFLICTS_WITH_FACT_SUPPORT,
            message="Evidence category conflicts with its required-fact support",
        )

    contradictory = any(fact.status == "contradicted" for fact in facts) or any(
        span.kind == "contradictory" for span in spans
    )
    if verdict.contradiction != contradictory or (verdict.category == "contradictory" and not contradictory):
        raise VerdictRejected(
            VerdictRule.CONTRADICTION_EVIDENCE_MISMATCH, message="Contradiction flag needs exact counterevidence"
        )
    return verdict.model_copy(update={"fact_assessments": facts, "spans": spans})


def _validate_context(request: JudgeContextInput, verdict: JudgeContextResult) -> JudgeContextResult:
    _validate_assessment_ids(request.reference, verdict)
    excerpts = _excerpt_index(request.context)
    facts = _resolve_facts(verdict.fact_assessments, excerpts)
    spans = _resolve_spans(verdict.spans, excerpts)
    contradictory = any(fact.status == "contradicted" for fact in facts) or any(
        span.kind == "contradictory" for span in spans
    )
    if verdict.sufficiency == "sufficient":
        _require_complete_support(request.reference, facts)
        if contradictory or any(constraint.status == "violated" for constraint in verdict.constraint_assessments):
            raise VerdictRejected(
                VerdictRule.SUFFICIENT_CONTEXT_CONFLICTS_WITH_SCOPE_OR_EVIDENCE,
                message="A sufficient context cannot have conflicting evidence or violated scope",
            )
    if verdict.sufficiency == "conflicting" and not contradictory:
        raise VerdictRejected(
            VerdictRule.CONFLICTING_CONTEXT_LACKS_COUNTEREVIDENCE,
            message="A conflicting context needs exact counterevidence",
        )
    return verdict.model_copy(update={"fact_assessments": facts, "spans": spans})


def _validate_answer(request: JudgeAnswerInput, verdict: JudgeAnswerResult) -> JudgeAnswerResult:
    _validate_assessment_ids(request.reference, verdict)
    excerpts = _excerpt_index([*request.context, *request.sources])
    facts = _resolve_facts(verdict.fact_assessments, excerpts)
    require_unique(claim.id for claim in verdict.claims)
    known_facts = {fact.id for fact in request.reference.facts}
    claims = [_validate_claim(claim, request.answer, known_facts, excerpts) for claim in verdict.claims]
    if verdict.completeness == "complete":
        _require_complete_support(request.reference, facts)
        covered = {fact_id for claim in claims if claim.status == "supported" for fact_id in claim.fact_ids}
        if not _required_fact_ids(request.reference) <= covered:
            raise VerdictRejected(
                VerdictRule.COMPLETE_ANSWER_MISSING_GROUNDED_CLAIMS,
                message="A complete answer needs grounded claims for all required facts",
            )
    if verdict.correctness == "correct" and (not claims or any(claim.status != "supported" for claim in claims)):
        raise VerdictRejected(
            VerdictRule.CORRECT_ANSWER_LACKS_GROUNDED_CLAIMS, message="A correct answer needs grounded material claims"
        )

    known_citations = {citation.id: citation.source_id for citation in request.citations}
    _require_exact_ids((citation.citation_id for citation in verdict.citations), known_citations)
    claim_ids = {claim.id for claim in claims}
    citations = [
        _validate_citation(citation, claim_ids, excerpts[known_citations[citation.citation_id]])
        for citation in verdict.citations
    ]
    return verdict.model_copy(update={"fact_assessments": facts, "claims": claims, "citations": citations})


def _validate_claim(
    claim: ClaimAssessment, answer: str, fact_ids: set[str], excerpts: Mapping[str, Excerpt]
) -> ClaimAssessment:
    if claim.text not in answer:
        raise VerdictRejected(
            VerdictRule.CLAIM_TEXT_NOT_VERBATIM, message="Material claim must quote the submitted answer"
        )
    require_unique(claim.fact_ids)
    if not set(claim.fact_ids) <= fact_ids:
        raise VerdictRejected(
            VerdictRule.CLAIM_REFERENCES_UNKNOWN_FACT, message="Claim refers to an unknown reference fact"
        )
    if claim.status in {"supported", "contradicted"} and not claim.quotes:
        raise VerdictRejected(
            VerdictRule.CLAIM_QUOTE_REQUIRED, message="Material claim needs exact supporting or contradictory evidence"
        )
    return claim.model_copy(update={"quotes": _resolve_quotes(claim.quotes, excerpts)})


def _validate_citation(citation: CitationAssessment, claim_ids: set[str], cited_excerpt: Excerpt) -> CitationAssessment:
    require_unique(citation.claim_ids)
    if not set(citation.claim_ids) <= claim_ids:
        raise VerdictRejected(
            VerdictRule.CITATION_REFERENCES_UNKNOWN_CLAIM, message="Citation refers to an unknown material claim"
        )
    if citation.status == "supported" and (not citation.claim_ids or not citation.quotes):
        raise VerdictRejected(
            VerdictRule.SUPPORTED_CITATION_LACKS_CLAIM_OR_QUOTE,
            message="A supported citation needs an answer claim and exact cited text",
        )
    return citation.model_copy(update={"quotes": _resolve_quotes(citation.quotes, {cited_excerpt.id: cited_excerpt})})


def _resolve_facts(facts: list[FactAssessment], excerpts: Mapping[str, Excerpt]) -> list[FactAssessment]:
    resolved = []
    for fact in facts:
        if bool(fact.quotes) != (fact.status in _QUOTED_FACT_STATUS):
            raise VerdictRejected(
                VerdictRule.FACT_STATUS_QUOTE_MISMATCH, message="Fact evidence does not match its assessment"
            )
        resolved.append(fact.model_copy(update={"quotes": _resolve_quotes(fact.quotes, excerpts)}))
    return resolved


def _resolve_spans(spans: list[SpanAssessment], excerpts: Mapping[str, Excerpt]) -> list[SpanAssessment]:
    return [span.model_copy(update={"quote": _resolve_quote(span.quote, excerpts)}) for span in spans]


def _resolve_quotes(quotes: list[Quote], excerpts: Mapping[str, Excerpt]) -> list[Quote]:
    return [_resolve_quote(quote, excerpts) for quote in quotes]


def _resolve_quote(quote: Quote, excerpts: Mapping[str, Excerpt]) -> Quote:
    excerpt = excerpts.get(quote.source_id)
    if excerpt is None:
        raise VerdictRejected(
            VerdictRule.QUOTE_EXCERPT_UNKNOWN_OR_INELIGIBLE, message="Quote refers to an unknown or ineligible excerpt"
        )
    if quote.start is not None and quote.end is not None:
        relative_start = quote.start - excerpt.start
        relative_end = quote.end - excerpt.start
        if relative_start < 0 or quote.end > excerpt.end or excerpt.text[relative_start:relative_end] != quote.text:
            raise VerdictRejected(
                VerdictRule.QUOTE_INTERVAL_MISMATCH, message="Quote does not match the supplied interval"
            )
        return quote

    position = excerpt.text.find(quote.text)
    if position < 0:
        raise VerdictRejected(VerdictRule.QUOTE_NOT_FOUND, message="Quote does not occur in the supplied excerpt")
    if excerpt.text.find(quote.text, position + 1) >= 0:
        raise VerdictRejected(
            VerdictRule.QUOTE_AMBIGUOUS, message="Quote must occur exactly once or specify exact coordinates"
        )
    start = excerpt.start + position
    return quote.model_copy(update={"start": start, "end": start + len(quote.text)})


def _validate_assessment_ids(
    reference: FrozenReference, verdict: JudgeEvidenceResult | JudgeContextResult | JudgeAnswerResult
) -> None:
    _require_exact_ids(
        (assessment.constraint_id for assessment in verdict.constraint_assessments),
        (constraint.id for constraint in reference.constraints),
    )
    _require_exact_ids(
        (assessment.fact_id for assessment in verdict.fact_assessments), (fact.id for fact in reference.facts)
    )


def _require_exact_ids(actual: Iterable[str], expected: Iterable[str]) -> None:
    identifiers = list(actual)
    require_unique(identifiers)
    if set(identifiers) != set(expected):
        raise VerdictRejected(
            VerdictRule.ASSESSMENT_IDENTIFIERS_MISMATCH, message="Assessment identifiers do not match the request"
        )


def _required_fact_ids(reference: FrozenReference) -> set[str]:
    return {fact.id for fact in reference.facts if fact.required}


def _require_complete_support(reference: FrozenReference, facts: list[FactAssessment]) -> None:
    required = _required_fact_ids(reference)
    if not required:
        raise VerdictRejected(
            VerdictRule.COMPLETE_WITHOUT_REQUIRED_FACTS, message="Completeness needs declared required facts"
        )
    supported = {fact.fact_id for fact in facts if fact.status == "supported"}
    if not required <= supported:
        raise VerdictRejected(
            VerdictRule.INCOMPLETE_REQUIRED_FACT_SUPPORT, message="Completeness needs evidence for every required fact"
        )


def _excerpt_index(excerpts: Iterable[Excerpt]) -> dict[str, Excerpt]:
    return {excerpt.id: excerpt for excerpt in excerpts}

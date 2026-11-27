"""Compare admitted judge verdicts with the frozen calibration expectations."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue

from agent_runtime.contracts import InvocationResult
from calibration.controls import CalibrationCase

GRADE_PERCENT = 90
SUPPORT_PERCENT = 95
OTHER_MODE_PERCENT = 90


@dataclass(frozen=True, slots=True)
class CaseScore:
    case: CalibrationCase
    result: InvocationResult | None
    fields: dict[str, bool]
    facts: dict[str, bool]
    quotes: dict[str, bool]
    required_facts: dict[str, bool]
    answer_support: bool | None

    @property
    def output(self) -> dict[str, JsonValue]:
        return self.result.output or {} if self.result is not None else {}

    @property
    def passed(self) -> bool:
        return (
            bool(self.output)
            and all(self.fields.values())
            and all(self.facts.values())
            and all(self.quotes.values())
            and all(self.required_facts.values())
            and self.answer_support is not False
        )


def score_case(case: CalibrationCase, result: InvocationResult | None) -> CaseScore:
    output = result.output or {} if result is not None else {}
    expected_fields = _object(case.expected.get("fields"))
    fields = {
        field: field in output
        and any(type(output[field]) is type(value) and output[field] == value for value in _list(allowed))
        for field, allowed in expected_fields.items()
    }
    expected_facts = _object(case.expected.get("fact_statuses"))
    facts = {
        str(item.get("fact_id")): item.get("status") for item in map(_object, _list(output.get("fact_assessments")))
    }
    expected_support = case.expected.get("answer_support")
    actual_grade = output.get("grade")
    actual_support = actual_grade > 0 if type(actual_grade) is int else None
    quotes = _quote_texts(output)
    required_facts = [
        str(fact.get("statement", "")).casefold()
        for fact in map(_object, _list(output.get("facts")))
        if fact.get("required") is True
    ]
    return CaseScore(
        case=case,
        result=result,
        fields=fields,
        facts={fact_id: facts.get(fact_id) == status for fact_id, status in expected_facts.items()},
        quotes={term: any(term in text for text in quotes) for term in _strings(case.expected.get("quote_contains"))},
        required_facts={
            term: any(term.casefold() in fact for fact in required_facts)
            for term in _strings(case.expected.get("required_fact_contains"))
        },
        answer_support=actual_support == expected_support if type(expected_support) is bool else None,
    )


def summarize(scores: Sequence[CaseScore], *, development: bool) -> dict[str, object]:
    primary = [score for score in scores if score.case.repeat_of is None]
    determinate = [score for score in primary if score.answer_support is not None]
    other = [score for score in primary if score.case.input["mode"] != "judge_evidence"]
    stateless = _repeat_checks(scores)
    grade = _count([score.fields.get("grade", False) for score in determinate])
    support = _count([score.answer_support is True for score in determinate])
    other_modes = _count([score.passed for score in other])
    critical = _count([score.passed for score in primary if score.case.critical])
    unknown = _count([_unknown(score.output) and score.passed for score in primary if _expects_unknown(score.case)])
    operational_errors = Counter(
        score.result.error.code.value for score in scores if score.result is not None and score.result.error is not None
    )
    pending = sum(score.result is None for score in scores)
    false_complete_scope = sum(
        score.output.get("answerability") == "not_found_in_complete_eligible_scope"
        and _object(score.case.input.get("scope")).get("complete") is not True
        for score in scores
    )
    passed = (
        not operational_errors
        and not pending
        and not false_complete_scope
        and _meets(grade, GRADE_PERCENT)
        and _meets(support, SUPPORT_PERCENT)
        and _meets(other_modes, OTHER_MODE_PERCENT)
        and _meets(critical, 100)
        and _meets(unknown, 100)
        and _meets(_count(list(stateless.values())), 100)
    )
    status: Literal["DEVELOPMENT_ONLY", "PASS", "NO_GO", "BLOCKED_REAL_API"]
    if development:
        status = "DEVELOPMENT_ONLY"
    elif operational_errors.get("MISSING_CREDENTIALS") and not any(score.output for score in scores):
        status = "BLOCKED_REAL_API"
    else:
        status = "PASS" if passed else "NO_GO"
    return {
        "status": status,
        "all_controls_matched": all(score.passed for score in scores),
        "grade_agreement": grade,
        "binary_support_agreement": support,
        "other_modes_agreement": other_modes,
        "critical_controls": critical,
        "expected_unknown": unknown,
        "observed_unknown": sum(_unknown(score.output) for score in primary),
        "categories": _category_counts(primary),
        "unknown_or_incomplete_scope_overclaims": false_complete_scope,
        "repeatability": stateless,
        "operational_errors": dict(operational_errors),
        "unexecuted": pending,
        "received_validated_verdicts": sum(bool(score.output) for score in scores),
        "fact_checks": _count(
            [matched for score in scores for matched in (*score.facts.values(), *score.required_facts.values())]
        ),
        "exact_quote_checks": _count([matched for score in scores for matched in score.quotes.values()]),
    }


def _count(matches: Sequence[bool]) -> dict[str, int]:
    return {"matched": sum(matches), "total": len(matches)}


def _meets(count: Mapping[str, int], percent: int) -> bool:
    return bool(count["total"]) and count["matched"] * 100 >= percent * count["total"]


def _category_counts(scores: Sequence[CaseScore]) -> dict[str, dict[str, int]]:
    expected = (score for score in scores if "category" in score.fields)
    categories: dict[str, list[bool]] = {}
    for score in expected:
        label = "|".join(_strings(_object(score.case.expected.get("fields")).get("category")))
        categories.setdefault(label, []).append(score.fields["category"])
    return {category: _count(values) for category, values in sorted(categories.items())}


def _repeat_checks(scores: Sequence[CaseScore]) -> dict[str, bool]:
    primary = {score.case.case_id: score for score in scores if score.case.repeat_of is None}
    comparisons = {}
    for repeated in scores:
        if repeated.case.repeat_of is None:
            continue
        original = primary[repeated.case.repeat_of]
        comparisons[repeated.case.case_id] = (
            repeated.passed
            and original.passed
            and all(
                field in original.output and original.output[field] == repeated.output[field]
                for field in repeated.fields
            )
        )
    return comparisons


def _unknown(output: Mapping[str, JsonValue]) -> bool:
    return "unknown" in [output.get(field) for field in ("category", "answerability", "sufficiency", "correctness")]


def _expects_unknown(case: CalibrationCase) -> bool:
    fields = _object(case.expected.get("fields"))
    markers = ("category", "answerability", "sufficiency", "correctness")
    return any(fields.get(field) == ["unknown"] for field in markers)


def _quote_texts(node: JsonValue) -> list[str]:
    if isinstance(node, dict):
        text = node.get("text")
        if "source_id" in node and isinstance(text, str):
            return [text]
        return [text for value in node.values() for text in _quote_texts(value)]
    if isinstance(node, list):
        return [text for value in node for text in _quote_texts(value)]
    return []


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def _list(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def _strings(value: JsonValue) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str)]

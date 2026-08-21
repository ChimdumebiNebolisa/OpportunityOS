from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from opportunityos.domain.decisions import (
    ALLOWED_TRANSITIONS,
    effort_penalty,
    evaluate_requirement,
    priority_score,
    score_opportunity,
    time_fit_score,
    urgency_score,
    validate_transition,
)
from opportunityos.domain.profile import (
    Candidate,
    authority,
    intervals_overlap,
    normalize_value,
    reconcile_field,
    values_equal,
)
from opportunityos.schemas import (
    DecisionLabel,
    EligibilityResult,
    LifecycleState,
    OverallEligibility,
    PredicateOperator,
)

WEIGHTS = {"a": 60, "b": 40}


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "result"),
    [
        (PredicateOperator.EQUALS, "US", "US", EligibilityResult.PASS),
        (PredicateOperator.NOT_EQUALS, "US", "NG", EligibilityResult.PASS),
        (PredicateOperator.IN, "US", ["US", "CA"], EligibilityResult.PASS),
        (PredicateOperator.NOT_IN, "US", ["NG", "CA"], EligibilityResult.PASS),
        (PredicateOperator.GREATER_THAN_OR_EQUAL, 3.5, 3.0, EligibilityResult.PASS),
        (PredicateOperator.LESS_THAN_OR_EQUAL, 21, 25, EligibilityResult.PASS),
        (PredicateOperator.RANGE, 21, [18, 25], EligibilityResult.PASS),
        (PredicateOperator.BEFORE, "2026-01", "2027-01", EligibilityResult.PASS),
        (PredicateOperator.AFTER, "2028-01", "2027-01", EligibilityResult.PASS),
        (PredicateOperator.CONTAINS, ["python", "rust"], "rust", EligibilityResult.PASS),
        (PredicateOperator.ANY_OF, ["python", "rust"], ["go", "rust"], EligibilityResult.PASS),
        (PredicateOperator.ALL_OF, ["python", "rust"], ["python", "rust"], EligibilityResult.PASS),
        (PredicateOperator.EQUALS, "US", "CA", EligibilityResult.FAIL),
    ],
)
def test_every_predicate_operator(
    operator: PredicateOperator, actual: object, expected: object, result: EligibilityResult
) -> None:
    check = evaluate_requirement(
        requirement_id="r",
        operator=operator,
        expected=expected,
        fact_value=actual,
        fact_ids=["f"],
        fact_state="verified",
    )
    assert check.result is result
    assert check.fact_ids == ("f",)


def test_requirement_conflict_missing_and_bad_shape() -> None:
    conflicted = evaluate_requirement(
        requirement_id="r",
        operator=PredicateOperator.EQUALS,
        expected="US",
        fact_value="US",
        fact_ids=["f"],
        fact_state="conflicted",
    )
    missing = evaluate_requirement(
        requirement_id="r",
        operator=PredicateOperator.EQUALS,
        expected="US",
        fact_value=None,
        fact_ids=[],
        fact_state=None,
    )
    malformed = evaluate_requirement(
        requirement_id="r",
        operator=PredicateOperator.RANGE,
        expected=[],
        fact_value=2,
        fact_ids=["f"],
        fact_state="verified",
    )
    assert conflicted.reason_code == "PROFILE_FACT_CONFLICTED"
    assert missing.reason_code == "PROFILE_FACT_MISSING"
    assert malformed.reason_code == "PREDICATE_UNREPRESENTABLE"


def test_score_validation_thresholds_and_bounds() -> None:
    with pytest.raises(ValueError, match="dimensions mismatch"):
        score_opportunity(
            assessments={"a": 10},
            assessment_confidences=[],
            weights=WEIGHTS,
            eligibility=OverallEligibility.ELIGIBLE,
            source_completeness=1,
            total_effort_minutes=1,
        )
    with pytest.raises(ValueError, match="sum to 100"):
        score_opportunity(
            assessments={"a": 10},
            assessment_confidences=[],
            weights={"a": 99},
            eligibility=OverallEligibility.ELIGIBLE,
            source_completeness=1,
            total_effort_minutes=1,
        )
    maybe = score_opportunity(
        assessments={"a": 6, "b": 6},
        assessment_confidences=[0.8],
        weights=WEIGHTS,
        eligibility=OverallEligibility.ELIGIBLE,
        source_completeness=0.8,
        total_effort_minutes=1,
    )
    low_confidence = score_opportunity(
        assessments={"a": 10, "b": 10},
        assessment_confidences=[],
        weights=WEIGHTS,
        eligibility=OverallEligibility.ELIGIBLE,
        source_completeness=0,
        total_effort_minutes=1,
    )
    review = score_opportunity(
        assessments={"a": 10, "b": 10},
        assessment_confidences=[1],
        weights=WEIGHTS,
        eligibility=OverallEligibility.REVIEW_REQUIRED,
        source_completeness=1,
        total_effort_minutes=1000,
        heavy_artifact=True,
    )
    passed = score_opportunity(
        assessments={"a": 1, "b": 1},
        assessment_confidences=[1],
        weights=WEIGHTS,
        eligibility=OverallEligibility.ELIGIBLE,
        source_completeness=1,
        total_effort_minutes=1000,
        heavy_artifact=True,
    )
    assert maybe.decision is DecisionLabel.MAYBE
    assert low_confidence.decision is DecisionLabel.MAYBE
    assert review.decision is DecisionLabel.REVIEW_REQUIRED and review.confidence == 0.59
    assert passed.decision is DecisionLabel.PASS and passed.net_score == 0
    assert effort_penalty(1000, heavy_artifact=True) == 15


@pytest.mark.parametrize(
    ("days", "expected"),
    [(2, 90), (5, 80), (10, 60), (20, 40), (31, 15)],
)
def test_urgency_bands(days: int, expected: float) -> None:
    now = datetime(2026, 1, 1)
    assert urgency_score(now + timedelta(days=days), now) == expected


def test_time_fit_missing_deadline_and_priority_cap() -> None:
    assert urgency_score(None) == 10
    assert time_fit_score(20, 30) == 100
    assert time_fit_score(100, 25) == 20
    assert (
        priority_score(net_value=100, urgency=100, readiness=100, time_fit=100, completion_ratio=1)
        == 100
    )


def candidate(
    identifier: str,
    value: object,
    *,
    field: str = "education.expected_graduation",
    source_id: str | None = None,
    source_locator: str | None = None,
    source_type: str = "local_document",
    trust: str = "credible",
    observed_offset: int = 0,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
) -> Candidate:
    return Candidate(
        id=identifier,
        field_path=field,
        value=value,
        value_type="string",
        source_id=source_id or identifier,
        source_type=source_type,
        trust_class=trust,
        confidence=0.9,
        effective_from=effective_from,
        effective_until=effective_until,
        observed_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=observed_offset),
        source_locator=source_locator,
    )


def test_normalization_equality_and_intervals() -> None:
    assert normalize_value({" b ": [" x  y ", 1]}) == {" b ": ["x y", 1]}
    assert values_equal({"b": 2, "a": " x "}, {"a": "x", "b": 2})
    first = candidate(
        "a",
        1,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        effective_until=datetime(2026, 2, 1, tzinfo=UTC),
    )
    overlapping = candidate("b", 2, effective_from=datetime(2026, 1, 15, tzinfo=UTC))
    later = candidate("c", 3, effective_from=datetime(2026, 3, 1, tzinfo=UTC))
    assert intervals_overlap(first, overlapping)
    assert not intervals_overlap(first, later)


@pytest.mark.parametrize(
    ("source_type", "field", "trust", "expected"),
    [
        ("model_inference", "skills.python", "unknown", 5),
        ("github_api", "github.repositories.x", "unknown", 85),
        ("github_api", "education.gpa", "unknown", 25),
        ("user_statement", "career.goal", "unknown", 95),
        ("official_webpage", "education.gpa", "unknown", 90),
        ("other", "education.gpa", "official", 90),
        ("user_statement", "education.gpa", "unknown", 80),
        ("local_document", "education.gpa", "credible", 65),
        ("chatgpt_snapshot", "education.gpa", "credible", 45),
        ("other", "education.gpa", "unknown", 40),
    ],
)
def test_authority_table(source_type: str, field: str, trust: str, expected: int) -> None:
    assert (
        authority(candidate("x", 1, field=field, source_type=source_type, trust=trust)) == expected
    )


def test_reconciliation_guards_and_paths() -> None:
    with pytest.raises(ValueError, match="At least one"):
        reconcile_field([])
    with pytest.raises(ValueError, match="same field"):
        reconcile_field([candidate("a", 1), candidate("b", 1, field="other")])

    equal = reconcile_field([candidate("a", " x "), candidate("b", "x")])
    assert equal.selected_value == "x" and equal.superseded_ids

    same_source = reconcile_field(
        [
            candidate("new", "2028", source_id="source", observed_offset=1),
            candidate("old", "2027", source_id="source"),
        ]
    )
    assert same_source.selected_id == "new" and same_source.superseded_ids == ("old",)

    same_logical_source = reconcile_field(
        [
            candidate(
                "new-record", "2028", source_locator="https://api.example/source", observed_offset=1
            ),
            candidate("old-record", "2027", source_locator="https://api.example/source"),
        ]
    )
    assert same_logical_source.selected_id == "new-record"

    authoritative = reconcile_field(
        [
            candidate("official", "A", source_type="official_webpage"),
            candidate("snapshot", "B", source_type="chatgpt_snapshot"),
        ]
    )
    assert authoritative.selected_id == "official"

    conflict = reconcile_field([candidate("a", "A"), candidate("b", "B", observed_offset=1)])
    assert conflict.selected_id is None and set(conflict.conflicted_ids) == {"a", "b"}

    non_overlapping = reconcile_field(
        [
            candidate(
                "new",
                "B",
                effective_from=datetime(2027, 1, 1, tzinfo=UTC),
                observed_offset=1,
            ),
            candidate(
                "old",
                "A",
                effective_until=datetime(2026, 12, 31, tzinfo=UTC),
            ),
        ]
    )
    assert non_overlapping.selected_id == "new"


def test_all_declared_lifecycle_transitions() -> None:
    for current, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            validate_transition(current, target)
    with pytest.raises(ValueError):
        validate_transition(LifecycleState.ARCHIVED, LifecycleState.DISCOVERED)

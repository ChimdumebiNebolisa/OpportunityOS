from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from opportunityos.domain.decisions import (
    CheckResult,
    effort_penalty,
    evaluate_requirement,
    overall_eligibility,
    priority_score,
    score_opportunity,
    urgency_score,
    validate_transition,
)
from opportunityos.schemas import (
    DecisionLabel,
    EligibilityResult,
    LifecycleState,
    OverallEligibility,
    PredicateOperator,
)

WEIGHTS = {
    "strategic_upside": 20,
    "profile_fit": 15,
    "recognizable_signal": 10,
    "tangible_output": 10,
    "access_network": 10,
    "financial_support": 5,
    "career_optionality": 10,
    "outcome_plausibility": 10,
    "preference_alignment": 10,
}


@given(st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False))
def test_score_replay_is_deterministic(value: float) -> None:
    assessments = {key: value for key in WEIGHTS}
    first = score_opportunity(
        assessments=assessments,
        assessment_confidences=[0.9] * len(WEIGHTS),
        weights=WEIGHTS,
        eligibility=OverallEligibility.ELIGIBLE,
        source_completeness=0.9,
        total_effort_minutes=60,
    )
    second = score_opportunity(
        assessments=assessments,
        assessment_confidences=[0.9] * len(WEIGHTS),
        weights=WEIGHTS,
        eligibility=OverallEligibility.ELIGIBLE,
        source_completeness=0.9,
        total_effort_minutes=60,
    )
    assert first == second


def test_hard_failure_and_unknown_gate_decision() -> None:
    failed = evaluate_requirement(
        requirement_id="r1",
        operator=PredicateOperator.EQUALS,
        expected="US",
        fact_value="NG",
        fact_ids=["f1"],
        fact_state="verified",
    )
    unknown = evaluate_requirement(
        requirement_id="r2",
        operator=PredicateOperator.UNKNOWN,
        expected=None,
        fact_value="value",
        fact_ids=["f2"],
        fact_state="verified",
    )
    assert overall_eligibility([failed]) is OverallEligibility.INELIGIBLE
    assert overall_eligibility([unknown]) is OverallEligibility.REVIEW_REQUIRED
    result = score_opportunity(
        assessments={key: 10 for key in WEIGHTS},
        assessment_confidences=[1] * len(WEIGHTS),
        weights=WEIGHTS,
        eligibility=OverallEligibility.INELIGIBLE,
        source_completeness=1,
        total_effort_minutes=10,
    )
    assert result.decision is DecisionLabel.PASS
    assert failed.result is EligibilityResult.FAIL


def test_penalty_urgency_and_completion_priority() -> None:
    assert [effort_penalty(value) for value in [30, 60, 120, 240, 480, 481]] == [
        0,
        2,
        4,
        7,
        10,
        13,
    ]
    now = datetime(2026, 8, 21, tzinfo=UTC)
    assert urgency_score(now - timedelta(seconds=1), now) == 0
    assert urgency_score(now + timedelta(hours=12), now) == 100
    base = priority_score(net_value=80, urgency=80, readiness=90, time_fit=100)
    nearly_done = priority_score(
        net_value=80, urgency=80, readiness=90, time_fit=100, completion_ratio=0.8
    )
    assert nearly_done > base


def test_lifecycle_rejects_invalid_jump() -> None:
    validate_transition(LifecycleState.DISCOVERED, LifecycleState.SOURCE_VERIFIED)
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        validate_transition(LifecycleState.DISCOVERED, LifecycleState.SUBMITTED)


def test_overall_all_pass() -> None:
    check = CheckResult("r", EligibilityResult.PASS, "OK", "ok", ())
    assert overall_eligibility([check]) is OverallEligibility.ELIGIBLE

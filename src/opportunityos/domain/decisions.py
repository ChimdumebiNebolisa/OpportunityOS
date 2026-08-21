"""Eligibility, scoring, priority, and lifecycle rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from opportunityos.schemas import (
    DecisionLabel,
    EligibilityResult,
    LifecycleState,
    OverallEligibility,
    PredicateOperator,
)


@dataclass(frozen=True)
class CheckResult:
    requirement_id: str
    result: EligibilityResult
    reason_code: str
    explanation: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScoreResult:
    raw_score: float
    effort_penalty: float
    net_score: float
    confidence: float
    decision: DecisionLabel


def _compare(actual: Any, operator: PredicateOperator, expected: Any) -> bool | None:
    if operator is PredicateOperator.UNKNOWN:
        return None
    if operator is PredicateOperator.EQUALS:
        return bool(actual == expected)
    if operator is PredicateOperator.NOT_EQUALS:
        return bool(actual != expected)
    if operator is PredicateOperator.IN:
        return bool(actual in expected)
    if operator is PredicateOperator.NOT_IN:
        return bool(actual not in expected)
    if operator is PredicateOperator.GREATER_THAN_OR_EQUAL:
        return bool(actual >= expected)
    if operator is PredicateOperator.LESS_THAN_OR_EQUAL:
        return bool(actual <= expected)
    if operator is PredicateOperator.RANGE:
        return bool(expected[0] <= actual <= expected[1])
    if operator is PredicateOperator.BEFORE:
        return bool(actual < expected)
    if operator is PredicateOperator.AFTER:
        return bool(actual > expected)
    if operator is PredicateOperator.CONTAINS:
        return expected in actual
    if operator is PredicateOperator.ANY_OF:
        return any(item in actual for item in expected)
    if operator is PredicateOperator.ALL_OF:
        return all(item in actual for item in expected)
    raise ValueError(f"Unsupported predicate operator: {operator}")


def evaluate_requirement(
    *,
    requirement_id: str,
    operator: PredicateOperator,
    expected: Any,
    fact_value: Any | None,
    fact_ids: list[str],
    fact_state: str | None,
) -> CheckResult:
    if fact_state == "conflicted":
        return CheckResult(
            requirement_id,
            EligibilityResult.CONFLICTED,
            "PROFILE_FACT_CONFLICTED",
            "A required profile fact has unresolved credible alternatives.",
            tuple(fact_ids),
        )
    if fact_value is None or fact_state in {None, "missing", "stale"}:
        return CheckResult(
            requirement_id,
            EligibilityResult.UNKNOWN,
            "PROFILE_FACT_MISSING",
            "No current canonical fact can answer this requirement.",
            tuple(fact_ids),
        )
    try:
        matches = _compare(fact_value, operator, expected)
    except (TypeError, ValueError, KeyError, IndexError):
        matches = None
    if matches is None:
        return CheckResult(
            requirement_id,
            EligibilityResult.UNKNOWN,
            "PREDICATE_UNREPRESENTABLE",
            "The requirement cannot be decided safely from normalized evidence.",
            tuple(fact_ids),
        )
    return CheckResult(
        requirement_id,
        EligibilityResult.PASS if matches else EligibilityResult.FAIL,
        "PREDICATE_MATCH" if matches else "PREDICATE_MISMATCH",
        "Canonical evidence satisfies the requirement."
        if matches
        else "Canonical evidence does not satisfy the requirement.",
        tuple(fact_ids),
    )


def overall_eligibility(checks: list[CheckResult]) -> OverallEligibility:
    if any(check.result is EligibilityResult.FAIL for check in checks):
        return OverallEligibility.INELIGIBLE
    if any(
        check.result in {EligibilityResult.UNKNOWN, EligibilityResult.CONFLICTED}
        for check in checks
    ):
        return OverallEligibility.REVIEW_REQUIRED
    return OverallEligibility.ELIGIBLE


def effort_penalty(total_minutes: int, heavy_artifact: bool = False) -> int:
    if total_minutes <= 30:
        penalty = 0
    elif total_minutes <= 60:
        penalty = 2
    elif total_minutes <= 120:
        penalty = 4
    elif total_minutes <= 240:
        penalty = 7
    elif total_minutes <= 480:
        penalty = 10
    else:
        penalty = 13
    return min(15, penalty + (2 if heavy_artifact else 0))


def score_opportunity(
    *,
    assessments: dict[str, float],
    assessment_confidences: list[float],
    weights: dict[str, int],
    eligibility: OverallEligibility,
    source_completeness: float,
    total_effort_minutes: int,
    heavy_artifact: bool = False,
    apply_threshold: int = 75,
    maybe_threshold: int = 55,
    apply_confidence: float = 0.70,
) -> ScoreResult:
    if set(assessments) != set(weights):
        missing = sorted(set(weights) - set(assessments))
        extra = sorted(set(assessments) - set(weights))
        raise ValueError(f"Assessment dimensions mismatch; missing={missing}, extra={extra}")
    if sum(weights.values()) != 100:
        raise ValueError("Scoring weights must sum to 100")
    raw = sum(Decimal(str(assessments[key])) * Decimal(weight) for key, weight in weights.items())
    raw = (raw / Decimal(10)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    penalty = Decimal(effort_penalty(total_effort_minutes, heavy_artifact))
    net = max(Decimal(0), min(Decimal(100), raw - penalty))
    average_assessment_confidence = (
        sum(assessment_confidences) / len(assessment_confidences) if assessment_confidences else 0.0
    )
    confidence = round(
        min(1.0, max(0.0, (source_completeness + average_assessment_confidence) / 2)), 4
    )
    if eligibility is OverallEligibility.INELIGIBLE:
        decision = DecisionLabel.PASS
    elif eligibility is OverallEligibility.REVIEW_REQUIRED:
        decision = DecisionLabel.REVIEW_REQUIRED
        confidence = min(confidence, 0.59)
    elif net >= apply_threshold and confidence >= apply_confidence:
        decision = DecisionLabel.APPLY
    elif net >= maybe_threshold:
        decision = DecisionLabel.MAYBE
    else:
        decision = DecisionLabel.PASS
    return ScoreResult(float(raw), float(penalty), float(net), confidence, decision)


def urgency_score(deadline: datetime | None, now: datetime | None = None) -> float:
    if deadline is None:
        return 10.0
    current = now or datetime.now(UTC)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    seconds = (deadline - current).total_seconds()
    if seconds <= 0:
        return 0.0
    days = seconds / 86400
    if days <= 1:
        return 100.0
    if days <= 3:
        return 90.0
    if days <= 7:
        return 80.0
    if days <= 14:
        return 60.0
    if days <= 30:
        return 40.0
    return 15.0


def time_fit_score(estimated_minutes: int, available_minutes: int) -> float:
    if estimated_minutes <= available_minutes:
        return 100.0
    ratio = available_minutes / estimated_minutes
    return round(max(0, min(95, ratio * 80)), 2)


def priority_score(
    *,
    net_value: float,
    urgency: float,
    readiness: float,
    time_fit: float,
    completion_ratio: float = 0,
) -> float:
    base = 0.55 * net_value + 0.20 * urgency + 0.15 * readiness + 0.10 * time_fit
    completion_bonus = 8 if completion_ratio >= 0.8 and net_value >= 70 else 0
    return round(min(100, base + completion_bonus), 2)


ALLOWED_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.DISCOVERED: {LifecycleState.SOURCE_VERIFIED, LifecycleState.ARCHIVED},
    LifecycleState.SOURCE_VERIFIED: {LifecycleState.PARSED, LifecycleState.REVIEW_REQUIRED},
    LifecycleState.PARSED: {LifecycleState.ELIGIBILITY_PENDING, LifecycleState.REVIEW_REQUIRED},
    LifecycleState.ELIGIBILITY_PENDING: {
        LifecycleState.ELIGIBLE,
        LifecycleState.INELIGIBLE,
        LifecycleState.REVIEW_REQUIRED,
    },
    LifecycleState.ELIGIBLE: {LifecycleState.EVALUATED, LifecycleState.EXPIRED},
    LifecycleState.INELIGIBLE: {LifecycleState.ARCHIVED},
    LifecycleState.REVIEW_REQUIRED: {
        LifecycleState.ELIGIBILITY_PENDING,
        LifecycleState.EXPIRED,
        LifecycleState.ARCHIVED,
    },
    LifecycleState.EVALUATED: {
        LifecycleState.SHORTLISTED,
        LifecycleState.PREPARING,
        LifecycleState.EXPIRED,
        LifecycleState.ARCHIVED,
    },
    LifecycleState.SHORTLISTED: {
        LifecycleState.PREPARING,
        LifecycleState.EXPIRED,
        LifecycleState.ARCHIVED,
    },
    LifecycleState.PREPARING: {
        LifecycleState.READY,
        LifecycleState.EXPIRED,
        LifecycleState.WITHDRAWN,
    },
    LifecycleState.READY: {
        LifecycleState.SUBMITTED,
        LifecycleState.EXPIRED,
        LifecycleState.WITHDRAWN,
    },
    LifecycleState.SUBMITTED: {
        LifecycleState.FOLLOW_UP_DUE,
        LifecycleState.ACCEPTED,
        LifecycleState.REJECTED,
        LifecycleState.WITHDRAWN,
    },
    LifecycleState.FOLLOW_UP_DUE: {
        LifecycleState.ACCEPTED,
        LifecycleState.REJECTED,
        LifecycleState.WITHDRAWN,
    },
    LifecycleState.ACCEPTED: {LifecycleState.ARCHIVED},
    LifecycleState.REJECTED: {LifecycleState.ARCHIVED},
    LifecycleState.WITHDRAWN: {LifecycleState.ARCHIVED},
    LifecycleState.EXPIRED: {LifecycleState.ARCHIVED},
    LifecycleState.ARCHIVED: set(),
}


def validate_transition(current: LifecycleState, target: LifecycleState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Invalid lifecycle transition: {current.value} -> {target.value}")

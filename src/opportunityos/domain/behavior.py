"""Pure V2 behavioral policies shared by application callers and tests."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta

from opportunityos.domain.decisions import urgency_score

BEHAVIOR_RULESET_VERSION = "2.0"


def execution_priority(
    *,
    opportunity_value: float,
    urgency: float,
    readiness: float,
    remaining_minutes: int,
    available_minutes: int,
    completion_ratio: float,
    dependencies_ready: bool,
    packet_ready: bool,
    unlocks_submission: bool,
) -> float:
    """Rank a current action while rewarding completion leverage and time fit."""
    if available_minutes <= 0 or remaining_minutes <= 0 or not dependencies_ready:
        return 0.0
    time_fit = (
        100.0
        if remaining_minutes <= available_minutes
        else min(95.0, available_minutes / remaining_minutes * 80.0)
    )
    completion_leverage = 1.0 + min(0.35, max(0.0, completion_ratio) * 0.35)
    packet_factor = 1.08 if packet_ready else 1.0
    submission_factor = 1.10 if unlocks_submission else 1.0
    urgency_factor = 0.65 + max(0.0, min(100.0, urgency)) / 285.0
    readiness_factor = 0.65 + max(0.0, min(100.0, readiness)) / 285.0
    time_factor = 0.5 + time_fit / 200.0
    value = max(0.0, min(100.0, opportunity_value))
    result = value * urgency_factor * readiness_factor * time_factor
    result *= completion_leverage * packet_factor * submission_factor
    return round(min(100.0, result), 2)


def reminder_severity(
    *, deadline: datetime | None, now: datetime, completion_ratio: float, value: float
) -> int:
    """Return 0-3 severity, with deadline rescue and leverage taking precedence."""
    if value < 0 or value < 65:
        return 0
    if deadline is not None:
        due = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
        hours = (due - now).total_seconds() / 3600
        if hours <= 24:
            return 3
        if hours <= 72:
            return 2
    if completion_ratio >= 0.8 or value >= 85:
        return 2
    return 1


def parse_clock(value: str) -> time:
    """Parse a private HH:MM clock setting without accepting ambiguous input."""
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as error:
        raise ValueError("Clock settings must use HH:MM") from error
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Clock settings must use a valid 24-hour time")
    return time(hour, minute)


def in_quiet_hours(current: datetime, start: str, end: str) -> bool:
    local = current.timetz().replace(tzinfo=None)
    quiet_start = parse_clock(start)
    quiet_end = parse_clock(end)
    if quiet_start == quiet_end:
        return True
    if quiet_start < quiet_end:
        return quiet_start <= local < quiet_end
    return local >= quiet_start or local < quiet_end


def notification_fingerprint(parts: Iterable[object]) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def follow_up_dates(
    submitted_at: datetime,
    *,
    expected_response_start: datetime | None,
    expected_response_end: datetime | None,
    default_days: int,
) -> tuple[datetime, datetime | None]:
    """Return the earliest and latest safe local follow-up dates."""
    submitted = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=UTC)
    earliest = expected_response_start or submitted + timedelta(days=default_days)
    latest = expected_response_end
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=UTC)
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return earliest, latest


def auto_preparation_gate(
    *,
    decision: str | None,
    eligibility: str | None,
    official_source: bool,
    verified_at: datetime | None,
    deadline: datetime | None,
    source_completeness: float,
    evaluation_current: bool,
    score: float,
    confidence: float,
    blocking_review: bool,
    user_passed: bool,
    lifecycle_permits: bool,
    budget_available: bool,
    now: datetime,
    freshness_hours: int,
    score_threshold: float,
    confidence_threshold: float,
) -> tuple[bool, str]:
    """Return a single deterministic gate result and a safe explanation."""
    checks = [
        (decision == "apply", "decision is not APPLY"),
        (eligibility == "eligible", "eligibility is not currently eligible"),
        (official_source, "verified official source is missing"),
        (
            verified_at is not None
            and (verified_at if verified_at.tzinfo else verified_at.replace(tzinfo=UTC))
            >= now - timedelta(hours=freshness_hours),
            "official source verification is stale",
        ),
        (
            deadline is not None
            and (deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)) > now,
            "future confirmed deadline is missing",
        ),
        (source_completeness >= 1, "official requirements are incomplete"),
        (evaluation_current, "evaluation inputs are stale"),
        (score >= score_threshold, "score is below automatic preparation threshold"),
        (confidence >= confidence_threshold, "confidence is below automatic preparation threshold"),
        (not blocking_review, "blocking review item is open"),
        (not user_passed, "user previously passed or withdrew"),
        (lifecycle_permits, "lifecycle does not permit preparation"),
        (budget_available, "automatic preparation budget is exhausted"),
    ]
    for passed, reason in checks:
        if not passed:
            return False, reason
    return True, "all automatic preparation gates passed"


def preference_sample_is_sufficient(count: int, minimum: int) -> bool:
    return count >= minimum


def opportunity_changed_materially(before: dict[str, object], after: dict[str, object]) -> bool:
    return any(
        before.get(key) != after.get(key)
        for key in {
            "deadline_at",
            "open_status",
            "application_url",
            "location",
            "source_completeness",
            "compensation_or_award",
        }
    )


def urgency_band(deadline: datetime | None, now: datetime) -> float:
    return urgency_score(deadline, now)

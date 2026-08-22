"""Deterministic hard policy checks for agent-proposed candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _behavior(policy: dict[str, Any], key: str, default: str = "allow") -> str:
    value = policy.get(key, default)
    return value if value in {"allow", "allow_with_warning", "reject"} else default


def evaluate_candidate(
    candidate: dict[str, Any], policy: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    global_policy = policy.get("global", {})
    category_policy = policy.get("categories", {}).get(candidate.get("category"), {})
    violations: list[str] = []
    warnings: list[str] = []

    status = str(candidate.get("status") or "unknown").lower()
    if bool(global_policy.get("reject_closed", True)) and status in {"closed", "expired"}:
        violations.append(f"status:{status}")
    deadline = parse_timestamp(candidate.get("deadline"))
    if deadline and deadline < current and bool(global_policy.get("reject_expired", True)):
        violations.append("deadline:expired")

    if bool(global_policy.get("require_official_verification", True)):
        if not candidate.get("official_url") or candidate.get("first_party") is False:
            violations.append("official_verification:required")
        if not candidate.get("verified_at"):
            violations.append("verified_at:required")

    freshness = category_policy.get("freshness", {})
    maximum_age = freshness.get("maximum_age_hours")
    if maximum_age is not None:
        published = parse_timestamp(candidate.get("published_at"))
        if published is None:
            behavior = _behavior(freshness, "unknown_age", "allow_with_warning")
            message = "published_at:unknown"
            (violations if behavior == "reject" else warnings).append(message)
        elif (current - published).total_seconds() > float(maximum_age) * 3600:
            violations.append("published_at:too_old")

    deadline_policy = category_policy.get("deadline", {})
    if deadline is None:
        behavior = _behavior(deadline_policy, "unknown", "allow")
        message = "deadline:unknown"
        (violations if behavior == "reject" else warnings).append(message)

    location_policy = category_policy.get("location", {})
    location_text = str(candidate.get("location") or "").lower()
    included = [str(item).lower() for item in location_policy.get("include", [])]
    excluded = [str(item).lower() for item in location_policy.get("exclude", [])]
    if included and not any(item in location_text for item in included):
        violations.append("location:not_included")
    if excluded and any(item in location_text for item in excluded):
        violations.append("location:excluded")

    exclusion = category_policy.get("exclude", {})
    for field in ("industry", "employment_type", "category"):
        value = candidate.get(field) or candidate.get("metadata", {}).get(field)
        excluded_values = [str(item).lower() for item in exclusion.get(f"{field}s", [])]
        if value and str(value).lower() in excluded_values:
            violations.append(f"{field}:excluded")

    return {
        "policy_result": "reject" if violations else ("warn" if warnings else "pass"),
        "violations": violations,
        "warnings": warnings,
    }

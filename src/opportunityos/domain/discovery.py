"""Pure deterministic policies for the V3 stateful discovery engine."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from urllib.parse import urlsplit

DISCOVERY_RULESET_VERSION = "3.0"

DISCOVERY_LENSES = (
    "scholarship",
    "fellowship",
    "undergraduate_research",
    "research_collaboration",
    "grant",
    "founder_program",
    "idea_stage_funding",
    "competition",
    "selective_technical",
    "open_source",
    "ai_ml",
    "ai_safety_security",
    "systems_infrastructure",
    "technical_entrepreneurship",
    "wildcard",
    "profile_gap",
    "similar_to_valued",
)
PRIMARY_LENSES = DISCOVERY_LENSES[:15]
STRATEGIC_LENSES = frozenset({"profile_gap", "similar_to_valued"})
EXPLORATORY_LENSES = frozenset({"wildcard"})
_SPACE_RE = re.compile(r"\s+")
_YEAR_RE = re.compile(r"\b20\d{2}\b")


def lens_class(lens: str) -> str:
    if lens in STRATEGIC_LENSES:
        return "strategic"
    if lens in EXPLORATORY_LENSES:
        return "exploratory"
    return "productive"


def normalize_query(query: str, *, max_length: int = 500) -> str:
    normalized = _SPACE_RE.sub(" ", query.strip()).casefold()
    if not normalized or len(normalized) > max_length:
        raise ValueError("Query must be non-empty and within the configured length")
    return normalized


def query_family(query: str) -> str:
    return _YEAR_RE.sub("{cycle}", normalize_query(query))


def canonical_source_domain(locator: str) -> str:
    parts = urlsplit(locator.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Source registry locators must be absolute HTTP(S) URLs")
    host = parts.hostname.casefold()
    return host[4:] if host.startswith("www.") else host


def deterministic_yield(
    *,
    raw: int,
    novel: int = 0,
    official_verified: int = 0,
    eligible: int = 0,
    apply: int = 0,
    maybe: int = 0,
    duplicate: int = 0,
    stale: int = 0,
    closed: int = 0,
    failures: int = 0,
) -> float:
    """Score search value, not search volume, on a stable 0-100 scale."""
    denominator = max(1, raw)
    positive = novel * 2 + official_verified * 3 + eligible * 5 + apply * 8 + maybe * 3
    negative = duplicate * 1.5 + stale + closed + failures * 2
    return round(max(0.0, min(100.0, (positive - negative) * 10 / denominator)), 2)


def recent_yield(observations: Sequence[Mapping[str, int]]) -> float:
    totals: dict[str, int] = {}
    for observation in observations:
        for key, value in observation.items():
            totals[key] = totals.get(key, 0) + max(0, int(value))
    return deterministic_yield(
        raw=totals.get("raw", 0),
        novel=totals.get("novel", 0),
        official_verified=totals.get("official_verified", 0),
        eligible=totals.get("eligible", 0),
        apply=totals.get("apply", 0),
        maybe=totals.get("maybe", 0),
        duplicate=totals.get("duplicate", 0),
        stale=totals.get("stale", 0),
        closed=totals.get("closed", 0),
        failures=totals.get("failures", 0),
    )


def allocate_queries(
    *,
    total: int,
    lenses: Iterable[str],
    baseline: int,
    productive_percent: int,
    strategic_percent: int,
    exploratory_percent: int,
) -> dict[str, int]:
    names = sorted(set(lenses))
    if not names or total < len(names) * baseline:
        raise ValueError("Global query budget cannot satisfy every lens baseline")
    if productive_percent + strategic_percent + exploratory_percent != 100:
        raise ValueError("Allocation percentages must total 100")
    allocation = {lens: baseline for lens in names}
    class_targets = {
        "productive": total * productive_percent // 100,
        "strategic": total * strategic_percent // 100,
        "exploratory": total * exploratory_percent // 100,
    }
    groups = _group_lenses(names)
    minimums = {
        class_name: len(class_lenses) * baseline for class_name, class_lenses in groups.items()
    }
    if sum(max(minimums[name], class_targets[name]) for name in groups) > total:
        class_targets = minimums
    else:
        remainder = total - sum(max(minimums[name], class_targets[name]) for name in groups)
        class_targets["productive"] = max(
            minimums["productive"], class_targets["productive"] + remainder
        )
    for class_name, class_lenses in groups.items():
        target = max(
            len(class_lenses) * baseline,
            class_targets[class_name],
        )
        for lens in class_lenses:
            if target <= len(class_lenses) * baseline:
                break
            allocation[lens] += 1
            target -= 1
        index = 0
        while target > len(class_lenses) * baseline:
            allocation[class_lenses[index % len(class_lenses)]] += 1
            target -= 1
            index += 1
    remainder = total - sum(allocation.values())
    for index in range(max(0, remainder)):
        allocation[names[index % len(names)]] += 1
    return allocation


def _group_lenses(lenses: Sequence[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"productive": [], "strategic": [], "exploratory": []}
    for lens in lenses:
        groups[lens_class(lens)].append(lens)
    return groups


def saturation_decision(
    observations: Sequence[Mapping[str, int]],
    *,
    queries_used: int,
    baseline: int,
    no_novel_queries: int,
    no_qualified_queries: int,
    duplicate_rate: float,
    max_depth_reached: bool = False,
    due_sources_complete: bool = False,
) -> tuple[bool, str | None]:
    if queries_used < baseline:
        return False, None
    if max_depth_reached:
        return True, "adaptive depth limit reached"
    if due_sources_complete and observations:
        return True, "due high-yield sources checked after baseline coverage"
    recent_novel = [int(item.get("novel", 0)) for item in observations]
    if len(recent_novel) >= no_novel_queries and all(
        value == 0 for value in recent_novel[-no_novel_queries:]
    ):
        return True, "marginal novelty collapsed"
    recent = observations[-no_qualified_queries:]
    if len(recent) >= no_qualified_queries:
        raw = sum(int(item.get("raw", 0)) for item in recent)
        qualified = sum(int(item.get("qualified", 0)) for item in recent)
        duplicates = sum(int(item.get("duplicate", 0)) for item in recent)
        if qualified == 0 and duplicates / max(1, raw) >= duplicate_rate:
            return True, "high duplicate rate with no qualified candidates"
    return False, None


def coverage_contract(
    *,
    enabled_lenses: Iterable[str],
    completed_lenses: Iterable[str],
    skipped_lenses: Mapping[str, str],
    baseline_counts: Mapping[str, int],
    baseline_floor: int,
    source_checks_due: int,
    source_checks_completed: int,
    adaptive_triggered: bool,
    dedup_completed: bool,
    official_verified: int,
    deep_evaluated: int,
    hard_failure: bool,
) -> bool:
    enabled = set(enabled_lenses)
    completed = set(completed_lenses)
    baseline_ok = all(
        baseline_counts.get(lens, 0) >= baseline_floor
        for lens in enabled
        if lens not in skipped_lenses
    )
    return bool(
        enabled
        and enabled - set(skipped_lenses) <= completed
        and baseline_ok
        and not skipped_lenses
        and source_checks_completed >= source_checks_due
        and (adaptive_triggered or not enabled)
        and dedup_completed
        and official_verified >= 0
        and deep_evaluated >= 0
        and not hard_failure
    )

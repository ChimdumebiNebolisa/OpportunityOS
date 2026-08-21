"""Deterministic profile reconciliation rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Candidate:
    id: str
    field_path: str
    value: Any
    value_type: str
    source_id: str
    source_type: str
    trust_class: str
    confidence: float
    effective_from: datetime | None
    effective_until: datetime | None
    observed_at: datetime
    source_locator: str | None = None


@dataclass(frozen=True)
class ReconciliationPlan:
    field_path: str
    selected_id: str | None
    selected_value: Any | None
    selected_confidence: float
    superseded_ids: tuple[str, ...]
    conflicted_ids: tuple[str, ...]
    reason: str


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in sorted(value.items())}
    return value


def values_equal(left: Any, right: Any) -> bool:
    return json.dumps(normalize_value(left), sort_keys=True) == json.dumps(
        normalize_value(right), sort_keys=True
    )


def intervals_overlap(left: Candidate, right: Candidate) -> bool:
    start_left = left.effective_from or datetime.min.replace(tzinfo=left.observed_at.tzinfo)
    start_right = right.effective_from or datetime.min.replace(tzinfo=right.observed_at.tzinfo)
    end_left = left.effective_until or datetime.max.replace(tzinfo=left.observed_at.tzinfo)
    end_right = right.effective_until or datetime.max.replace(tzinfo=right.observed_at.tzinfo)
    return start_left < end_right and start_right < end_left


def authority(candidate: Candidate) -> int:
    field = candidate.field_path
    source = candidate.source_type
    trust = candidate.trust_class.lower()
    if source == "model_inference":
        return 5
    if source == "github_api":
        return 85 if field.startswith(("github.", "projects.")) else 25
    if source == "user_statement" and any(
        token in field for token in ("goal", "preference", "intended", "expected_graduation")
    ):
        return 95
    if "official" in trust or source == "official_webpage":
        return 90
    if source == "user_statement":
        return 80
    if source == "local_document":
        return 65
    if source == "chatgpt_snapshot":
        return 45
    return 40


def reconcile_field(candidates: list[Candidate]) -> ReconciliationPlan:
    """Return a persistence-neutral projection/conflict plan for one field."""
    if not candidates:
        raise ValueError("At least one candidate is required")
    field = candidates[0].field_path
    if any(candidate.field_path != field for candidate in candidates):
        raise ValueError("All candidates must belong to the same field")

    ordered = sorted(candidates, key=lambda item: (authority(item), item.observed_at), reverse=True)
    winner = ordered[0]
    superseded: list[str] = []
    conflicts: list[str] = []

    for other in ordered[1:]:
        if values_equal(winner.value, other.value):
            superseded.append(other.id)
            continue
        same_source = winner.source_id == other.source_id or bool(
            winner.source_locator
            and other.source_locator
            and winner.source_locator == other.source_locator
        )
        newer = winner.observed_at > other.observed_at
        if same_source and newer:
            superseded.append(other.id)
            continue
        authority_gap = authority(winner) - authority(other)
        if authority_gap >= 20:
            superseded.append(other.id)
            continue
        if intervals_overlap(winner, other):
            conflicts.extend([winner.id, other.id])
        else:
            superseded.append(other.id)

    if conflicts:
        return ReconciliationPlan(
            field_path=field,
            selected_id=None,
            selected_value=None,
            selected_confidence=0,
            superseded_ids=tuple(dict.fromkeys(superseded)),
            conflicted_ids=tuple(dict.fromkeys(conflicts)),
            reason="credible_overlapping_values_disagree",
        )
    return ReconciliationPlan(
        field_path=field,
        selected_id=winner.id,
        selected_value=normalize_value(winner.value),
        selected_confidence=winner.confidence,
        superseded_ids=tuple(superseded),
        conflicted_ids=(),
        reason="deterministic_authority_and_recency_winner",
    )

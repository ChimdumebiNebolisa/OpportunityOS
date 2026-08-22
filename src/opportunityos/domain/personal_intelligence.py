"""Pure policy for V3.1 personal-source evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from opportunityos.domain.profile import normalize_value, values_equal

ALLOWED_ASSERTIONS = {
    "reported",
    "observed",
    "inferred",
    "direct_assertion",
    "correction",
    "intention",
    "external_authoritative_result",
}
SUPPRESSED_ASSERTIONS = {
    "hypothetical",
    "brainstorming",
    "quoted",
    "copied_source",
    "third_party",
    "assistant_summary",
    "uncertain",
}
HIGH_IMPACT_PREFIXES = (
    "education.",
    "career.",
    "goals.",
    "constraints.",
    "preferences.",
    "research.",
    "opportunities.",
    "projects.",
)


@dataclass(frozen=True)
class AssertionClassification:
    assertion_kind: str
    subject_identity: str
    eligible_for_profile: bool
    reason: str


@dataclass(frozen=True)
class MaterialityDecision:
    material: bool
    score: float
    reason: str


def _digest(value: Any) -> str:
    payload = json.dumps(normalize_value(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_fingerprint(
    *, locator: str, content: str = "", provider_fingerprint: str | None = None
) -> str:
    """Return a stable record fingerprint without retaining the source body."""
    return _digest(
        {
            "locator": locator,
            "content": content.strip()[:5000],
            "provider_fingerprint": provider_fingerprint,
        }
    )


def candidate_fingerprint(
    *,
    field_path: str,
    value: Any,
    effective_from: datetime | None,
    source_event_at: datetime | None,
    content_fingerprint_value: str | None,
) -> str:
    return _digest(
        {
            "field_path": field_path,
            "value": normalize_value(value),
            "effective_from": effective_from.isoformat() if effective_from else None,
            "source_event_at": source_event_at.isoformat() if source_event_at else None,
            "content_fingerprint": content_fingerprint_value,
        }
    )


def classify_assertion(
    *,
    text: str = "",
    author_role: str = "user",
    subject_identity: str = "user",
    assertion_kind: str | None = None,
) -> AssertionClassification:
    """Classify untrusted text without treating it as executable instruction."""
    normalized_subject = subject_identity.strip().lower() or "unknown"
    explicit = (assertion_kind or "").strip().lower()
    lowered = text.strip().lower()
    if normalized_subject not in {"user", "self", "me"}:
        return AssertionClassification(
            "third_party", normalized_subject, False, "subject_is_not_user"
        )
    if author_role.strip().lower() in {"assistant", "model", "system"}:
        return AssertionClassification("assistant_summary", "user", False, "assistant_authored")
    if explicit in SUPPRESSED_ASSERTIONS:
        return AssertionClassification(explicit, "user", False, "explicitly_suppressed")
    if explicit in ALLOWED_ASSERTIONS:
        return AssertionClassification(explicit, "user", True, "explicitly_classified")
    if re.search(r"\b(hypothetically|hypothetical|if i were|suppose i)\b", lowered):
        return AssertionClassification("hypothetical", "user", False, "hypothetical_language")
    if re.search(r"\b(quoted|quote|forwarded|original message|wrote:)\b", lowered):
        return AssertionClassification("quoted", "user", False, "quoted_or_forwarded_language")
    if re.search(r"\b(i might|i may|i could|i am considering|i'm considering|maybe i)\b", lowered):
        return AssertionClassification("intention", "user", True, "future_intention")
    if lowered.startswith(
        ("no,", "actually", "correction", "correct that", "to clarify")
    ) or re.search(r"\b(correction|correct that)\b", lowered):
        return AssertionClassification("correction", "user", True, "explicit_correction")
    return AssertionClassification("direct_assertion", "user", True, "user_authored_statement")


def materiality(
    *,
    field_path: str,
    value: Any,
    current_value: Any | None,
    confidence: float,
    assertion_kind: str,
    threshold: float,
) -> MaterialityDecision:
    if assertion_kind in SUPPRESSED_ASSERTIONS:
        return MaterialityDecision(False, 0, "suppressed_assertion")
    if current_value is not None and values_equal(current_value, value):
        return MaterialityDecision(False, 0, "exact_agreement")
    score = confidence
    if field_path.startswith(HIGH_IMPACT_PREFIXES):
        score = min(1.0, score + 0.15)
    if assertion_kind == "correction":
        score = min(1.0, score + 0.10)
    return MaterialityDecision(
        score >= threshold, score, "material_change" if score >= threshold else "below_threshold"
    )


def source_modes_valid(source: str, mode: str) -> bool:
    if source in {"github", "gmail"}:
        return mode in {"disabled", "continuous"}
    if source == "chatgpt":
        return mode in {"disabled", "snapshot_only", "continuous"}
    return False

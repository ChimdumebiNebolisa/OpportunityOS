"""Durable automation controls and automatic-preparation policy."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from opportunityos.application.applications import ApplicationService
from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.behavior import BEHAVIOR_RULESET_VERSION, auto_preparation_gate
from opportunityos.infrastructure.database import (
    AutomationControlRow,
    CanonicalFactRow,
    DecisionEventRow,
    EvaluationRow,
    OpportunityRow,
    PreparationPolicyRow,
    ReviewItemRow,
    SourceRow,
)
from opportunityos.schemas import ClaimInput, LifecycleState
from opportunityos.util import new_id, utc_now

CONTROL_KEYS = {
    "automation",
    "scouts",
    "discovery",
    "auto_prepare",
    "reminders",
    "daily_brief",
    "evening_rescue",
    "weekly_strategy",
}


class AutomationService:
    """Expose local automation policy without owning V1 truth or transport."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def set_control(
        self, key: str, enabled: bool, *, reason: str = "user control"
    ) -> dict[str, Any]:
        if key not in CONTROL_KEYS:
            raise ValueError(f"Unknown automation control: {key}")
        with self.context.database.transaction() as session:
            row = session.get(AutomationControlRow, key)
            now = utc_now()
            if row is None:
                row = AutomationControlRow(
                    key=key, enabled=enabled, reason=reason[:500], updated_at=now
                )
                session.add(row)
            else:
                row.enabled = enabled
                row.reason = reason[:500]
                row.updated_at = now
            audit(
                session,
                event_type="automation_control_changed",
                reason=reason[:500],
                subject_type="automation_control",
                subject_id=key,
                actor="user",
                details={"enabled": enabled},
            )
            return {"key": key, "enabled": enabled, "reason": reason[:500]}

    def controls(self) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            stored = {row.key: row for row in session.scalars(select(AutomationControlRow)).all()}
            defaults = {
                "automation": self.context.settings.automation.enabled,
                "scouts": self.context.settings.scouts.enabled,
                "discovery": self.context.settings.discovery.enabled,
                "auto_prepare": self.context.settings.auto_prepare.enabled,
                "reminders": self.context.settings.notifications.enabled,
                "daily_brief": self.context.settings.briefs.daily_enabled,
                "evening_rescue": self.context.settings.briefs.evening_rescue_enabled,
                "weekly_strategy": self.context.settings.briefs.weekly_strategy_enabled,
            }
            return [
                {
                    "key": key,
                    "enabled": stored[key].enabled if key in stored else defaults[key],
                    "reason": stored[key].reason if key in stored else "configured default",
                    "updated_at": stored[key].updated_at if key in stored else None,
                }
                for key in sorted(CONTROL_KEYS)
            ]

    def _control_enabled(self, session: Any, key: str) -> bool:
        row = session.get(AutomationControlRow, key)
        if row is not None:
            return bool(row.enabled)
        defaults = {
            "automation": self.context.settings.automation.enabled,
            "scouts": self.context.settings.scouts.enabled,
            "discovery": self.context.settings.discovery.enabled,
            "auto_prepare": self.context.settings.auto_prepare.enabled,
            "reminders": self.context.settings.notifications.enabled,
            "daily_brief": self.context.settings.briefs.daily_enabled,
            "evening_rescue": self.context.settings.briefs.evening_rescue_enabled,
            "weekly_strategy": self.context.settings.briefs.weekly_strategy_enabled,
        }
        return defaults[key]

    def auto_preparation_gate(
        self, opportunity_id: str, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        operation = "auto_prepare.evaluate_gate"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            projection = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            sources = session.scalars(
                select(SourceRow).where(SourceRow.id.in_(opportunity.source_ids))
            ).all()
            official = any(
                source.official_status == "official" and source.source_type == "official_webpage"
                for source in sources
            )
            blocking_review = bool(
                session.scalar(
                    select(ReviewItemRow.id).where(
                        ReviewItemRow.status == "open",
                        ReviewItemRow.severity == "high",
                        ReviewItemRow.subject_ref == opportunity_id,
                    )
                )
            )
            user_passed = bool(
                session.scalar(
                    select(DecisionEventRow.id).where(
                        DecisionEventRow.opportunity_id == opportunity_id,
                        DecisionEventRow.actor == "user",
                        DecisionEventRow.decision.in_(["pass", "withdrawn"]),
                    )
                )
            )
            prepared_today = int(
                session.scalar(
                    select(func.count(PreparationPolicyRow.id)).where(
                        PreparationPolicyRow.created_at
                        >= datetime.combine(utc_now().date(), datetime.min.time(), tzinfo=UTC),
                        PreparationPolicyRow.gate_result == "pass",
                        PreparationPolicyRow.prepared_application_id.is_not(None),
                    )
                )
                or 0
            )
            now = utc_now()
            permitted_lifecycle = opportunity.lifecycle_state in {
                LifecycleState.EVALUATED.value,
                LifecycleState.SHORTLISTED.value,
                LifecycleState.PREPARING.value,
            }
            passed, reason = auto_preparation_gate(
                decision=evaluation.decision_label if evaluation else None,
                eligibility=(evaluation.eligibility_summary.get("overall") if evaluation else None),
                official_source=official,
                verified_at=opportunity.last_verified_at,
                deadline=opportunity.deadline_at,
                source_completeness=opportunity.source_completeness,
                evaluation_current=bool(
                    evaluation
                    and evaluation.profile_projection_version == projection
                    and evaluation.opportunity_version == opportunity.version
                ),
                score=evaluation.net_value_score if evaluation else 0,
                confidence=evaluation.decision_confidence if evaluation else 0,
                blocking_review=blocking_review,
                user_passed=user_passed,
                lifecycle_permits=permitted_lifecycle,
                budget_available=prepared_today < self.context.settings.auto_prepare.max_per_day,
                now=now,
                freshness_hours=self.context.settings.auto_prepare.freshness_hours,
                score_threshold=self.context.settings.auto_prepare.score_threshold,
                confidence_threshold=self.context.settings.auto_prepare.confidence_threshold,
            )
            if not self._control_enabled(session, "automation"):
                passed, reason = False, "all proactive automation is paused"
            elif not self._control_enabled(session, "auto_prepare"):
                passed, reason = False, "automatic preparation is disabled"
            policy = PreparationPolicyRow(
                id=new_id(),
                opportunity_id=opportunity_id,
                evaluation_id=evaluation.id if evaluation else None,
                gate_version=BEHAVIOR_RULESET_VERSION,
                score=evaluation.net_value_score if evaluation else 0,
                confidence=evaluation.decision_confidence if evaluation else 0,
                gate_result="pass" if passed else "fail",
                reason=reason,
                prepared_application_id=None,
                created_at=now,
            )
            session.add(policy)
            result = {
                "policy_id": policy.id,
                "opportunity_id": opportunity_id,
                "gate_result": policy.gate_result,
                "reason": reason,
                "score": policy.score,
                "confidence": policy.confidence,
                "ruleset_version": policy.gate_version,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def auto_prepare_execute(
        self,
        opportunity_id: str,
        claims: list[ClaimInput],
        *,
        generation_model: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "auto_prepare.execute"
        previous: dict[str, Any] | None = None
        if idempotency_key:
            with self.context.database.transaction() as session:
                previous = idempotent_result(session, idempotency_key, operation)
        if previous:
            return previous
        gate = self.auto_preparation_gate(
            opportunity_id,
            idempotency_key=f"{idempotency_key}:gate" if idempotency_key else None,
        )
        if gate["gate_result"] != "pass":
            raise ValueError(f"Automatic preparation blocked: {gate['reason']}")
        packet = ApplicationService(self.context).prepare(
            opportunity_id,
            claims,
            generation_model=generation_model,
            idempotency_key=f"{idempotency_key}:packet" if idempotency_key else None,
        )
        with self.context.database.transaction() as session:
            policy = session.get(PreparationPolicyRow, gate["policy_id"])
            if policy is not None:
                policy.prepared_application_id = packet["application_id"]
            audit(
                session,
                event_type="automatic_packet_prepared",
                reason="automatic preparation gate passed",
                subject_type="opportunity",
                subject_id=opportunity_id,
                after_ids=[packet["application_id"]],
                ruleset_version=BEHAVIOR_RULESET_VERSION,
                details={"external_submission_performed": False},
            )
            result = {**packet, "automatic": True, "external_submission_performed": False}
            store_idempotent(session, idempotency_key, operation, result)
            return result

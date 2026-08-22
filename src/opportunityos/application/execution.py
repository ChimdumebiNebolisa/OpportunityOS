"""Execution-risk and reminder interface for proactive local work."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.behavior import (
    BEHAVIOR_RULESET_VERSION,
    in_quiet_hours,
    notification_fingerprint,
    reminder_severity,
)
from opportunityos.infrastructure.database import (
    ActionItemRow,
    ApplicationRow,
    AuditEventRow,
    AutomationControlRow,
    CanonicalFactRow,
    EvaluationRow,
    OpportunityRow,
    ReminderStateRow,
    ReviewItemRow,
)
from opportunityos.schemas import ActionStatus, DecisionLabel, LifecycleState
from opportunityos.util import new_id, utc_now


class ExecutionService:
    """Keep reminder state durable while reusing V1 current-evaluation guards."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def _projection_version(self, session: Any) -> int:
        return int(session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0)

    def _latest_evaluations(self, session: Any) -> dict[str, EvaluationRow]:
        rows = session.scalars(
            select(EvaluationRow).order_by(EvaluationRow.created_at.desc())
        ).all()
        latest: dict[str, EvaluationRow] = {}
        for row in rows:
            latest.setdefault(row.opportunity_id, row)
        return latest

    def get_risk(self, *, available_minutes: int | None = None) -> list[dict[str, Any]]:
        """Return current reminder candidates without claiming external delivery."""
        if not self.context.settings.automation.enabled:
            return []
        minutes = available_minutes or self.context.settings.default_action_minutes
        if minutes < 1:
            raise ValueError("Available minutes must be positive")
        now = utc_now()
        if not self.context.settings.notifications.enabled:
            return []
        try:
            local_now = now.astimezone(ZoneInfo(self.context.settings.timezone))
        except ZoneInfoNotFoundError:
            local_now = now
        if in_quiet_hours(
            local_now,
            self.context.settings.notifications.quiet_hours_start,
            self.context.settings.notifications.quiet_hours_end,
        ):
            return []
        with self.context.database.transaction() as session:
            automation_control = session.get(AutomationControlRow, "automation")
            reminders_control = session.get(AutomationControlRow, "reminders")
            if (automation_control and not automation_control.enabled) or (
                reminders_control and not reminders_control.enabled
            ):
                return []
            if self._delivered_today(session) >= self.context.settings.notifications.daily_cap:
                return []
            projection_version = self._projection_version(session)
            latest = self._latest_evaluations(session)
            opportunities = {row.id: row for row in session.scalars(select(OpportunityRow)).all()}
            candidates: list[dict[str, Any]] = []
            for action in session.scalars(
                select(ActionItemRow).where(
                    ActionItemRow.status.in_(
                        [ActionStatus.READY.value, ActionStatus.IN_PROGRESS.value]
                    )
                )
            ).all():
                if not action.opportunity_id:
                    continue
                opportunity = opportunities.get(action.opportunity_id)
                evaluation = latest.get(action.opportunity_id)
                if opportunity is None or evaluation is None:
                    continue
                if (
                    evaluation.profile_projection_version != projection_version
                    or evaluation.opportunity_version != opportunity.version
                    or evaluation.decision_label != DecisionLabel.APPLY.value
                    or evaluation.net_value_score < self.context.settings.execution.nudge_min_score
                    or action.estimated_minutes > minutes * 4
                ):
                    continue
                blocking_review = session.scalar(
                    select(ReviewItemRow.id).where(
                        ReviewItemRow.status == "open",
                        ReviewItemRow.severity == "high",
                        ReviewItemRow.subject_ref == opportunity.id,
                    )
                )
                if blocking_review:
                    continue
                severity = reminder_severity(
                    deadline=opportunity.deadline_at,
                    now=now,
                    completion_ratio=action.completion_ratio,
                    value=evaluation.net_value_score,
                )
                if severity == 0:
                    continue
                state = session.scalar(
                    select(ReminderStateRow).where(
                        ReminderStateRow.opportunity_id == opportunity.id,
                        ReminderStateRow.action_id == action.id,
                        ReminderStateRow.reminder_type == "completion",
                    )
                )
                fingerprint = notification_fingerprint(
                    [
                        "completion",
                        opportunity.id,
                        opportunity.version,
                        evaluation.id,
                        severity,
                        round(action.completion_ratio, 3),
                        action.estimated_minutes,
                    ]
                )
                if state is None:
                    state = ReminderStateRow(
                        id=new_id(),
                        opportunity_id=opportunity.id,
                        action_id=action.id,
                        reminder_type="completion",
                        severity=severity,
                        first_due_at=now,
                        next_due_at=now,
                        snoozed_until=None,
                        last_delivered_at=None,
                        last_delivery_fingerprint=None,
                        delivery_count=0,
                        stopped=False,
                        stopped_reason=None,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(state)
                if state.stopped or (state.snoozed_until and state.snoozed_until > now):
                    continue
                if state.last_delivery_fingerprint == fingerprint and state.last_delivered_at:
                    delivered_at = state.last_delivered_at
                    if delivered_at.tzinfo is None:
                        delivered_at = delivered_at.replace(tzinfo=UTC)
                    if delivered_at >= now - timedelta(days=1):
                        continue
                state.severity = severity
                state.next_due_at = now
                state.updated_at = now
                candidates.append(
                    {
                        "reminder_id": state.id,
                        "opportunity_id": opportunity.id,
                        "action_id": action.id,
                        "reminder_type": state.reminder_type,
                        "severity": severity,
                        "fingerprint": fingerprint,
                        "title": opportunity.canonical_title,
                        "deadline": opportunity.deadline_at,
                        "remaining_human_minutes": action.estimated_minutes,
                        "packet_ready": bool(
                            session.scalar(
                                select(ApplicationRow.id).where(
                                    ApplicationRow.opportunity_id == opportunity.id,
                                    ApplicationRow.state == LifecycleState.READY.value,
                                )
                            )
                        ),
                        "next_action": action.description,
                    }
                )
            ranked = sorted(
                candidates,
                key=lambda item: (-int(item["severity"]), item["deadline"] or now),
            )
            return ranked[: self.context.settings.notifications.daily_cap]

    def _delivered_today(self, session: Any) -> int:
        start = datetime.combine(utc_now().date(), datetime.min.time(), tzinfo=UTC)
        return int(
            session.scalar(
                select(func.count(AuditEventRow.id)).where(
                    AuditEventRow.event_type == "proactive_notification_delivered",
                    AuditEventRow.created_at >= start,
                )
            )
            or 0
        )

    def record_delivery(
        self, reminder_id: str, fingerprint: str, *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        operation = "execution.record_delivery"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            if self._delivered_today(session) >= self.context.settings.notifications.daily_cap:
                raise ValueError("Daily proactive notification cap reached")
            state = session.get(ReminderStateRow, reminder_id)
            if state is None or state.stopped:
                raise ValueError("Reminder is not deliverable")
            now = utc_now()
            state.last_delivered_at = now
            state.last_delivery_fingerprint = fingerprint
            state.delivery_count += 1
            state.updated_at = now
            audit(
                session,
                event_type="proactive_notification_delivered",
                reason="material reminder approved for Hermes delivery",
                subject_type="reminder",
                subject_id=state.id,
                after_ids=[state.opportunity_id, state.action_id],
                ruleset_version=BEHAVIOR_RULESET_VERSION,
                details={"reminder_type": state.reminder_type, "fingerprint": fingerprint},
            )
            result = {"reminder_id": state.id, "delivered": True, "fingerprint": fingerprint}
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def snooze(
        self,
        action_id: str,
        until: datetime | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "execution.snooze"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            state = session.scalar(
                select(ReminderStateRow).where(ReminderStateRow.action_id == action_id)
            )
            if state is None:
                raise ValueError("Reminder state not found")
            snoozed_until = until or utc_now() + timedelta(
                hours=self.context.settings.notifications.default_snooze_hours
            )
            if snoozed_until.tzinfo is None:
                snoozed_until = snoozed_until.replace(tzinfo=UTC)
            state.snoozed_until = snoozed_until
            state.next_due_at = snoozed_until
            state.updated_at = utc_now()
            result = {"action_id": action_id, "snoozed_until": snoozed_until}
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def stop(
        self, opportunity_id: str, *, reason: str = "user stopped reminders"
    ) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            states = session.scalars(
                select(ReminderStateRow).where(ReminderStateRow.opportunity_id == opportunity_id)
            ).all()
            if not states:
                raise ValueError("Reminder state not found")
            now = utc_now()
            for state in states:
                state.stopped = True
                state.stopped_reason = reason[:500]
                state.updated_at = now
            audit(
                session,
                event_type="reminders_stopped",
                reason=reason[:500],
                subject_type="opportunity",
                subject_id=opportunity_id,
                actor="user",
            )
            return {"opportunity_id": opportunity_id, "stopped": True, "count": len(states)}

    def mark_passed(self, opportunity_id: str) -> dict[str, Any]:
        """Stop local reminders after the user explicitly passes an opportunity."""
        return self.stop(opportunity_id, reason="user passed opportunity")

    def mark_applied(self, opportunity_id: str) -> dict[str, Any]:
        """Stop local reminders after the user records an external application."""
        return self.stop(opportunity_id, reason="user marked opportunity applied")

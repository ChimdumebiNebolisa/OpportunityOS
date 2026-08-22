"""Material-only daily, rescue, and strategy brief interface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from opportunityos.application.common import audit
from opportunityos.application.context import ApplicationContext
from opportunityos.application.decisions import DecisionService
from opportunityos.application.followup import FollowUpService
from opportunityos.domain.behavior import notification_fingerprint, preference_sample_is_sufficient
from opportunityos.infrastructure.database import (
    AutomationControlRow,
    BriefRunRow,
    DecisionEventRow,
    EvaluationRow,
    OpportunityRow,
    StrategySnapshotRow,
)
from opportunityos.schemas import LifecycleState
from opportunityos.util import new_id, utc_now


class BriefService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def build(self, brief_type: str, *, available_minutes: int | None = None) -> dict[str, Any]:
        if brief_type not in {"daily", "evening", "weekly"}:
            raise ValueError("brief_type must be daily, evening, or weekly")
        if brief_type == "daily" and not self.context.settings.briefs.daily_enabled:
            return {"brief_type": brief_type, "delivery_result": "silent", "items": []}
        if brief_type == "evening" and not self.context.settings.briefs.evening_rescue_enabled:
            return {"brief_type": brief_type, "delivery_result": "silent", "items": []}
        if brief_type == "weekly" and not self.context.settings.briefs.weekly_strategy_enabled:
            return {"brief_type": brief_type, "delivery_result": "silent", "items": []}
        control_key = {
            "daily": "daily_brief",
            "evening": "evening_rescue",
            "weekly": "weekly_strategy",
        }[brief_type]
        with self.context.database.transaction() as session:
            automation_control = session.get(AutomationControlRow, "automation")
            brief_control = session.get(AutomationControlRow, control_key)
            if (automation_control and not automation_control.enabled) or (
                brief_control and not brief_control.enabled
            ):
                return {"brief_type": brief_type, "delivery_result": "silent", "items": []}
        queue = DecisionService(self.context).queue(available_minutes)
        due_followups = FollowUpService(self.context).get_due()
        now = utc_now()
        with self.context.database.transaction() as session:
            if brief_type == "weekly":
                items, metrics, recommendation = self._weekly(session, now)
            else:
                items = self._items(session, brief_type, queue, due_followups, now)
                metrics = {}
                recommendation = None
            selected_ids = [str(item["id"]) for item in items]
            fingerprint = notification_fingerprint([brief_type, *selected_ids])
            previous = session.scalar(
                select(BriefRunRow)
                .where(BriefRunRow.brief_type == brief_type)
                .order_by(BriefRunRow.started_at.desc())
            )
            if not items or (previous and previous.fingerprint == fingerprint):
                result = {
                    "brief_type": brief_type,
                    "delivery_result": "silent",
                    "items": [],
                    "metrics": metrics,
                }
                session.add(
                    BriefRunRow(
                        id=new_id(),
                        brief_type=brief_type,
                        started_at=now,
                        ended_at=utc_now(),
                        selected_item_ids=[],
                        delivery_result="silent",
                        fingerprint=fingerprint,
                    )
                )
                return result
            run = BriefRunRow(
                id=new_id(),
                brief_type=brief_type,
                started_at=now,
                ended_at=utc_now(),
                selected_item_ids=selected_ids,
                delivery_result="digest",
                fingerprint=fingerprint,
            )
            session.add(run)
            if recommendation is not None:
                session.add(
                    StrategySnapshotRow(
                        id=new_id(),
                        period_start=now - timedelta(days=7),
                        period_end=now,
                        metrics=metrics,
                        recommendation=recommendation,
                        evidence_count=int(metrics.get("evidence_count", 0)),
                        created_at=now,
                    )
                )
            audit(
                session,
                event_type="brief_built",
                reason="material local brief built",
                subject_type="brief",
                subject_id=run.id,
                ruleset_version="2.0",
                details={"brief_type": brief_type, "item_count": len(items)},
            )
            return {
                "brief_id": run.id,
                "brief_type": brief_type,
                "delivery_result": "digest",
                "items": items,
                "metrics": metrics,
                "recommendation": recommendation,
                "message": self._render(brief_type, items, recommendation),
            }

    def _items(
        self,
        session: Any,
        brief_type: str,
        queue: list[dict[str, Any]],
        due_followups: list[dict[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if brief_type == "evening":
            for item in queue:
                deadline = item.get("deadline")
                if deadline is None:
                    continue
                due = deadline if deadline.tzinfo else deadline.replace(tzinfo=UTC)
                if due <= now + timedelta(
                    hours=self.context.settings.execution.deadline_rescue_hours
                ):
                    items.append({"id": item["action_id"], "kind": "rescue", **item})
        else:
            for item in queue:
                if (
                    float(item["net_value_score"])
                    >= self.context.settings.execution.nudge_min_score
                ):
                    items.append({"id": item["action_id"], "kind": "needs_completion", **item})
            for item in due_followups:
                items.append({"id": item["follow_up_id"], "kind": "follow_up", **item})
            recent = session.scalars(
                select(EvaluationRow)
                .where(EvaluationRow.created_at >= now - timedelta(days=1))
                .order_by(EvaluationRow.created_at.desc())
            ).all()
            opportunities = {row.id: row for row in session.scalars(select(OpportunityRow)).all()}
            seen = {str(item["opportunity_id"]) for item in items if "opportunity_id" in item}
            for evaluation in recent:
                opportunity = opportunities.get(evaluation.opportunity_id)
                if (
                    opportunity
                    and opportunity.id not in seen
                    and evaluation.decision_label == "apply"
                    and evaluation.net_value_score
                    >= self.context.settings.execution.high_value_threshold
                ):
                    items.append(
                        {
                            "id": evaluation.id,
                            "kind": "new",
                            "opportunity_id": opportunity.id,
                            "title": opportunity.canonical_title,
                            "decision": evaluation.decision_label,
                            "net_value_score": evaluation.net_value_score,
                            "deadline": opportunity.deadline_at,
                        }
                    )
                    seen.add(opportunity.id)
        return items[: self.context.settings.briefs.max_items]

    def _weekly(
        self, session: Any, now: datetime
    ) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
        since = now - timedelta(days=7)
        discovered = int(
            session.scalar(
                select(func.count(EvaluationRow.id)).where(EvaluationRow.created_at >= since)
            )
            or 0
        )
        apply_count = int(
            session.scalar(
                select(func.count(EvaluationRow.id)).where(
                    EvaluationRow.created_at >= since, EvaluationRow.decision_label == "apply"
                )
            )
            or 0
        )
        submitted = int(
            session.scalar(
                select(func.count(DecisionEventRow.id)).where(
                    DecisionEventRow.created_at >= since,
                    DecisionEventRow.decision == LifecycleState.SUBMITTED.value,
                )
            )
            or 0
        )
        expired = int(
            session.scalar(
                select(func.count(DecisionEventRow.id)).where(
                    DecisionEventRow.created_at >= since,
                    DecisionEventRow.decision == LifecycleState.EXPIRED.value,
                )
            )
            or 0
        )
        evidence_count = discovered + submitted
        metrics = {
            "evaluations": discovered,
            "apply_count": apply_count,
            "submitted_count": submitted,
            "expired_count": expired,
            "evidence_count": evidence_count,
        }
        if not preference_sample_is_sufficient(
            evidence_count, self.context.settings.briefs.minimum_strategy_evidence
        ):
            return [], metrics, None
        recommendation = (
            "Review whether the current execution threshold and scout mix still match the "
            "user's observed decisions; no policy was changed automatically."
        )
        return (
            [{"id": f"strategy:{now.date()}", "kind": "strategy", **metrics}],
            metrics,
            recommendation,
        )

    @staticmethod
    def _render(brief_type: str, items: list[dict[str, Any]], recommendation: str | None) -> str:
        lines = [f"{brief_type.title()} Opportunity Brief"]
        for item in items:
            title = item.get("title", item.get("kind", "item"))
            score = item.get("net_value_score")
            suffix = f" — score {float(score):.1f}" if score is not None else ""
            lines.append(f"- {title}{suffix}")
        if recommendation:
            lines.append(f"Strategy note: {recommendation}")
        return "\n".join(lines)

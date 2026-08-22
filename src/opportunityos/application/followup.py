"""Explicit-submission follow-up policy and private draft interface."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from opportunityos.application.applications import ApplicationService
from opportunityos.application.common import audit
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.behavior import follow_up_dates
from opportunityos.infrastructure.database import (
    ApplicationRow,
    EvaluationRow,
    FollowUpStateRow,
    OpportunityRow,
)
from opportunityos.schemas import LifecycleState
from opportunityos.util import new_id, utc_now


class FollowUpService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def register_submission(
        self,
        opportunity_id: str,
        submitted_at: datetime,
        *,
        expected_response_start: datetime | None = None,
        expected_response_end: datetime | None = None,
        prohibited: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        submitted = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=UTC)
        earliest, latest = follow_up_dates(
            submitted,
            expected_response_start=expected_response_start,
            expected_response_end=expected_response_end,
            default_days=self.context.settings.followup.default_days,
        )
        with self.context.database.transaction() as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            state = session.scalar(
                select(FollowUpStateRow).where(FollowUpStateRow.opportunity_id == opportunity_id)
            )
            if state is None:
                state = FollowUpStateRow(
                    id=new_id(),
                    opportunity_id=opportunity_id,
                    submitted_at=submitted,
                    expected_response_start=expected_response_start,
                    expected_response_end=expected_response_end,
                    earliest_followup_at=earliest,
                    latest_followup_at=latest,
                    followup_prohibited=prohibited,
                    followup_reason=reason,
                    followup_draft_artifact_id=None,
                    completed_at=None,
                )
                session.add(state)
            else:
                state.submitted_at = submitted
                state.expected_response_start = expected_response_start
                state.expected_response_end = expected_response_end
                state.earliest_followup_at = earliest
                state.latest_followup_at = latest
                state.followup_prohibited = prohibited
                state.followup_reason = reason
                state.completed_at = None
            audit(
                session,
                event_type="follow_up_registered",
                reason="explicit submission recorded",
                subject_type="opportunity",
                subject_id=opportunity_id,
                actor="user",
                after_ids=[state.id],
                details={"prohibited": prohibited},
            )
            return self._state_dict(state, opportunity)

    @staticmethod
    def _state_dict(state: FollowUpStateRow, opportunity: OpportunityRow) -> dict[str, Any]:
        return {
            "follow_up_id": state.id,
            "opportunity_id": opportunity.id,
            "title": opportunity.canonical_title,
            "submitted_at": state.submitted_at,
            "earliest_followup_at": state.earliest_followup_at,
            "latest_followup_at": state.latest_followup_at,
            "prohibited": state.followup_prohibited,
            "reason": state.followup_reason,
            "draft_artifact_id": state.followup_draft_artifact_id,
            "completed_at": state.completed_at,
        }

    def get_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        if not self.context.settings.followup.enabled:
            return []
        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(FollowUpStateRow).where(
                    FollowUpStateRow.earliest_followup_at <= current,
                    FollowUpStateRow.followup_prohibited.is_(False),
                    FollowUpStateRow.completed_at.is_(None),
                )
            ).all()
            result: list[dict[str, Any]] = []
            for state in rows:
                opportunity = session.get(OpportunityRow, state.opportunity_id)
                application = session.scalar(
                    select(ApplicationRow).where(
                        ApplicationRow.opportunity_id == state.opportunity_id
                    )
                )
                if (
                    opportunity is None
                    or opportunity.lifecycle_state != LifecycleState.SUBMITTED.value
                    or application is None
                    or application.outcome is not None
                ):
                    continue
                result.append(self._state_dict(state, opportunity))
            return result

    def prepare_draft(self, opportunity_id: str) -> dict[str, Any]:
        due = next(
            (item for item in self.get_due() if item["opportunity_id"] == opportunity_id),
            None,
        )
        if due is None:
            raise ValueError("Opportunity is not currently eligible for follow-up")
        with self.context.database.transaction() as session:
            application = session.scalar(
                select(ApplicationRow).where(ApplicationRow.opportunity_id == opportunity_id)
            )
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            opportunity = session.get(OpportunityRow, opportunity_id)
            if application is None or opportunity is None:
                raise ValueError("A submitted application record is required")
            fact_ids = list(evaluation.strongest_evidence) if evaluation else []
        if not fact_ids:
            raise ValueError("Follow-up draft requires grounded canonical evidence")
        content = (
            f"Subject: Follow-up regarding {opportunity.canonical_title}\n\n"
            f"Hello {opportunity.organization},\n\n"
            "I am following up on my application and would appreciate any update "
            "you can share about its status. Thank you for your time.\n\n"
            "Nothing has been sent. Review the official contact policy and personalize "
            "this draft before any manual action.\n"
        )
        stored = ApplicationService(self.context).store_artifact(
            application.id,
            artifact_type="follow-up-draft",
            content=content,
            supporting_fact_ids=fact_ids,
            generation_model="deterministic-template",
            prompt_version="2.0",
            idempotency_key=f"follow-up-draft:{opportunity_id}",
        )
        with self.context.database.transaction() as session:
            state = session.scalar(
                select(FollowUpStateRow).where(FollowUpStateRow.opportunity_id == opportunity_id)
            )
            if state is None:
                raise ValueError("Follow-up state not found")
            state.followup_draft_artifact_id = stored["artifact_id"]
            audit(
                session,
                event_type="follow_up_draft_prepared",
                reason="grounded private follow-up draft",
                subject_type="opportunity",
                subject_id=opportunity_id,
                after_ids=[stored["artifact_id"]],
                details={"external_action": False},
            )
            return {**due, "draft_artifact_id": stored["artifact_id"], "sent": False}

    def mark_complete(self, opportunity_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            state = session.scalar(
                select(FollowUpStateRow).where(FollowUpStateRow.opportunity_id == opportunity_id)
            )
            if state is None:
                raise ValueError("Follow-up state not found")
            state.completed_at = utc_now()
            audit(
                session,
                event_type="follow_up_completed",
                reason="explicit user follow-up completion",
                subject_type="opportunity",
                subject_id=opportunity_id,
                actor="user",
            )
            return {"opportunity_id": opportunity_id, "completed_at": state.completed_at}

"""Bounded reevaluation of active decisions after profile/source changes."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select

from opportunityos.application.context import ApplicationContext
from opportunityos.application.decisions import DecisionService
from opportunityos.infrastructure.database import (
    EvaluationRow,
    OpportunityRow,
    RequirementRow,
)
from opportunityos.schemas import LifecycleState

TERMINAL_STATES = {
    LifecycleState.READY.value,
    LifecycleState.SUBMITTED.value,
    LifecycleState.FOLLOW_UP_DUE.value,
    LifecycleState.ACCEPTED.value,
    LifecycleState.REJECTED.value,
    LifecycleState.WITHDRAWN.value,
    LifecycleState.EXPIRED.value,
    LifecycleState.ARCHIVED.value,
}


class PropagationService:
    """Provide one bounded caller-facing seam for downstream reevaluation."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def reevaluate_dependents(self, field_paths: list[str], *, limit: int = 20) -> dict[str, Any]:
        if not field_paths:
            raise ValueError("At least one changed profile field is required")
        if limit < 1 or limit > 100:
            raise ValueError("Reevaluation limit must be between 1 and 100")
        with self.context.database.transaction() as session:
            opportunity_ids = list(
                dict.fromkeys(
                    session.scalars(
                        select(RequirementRow.opportunity_id).where(
                            RequirementRow.field_path.in_(field_paths),
                            RequirementRow.status != "superseded",
                        )
                    ).all()
                )
            )[:limit]
            baselines: dict[str, dict[str, Any]] = {}
            for opportunity_id in opportunity_ids:
                opportunity = session.get(OpportunityRow, opportunity_id)
                current = session.scalar(
                    select(EvaluationRow)
                    .where(EvaluationRow.opportunity_id == opportunity_id)
                    .order_by(EvaluationRow.created_at.desc())
                )
                if opportunity is None or current is None:
                    continue
                if opportunity.lifecycle_state in TERMINAL_STATES:
                    continue
                baselines[opportunity_id] = {
                    "decision": current.decision_label,
                    "score": current.net_value_score,
                    "eligibility": current.eligibility_summary.get("overall"),
                    "effort": current.total_effort_minutes,
                    "next_action": current.next_action_minutes,
                    "risk": current.main_risk,
                }
        changes: list[dict[str, Any]] = []
        decisions = DecisionService(self.context)
        for opportunity_id, before in baselines.items():
            computed = decisions.evaluate(
                opportunity_id,
                total_effort_minutes=cast(int, before["effort"]),
                next_action_minutes=cast(int, before["next_action"]),
                main_risk=str(before["risk"]),
                model_provider="propagation",
                model_id="deterministic-v2",
                idempotency_key=None,
            )
            after = {
                "decision": computed["decision"],
                "score": computed["net_value_score"],
                "eligibility": computed["eligibility"].get("overall"),
            }
            material = (
                before["decision"] != after["decision"]
                or before["eligibility"] != after["eligibility"]
                or abs(float(before["score"]) - float(after["score"])) >= 5
            )
            if material:
                changes.append(
                    {
                        "opportunity_id": opportunity_id,
                        "before": before,
                        "after": after,
                        "material": True,
                    }
                )
        return {
            "changed_fields": sorted(set(field_paths)),
            "considered": len(baselines),
            "reevaluated": len(baselines),
            "material_changes": changes,
            "silent": not changes,
        }

    def reevaluate_opportunity(self, opportunity_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            if opportunity is None or evaluation is None:
                raise ValueError("Current opportunity evaluation is required")
            before = {
                "decision": evaluation.decision_label,
                "score": evaluation.net_value_score,
                "eligibility": evaluation.eligibility_summary.get("overall"),
                "effort": evaluation.total_effort_minutes,
                "next_action": evaluation.next_action_minutes,
                "risk": evaluation.main_risk,
            }
        result = DecisionService(self.context).evaluate(
            opportunity_id,
            total_effort_minutes=cast(int, before["effort"]),
            next_action_minutes=cast(int, before["next_action"]),
            main_risk=str(before["risk"]),
            model_provider="reverification",
            model_id="deterministic-v2",
        )
        return {
            "opportunity_id": opportunity_id,
            "before": before,
            "after": {
                "decision": result["decision"],
                "score": result["net_value_score"],
                "eligibility": result["eligibility"].get("overall"),
            },
        }

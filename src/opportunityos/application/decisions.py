"""Deterministic eligibility, scoring, lifecycle, and queue interface."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.domain.decisions import (
    evaluate_requirement,
    overall_eligibility,
    priority_score,
    score_opportunity,
    time_fit_score,
    urgency_score,
    validate_transition,
)
from opportunityos.infrastructure.database import (
    ActionItemRow,
    AssessmentRow,
    CanonicalFactRow,
    DecisionEventRow,
    EligibilityCheckRow,
    EvaluationRow,
    OpportunityRow,
    RequirementRow,
    SourceRow,
)
from opportunityos.schemas import (
    ActionInput,
    ActionStatus,
    AssessmentInput,
    DecisionLabel,
    LifecycleState,
    OverallEligibility,
    PredicateOperator,
)
from opportunityos.util import new_id, utc_now


class DecisionService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    @staticmethod
    def _fact_state(fact: CanonicalFactRow | None) -> str | None:
        if fact is None:
            return None
        now = utc_now()
        effective_from = fact.effective_from
        effective_until = fact.effective_until
        if effective_from and effective_from.tzinfo is None:
            effective_from = effective_from.replace(tzinfo=UTC)
        if effective_until and effective_until.tzinfo is None:
            effective_until = effective_until.replace(tzinfo=UTC)
        if (effective_from and effective_from > now) or (
            effective_until and effective_until <= now
        ):
            return "stale"
        return fact.verification_status

    @staticmethod
    def _opportunity_gate(session: Session, opportunity: OpportunityRow) -> list[str]:
        sources = session.scalars(
            select(SourceRow).where(SourceRow.id.in_(opportunity.source_ids))
        ).all()
        problems: list[str] = []
        if not opportunity.canonical_url or not any(
            source.official_status == "official" and source.source_type == "official_webpage"
            for source in sources
        ):
            problems.append("official source is missing")
        last_verified = opportunity.last_verified_at
        if last_verified and last_verified.tzinfo is None:
            last_verified = last_verified.replace(tzinfo=UTC)
        now = utc_now()
        if not last_verified or last_verified < now - timedelta(days=1):
            problems.append("official source verification is stale")
        if opportunity.source_completeness < 1:
            problems.append("official requirements are incomplete")
        if opportunity.open_status not in {"open", "future"}:
            problems.append("opportunity is not verified open or future")
        deadline = opportunity.deadline_at
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if not deadline or deadline <= now:
            problems.append("verified future deadline is missing")
        return problems

    def submit_assessment(
        self, value: AssessmentInput, *, idempotency_key: str | None = None
    ) -> str:
        operation = "decision.submit_assessment"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["assessment_id"])
            if session.get(OpportunityRow, value.opportunity_id) is None:
                raise ValueError("Opportunity not found")
            fact_ids = set(value.supporting_fact_ids)
            source_ids = set(value.source_ids)
            existing_facts = set(
                session.scalars(
                    select(CanonicalFactRow.id).where(CanonicalFactRow.id.in_(fact_ids))
                ).all()
            )
            if existing_facts != fact_ids:
                raise ValueError("Assessment references unknown canonical facts")
            existing_sources = set(
                session.scalars(select(SourceRow.id).where(SourceRow.id.in_(source_ids))).all()
            )
            if existing_sources != source_ids:
                raise ValueError("Assessment references unknown sources")
            assessment_id = new_id()
            session.add(
                AssessmentRow(
                    id=assessment_id,
                    opportunity_id=value.opportunity_id,
                    dimension=value.dimension,
                    value=value.value,
                    rationale=value.rationale,
                    supporting_fact_ids=value.supporting_fact_ids,
                    source_ids=value.source_ids,
                    confidence=value.confidence,
                    model_provider=value.model_provider,
                    model_id=value.model_id,
                    prompt_version=value.prompt_version,
                    created_at=utc_now(),
                )
            )
            audit(
                session,
                event_type="assessment_submitted",
                reason="validated subjective component",
                subject_type="opportunity",
                subject_id=value.opportunity_id,
                actor="hermes",
                after_ids=[assessment_id, *sorted(existing_facts), *sorted(existing_sources)],
                details={"dimension": value.dimension},
            )
            store_idempotent(session, idempotency_key, operation, {"assessment_id": assessment_id})
            return assessment_id

    def evaluate_eligibility(self, opportunity_id: str) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            requirements = session.scalars(
                select(RequirementRow).where(
                    RequirementRow.opportunity_id == opportunity_id,
                    RequirementRow.status != "superseded",
                )
            ).all()
            checks = []
            hard_checks = []
            for requirement in requirements:
                fact = session.scalar(
                    select(CanonicalFactRow).where(
                        CanonicalFactRow.field_path == requirement.field_path
                    )
                )
                predicate = requirement.normalized_predicate
                operator = (
                    PredicateOperator.UNKNOWN
                    if requirement.status in {"ambiguous", "missing"}
                    else PredicateOperator(str(predicate["operator"]))
                )
                check = evaluate_requirement(
                    requirement_id=requirement.id,
                    operator=operator,
                    expected=predicate.get("expected"),
                    fact_value=fact.typed_value if fact else None,
                    fact_ids=[fact.id] if fact else [],
                    fact_state=self._fact_state(fact),
                )
                checks.append(check)
                if requirement.hard_or_soft == "hard":
                    hard_checks.append(check)
            overall = overall_eligibility(hard_checks)
            source_gate = self._opportunity_gate(session, opportunity)
            if overall is OverallEligibility.ELIGIBLE and source_gate:
                overall = OverallEligibility.REVIEW_REQUIRED
            return {
                "opportunity_id": opportunity_id,
                "overall": overall.value,
                "checks": [
                    {
                        "requirement_id": check.requirement_id,
                        "result": check.result.value,
                        "reason_code": check.reason_code,
                        "explanation": check.explanation,
                        "fact_ids": list(check.fact_ids),
                    }
                    for check in checks
                ],
                "source_gate": source_gate,
            }

    def evaluate(
        self,
        opportunity_id: str,
        *,
        total_effort_minutes: int,
        next_action_minutes: int,
        main_risk: str,
        model_provider: str,
        model_id: str,
        heavy_artifact: bool = False,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "decision.evaluate"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            if opportunity.lifecycle_state in {
                LifecycleState.READY.value,
                LifecycleState.SUBMITTED.value,
                LifecycleState.FOLLOW_UP_DUE.value,
                LifecycleState.ACCEPTED.value,
                LifecycleState.REJECTED.value,
                LifecycleState.WITHDRAWN.value,
                LifecycleState.EXPIRED.value,
                LifecycleState.ARCHIVED.value,
            }:
                raise ValueError("Opportunities at READY or later cannot be reevaluated")
            requirements = session.scalars(
                select(RequirementRow).where(
                    RequirementRow.opportunity_id == opportunity_id,
                    RequirementRow.status != "superseded",
                )
            ).all()
            checks = []
            hard_checks = []
            now = utc_now()
            for requirement in requirements:
                fact = session.scalar(
                    select(CanonicalFactRow).where(
                        CanonicalFactRow.field_path == requirement.field_path
                    )
                )
                predicate = requirement.normalized_predicate
                operator = (
                    PredicateOperator.UNKNOWN
                    if requirement.status in {"ambiguous", "missing"}
                    else PredicateOperator(str(predicate["operator"]))
                )
                check = evaluate_requirement(
                    requirement_id=requirement.id,
                    operator=operator,
                    expected=predicate.get("expected"),
                    fact_value=fact.typed_value if fact else None,
                    fact_ids=[fact.id] if fact else [],
                    fact_state=self._fact_state(fact),
                )
                checks.append(check)
                if requirement.hard_or_soft == "hard":
                    hard_checks.append(check)
                session.add(
                    EligibilityCheckRow(
                        id=new_id(),
                        opportunity_id=opportunity_id,
                        requirement_id=requirement.id,
                        profile_fact_ids=list(check.fact_ids),
                        result=check.result.value,
                        deterministic_reason_code=check.reason_code,
                        explanation=check.explanation,
                        evaluated_at=now,
                        eligibility_ruleset_version=requirement.ruleset_version,
                    )
                )
            eligibility = overall_eligibility(hard_checks)
            source_gate = self._opportunity_gate(session, opportunity)
            if eligibility is OverallEligibility.ELIGIBLE and source_gate:
                eligibility = OverallEligibility.REVIEW_REQUIRED
            assessment_rows = session.scalars(
                select(AssessmentRow)
                .where(AssessmentRow.opportunity_id == opportunity_id)
                .order_by(AssessmentRow.created_at.desc())
            ).all()
            latest: dict[str, AssessmentRow] = {}
            for assessment in assessment_rows:
                latest.setdefault(assessment.dimension, assessment)
            weights = self.context.settings.scoring.weights
            score = score_opportunity(
                assessments={key: row.value for key, row in latest.items()},
                assessment_confidences=[row.confidence for row in latest.values()],
                weights=weights,
                eligibility=eligibility,
                source_completeness=opportunity.source_completeness,
                total_effort_minutes=total_effort_minutes,
                heavy_artifact=heavy_artifact,
                apply_threshold=self.context.settings.scoring.apply_threshold,
                maybe_threshold=self.context.settings.scoring.maybe_threshold,
                apply_confidence=self.context.settings.scoring.apply_confidence,
            )
            projection_version = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            assessment_ids = [row.id for row in latest.values()]
            strongest = list(
                dict.fromkeys(
                    fact_id
                    for row in sorted(latest.values(), key=lambda item: item.value, reverse=True)
                    for fact_id in row.supporting_fact_ids
                )
            )[:5]
            evaluation_id = new_id()
            evaluation = EvaluationRow(
                id=evaluation_id,
                opportunity_id=opportunity_id,
                profile_projection_version=projection_version,
                opportunity_version=opportunity.version,
                eligibility_summary={
                    "overall": eligibility.value,
                    "checks": [
                        {
                            "requirement_id": check.requirement_id,
                            "result": check.result.value,
                            "reason_code": check.reason_code,
                            "fact_ids": list(check.fact_ids),
                        }
                        for check in checks
                    ],
                    "source_gate": source_gate,
                },
                raw_value_score=score.raw_score,
                effort_penalty=score.effort_penalty,
                net_value_score=score.net_score,
                decision_label=score.decision.value,
                decision_confidence=score.confidence,
                strongest_evidence=strongest,
                main_risk=main_risk,
                total_effort_minutes=total_effort_minutes,
                next_action_minutes=next_action_minutes,
                scoring_ruleset_version=self.context.settings.scoring.ruleset_version,
                subjective_assessment_ids=assessment_ids,
                model_provider=model_provider,
                model_id=model_id,
                source_ids=opportunity.source_ids,
                created_at=now,
            )
            session.add(evaluation)
            deadline = opportunity.deadline_at
            if deadline and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if deadline and deadline <= now:
                opportunity.lifecycle_state = LifecycleState.EXPIRED.value
            elif eligibility is OverallEligibility.INELIGIBLE:
                opportunity.lifecycle_state = LifecycleState.INELIGIBLE.value
            elif eligibility is OverallEligibility.REVIEW_REQUIRED:
                opportunity.lifecycle_state = LifecycleState.REVIEW_REQUIRED.value
            elif opportunity.lifecycle_state not in {
                LifecycleState.SHORTLISTED.value,
                LifecycleState.PREPARING.value,
            }:
                opportunity.lifecycle_state = LifecycleState.EVALUATED.value
            opportunity.updated_at = now
            session.add(
                DecisionEventRow(
                    id=new_id(),
                    opportunity_id=opportunity_id,
                    decision=score.decision.value,
                    reason="deterministic eligibility and scoring evaluation",
                    actor="system",
                    created_at=now,
                )
            )
            audit(
                session,
                event_type="evaluation_computed",
                reason="versioned deterministic evaluation",
                subject_type="opportunity",
                subject_id=opportunity_id,
                after_ids=[evaluation_id, *assessment_ids],
                ruleset_version=self.context.settings.scoring.ruleset_version,
                details={"decision": score.decision.value, "eligibility": eligibility.value},
            )
            result = self._evaluation_dict(evaluation)
            store_idempotent(session, idempotency_key, operation, result)
            return result

    @staticmethod
    def _evaluation_dict(row: EvaluationRow) -> dict[str, Any]:
        return {
            "evaluation_id": row.id,
            "opportunity_id": row.opportunity_id,
            "eligibility": row.eligibility_summary,
            "raw_value_score": row.raw_value_score,
            "effort_penalty": row.effort_penalty,
            "net_value_score": row.net_value_score,
            "decision": row.decision_label,
            "confidence": row.decision_confidence,
            "strongest_evidence": row.strongest_evidence,
            "main_risk": row.main_risk,
            "total_effort_minutes": row.total_effort_minutes,
            "next_action_minutes": row.next_action_minutes,
            "profile_projection_version": row.profile_projection_version,
            "opportunity_version": row.opportunity_version,
            "ruleset_version": row.scoring_ruleset_version,
        }

    def get_evaluation(self, opportunity_id: str) -> dict[str, Any] | None:
        with self.context.database.transaction() as session:
            row = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            if row is None:
                return None
            opportunity = session.get(OpportunityRow, opportunity_id)
            projection_version = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            result = self._evaluation_dict(row)
            result["current"] = bool(
                opportunity
                and row.profile_projection_version == projection_version
                and row.opportunity_version == opportunity.version
            )
            return result

    def create_action(
        self, value: ActionInput, *, completion_ratio: float = 0, idempotency_key: str | None = None
    ) -> str:
        operation = "decision.create_action"
        if not 0 <= completion_ratio <= 1:
            raise ValueError("completion_ratio must be between 0 and 1")
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return str(previous["action_id"])
            if value.opportunity_id:
                opportunity = session.get(OpportunityRow, value.opportunity_id)
                if opportunity is None:
                    raise ValueError("Opportunity not found")
                evaluation = session.scalar(
                    select(EvaluationRow)
                    .where(EvaluationRow.opportunity_id == value.opportunity_id)
                    .order_by(EvaluationRow.created_at.desc())
                )
                projection_version = int(
                    session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
                )
                if (
                    evaluation is None
                    or evaluation.profile_projection_version != projection_version
                    or evaluation.opportunity_version != opportunity.version
                    or evaluation.decision_label
                    not in {DecisionLabel.APPLY.value, DecisionLabel.MAYBE.value}
                ):
                    raise ValueError("Action requires a current actionable evaluation")
            action_id = new_id()
            now = utc_now()
            session.add(
                ActionItemRow(
                    id=action_id,
                    opportunity_id=value.opportunity_id,
                    action_type=value.action_type,
                    description=value.description,
                    estimated_minutes=value.estimated_minutes,
                    due_at=value.due_at,
                    dependencies=value.dependencies,
                    readiness_score=value.readiness_score,
                    status=value.status.value,
                    completion_ratio=completion_ratio,
                    created_at=now,
                    updated_at=now,
                )
            )
            audit(
                session,
                event_type="action_created",
                reason="action generated from evaluated workflow",
                subject_type="action",
                subject_id=action_id,
                after_ids=[action_id],
            )
            store_idempotent(session, idempotency_key, operation, {"action_id": action_id})
            return action_id

    def queue(self, available_minutes: int | None = None) -> list[dict[str, Any]]:
        minutes = available_minutes or self.context.settings.default_action_minutes
        if minutes <= 0:
            raise ValueError("Available minutes must be positive")
        with self.context.database.transaction() as session:
            actions = session.scalars(
                select(ActionItemRow).where(ActionItemRow.status == ActionStatus.READY.value)
            ).all()
            evaluations = session.scalars(
                select(EvaluationRow).order_by(EvaluationRow.created_at.desc())
            ).all()
            latest: dict[str, EvaluationRow] = {}
            for evaluation in evaluations:
                latest.setdefault(evaluation.opportunity_id, evaluation)
            opportunities = {row.id: row for row in session.scalars(select(OpportunityRow)).all()}
            projection_version = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            now = datetime.now(UTC)
            ranked: list[dict[str, Any]] = []
            for action in actions:
                if not action.opportunity_id or action.opportunity_id not in latest:
                    continue
                opportunity = opportunities[action.opportunity_id]
                if opportunity.deadline_at is not None:
                    deadline = opportunity.deadline_at
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=UTC)
                    if deadline <= now:
                        opportunity.lifecycle_state = LifecycleState.EXPIRED.value
                        continue
                evaluation = latest[action.opportunity_id]
                if (
                    evaluation.profile_projection_version != projection_version
                    or evaluation.opportunity_version != opportunity.version
                    or evaluation.decision_label
                    not in {DecisionLabel.APPLY.value, DecisionLabel.MAYBE.value}
                ):
                    continue
                urgency = urgency_score(opportunity.deadline_at, now)
                time_fit = time_fit_score(action.estimated_minutes, minutes)
                priority = priority_score(
                    net_value=evaluation.net_value_score,
                    urgency=urgency,
                    readiness=action.readiness_score,
                    time_fit=time_fit,
                    completion_ratio=action.completion_ratio,
                )
                ranked.append(
                    {
                        "action_id": action.id,
                        "opportunity_id": opportunity.id,
                        "title": opportunity.canonical_title,
                        "description": action.description,
                        "estimated_minutes": action.estimated_minutes,
                        "deadline": opportunity.deadline_at,
                        "decision": evaluation.decision_label,
                        "net_value_score": evaluation.net_value_score,
                        "priority_score": priority,
                        "reason": (
                            f"Value {evaluation.net_value_score:.1f}, urgency {urgency:.1f}, "
                            f"readiness {action.readiness_score:.1f}, time fit {time_fit:.1f}."
                        ),
                    }
                )
            return sorted(ranked, key=lambda item: float(item["priority_score"]), reverse=True)

    def next_action(self, available_minutes: int | None = None) -> dict[str, Any] | None:
        ranked = self.queue(available_minutes)
        return ranked[0] if ranked else None

    def complete_action(self, action_id: str, *, skipped: bool = False) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            action = session.get(ActionItemRow, action_id)
            if action is None or action.status not in {
                ActionStatus.READY.value,
                ActionStatus.IN_PROGRESS.value,
            }:
                raise ValueError("Completable action not found")
            action.status = ActionStatus.SKIPPED.value if skipped else ActionStatus.COMPLETE.value
            action.updated_at = utc_now()
            audit(
                session,
                event_type="action_skipped" if skipped else "action_completed",
                reason="explicit user action",
                subject_type="action",
                subject_id=action.id,
                actor="user",
            )
            return {"action_id": action.id, "status": action.status}

    def update_lifecycle(
        self,
        opportunity_id: str,
        target: LifecycleState,
        *,
        actor: str = "user",
        confirmed: bool = False,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            opportunity = session.get(OpportunityRow, opportunity_id)
            if opportunity is None:
                raise ValueError("Opportunity not found")
            current = LifecycleState(opportunity.lifecycle_state)
            validate_transition(current, target)
            if target is LifecycleState.SUBMITTED and (not confirmed or occurred_at is None):
                raise ValueError("SUBMITTED requires explicit confirmation and timestamp")
            if target in {LifecycleState.ACCEPTED, LifecycleState.REJECTED} and actor == "system":
                raise ValueError(
                    "Outcome transitions require user or authoritative imported evidence"
                )
            opportunity.lifecycle_state = target.value
            opportunity.updated_at = utc_now()
            session.add(
                DecisionEventRow(
                    id=new_id(),
                    opportunity_id=opportunity_id,
                    decision=target.value,
                    reason="explicit lifecycle transition",
                    actor=actor,
                    created_at=occurred_at or utc_now(),
                )
            )
            audit(
                session,
                event_type="lifecycle_updated",
                reason=f"{current.value} -> {target.value}",
                subject_type="opportunity",
                subject_id=opportunity_id,
                actor=actor,
                details={"from": current.value, "to": target.value},
            )
            return {"opportunity_id": opportunity_id, "state": target.value}

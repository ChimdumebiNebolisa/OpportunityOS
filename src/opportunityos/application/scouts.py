"""Bounded deterministic scout-run controller. Scheduling remains in Hermes."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select

from opportunityos.application.common import audit, idempotent_result, store_idempotent
from opportunityos.application.context import ApplicationContext
from opportunityos.infrastructure.database import (
    CanonicalFactRow,
    EvaluationRow,
    OpportunityRow,
    ScoutRunRow,
    SourceRow,
)
from opportunityos.schemas import DecisionLabel, ScoutRunInput
from opportunityos.util import new_id, utc_now


class ScoutService:
    def __init__(self, context: ApplicationContext) -> None:
        self.context = context

    def begin(self, value: ScoutRunInput, *, idempotency_key: str | None = None) -> dict[str, Any]:
        operation = "scout.begin"
        configured = self.context.settings.scouts.model_dump()
        budget = {
            key: min(int(value.budget.get(key, maximum)), int(maximum))
            for key, maximum in configured.items()
        }
        if any(amount < 0 for amount in budget.values()):
            raise ValueError("Scout budgets cannot be negative")
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            previous_run = session.scalar(
                select(ScoutRunRow)
                .where(
                    ScoutRunRow.category == value.category,
                    ScoutRunRow.status == "success",
                )
                .order_by(ScoutRunRow.ended_at.desc())
            )
            now = utc_now()
            catch_up_from = None
            if previous_run and previous_run.ended_at:
                ended = previous_run.ended_at
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=UTC)
                if now - ended > timedelta(days=1):
                    catch_up_from = ended
            run_id = new_id()
            session.add(
                ScoutRunRow(
                    id=run_id,
                    category=value.category,
                    query_plan=value.query_plan,
                    budget=budget,
                    counters={
                        "queries": 0,
                        "pages": 0,
                        "model_calls": 0,
                        "deep_evaluations": 0,
                        "notifications": 0,
                        "budget_stops": 0,
                    },
                    sources_considered=[],
                    candidates=[],
                    strong_candidates=[],
                    candidate_versions={},
                    delivered_versions={},
                    errors=[],
                    started_at=now,
                    ended_at=None,
                    delivery_result=None,
                    status="running",
                    catch_up_from=catch_up_from,
                )
            )
            result = {
                "run_id": run_id,
                "category": value.category,
                "budget": budget,
                "catch_up_from": catch_up_from.isoformat() if catch_up_from else None,
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def record_usage(
        self,
        run_id: str,
        *,
        queries: int = 0,
        pages: int = 0,
        model_calls: int = 0,
        deep_evaluations: int = 0,
    ) -> dict[str, Any]:
        increments = {
            "queries": queries,
            "pages": pages,
            "model_calls": model_calls,
            "deep_evaluations": deep_evaluations,
        }
        if any(value < 0 for value in increments.values()):
            raise ValueError("Usage increments cannot be negative")
        limits = {
            "queries": "max_queries",
            "pages": "max_candidate_pages",
            "model_calls": "max_model_calls",
            "deep_evaluations": "max_deep_evaluations",
        }
        with self.context.database.transaction() as session:
            run = session.get(ScoutRunRow, run_id)
            if run is None or run.status != "running":
                raise ValueError("Running scout not found")
            counters = dict(run.counters)
            stopped_reason: str | None = None
            if model_calls:
                day_start = datetime.combine(utc_now().date(), time.min, tzinfo=UTC)
                daily_runs = session.scalars(
                    select(ScoutRunRow).where(ScoutRunRow.started_at >= day_start)
                ).all()
                daily_used = sum(int(item.counters.get("model_calls", 0)) for item in daily_runs)
                if daily_used + model_calls > int(run.budget["daily_model_calls"]):
                    counters["budget_stops"] = int(counters["budget_stops"]) + 1
                    run.status = "budget_stopped"
                    run.ended_at = utc_now()
                    stopped_reason = "Daily scout model-call budget reached"
            for key, increment in increments.items():
                if stopped_reason:
                    break
                attempted = int(counters[key]) + increment
                if attempted > int(run.budget[limits[key]]):
                    counters["budget_stops"] = int(counters["budget_stops"]) + 1
                    run.status = "budget_stopped"
                    run.ended_at = utc_now()
                    stopped_reason = f"Scout {key} budget reached"
                    break
                counters[key] = attempted
            elapsed = (
                utc_now() - run.started_at.replace(tzinfo=run.started_at.tzinfo or UTC)
            ).total_seconds()
            if not stopped_reason and elapsed > int(run.budget["max_duration_seconds"]):
                counters["budget_stops"] = int(counters["budget_stops"]) + 1
                run.status = "budget_stopped"
                run.ended_at = utc_now()
                stopped_reason = "Scout duration budget reached"
            run.counters = counters
            return {
                **{key: int(value) for key, value in counters.items()},
                "stopped": bool(stopped_reason),
                "reason": stopped_reason,
            }

    def record_candidate(
        self,
        run_id: str,
        opportunity_id: str,
        *,
        source_ids: list[str],
    ) -> dict[str, Any]:
        with self.context.database.transaction() as session:
            run = session.get(ScoutRunRow, run_id)
            opportunity = session.get(OpportunityRow, opportunity_id)
            if run is None or run.status != "running" or opportunity is None:
                raise ValueError("Running scout or opportunity not found")
            evaluation = session.scalar(
                select(EvaluationRow)
                .where(EvaluationRow.opportunity_id == opportunity_id)
                .order_by(EvaluationRow.created_at.desc())
            )
            sources = session.scalars(select(SourceRow).where(SourceRow.id.in_(source_ids))).all()
            if {source.id for source in sources} != set(source_ids):
                raise ValueError("Scout candidate references unknown sources")
            if not source_ids or not set(source_ids).issubset(set(opportunity.source_ids)):
                raise ValueError("Scout candidate sources are not attached to the opportunity")
            official = any(
                source.official_status == "official" and source.source_type == "official_webpage"
                for source in sources
            )
            deadline = opportunity.deadline_at
            if deadline and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            projection_version = int(
                session.scalar(select(func.sum(CanonicalFactRow.projection_version))) or 0
            )
            last_verified = opportunity.last_verified_at
            if last_verified and last_verified.tzinfo is None:
                last_verified = last_verified.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            strong = bool(
                evaluation
                and evaluation.profile_projection_version == projection_version
                and evaluation.opportunity_version == opportunity.version
                and official
                and last_verified
                and last_verified >= now - timedelta(days=1)
                and opportunity.source_completeness >= 1
                and opportunity.open_status in {"open", "future"}
                and deadline
                and deadline > now
                and evaluation.eligibility_summary.get("overall") == "eligible"
                and evaluation.decision_label == DecisionLabel.APPLY.value
                and evaluation.net_value_score >= self.context.settings.scoring.apply_threshold
                and evaluation.decision_confidence >= self.context.settings.scoring.apply_confidence
            )
            version_key = (
                f"{opportunity.version}:{projection_version}:"
                f"{evaluation.decision_label if evaluation else 'none'}:"
                f"{evaluation.net_value_score if evaluation else 0}:"
                f"{evaluation.decision_confidence if evaluation else 0}"
            )
            prior_runs = session.scalars(
                select(ScoutRunRow).where(
                    ScoutRunRow.category == run.category,
                    ScoutRunRow.id != run.id,
                    ScoutRunRow.delivery_result == "digest",
                )
            ).all()
            if any(
                prior.delivered_versions.get(opportunity_id) == version_key for prior in prior_runs
            ):
                strong = False
            candidates = list(run.candidates)
            if opportunity_id not in candidates:
                candidates.append(opportunity_id)
            run.candidates = candidates
            strong_candidates = list(run.strong_candidates)
            if strong and opportunity_id not in strong_candidates:
                strong_candidates.append(opportunity_id)
            run.strong_candidates = strong_candidates
            candidate_versions = dict(run.candidate_versions)
            candidate_versions[opportunity_id] = version_key
            run.candidate_versions = candidate_versions
            run.sources_considered = sorted(set(run.sources_considered) | set(source_ids))
            audit(
                session,
                event_type="scout_candidate_recorded",
                reason="candidate passed deterministic quality gate"
                if strong
                else "candidate retained below delivery gate",
                subject_type="scout_run",
                subject_id=run_id,
                after_ids=[opportunity_id],
                details={"strong": strong},
            )
            return {"opportunity_id": opportunity_id, "strong": strong}

    def finish(
        self,
        run_id: str,
        *,
        material_opportunity_ids: list[str],
        errors: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        operation = "scout.finish"
        with self.context.database.transaction() as session:
            previous = idempotent_result(session, idempotency_key, operation)
            if previous:
                return previous
            run = session.get(ScoutRunRow, run_id)
            if run is None or run.status not in {"running", "budget_stopped"}:
                raise ValueError("Finishable scout run not found")
            material = [item for item in material_opportunity_ids if item in run.strong_candidates]
            max_notifications = int(run.budget["max_notifications"])
            material = material[:max_notifications]
            counters = dict(run.counters)
            counters["notifications"] = len(material)
            run.counters = counters
            run.errors = list(errors or [])
            run.ended_at = utc_now()
            run.delivery_result = "digest" if material else "silent"
            run.delivered_versions = {
                opportunity_id: run.candidate_versions[opportunity_id]
                for opportunity_id in material
            }
            if run.status != "budget_stopped":
                run.status = "success" if not errors else "partial"
            audit(
                session,
                event_type="scout_finished",
                reason="bounded scout finalized",
                subject_type="scout_run",
                subject_id=run_id,
                details={"delivery": run.delivery_result, "material_count": len(material)},
            )
            result = {
                "run_id": run_id,
                "status": run.status,
                "delivery_result": run.delivery_result,
                "material_opportunity_ids": material,
                "counters": counters,
                "digest": None
                if not material
                else {"opportunity_ids": material, "official_links_required": True},
            }
            store_idempotent(session, idempotency_key, operation, result)
            return result

    def status(self) -> list[dict[str, Any]]:
        with self.context.database.transaction() as session:
            rows = session.scalars(
                select(ScoutRunRow).order_by(ScoutRunRow.started_at.desc())
            ).all()
            latest: dict[str, ScoutRunRow] = {}
            for row in rows:
                latest.setdefault(row.category, row)
            return [
                {
                    "run_id": row.id,
                    "category": row.category,
                    "status": row.status,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "delivery_result": row.delivery_result,
                    "counters": row.counters,
                }
                for row in latest.values()
            ]

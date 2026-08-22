from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from opportunityos.application.automation import AutomationService
from opportunityos.application.briefs import BriefService
from opportunityos.application.decisions import DecisionService
from opportunityos.application.execution import ExecutionService
from opportunityos.application.followup import FollowUpService
from opportunityos.application.health import HealthService
from opportunityos.application.propagation import PropagationService
from opportunityos.domain.behavior import execution_priority, in_quiet_hours
from opportunityos.infrastructure.database import FollowUpStateRow, OpportunityRow
from opportunityos.schemas import ActionInput, ClaimInput, LifecycleState
from tests.e2e.test_core_workflows import _assess, _seed


def test_behavior_policies_reward_completion_and_respect_quiet_hours() -> None:
    nearly_complete = execution_priority(
        opportunity_value=93,
        urgency=90,
        readiness=90,
        remaining_minutes=20,
        available_minutes=30,
        completion_ratio=0.85,
        dependencies_ready=True,
        packet_ready=True,
        unlocks_submission=True,
    )
    distant = execution_priority(
        opportunity_value=95,
        urgency=15,
        readiness=50,
        remaining_minutes=180,
        available_minutes=30,
        completion_ratio=0,
        dependencies_ready=True,
        packet_ready=False,
        unlocks_submission=False,
    )
    assert nearly_complete > distant
    assert in_quiet_hours(datetime(2026, 1, 2, 23, 0, tzinfo=UTC), "22:00", "08:00")
    assert not in_quiet_hours(datetime(2026, 1, 2, 12, 0, tzinfo=UTC), "22:00", "08:00")


def test_auto_preparation_gate_and_private_packet(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    automation = AutomationService(context)
    gate = automation.auto_preparation_gate(opportunity_id)
    assert gate["gate_result"] == "pass"
    packet = automation.auto_prepare_execute(
        opportunity_id,
        [ClaimInput(text="Grounded synthetic claim.", supporting_fact_ids=[fact_id])],
        idempotency_key="auto-prep-1",
    )
    assert packet["automatic"] is True
    assert packet["external_submission_performed"] is False
    context.settings.auto_prepare.score_threshold = 101
    blocked = automation.auto_preparation_gate(opportunity_id)
    assert blocked["gate_result"] == "fail"


def test_reminder_delivery_snooze_and_stop(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    action_id = DecisionService(context).create_action(
        ActionInput(
            opportunity_id=opportunity_id,
            action_type="review_packet",
            description="Review the prepared packet.",
            estimated_minutes=10,
            readiness_score=90,
        ),
        completion_ratio=0.9,
    )
    execution = ExecutionService(context)
    candidates = execution.get_risk(available_minutes=30)
    assert candidates and candidates[0]["action_id"] == action_id
    execution.record_delivery(candidates[0]["reminder_id"], candidates[0]["fingerprint"])
    assert execution.get_risk(available_minutes=30) == []
    snoozed = execution.snooze(action_id, utc_now_for_test() + timedelta(hours=2))
    assert snoozed["action_id"] == action_id
    assert execution.stop(opportunity_id)["stopped"] is True
    assert execution.mark_passed(opportunity_id)["stopped"] is True
    assert execution.mark_applied(opportunity_id)["stopped"] is True


def test_followup_due_prepares_private_draft(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    decisions = DecisionService(context)
    decisions.evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    from opportunityos.application.applications import ApplicationService

    packet = ApplicationService(context).prepare(
        opportunity_id,
        [ClaimInput(text="Grounded claim.", supporting_fact_ids=[fact_id])],
    )
    ApplicationService(context).mark_ready(packet["application_id"])
    submitted_at = datetime.now(UTC) - timedelta(days=15)
    decisions.update_lifecycle(
        opportunity_id,
        LifecycleState.SUBMITTED,
        confirmed=True,
        occurred_at=submitted_at,
    )
    with context.database.transaction() as session:
        state = session.query(FollowUpStateRow).filter_by(opportunity_id=opportunity_id).one()
        state.earliest_followup_at = datetime.now(UTC) - timedelta(minutes=1)
    followup = FollowUpService(context)
    assert followup.get_due()
    draft = followup.prepare_draft(opportunity_id)
    assert draft["sent"] is False
    assert draft["draft_artifact_id"]


def test_brief_quiet_health_backup_and_controls(context_factory: Any) -> None:
    context = context_factory()
    assert BriefService(context).build("daily")["delivery_result"] == "silent"
    backup = HealthService(context).backup_auto()
    assert backup["status"] == "created"
    assert HealthService(context).backup_status()["fresh"] is True
    health = HealthService(context).check()
    assert health["components"]
    AutomationService(context).set_control("automation", False)
    controls = {item["key"]: item for item in AutomationService(context).controls()}
    assert controls["automation"]["enabled"] is False


def test_profile_propagation_is_bounded(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    result = PropagationService(context).reevaluate_dependents(["identity.citizenship"], limit=1)
    assert result["considered"] == 1
    assert result["reevaluated"] == 1


def test_adversarial_stale_source_quiet_hours_cap_and_local_controls(
    context_factory: Any,
) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    with context.database.transaction() as session:
        opportunity = session.get(OpportunityRow, opportunity_id)
        assert opportunity is not None
        opportunity.last_verified_at = datetime.now(UTC) - timedelta(days=3)
    stale_gate = AutomationService(context).auto_preparation_gate(opportunity_id)
    assert stale_gate["gate_result"] == "fail"
    assert "stale" in stale_gate["reason"]

    action_id = DecisionService(context).create_action(
        ActionInput(
            opportunity_id=opportunity_id,
            action_type="review_packet",
            description="Review the prepared packet.",
            estimated_minutes=10,
            readiness_score=90,
        ),
        completion_ratio=0.9,
    )
    context.settings.notifications.quiet_hours_start = "00:00"
    context.settings.notifications.quiet_hours_end = "23:59"
    assert ExecutionService(context).get_risk(available_minutes=30) == []
    context.settings.notifications.quiet_hours_start = "23:59"
    context.settings.notifications.quiet_hours_end = "23:58"
    context.settings.notifications.daily_cap = 0
    assert ExecutionService(context).get_risk(available_minutes=30) == []
    context.settings.notifications.daily_cap = 3
    AutomationService(context).set_control("reminders", False)
    assert ExecutionService(context).get_risk(available_minutes=30) == []
    AutomationService(context).set_control("reminders", True)
    assert action_id


def utc_now_for_test() -> datetime:
    return datetime.now(UTC)

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from opportunityos.application.applications import ApplicationService
from opportunityos.application.decisions import DecisionService
from opportunityos.application.opportunities import OpportunityService
from opportunityos.application.profile import ProfileService
from opportunityos.infrastructure.database import CanonicalFactRow, OpportunityRow, SourceRow
from opportunityos.schemas import (
    ActionInput,
    AssessmentInput,
    ClaimInput,
    LifecycleState,
    ObservationInput,
    OfficialStatus,
    OpportunityInput,
    PredicateOperator,
    RequirementInput,
    SourceCreate,
    SourceType,
)


def _source(
    service: ProfileService | OpportunityService,
    locator: str,
    *,
    official: bool = False,
    source_type: SourceType | None = None,
) -> str:
    return service.add_source(
        SourceCreate(
            source_type=source_type
            or (SourceType.OFFICIAL_WEBPAGE if official else SourceType.USER_STATEMENT),
            source_locator=locator,
            display_name=locator,
            official_status=OfficialStatus.OFFICIAL if official else OfficialStatus.UNKNOWN,
            retrieved_at=datetime.now(UTC),
            content_hash=("a" if official else "b") * 64,
            mime_type="text/html" if official else "text/plain",
            trust_class="official" if official else "credible",
        )
    )


def _seed(context: Any, citizenship: str | None = "US") -> tuple[str, str | None, str]:
    profile = ProfileService(context)
    opportunity_service = OpportunityService(context)
    fact_id = None
    if citizenship is not None:
        profile_source = _source(profile, f"synthetic-user-{citizenship}")
        profile.submit_observations(
            [
                ObservationInput(
                    field_path="identity.citizenship",
                    value=citizenship,
                    source_id=profile_source,
                    evidence_locator="synthetic user statement",
                    extraction_confidence=1,
                    observed_at=datetime.now(UTC),
                )
            ]
        )
        fact_id = profile.get_fact("identity.citizenship")["id"]
    official_source = _source(
        opportunity_service,
        "https://example.org/synthetic-scholarship",
        official=True,
    )
    submitted = opportunity_service.submit_opportunity(
        OpportunityInput(
            canonical_title="Synthetic Global Scholarship",
            organization="Synthetic Foundation",
            opportunity_type="scholarship",
            cycle="2027",
            canonical_url="https://example.org/synthetic-scholarship",
            application_url="https://example.org/synthetic-scholarship/apply",
            deadline_at=datetime.now(UTC) + timedelta(days=20),
            deadline_timezone="UTC",
            open_status="open",
            source_completeness=1,
            source_ids=[official_source],
        )
    )
    opportunity_id = submitted["opportunity_id"]
    opportunity_service.submit_requirement(
        RequirementInput(
            opportunity_id=opportunity_id,
            requirement_type="citizenship",
            field_path="identity.citizenship",
            operator=PredicateOperator.EQUALS,
            expected="US",
            hard=True,
            extracted_text="Applicant must be a U.S. citizen.",
            source_id=official_source,
            evidence_locator="Eligibility section",
            extraction_confidence=1,
        )
    )
    return opportunity_id, fact_id, official_source


def _assess(context: Any, opportunity_id: str, fact_id: str | None, source_id: str) -> None:
    decisions = DecisionService(context)
    for dimension in context.settings.scoring.weights:
        decisions.submit_assessment(
            AssessmentInput(
                opportunity_id=opportunity_id,
                dimension=dimension,
                value=9,
                rationale="Strong synthetic strategic fit backed by the accepted test profile.",
                supporting_fact_ids=[fact_id] if fact_id else [],
                source_ids=[source_id],
                confidence=0.9,
                model_provider="synthetic",
                model_id="fixture-model",
                prompt_version="1.0",
            )
        )


def test_eligible_evaluate_queue_and_grounded_packet(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    decisions = DecisionService(context)
    evaluation = decisions.evaluate(
        opportunity_id,
        total_effort_minutes=60,
        next_action_minutes=20,
        main_risk="One recommendation letter is still manual.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    assert evaluation["decision"] == "apply"
    action_id = decisions.create_action(
        ActionInput(
            opportunity_id=opportunity_id,
            action_type="prepare_evidence",
            description="Review the evidence map and choose one project example.",
            estimated_minutes=20,
            due_at=datetime.now(UTC) + timedelta(days=10),
            readiness_score=95,
        )
    )
    next_action = decisions.next_action(30)
    assert next_action and next_action["action_id"] == action_id
    packet = ApplicationService(context).prepare(
        opportunity_id,
        [
            ClaimInput(
                text="The applicant satisfies the verified citizenship requirement.",
                supporting_fact_ids=[fact_id],
            )
        ],
        generation_model="fixture-model",
    )
    assert packet["external_submission_performed"] is False
    assert set(packet["artifact_types"]) == ApplicationService.REQUIRED_ARTIFACTS
    ready = ApplicationService(context).mark_ready(packet["application_id"])
    assert ready["state"] == "ready"


def test_hard_failure_is_pass_even_with_high_assessments(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context, citizenship="NG")
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    result = DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Hard citizenship mismatch.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    assert result["eligibility"]["overall"] == "ineligible"
    assert result["decision"] == "pass"
    assert result["net_value_score"] >= 90


def test_missing_hard_fact_requires_review(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context, citizenship=None)
    _assess(context, opportunity_id, fact_id, source_id)
    result = DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Citizenship evidence is missing.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    assert result["eligibility"]["overall"] == "review_required"
    assert result["decision"] == "review_required"


def test_expired_profile_fact_requires_review(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, _source_id = _seed(context)
    assert fact_id is not None
    with context.database.transaction() as session:
        fact = session.get(CanonicalFactRow, fact_id)
        assert fact is not None
        fact.effective_until = datetime.now(UTC) - timedelta(minutes=1)
    result = DecisionService(context).evaluate_eligibility(opportunity_id)
    assert result["overall"] == "review_required"
    assert result["checks"][0]["reason_code"] == "PROFILE_FACT_MISSING"


def test_unverified_or_incomplete_official_source_blocks_apply(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    with context.database.transaction() as session:
        source = session.get(SourceRow, source_id)
        opportunity = session.get(OpportunityRow, opportunity_id)
        assert source is not None and opportunity is not None
        source.official_status = "unofficial"
        opportunity.source_completeness = 0.5
    eligibility = DecisionService(context).evaluate_eligibility(opportunity_id)
    assert eligibility["overall"] == "review_required"
    assert "official source is missing" in eligibility["source_gate"]
    assert "official requirements are incomplete" in eligibility["source_gate"]

    _assess(context, opportunity_id, fact_id, source_id)
    evaluation = DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Official source verification is incomplete.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    assert evaluation["decision"] == "review_required"


def test_expired_opportunity_is_marked_expired_and_not_actionable(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    with context.database.transaction() as session:
        opportunity = session.get(OpportunityRow, opportunity_id)
        assert opportunity is not None
        opportunity.deadline_at = datetime.now(UTC) - timedelta(minutes=1)
    _assess(context, opportunity_id, fact_id, source_id)
    decisions = DecisionService(context)
    result = decisions.evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="The deadline has passed.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    assert result["decision"] == "review_required"
    opportunity = OpportunityService(context).get(opportunity_id)
    assert opportunity and opportunity["lifecycle_state"] == "expired"
    with pytest.raises(ValueError, match="current actionable evaluation"):
        decisions.create_action(
            ActionInput(
                opportunity_id=opportunity_id,
                action_type="apply",
                description="This expired action must not be created.",
                estimated_minutes=5,
                readiness_score=100,
            )
        )


def test_unsupported_claim_is_rejected(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    with pytest.raises(ValueError, match="Grounding failed"):
        ApplicationService(context).prepare(
            opportunity_id,
            [ClaimInput(text="Fabricated award winner", supporting_fact_ids=["missing-fact"])],
        )


def test_assessment_rejects_unknown_source(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, _source_id = _seed(context)
    assert fact_id is not None
    with pytest.raises(ValueError, match="unknown sources"):
        DecisionService(context).submit_assessment(
            AssessmentInput(
                opportunity_id=opportunity_id,
                dimension="career_alignment",
                value=8,
                rationale="Synthetic assessment with an invalid evidence source.",
                supporting_fact_ids=[fact_id],
                source_ids=["missing-source"],
                confidence=0.8,
                model_provider="synthetic",
                model_id="fixture-model",
                prompt_version="1.0",
            )
        )


def test_ready_blocks_review_claim_and_regeneration_updates_packet(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    applications = ApplicationService(context)
    packet = applications.prepare(
        opportunity_id,
        [
            ClaimInput(
                text="This claim still needs a human review.",
                supporting_fact_ids=[fact_id],
                status="needs_review",
            )
        ],
    )
    with pytest.raises(ValueError, match="all claims"):
        applications.mark_ready(packet["application_id"])

    regenerated = applications.prepare(
        opportunity_id,
        [
            ClaimInput(
                text="The reviewed claim is now approved.",
                supporting_fact_ids=[fact_id],
                status="user_approved",
            )
        ],
        generation_model="fixture-model-v2",
    )
    assert regenerated["application_id"] == packet["application_id"]
    assert applications.mark_ready(packet["application_id"])["state"] == "ready"


def test_ready_blocks_stale_evaluation_and_stale_packet(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    decisions = DecisionService(context)
    decisions.evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    applications = ApplicationService(context)
    packet = applications.prepare(
        opportunity_id,
        [ClaimInput(text="Grounded claim.", supporting_fact_ids=[fact_id])],
    )
    decisions.evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Updated synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    with pytest.raises(ValueError, match="older evaluation"):
        applications.mark_ready(packet["application_id"])

    applications.prepare(
        opportunity_id,
        [ClaimInput(text="Grounded claim.", supporting_fact_ids=[fact_id])],
    )
    profile = ProfileService(context)
    added_source = _source(profile, "synthetic-new-profile-evidence")
    profile.submit_observations(
        [
            ObservationInput(
                field_path="skills.synthetic",
                value=True,
                source_id=added_source,
                evidence_locator="synthetic update",
                extraction_confidence=1,
                observed_at=datetime.now(UTC),
            )
        ]
    )
    with pytest.raises(ValueError, match="evaluation inputs are stale"):
        applications.mark_ready(packet["application_id"])

    decisions.evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Current synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    applications.prepare(
        opportunity_id,
        [ClaimInput(text="Grounded claim.", supporting_fact_ids=[fact_id])],
    )
    assert applications.mark_ready(packet["application_id"])["state"] == "ready"


def test_ready_requires_current_official_source_and_deadline(context_factory: Any) -> None:
    context = context_factory()
    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=10,
        next_action_minutes=5,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    applications = ApplicationService(context)
    packet = applications.prepare(
        opportunity_id,
        [ClaimInput(text="Grounded claim.", supporting_fact_ids=[fact_id])],
    )
    with context.database.transaction() as session:
        opportunity = session.get(OpportunityRow, opportunity_id)
        assert opportunity is not None
        opportunity.deadline_at = None
        opportunity.last_verified_at = None
    with pytest.raises(ValueError) as error:
        applications.mark_ready(packet["application_id"])
    assert "official source verification" in str(error.value)
    assert "verified future deadline" in str(error.value)


def test_opportunity_intake_duplicate_lookup_and_application_context(
    context_factory: Any, tmp_path: Any
) -> None:
    context = context_factory()
    opportunities = OpportunityService(context)
    with pytest.raises(ValueError, match="empty"):
        opportunities.ingest_text("  ")
    text = opportunities.ingest_text("Synthetic opportunity text", idempotency_key="text-1")
    assert text["needs_structured_extraction"] is True
    assert opportunities.ingest_text("Synthetic opportunity text", idempotency_key="text-1") == text

    path = tmp_path / "opportunity.txt"
    path.write_text("Synthetic file opportunity", encoding="utf-8")
    assert opportunities.ingest_file(path)["text"] == "Synthetic file opportunity"

    opportunity_id, fact_id, source_id = _seed(context)
    assert fact_id is not None
    record = opportunities.get(opportunity_id)
    assert record and len(record["requirements"]) == 1
    assert opportunities.find_duplicates(
        "Synthetic Foundation", "Synthetic Global Scholarship", "2027"
    ) == [opportunity_id]
    duplicate = opportunities.submit_opportunity(
        OpportunityInput(
            canonical_title="Synthetic Global Scholarship",
            organization="Synthetic Foundation",
            opportunity_type="scholarship",
            cycle="2027",
            canonical_url="https://example.org/synthetic-scholarship?utm_source=test",
            application_url="https://example.org/synthetic-scholarship/apply",
            deadline_at=datetime.now(UTC) + timedelta(days=30),
            deadline_timezone="UTC",
            open_status="open",
            source_completeness=1,
            source_ids=[source_id],
        ),
        idempotency_key="duplicate-1",
    )
    assert duplicate["duplicate"] is True and duplicate["opportunity_id"] == opportunity_id
    updated = opportunities.get(opportunity_id)
    assert updated and updated["version"] == 2
    assert opportunities.get("missing") is None

    _assess(context, opportunity_id, fact_id, source_id)
    DecisionService(context).evaluate(
        opportunity_id,
        total_effort_minutes=20,
        next_action_minutes=10,
        main_risk="Synthetic risk.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    applications = ApplicationService(context)
    application_id = applications.create(opportunity_id, idempotency_key="application-1")
    assert applications.create(opportunity_id) == application_id
    prepared_context = applications.prepare_context(opportunity_id)
    assert prepared_context["evaluation"]["decision"] == "apply"
    stored = applications.store_artifact(
        application_id,
        artifact_type="custom/answer",
        content="Synthetic supported answer.",
        supporting_fact_ids=[fact_id],
        idempotency_key="artifact-1",
    )
    assert stored == applications.store_artifact(
        application_id,
        artifact_type="custom/answer",
        content="Synthetic supported answer.",
        supporting_fact_ids=[fact_id],
        idempotency_key="artifact-1",
    )
    with pytest.raises(ValueError, match="already exists"):
        applications.store_artifact(
            application_id,
            artifact_type="custom/answer",
            content="A second custom answer.",
            supporting_fact_ids=[fact_id],
        )
    with pytest.raises(ValueError, match=r"application\.prepare"):
        applications.store_artifact(
            application_id,
            artifact_type="evidence_map",
            content="Reserved packet artifact.",
            supporting_fact_ids=[fact_id],
        )
    with pytest.raises(ValueError, match="unsafe canonical evidence"):
        applications.store_artifact(
            application_id,
            artifact_type="unsupported",
            content="No evidence.",
            supporting_fact_ids=[],
        )


def test_action_completion_queue_guards_and_lifecycle_confirmation(context_factory: Any) -> None:
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
    assert decisions.get_evaluation(opportunity_id) is not None
    assert decisions.get_evaluation("missing") is None
    with pytest.raises(ValueError, match="Available minutes"):
        decisions.queue(-1)
    with pytest.raises(ValueError, match="completion_ratio"):
        decisions.create_action(
            ActionInput(
                opportunity_id=opportunity_id,
                action_type="invalid",
                description="Invalid ratio fixture.",
                estimated_minutes=10,
                readiness_score=50,
            ),
            completion_ratio=2,
        )
    action = ActionInput(
        opportunity_id=opportunity_id,
        action_type="review",
        description="Review synthetic evidence.",
        estimated_minutes=10,
        readiness_score=80,
    )
    completed_id = decisions.create_action(action)
    skipped_id = decisions.create_action(action)
    assert decisions.complete_action(completed_id)["status"] == "complete"
    assert decisions.complete_action(skipped_id, skipped=True)["status"] == "skipped"
    with pytest.raises(ValueError, match="Completable"):
        decisions.complete_action(completed_id)

    decisions.update_lifecycle(opportunity_id, target=LifecycleState.PREPARING)
    decisions.update_lifecycle(opportunity_id, target=LifecycleState.READY)
    with pytest.raises(ValueError, match="explicit confirmation"):
        decisions.update_lifecycle(opportunity_id, target=LifecycleState.SUBMITTED)
    occurred_at = datetime.now(UTC)
    assert (
        decisions.update_lifecycle(
            opportunity_id,
            target=LifecycleState.SUBMITTED,
            confirmed=True,
            occurred_at=occurred_at,
        )["state"]
        == "submitted"
    )
    with pytest.raises(ValueError, match="Outcome transitions"):
        decisions.update_lifecycle(opportunity_id, target=LifecycleState.ACCEPTED, actor="system")


def test_profile_change_removes_stale_evaluation_actions_from_queue(
    context_factory: Any,
) -> None:
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
    action = ActionInput(
        opportunity_id=opportunity_id,
        action_type="review",
        description="Review synthetic evidence.",
        estimated_minutes=10,
        readiness_score=80,
    )
    decisions.create_action(action)
    assert len(decisions.queue()) == 1

    profile = ProfileService(context)
    added_source = _source(profile, "synthetic-stale-queue-evidence")
    profile.submit_observations(
        [
            ObservationInput(
                field_path="skills.queue_fixture",
                value=True,
                source_id=added_source,
                evidence_locator="synthetic update",
                extraction_confidence=1,
                observed_at=datetime.now(UTC),
            )
        ]
    )
    assert decisions.queue() == []
    assert decisions.get_evaluation(opportunity_id)["current"] is False
    with pytest.raises(ValueError, match="current actionable evaluation"):
        decisions.create_action(action)

"""Seed a complete, visibly synthetic local workflow without network access."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opportunityos.application.applications import ApplicationService
from opportunityos.application.context import ApplicationContext
from opportunityos.application.decisions import DecisionService
from opportunityos.application.opportunities import OpportunityService
from opportunityos.application.profile import ProfileService
from opportunityos.schemas import (
    ActionInput,
    AssessmentInput,
    ClaimInput,
    ObservationInput,
    OfficialStatus,
    OpportunityInput,
    PredicateOperator,
    RequirementInput,
    SourceCreate,
    SourceType,
)


def source(service: ProfileService | OpportunityService, locator: str, official: bool) -> str:
    return service.add_source(
        SourceCreate(
            source_type=SourceType.OFFICIAL_WEBPAGE if official else SourceType.USER_STATEMENT,
            source_locator=locator,
            display_name=f"Synthetic {'official' if official else 'profile'} evidence",
            official_status=OfficialStatus.OFFICIAL if official else OfficialStatus.UNKNOWN,
            retrieved_at=datetime.now(UTC),
            content_hash=("a" if official else "b") * 64,
            mime_type="text/html" if official else "text/plain",
            trust_class="official" if official else "credible",
        )
    )


def main() -> None:
    context = ApplicationContext.create(Path.cwd())
    profile = ProfileService(context)
    opportunities = OpportunityService(context)
    decisions = DecisionService(context)
    profile_source = source(profile, "synthetic:user-statement", False)
    profile.submit_observations(
        [
            ObservationInput(
                field_path="identity.citizenship",
                value="US",
                source_id=profile_source,
                evidence_locator="synthetic fixture",
                extraction_confidence=1,
                observed_at=datetime.now(UTC),
            )
        ]
    )
    fact = profile.get_fact("identity.citizenship")
    assert fact is not None
    official_source = source(opportunities, "https://example.org/synthetic-scholarship", True)
    submitted = opportunities.submit_opportunity(
        OpportunityInput(
            canonical_title="Synthetic Global Scholarship",
            organization="Synthetic Foundation",
            opportunity_type="scholarship",
            cycle="2027",
            canonical_url="https://example.org/synthetic-scholarship",
            application_url="https://example.org/synthetic-scholarship/apply",
            deadline_at=datetime.now(UTC) + timedelta(days=60),
            deadline_timezone="UTC",
            open_status="open",
            source_completeness=1,
            source_ids=[official_source],
        )
    )
    opportunity_id = str(submitted["opportunity_id"])
    opportunities.submit_requirement(
        RequirementInput(
            opportunity_id=opportunity_id,
            requirement_type="citizenship",
            field_path="identity.citizenship",
            operator=PredicateOperator.EQUALS,
            expected="US",
            hard=True,
            extracted_text="Applicant must be a U.S. citizen.",
            source_id=official_source,
            evidence_locator="synthetic eligibility section",
            extraction_confidence=1,
        )
    )
    for dimension in context.settings.scoring.weights:
        decisions.submit_assessment(
            AssessmentInput(
                opportunity_id=opportunity_id,
                dimension=dimension,
                value=9,
                rationale="Strong synthetic fit backed by the synthetic accepted profile.",
                supporting_fact_ids=[str(fact["id"])],
                source_ids=[official_source],
                confidence=0.9,
                model_provider="synthetic",
                model_id="fixture-model",
                prompt_version="1.0",
            )
        )
    evaluation = decisions.evaluate(
        opportunity_id,
        total_effort_minutes=60,
        next_action_minutes=20,
        main_risk="Synthetic recommendation letter remains a manual step.",
        model_provider="synthetic",
        model_id="fixture-model",
    )
    action_id = decisions.create_action(
        ActionInput(
            opportunity_id=opportunity_id,
            action_type="prepare_evidence",
            description="Review the synthetic evidence map.",
            estimated_minutes=20,
            due_at=datetime.now(UTC) + timedelta(days=14),
            readiness_score=95,
        )
    )
    packet = ApplicationService(context).prepare(
        opportunity_id,
        [
            ClaimInput(
                text="The synthetic applicant satisfies the citizenship fixture.",
                supporting_fact_ids=[str(fact["id"])],
            )
        ],
        generation_model="fixture-model",
    )
    print(
        json.dumps(
            {
                "result": "PASS",
                "opportunity_id": opportunity_id,
                "evaluation": evaluation,
                "action_id": action_id,
                "application_id": packet["application_id"],
                "packet_path": packet["packet_path"],
                "external_submission_performed": False,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()

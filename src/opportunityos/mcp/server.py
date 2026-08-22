"""Typed, least-privilege stdio MCP tools for Hermes."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings as FastMCPSettings
from pydantic import ValidationError

from opportunityos.application.applications import ApplicationService
from opportunityos.application.automation import AutomationService
from opportunityos.application.briefs import BriefService
from opportunityos.application.context import ApplicationContext
from opportunityos.application.decisions import DecisionService
from opportunityos.application.discovery import DiscoveryService
from opportunityos.application.execution import ExecutionService
from opportunityos.application.followup import FollowUpService
from opportunityos.application.health import HealthService
from opportunityos.application.operations import OperationsService
from opportunityos.application.opportunities import OpportunityService
from opportunityos.application.profile import ProfileService
from opportunityos.application.propagation import PropagationService
from opportunityos.application.scouts import ScoutService
from opportunityos.schemas import (
    ActionInput,
    AssessmentInput,
    ClaimInput,
    DiscoveryExpansionInput,
    DiscoveryQueryInput,
    DiscoverySourceCheckInput,
    LifecycleState,
    ObservationInput,
    OpportunityInput,
    RequirementInput,
    ResolutionInput,
    ScoutRunInput,
    SourceCreate,
)

# MCP SDK 1.29.0 defines Settings before FastMCP, leaving the lifespan forward
# reference incomplete. Rebuild after both classes import (upstream issue #3294).
FastMCPSettings.model_rebuild()
mcp = FastMCP("OpportunityOS")
T = TypeVar("T")


def _context() -> ApplicationContext:
    repository = Path(os.environ.get("OPPORTUNITYOS_REPOSITORY_ROOT", Path.cwd()))
    return ApplicationContext.create(repository)


def _safe(call: Callable[[], T]) -> dict[str, Any]:
    try:
        return {"ok": True, "data": call(), "error": None, "error_code": None}
    except (ValueError, TypeError) as error:
        return {"ok": False, "data": None, "error": str(error), "error_code": "INVALID_INPUT"}
    except Exception:
        return {
            "ok": False,
            "data": None,
            "error": (
                "The local operation failed; run `opportunityos doctor` for recovery guidance."
            ),
            "error_code": "LOCAL_OPERATION_FAILED",
        }


@mcp.tool()
def profile_get_current() -> dict[str, Any]:
    """Read the current canonical profile projection."""
    return _safe(lambda: ProfileService(_context()).get_current())


@mcp.tool()
def profile_get_fact(field_path: str) -> dict[str, Any]:
    """Read one canonical fact by its profile field path."""
    return _safe(lambda: ProfileService(_context()).get_fact(field_path))


@mcp.tool()
def profile_submit_observations(
    observations: list[dict[str, Any]], idempotency_key: str
) -> dict[str, Any]:
    """Write validated candidate observations; this never writes canonical truth directly."""
    return _safe(
        lambda: ProfileService(_context()).submit_observations(
            [ObservationInput.model_validate(item) for item in observations],
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def profile_get_dependencies(field_paths: list[str]) -> dict[str, Any]:
    """List opportunity identifiers that depend on profile field paths."""
    return _safe(lambda: ProfileService(_context()).get_dependencies(field_paths))


@mcp.tool()
def profile_rebuild_projection() -> dict[str, Any]:
    """Rebuild canonical profile state from append-only evidence and resolutions."""
    return _safe(lambda: ProfileService(_context()).rebuild_projection())


@mcp.tool()
def profile_sync_status() -> dict[str, Any]:
    """Read projection, review, and connector synchronization state."""
    return _safe(lambda: ProfileService(_context()).sync_status())


@mcp.tool()
def profile_sync_github(username: str, idempotency_key: str) -> dict[str, Any]:
    """Import conservative GitHub metadata observations without asserting expertise."""
    return _safe(
        lambda: ProfileService(_context()).sync_github(username, idempotency_key=idempotency_key)
    )


@mcp.tool()
def review_list() -> dict[str, Any]:
    """List open review items."""
    return _safe(lambda: ProfileService(_context()).list_reviews())


@mcp.tool()
def review_get(review_id: str) -> dict[str, Any]:
    """Read one review item and its candidate identifiers."""
    return _safe(lambda: ProfileService(_context()).get_review(review_id))


@mcp.tool()
def review_resolve(
    review_id: str, resolution: dict[str, Any], idempotency_key: str
) -> dict[str, Any]:
    """Apply an explicit human resolution and rebuild affected truth."""
    return _safe(
        lambda: ProfileService(_context()).resolve_review(
            review_id,
            ResolutionInput.model_validate(resolution),
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def review_defer(review_id: str, until: datetime) -> dict[str, Any]:
    """Defer a review item until a specified time."""
    return _safe(lambda: ProfileService(_context()).defer_review(review_id, until))


@mcp.tool()
def opportunity_submit_input(input_value: str, idempotency_key: str) -> dict[str, Any]:
    """Cache a supported file or retrieve URL/text as untrusted candidate source data."""

    def submit() -> Any:
        service = OpportunityService(_context())
        path = Path(input_value)
        if path.exists():
            return service.ingest_file(path, idempotency_key=idempotency_key)
        if input_value.startswith(("https://", "http://")):
            return service.ingest_url(input_value, idempotency_key=idempotency_key)
        return service.ingest_text(input_value, idempotency_key=idempotency_key)

    return _safe(submit)


@mcp.tool()
def opportunity_submit_source(source: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    """Store a provenance source record after schema validation."""

    def submit() -> dict[str, str]:
        value = SourceCreate.model_validate(source)
        if value.official_status.value == "official" or "official" in value.trust_class.lower():
            raise ValueError(
                "Official status or trust requires OpportunityOS retrieval through "
                "opportunity_reverify"
            )
        value = value.model_copy(update={"trust_class": "candidate"})
        return {"source_id": OpportunityService(_context()).add_source(value, idempotency_key)}

    return _safe(submit)


@mcp.tool()
def opportunity_submit_extraction(
    opportunity: dict[str, Any],
    requirements: list[dict[str, Any]],
    idempotency_key: str,
    repair_attempt: int = 0,
) -> dict[str, Any]:
    """Store a validated normalized opportunity and its structured requirements."""

    def submit() -> Any:
        service = OpportunityService(_context())
        try:
            if repair_attempt not in {0, 1}:
                raise ValueError("repair_attempt must be 0 or 1")
            validated_opportunity = OpportunityInput.model_validate(opportunity)
            validated_requirements = []
            for item in requirements:
                payload = dict(item)
                payload["opportunity_id"] = "pending-validation"
                validated_requirements.append(RequirementInput.model_validate(payload))
            if any(
                requirement.source_id not in validated_opportunity.source_ids
                for requirement in validated_requirements
            ):
                raise ValueError("Every requirement source must be attached to the opportunity")
        except (ValidationError, ValueError) as error:
            if repair_attempt == 1:
                review_id = service.record_extraction_failure(
                    f"extraction:{idempotency_key}",
                    idempotency_key=f"{idempotency_key}:failure",
                )
                raise ValueError(
                    f"Structured extraction invalid after one repair; review item {review_id}"
                ) from error
            raise ValueError(
                "Structured extraction is invalid; retry once with repaired JSON"
            ) from error
        result = service.submit_opportunity(
            validated_opportunity,
            idempotency_key=f"{idempotency_key}:opportunity",
        )
        opportunity_id = str(result["opportunity_id"])
        requirement_ids = []
        for index, requirement in enumerate(validated_requirements):
            requirement_ids.append(
                service.submit_requirement(
                    requirement.model_copy(update={"opportunity_id": opportunity_id}),
                    idempotency_key=f"{idempotency_key}:requirement:{index}",
                )
            )
        return {**result, "requirement_ids": requirement_ids}

    return _safe(submit)


@mcp.tool()
def opportunity_get(opportunity_id: str) -> dict[str, Any]:
    """Read an opportunity, source references, and requirements."""
    return _safe(lambda: OpportunityService(_context()).get(opportunity_id))


@mcp.tool()
def opportunity_find_duplicates(
    organization: str, title: str, cycle: str | None = None
) -> dict[str, Any]:
    """Find deterministic semantic-key duplicates for the same cycle."""
    return _safe(lambda: OpportunityService(_context()).find_duplicates(organization, title, cycle))


@mcp.tool()
def opportunity_reverify(opportunity_id: str, idempotency_key: str) -> dict[str, Any]:
    """Retrieve an opportunity's canonical official source and compare its content version."""
    return _safe(
        lambda: OpportunityService(_context()).reverify(
            opportunity_id, idempotency_key=idempotency_key
        )
    )


@mcp.tool()
def eligibility_evaluate(opportunity_id: str) -> dict[str, Any]:
    """Evaluate normalized hard requirements from canonical facts only."""
    return _safe(lambda: DecisionService(_context()).evaluate_eligibility(opportunity_id))


@mcp.tool()
def assessment_submit(assessment: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    """Store an evidence-linked subjective component for deterministic scoring."""
    return _safe(
        lambda: {
            "assessment_id": DecisionService(_context()).submit_assessment(
                AssessmentInput.model_validate(assessment), idempotency_key=idempotency_key
            )
        }
    )


@mcp.tool()
def evaluation_compute(
    opportunity_id: str,
    total_effort_minutes: int,
    next_action_minutes: int,
    main_risk: str,
    model_provider: str,
    model_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Compute and persist deterministic eligibility, score, confidence, and decision."""
    return _safe(
        lambda: DecisionService(_context()).evaluate(
            opportunity_id,
            total_effort_minutes=total_effort_minutes,
            next_action_minutes=next_action_minutes,
            main_risk=main_risk,
            model_provider=model_provider,
            model_id=model_id,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def evaluation_get(opportunity_id: str) -> dict[str, Any]:
    """Read the latest versioned evaluation."""
    return _safe(lambda: DecisionService(_context()).get_evaluation(opportunity_id))


@mcp.tool()
def queue_list(available_minutes: int = 45) -> dict[str, Any]:
    """List ready actions ranked for the available time."""
    return _safe(lambda: DecisionService(_context()).queue(available_minutes))


@mcp.tool()
def queue_next(available_minutes: int = 45) -> dict[str, Any]:
    """Return one highest-value ready action for the available time."""
    return _safe(lambda: DecisionService(_context()).next_action(available_minutes))


@mcp.tool()
def action_create(
    action: dict[str, Any], completion_ratio: float, idempotency_key: str
) -> dict[str, Any]:
    """Create one bounded local action from a completed deterministic evaluation."""
    return _safe(
        lambda: {
            "action_id": DecisionService(_context()).create_action(
                ActionInput.model_validate(action),
                completion_ratio=completion_ratio,
                idempotency_key=idempotency_key,
            )
        }
    )


@mcp.tool()
def action_complete(action_id: str) -> dict[str, Any]:
    """Record explicit completion of a local action."""
    return _safe(lambda: DecisionService(_context()).complete_action(action_id))


@mcp.tool()
def action_skip(action_id: str) -> dict[str, Any]:
    """Record explicit skipping of a local action."""
    return _safe(lambda: DecisionService(_context()).complete_action(action_id, skipped=True))


@mcp.tool()
def application_create(opportunity_id: str, idempotency_key: str) -> dict[str, Any]:
    """Create a private application record after an explicit preparation request."""
    return _safe(
        lambda: {
            "application_id": ApplicationService(_context()).create(
                opportunity_id, idempotency_key=idempotency_key
            )
        }
    )


@mcp.tool()
def application_prepare_context(opportunity_id: str) -> dict[str, Any]:
    """Read official requirements and eligible evidence for grounded drafting."""
    return _safe(lambda: ApplicationService(_context()).prepare_context(opportunity_id))


@mcp.tool()
def application_prepare(
    opportunity_id: str,
    claims: list[dict[str, Any]],
    idempotency_key: str,
    generation_model: str | None = None,
    prompt_version: str = "1.0",
) -> dict[str, Any]:
    """Compile or refresh the seven reserved private packet artifacts from grounded claims."""
    return _safe(
        lambda: ApplicationService(_context()).prepare(
            opportunity_id,
            [ClaimInput.model_validate(claim) for claim in claims],
            generation_model=generation_model,
            prompt_version=prompt_version,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def application_store_artifact(
    application_id: str,
    artifact_type: str,
    content: str,
    supporting_fact_ids: list[str],
    idempotency_key: str,
) -> dict[str, Any]:
    """Store one supplemental private artifact when every evidence identifier is safe."""
    return _safe(
        lambda: ApplicationService(_context()).store_artifact(
            application_id,
            artifact_type=artifact_type,
            content=content,
            supporting_fact_ids=supporting_fact_ids,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def application_mark_ready(application_id: str) -> dict[str, Any]:
    """Mark a packet ready only after source, deadline, eligibility, and grounding checks."""
    return _safe(lambda: ApplicationService(_context()).mark_ready(application_id))


@mcp.tool()
def lifecycle_update(
    opportunity_id: str,
    state: str,
    confirmed: bool = False,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Apply a validated local lifecycle transition; SUBMITTED requires confirmation."""
    return _safe(
        lambda: DecisionService(_context()).update_lifecycle(
            opportunity_id,
            LifecycleState(state),
            confirmed=confirmed,
            occurred_at=occurred_at,
        )
    )


@mcp.tool()
def scout_begin(run: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    """Begin a bounded category scout run controlled by Hermes cron."""
    return _safe(
        lambda: ScoutService(_context()).begin(
            ScoutRunInput.model_validate(run), idempotency_key=idempotency_key
        )
    )


@mcp.tool()
def scout_record_candidate(
    run_id: str, opportunity_id: str, source_ids: list[str]
) -> dict[str, Any]:
    """Record a candidate and apply the deterministic delivery quality gate."""
    return _safe(
        lambda: ScoutService(_context()).record_candidate(
            run_id, opportunity_id, source_ids=source_ids
        )
    )


@mcp.tool()
def scout_record_usage(
    run_id: str,
    queries: int = 0,
    pages: int = 0,
    model_calls: int = 0,
    deep_evaluations: int = 0,
) -> dict[str, Any]:
    """Record observable usage and stop the run at a deterministic configured limit."""
    return _safe(
        lambda: ScoutService(_context()).record_usage(
            run_id,
            queries=queries,
            pages=pages,
            model_calls=model_calls,
            deep_evaluations=deep_evaluations,
        )
    )


@mcp.tool()
def scout_finish(
    run_id: str,
    material_opportunity_ids: list[str],
    errors: list[str],
    idempotency_key: str,
) -> dict[str, Any]:
    """Finalize a run with a bounded digest or an explicit silent result."""
    return _safe(
        lambda: ScoutService(_context()).finish(
            run_id,
            material_opportunity_ids=material_opportunity_ids,
            errors=errors,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def scout_abort(run_id: str, reason: str = "scout run stopped by operator") -> dict[str, Any]:
    """Close an interrupted scout run without claiming success."""
    return _safe(lambda: ScoutService(_context()).abort(run_id, reason=reason))


@mcp.tool()
def discovery_begin(idempotency_key: str | None = None) -> dict[str, Any]:
    """Plan one bounded global discovery cycle across every enabled lens."""
    return _safe(lambda: DiscoveryService(_context()).begin_global(idempotency_key=idempotency_key))


@mcp.tool()
def discovery_record_query(
    run_id: str,
    observation: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Record one bounded query outcome; source text remains untrusted data."""
    return _safe(
        lambda: DiscoveryService(_context()).record_query(
            run_id,
            DiscoveryQueryInput.model_validate(observation),
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def discovery_expand_branch(
    run_id: str,
    proposal: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create one bounded adaptive branch with explicit lineage and reason."""
    return _safe(
        lambda: DiscoveryService(_context()).expand_branch(
            run_id,
            DiscoveryExpansionInput.model_validate(proposal),
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def discovery_record_source_check(
    run_id: str,
    source_check: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Record a bounded source check and update private source productivity state."""
    return _safe(
        lambda: DiscoveryService(_context()).record_source_check(
            run_id,
            DiscoverySourceCheckInput.model_validate(source_check),
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def discovery_finish(
    run_id: str,
    completed_lenses: list[str],
    skipped_lenses: dict[str, str],
    errors: list[str] | None = None,
    material_opportunity_ids: list[str] | None = None,
    dedup_completed: bool = True,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Finalize global coverage honestly, returning a digest or [SILENT]."""
    return _safe(
        lambda: DiscoveryService(_context()).finish(
            run_id,
            completed_lenses=completed_lenses,
            skipped_lenses=skipped_lenses,
            errors=errors,
            material_opportunity_ids=material_opportunity_ids,
            dedup_completed=dedup_completed,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def discovery_coverage(run_id: str) -> dict[str, Any]:
    """Read one private machine-readable global coverage report."""
    return _safe(lambda: DiscoveryService(_context()).coverage(run_id))


@mcp.tool()
def discovery_strategies(lens: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Read bounded persisted query strategy lineage and yield metrics."""
    return _safe(lambda: DiscoveryService(_context()).strategies(lens=lens, limit=limit))


@mcp.tool()
def discovery_sources(due_only: bool = False, limit: int = 50) -> dict[str, Any]:
    """Read bounded source registry state, optionally limited to due sources."""
    return _safe(lambda: DiscoveryService(_context()).sources(due_only=due_only, limit=limit))


@mcp.tool()
def discovery_status() -> dict[str, Any]:
    """Read current global discovery configuration and private run-state summary."""
    return _safe(lambda: DiscoveryService(_context()).status())


@mcp.tool()
def execution_get_risk(available_minutes: int = 45) -> dict[str, Any]:
    """Return high-value unfinished reminder candidates without delivering them."""
    return _safe(lambda: ExecutionService(_context()).get_risk(available_minutes=available_minutes))


@mcp.tool()
def execution_next(available_minutes: int = 45) -> dict[str, Any]:
    """Return the one highest-leverage current action first."""
    return _safe(lambda: DecisionService(_context()).next_action(available_minutes))


@mcp.tool()
def execution_record_delivery(
    reminder_id: str, fingerprint: str, idempotency_key: str
) -> dict[str, Any]:
    """Record a redacted reminder delivery after Hermes accepts the local result."""
    return _safe(
        lambda: ExecutionService(_context()).record_delivery(
            reminder_id, fingerprint, idempotency_key=idempotency_key
        )
    )


@mcp.tool()
def execution_snooze(
    action_id: str, until: datetime | None = None, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Snooze one local action reminder."""
    return _safe(
        lambda: ExecutionService(_context()).snooze(
            action_id, until, idempotency_key=idempotency_key
        )
    )


@mcp.tool()
def execution_stop_reminders(opportunity_id: str) -> dict[str, Any]:
    """Stop local reminders for one opportunity."""
    return _safe(lambda: ExecutionService(_context()).stop(opportunity_id))


@mcp.tool()
def execution_mark_passed(opportunity_id: str) -> dict[str, Any]:
    """Stop local reminders after an explicit user pass decision."""
    return _safe(lambda: ExecutionService(_context()).mark_passed(opportunity_id))


@mcp.tool()
def execution_mark_applied(opportunity_id: str) -> dict[str, Any]:
    """Stop local reminders after an explicit user-applied record."""
    return _safe(lambda: ExecutionService(_context()).mark_applied(opportunity_id))


@mcp.tool()
def auto_prepare_evaluate_gate(
    opportunity_id: str, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Evaluate and persist the deterministic automatic-preparation gate."""
    return _safe(
        lambda: AutomationService(_context()).auto_preparation_gate(
            opportunity_id, idempotency_key=idempotency_key
        )
    )


@mcp.tool()
def auto_prepare_execute(
    opportunity_id: str,
    claims: list[dict[str, Any]],
    idempotency_key: str,
    generation_model: str | None = None,
) -> dict[str, Any]:
    """Prepare a private grounded packet only after the gate passes."""
    return _safe(
        lambda: AutomationService(_context()).auto_prepare_execute(
            opportunity_id,
            [ClaimInput.model_validate(claim) for claim in claims],
            generation_model=generation_model,
            idempotency_key=idempotency_key,
        )
    )


@mcp.tool()
def followup_get_due() -> dict[str, Any]:
    """List explicitly submitted opportunities currently eligible for follow-up."""
    return _safe(lambda: FollowUpService(_context()).get_due())


@mcp.tool()
def followup_prepare_draft(opportunity_id: str) -> dict[str, Any]:
    """Prepare a private grounded follow-up draft; nothing is sent."""
    return _safe(lambda: FollowUpService(_context()).prepare_draft(opportunity_id))


@mcp.tool()
def followup_mark_complete(opportunity_id: str) -> dict[str, Any]:
    """Record explicit local completion of a follow-up."""
    return _safe(lambda: FollowUpService(_context()).mark_complete(opportunity_id))


@mcp.tool()
def brief_build(brief_type: str, available_minutes: int = 45) -> dict[str, Any]:
    """Build a material-only daily, evening, or weekly local brief."""
    return _safe(
        lambda: BriefService(_context()).build(brief_type, available_minutes=available_minutes)
    )


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Check local health without inspecting credentials or private content."""
    return _safe(lambda: HealthService(_context()).check())


@mcp.tool()
def health_record_live_test(component: str, success: bool, detail_code: str) -> dict[str, Any]:
    """Record controlled local/live evidence for one health component."""
    return _safe(
        lambda: HealthService(_context()).record_live_test(component, success, detail_code)
    )


@mcp.tool()
def backup_run_auto() -> dict[str, Any]:
    """Run the configured private automatic-backup policy."""
    return _safe(lambda: HealthService(_context()).backup_auto())


@mcp.tool()
def backup_status() -> dict[str, Any]:
    """Read the latest private backup freshness and checksum."""
    return _safe(lambda: HealthService(_context()).backup_status())


@mcp.tool()
def profile_reevaluate_dependents(field_paths: list[str], limit: int = 20) -> dict[str, Any]:
    """Reevaluate active opportunities affected by changed canonical profile fields."""
    return _safe(
        lambda: PropagationService(_context()).reevaluate_dependents(field_paths, limit=limit)
    )


@mcp.tool()
def automation_controls() -> dict[str, Any]:
    """List effective local automation controls."""
    return _safe(lambda: AutomationService(_context()).controls())


@mcp.tool()
def automation_set_control(key: str, enabled: bool, reason: str = "user control") -> dict[str, Any]:
    """Enable or disable one local automation class."""
    return _safe(lambda: AutomationService(_context()).set_control(key, enabled, reason=reason))


@mcp.tool()
def system_status() -> dict[str, Any]:
    """Read local health and honest external integration gates."""
    return _safe(lambda: OperationsService(_context()).status())


@mcp.tool()
def backup_create() -> dict[str, Any]:
    """Create and integrity-check a private local database backup."""
    return _safe(lambda: OperationsService(_context()).backup())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

"""Operational CLI using the same application interfaces as MCP."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

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
    ClaimInput,
    DiscoveryExpansionInput,
    DiscoveryQueryInput,
    DiscoverySourceCheckInput,
    LifecycleState,
    ResolutionInput,
    ScoutRunInput,
)
from opportunityos.security import audit_public_repository

app = typer.Typer(no_args_is_help=True, help="Evidence-backed local opportunity intelligence.")
profile_app = typer.Typer(no_args_is_help=True, help="Profile evidence and projection.")
review_app = typer.Typer(no_args_is_help=True, help="Human review inbox.")
opportunity_app = typer.Typer(no_args_is_help=True, help="Opportunity records.")
lifecycle_app = typer.Typer(no_args_is_help=True, help="Opportunity lifecycle.")
scout_app = typer.Typer(no_args_is_help=True, help="Bounded Hermes scout state.")
discovery_app = typer.Typer(no_args_is_help=True, help="Global V3 discovery state and coverage.")
audit_app = typer.Typer(no_args_is_help=True, help="Public repository safety.")
app.add_typer(profile_app, name="profile")
app.add_typer(review_app, name="review")
app.add_typer(opportunity_app, name="opportunity")
app.add_typer(lifecycle_app, name="lifecycle")
app.add_typer(scout_app, name="scout")
app.add_typer(discovery_app, name="discovery")
app.add_typer(audit_app, name="audit")


def _context() -> ApplicationContext:
    return ApplicationContext.create(Path.cwd())


def _emit(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))


@app.command()
def setup() -> None:
    """Initialize private directories and the local database."""
    context = _context()
    result = OperationsService(context).initialize()
    result["next_steps"] = [
        "Install Hermes using the current official native Windows instructions.",
        "Run `hermes model` and select ChatGPT or Codex Subscription.",
        "Review docs/HERMES_SETUP.md before registering MCP and skills.",
        "Configure a numeric Discord allowlist; never enable allow-all.",
    ]
    _emit(result)


@app.command()
def doctor() -> None:
    """Run safe local checks and report external gates honestly."""
    _emit(OperationsService(_context()).doctor())


@app.command()
def status() -> None:
    """Show database, privacy, integration, and scout status."""
    _emit(OperationsService(_context()).status())


@profile_app.command("show")
def profile_show() -> None:
    _emit(ProfileService(_context()).get_current())


@profile_app.command("import")
def profile_import(path: Path) -> None:
    if path.suffix.lower() != ".json":
        raise typer.BadParameter(
            "Prose snapshots require Hermes structured extraction; use the profile-sync skill."
        )
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    _emit(ProfileService(_context()).import_chatgpt_snapshot(snapshot))


@profile_app.command("sync-github")
def profile_sync_github(username: str) -> None:
    _emit(ProfileService(_context()).sync_github(username))


@profile_app.command("rebuild")
def profile_rebuild() -> None:
    _emit(ProfileService(_context()).rebuild_projection())


@review_app.command("list")
def review_list() -> None:
    _emit(ProfileService(_context()).list_reviews())


@review_app.command("resolve")
def review_resolve(
    review_id: str,
    candidate_id: str | None = typer.Option(None, help="Select an existing candidate."),
    entered_json: str | None = typer.Option(None, help="Enter a replacement JSON value."),
    note: str = typer.Option("", help="Human resolution note."),
) -> None:
    if bool(candidate_id) == bool(entered_json):
        raise typer.BadParameter("Provide exactly one of --candidate-id or --entered-json")
    value = ResolutionInput(
        action="select" if candidate_id else "enter",
        selected_candidate_id=candidate_id,
        entered_value=json.loads(entered_json) if entered_json else None,
        alternatives_considered=[],
        note=note,
        scope="until_newer_evidence",
    )
    _emit(ProfileService(_context()).resolve_review(review_id, value))


@review_app.command("defer")
def review_defer(review_id: str, until: datetime) -> None:
    _emit(ProfileService(_context()).defer_review(review_id, until))


@app.command()
def ingest(input_value: str) -> None:
    """Cache a supported file or retrieve a URL/text as untrusted source data."""
    service = OpportunityService(_context())
    path = Path(input_value)
    if path.exists():
        _emit(service.ingest_file(path))
    elif input_value.startswith(("https://", "http://")):
        _emit(service.ingest_url(input_value))
    else:
        _emit(service.ingest_text(input_value))


@opportunity_app.command("show")
def opportunity_show(opportunity_id: str) -> None:
    value = OpportunityService(_context()).get(opportunity_id)
    if value is None:
        raise typer.BadParameter("Opportunity not found")
    _emit(value)


@app.command()
def queue(minutes: int = typer.Option(45, min=1)) -> None:
    _emit(DecisionService(_context()).queue(minutes))


@app.command("next")
def next_action(minutes: int = typer.Option(45, min=1)) -> None:
    _emit(DecisionService(_context()).next_action(minutes))


@app.command()
def prepare(opportunity_id: str, claims_json: Path | None = None) -> None:
    claims = []
    if claims_json:
        claims = [ClaimInput.model_validate(item) for item in json.loads(claims_json.read_text())]
    _emit(ApplicationService(_context()).prepare(opportunity_id, claims))


@lifecycle_app.command("update")
def lifecycle_update(
    opportunity_id: str,
    state: LifecycleState,
    confirmed: bool = typer.Option(False),
    occurred_at: datetime | None = typer.Option(None),
) -> None:
    _emit(
        DecisionService(_context()).update_lifecycle(
            opportunity_id, state, confirmed=confirmed, occurred_at=occurred_at
        )
    )


@scout_app.command("run")
def scout_run(category: str) -> None:
    context = _context()
    service = ScoutService(context)
    start = service.begin(
        ScoutRunInput(category=category, query_plan=[], budget=context.settings.scouts.model_dump())
    )
    _emit(service.finish(str(start["run_id"]), material_opportunity_ids=[]))


@scout_app.command("status")
def scout_status() -> None:
    _emit(ScoutService(_context()).status())


@scout_app.command("abort")
def scout_abort(run_id: str, reason: str = typer.Option("scout run stopped by operator")) -> None:
    _emit(ScoutService(_context()).abort(run_id, reason=reason))


def _json_file(path: Path, *, max_bytes: int = 131_072) -> Any:
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        raise typer.BadParameter("JSON input exceeds the bounded CLI input size")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise typer.BadParameter("JSON input is invalid") from error


@discovery_app.command("begin")
def discovery_begin(idempotency_key: str | None = typer.Option(None)) -> None:
    _emit(DiscoveryService(_context()).begin_global(idempotency_key=idempotency_key))


@discovery_app.command("query")
def discovery_query(
    run_id: str,
    observation_json: Path,
    idempotency_key: str | None = typer.Option(None),
) -> None:
    _emit(
        DiscoveryService(_context()).record_query(
            run_id,
            DiscoveryQueryInput.model_validate(_json_file(observation_json)),
            idempotency_key=idempotency_key,
        )
    )


@discovery_app.command("expand")
def discovery_expand(
    run_id: str,
    proposal_json: Path,
    idempotency_key: str | None = typer.Option(None),
) -> None:
    _emit(
        DiscoveryService(_context()).expand_branch(
            run_id,
            DiscoveryExpansionInput.model_validate(_json_file(proposal_json)),
            idempotency_key=idempotency_key,
        )
    )


@discovery_app.command("source-check")
def discovery_source_check(
    run_id: str,
    source_check_json: Path,
    idempotency_key: str | None = typer.Option(None),
) -> None:
    _emit(
        DiscoveryService(_context()).record_source_check(
            run_id,
            DiscoverySourceCheckInput.model_validate(_json_file(source_check_json)),
            idempotency_key=idempotency_key,
        )
    )


@discovery_app.command("finish")
def discovery_finish(
    run_id: str,
    finish_json: Path,
    idempotency_key: str | None = typer.Option(None),
) -> None:
    payload = _json_file(finish_json)
    if not isinstance(payload, dict):
        raise typer.BadParameter("Finish JSON must be an object")
    _emit(
        DiscoveryService(_context()).finish(
            run_id,
            completed_lenses=list(payload.get("completed_lenses", [])),
            skipped_lenses=dict(payload.get("skipped_lenses", {})),
            errors=list(payload.get("errors", [])),
            material_opportunity_ids=list(payload.get("material_opportunity_ids", [])),
            dedup_completed=bool(payload.get("dedup_completed", True)),
            idempotency_key=idempotency_key,
        )
    )


@discovery_app.command("coverage")
def discovery_coverage(run_id: str) -> None:
    _emit(DiscoveryService(_context()).coverage(run_id))


@discovery_app.command("strategies")
def discovery_strategies(
    lens: str | None = typer.Option(None), limit: int = typer.Option(50, min=1, max=200)
) -> None:
    _emit(DiscoveryService(_context()).strategies(lens=lens, limit=limit))


@discovery_app.command("sources")
def discovery_sources(
    due_only: bool = typer.Option(False), limit: int = typer.Option(50, min=1, max=200)
) -> None:
    _emit(DiscoveryService(_context()).sources(due_only=due_only, limit=limit))


@discovery_app.command("status")
def discovery_status() -> None:
    _emit(DiscoveryService(_context()).status())


@app.command("execution-risk")
def execution_risk(minutes: int = typer.Option(45, min=1)) -> None:
    _emit(ExecutionService(_context()).get_risk(available_minutes=minutes))


@app.command("execution-next")
def execution_next(minutes: int = typer.Option(45, min=1)) -> None:
    _emit(DecisionService(_context()).next_action(minutes))


@app.command()
def snooze(action_id: str, until: datetime | None = typer.Option(None)) -> None:
    _emit(ExecutionService(_context()).snooze(action_id, until))


@app.command("stop-reminders")
def stop_reminders(opportunity_id: str) -> None:
    _emit(ExecutionService(_context()).stop(opportunity_id))


@app.command("mark-passed")
def mark_passed(opportunity_id: str) -> None:
    _emit(ExecutionService(_context()).mark_passed(opportunity_id))


@app.command("mark-applied")
def mark_applied(opportunity_id: str) -> None:
    _emit(ExecutionService(_context()).mark_applied(opportunity_id))


@app.command("auto-prepare-gate")
def auto_prepare_gate(opportunity_id: str) -> None:
    _emit(AutomationService(_context()).auto_preparation_gate(opportunity_id))


@app.command("auto-prepare")
def auto_prepare(opportunity_id: str, claims_json: Path) -> None:
    claims = [ClaimInput.model_validate(item) for item in json.loads(claims_json.read_text())]
    _emit(AutomationService(_context()).auto_prepare_execute(opportunity_id, claims))


@app.command("followup-due")
def followup_due() -> None:
    _emit(FollowUpService(_context()).get_due())


@app.command("followup-prepare")
def followup_prepare(opportunity_id: str) -> None:
    _emit(FollowUpService(_context()).prepare_draft(opportunity_id))


@app.command("followup-complete")
def followup_complete(opportunity_id: str) -> None:
    _emit(FollowUpService(_context()).mark_complete(opportunity_id))


@app.command()
def brief(brief_type: str = typer.Argument(..., metavar="daily|evening|weekly")) -> None:
    _emit(BriefService(_context()).build(brief_type))


@app.command()
def health() -> None:
    _emit(HealthService(_context()).check())


@app.command("health-live")
def health_live(component: str, success: bool, detail_code: str) -> None:
    _emit(HealthService(_context()).record_live_test(component, success, detail_code))


@app.command("backup-auto")
def backup_auto() -> None:
    _emit(HealthService(_context()).backup_auto())


@app.command("backup-status")
def backup_status() -> None:
    _emit(HealthService(_context()).backup_status())


@app.command("automation-controls")
def automation_controls() -> None:
    _emit(AutomationService(_context()).controls())


@app.command("automation-control")
def automation_control(key: str, enabled: bool, reason: str = typer.Option("user control")) -> None:
    _emit(AutomationService(_context()).set_control(key, enabled, reason=reason))


@profile_app.command("reevaluate-dependents")
def profile_reevaluate_dependents(
    field_path: list[str] = typer.Argument(...), limit: int = typer.Option(20, min=1, max=100)
) -> None:
    _emit(PropagationService(_context()).reevaluate_dependents(field_path, limit=limit))


@app.command()
def backup() -> None:
    _emit(OperationsService(_context()).backup())


@app.command()
def restore(backup_path: Path, target_directory: Path) -> None:
    _emit(OperationsService(_context()).restore(backup_path, target_directory))


@app.command("export")
def export_data() -> None:
    _emit({"export_path": str(OperationsService(_context()).export_json())})


@app.command()
def purge(older_than_days: int = typer.Option(30, min=1)) -> None:
    _emit({"attachments_removed": OperationsService(_context()).purge_attachments(older_than_days)})


@audit_app.command("public-repo")
def audit_public_repo() -> None:
    findings = audit_public_repository(Path.cwd())
    _emit(
        {
            "result": "PASS" if not findings else "FAIL",
            "findings": [finding.__dict__ for finding in findings],
        }
    )
    if findings:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

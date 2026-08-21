"""Operational CLI using the same application interfaces as MCP."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import typer

from opportunityos.application.applications import ApplicationService
from opportunityos.application.context import ApplicationContext
from opportunityos.application.decisions import DecisionService
from opportunityos.application.operations import OperationsService
from opportunityos.application.opportunities import OpportunityService
from opportunityos.application.profile import ProfileService
from opportunityos.application.scouts import ScoutService
from opportunityos.schemas import ClaimInput, LifecycleState, ResolutionInput, ScoutRunInput
from opportunityos.security import audit_public_repository

app = typer.Typer(no_args_is_help=True, help="Evidence-backed local opportunity intelligence.")
profile_app = typer.Typer(no_args_is_help=True, help="Profile evidence and projection.")
review_app = typer.Typer(no_args_is_help=True, help="Human review inbox.")
opportunity_app = typer.Typer(no_args_is_help=True, help="Opportunity records.")
lifecycle_app = typer.Typer(no_args_is_help=True, help="Opportunity lifecycle.")
scout_app = typer.Typer(no_args_is_help=True, help="Bounded Hermes scout state.")
audit_app = typer.Typer(no_args_is_help=True, help="Public repository safety.")
app.add_typer(profile_app, name="profile")
app.add_typer(review_app, name="review")
app.add_typer(opportunity_app, name="opportunity")
app.add_typer(lifecycle_app, name="lifecycle")
app.add_typer(scout_app, name="scout")
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

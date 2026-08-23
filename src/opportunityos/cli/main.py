"""Small, structured CLI for the OpportunityOS v4 protocol."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import typer

from opportunityos.v4.export import export_state, import_state
from opportunityos.v4.models import ProfileDocument
from opportunityos.v4.runtime import (
    RuntimePaths,
    RuntimeStateError,
    merge_mappings,
    read_yaml,
    write_yaml,
)
from opportunityos.v4.store import HistoryStore

app = typer.Typer(
    no_args_is_help=True,
    help="Model-agnostic, self-learning opportunity discovery memory.",
)
profile_app = typer.Typer(no_args_is_help=True, help="Private user context.")
policy_app = typer.Typer(no_args_is_help=True, help="Deterministic hard constraints.")
run_app = typer.Typer(no_args_is_help=True, help="Search-run protocol.")
candidate_app = typer.Typer(no_args_is_help=True, help="Candidate checks and recording.")
feedback_app = typer.Typer(no_args_is_help=True, help="Search feedback.")
strategy_app = typer.Typer(no_args_is_help=True, help="Learned search strategy.")
history_app = typer.Typer(no_args_is_help=True, help="Opportunity history.")

app.add_typer(profile_app, name="profile")
app.add_typer(policy_app, name="policy")
app.add_typer(run_app, name="run")
app.add_typer(candidate_app, name="candidate")
app.add_typer(feedback_app, name="feedback")
app.add_typer(strategy_app, name="strategy")
app.add_typer(history_app, name="history")


def _store() -> tuple[RuntimePaths, HistoryStore]:
    paths = RuntimePaths.from_environment(Path.cwd())
    store = HistoryStore(paths)
    store.initialize()
    return paths, store


def _emit(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))


def _format(value: Any, output_format: str) -> None:
    if output_format not in {"json", "human"}:
        raise typer.BadParameter("--format must be json or human")
    _emit(value)


def _json_file(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        if len(payload) > 131_072:
            raise ValueError("JSON input exceeds the bounded CLI input size")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise typer.BadParameter("JSON input is invalid or unreadable") from error
    if not isinstance(value, dict):
        raise typer.BadParameter("JSON input must be an object")
    return value


@app.command("init")
def init(output_format: str = typer.Option("human", "--format")) -> None:
    """Create private profile, policy, strategy, and SQLite state."""
    paths, _ = _store()
    _format(
        {"schema_version": 1, "initialized": True, "state_root": str(paths.root)}, output_format
    )


@app.command("context")
def context(
    category: str = typer.Option(..., "--category"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    """Return compact profile, policy, strategy, and history for one search."""
    _, store = _store()
    _format(store.context(category), output_format)


@profile_app.command("show")
def profile_show(output_format: str = typer.Option("human", "--format")) -> None:
    paths, _ = _store()
    _format(read_yaml(paths.profile), output_format)


@profile_app.command("import")
def profile_import(path: Path) -> None:
    try:
        value = (
            read_yaml(path)
            if path.suffix.lower() in {".yaml", ".yml"}
            else json.loads(path.read_text(encoding="utf-8"))
        )
        ProfileDocument.model_validate(value)
        paths, _ = _store()
        write_yaml(paths.profile, value)
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeStateError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    _emit({"schema_version": 1, "imported": True, "profile_path": str(paths.profile)})


@profile_app.command("export")
def profile_export(
    destination: Path | None = typer.Argument(None),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    paths, _ = _store()
    value = read_yaml(paths.profile)
    if destination:
        write_yaml(destination, value)
        value = {"schema_version": 1, "export_path": str(destination.absolute())}
    _format(value, output_format)


@profile_app.command("patch")
def profile_patch(
    patch_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    patch = _json_file(patch_json)
    paths, _ = _store()
    updated = merge_mappings(read_yaml(paths.profile), patch)
    ProfileDocument.model_validate(updated)
    write_yaml(paths.profile, updated)
    _format({"schema_version": 1, "updated": True, "profile": updated}, output_format)


@policy_app.command("show")
def policy_show(output_format: str = typer.Option("human", "--format")) -> None:
    paths, _ = _store()
    _format(read_yaml(paths.policy), output_format)


@policy_app.command("patch")
def policy_patch(
    policy_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    patch = _json_file(policy_json)
    paths, _ = _store()
    updated = merge_mappings(read_yaml(paths.policy), patch)
    write_yaml(paths.policy, updated)
    _format({"schema_version": 1, "updated": True, "policy": updated}, output_format)


@run_app.command("start")
def run_start(
    category: str = typer.Option(..., "--category"),
    agent: str | None = typer.Option(None, "--agent"),
    model: str | None = typer.Option(None, "--model"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(store.start_run(category, agent, model), output_format)


@run_app.command("finish")
def run_finish(
    run_id: str,
    summary_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(store.finish_run(run_id, _json_file(summary_json)), output_format)


@candidate_app.command("check")
def candidate_check(
    candidate_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(store.check_candidate(_json_file(candidate_json)), output_format)


@candidate_app.command("record")
def candidate_record(
    run_id: str = typer.Option(..., "--run"),
    candidate_json: Path = typer.Option(..., "--json"),
    query: str | None = typer.Option(None, "--query"),
    source: str | None = typer.Option(None, "--source"),
    rank: int | None = typer.Option(None, "--rank"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(
        store.record_candidate(
            run_id, _json_file(candidate_json), query=query, source=source, rank=rank
        ),
        output_format,
    )


@feedback_app.command("add")
def feedback_add(
    feedback_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(store.add_feedback(_json_file(feedback_json)), output_format)


@strategy_app.command("show")
def strategy_show(output_format: str = typer.Option("human", "--format")) -> None:
    _, store = _store()
    _format(store.strategy_show(), output_format)


@strategy_app.command("history")
def strategy_history(
    limit: int = typer.Option(50, min=1, max=200),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format({"schema_version": 1, "revisions": store.strategy_history(limit)}, output_format)


@strategy_app.command("propose")
def strategy_propose(
    proposal_json: Path = typer.Option(..., "--json"),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    try:
        result = store.propose_strategy(_json_file(proposal_json))
    except (ValueError, RuntimeStateError) as error:
        raise typer.BadParameter(str(error)) from error
    _format(result, output_format)


@strategy_app.command("rollback")
def strategy_rollback(
    revision: int,
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    try:
        result = store.rollback_strategy(revision)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    _format(result, output_format)


@history_app.command("recent")
def history_recent(
    limit: int = typer.Option(20, min=1, max=200),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(
        {"schema_version": 1, "opportunities": store.recent_history(limit=limit)}, output_format
    )


@history_app.command("search")
def history_search(
    query: str,
    limit: int = typer.Option(20, min=1, max=200),
    output_format: str = typer.Option("human", "--format"),
) -> None:
    _, store = _store()
    _format(
        {"schema_version": 1, "opportunities": store.recent_history(query, limit)}, output_format
    )


@app.command("export")
def export(destination: Path = typer.Argument(Path("opportunityos-export.zip"))) -> None:
    paths, _ = _store()
    _emit(export_state(paths, destination))


@app.command("import")
def import_archive(source: Path) -> None:
    paths, _ = _store()
    _emit(import_state(paths, source))


def main() -> None:
    """Run the CLI with stable failure classes for agent callers."""
    try:
        app()
    except RuntimeStateError as error:
        typer.echo(str(error), err=True)
        raise SystemExit(2) from error
    except sqlite3.DatabaseError as error:
        typer.echo(f"Local state error: {error}", err=True)
        raise SystemExit(2) from error
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()

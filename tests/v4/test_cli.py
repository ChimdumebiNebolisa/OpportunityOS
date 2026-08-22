from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from opportunityos.cli.main import app


def _candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "title": "Synthetic Program",
        "organization": "Synthetic Org",
        "category": "research",
        "source_url": "https://synthetic.example/program",
        "official_url": "https://synthetic.example/program",
        "status": "open",
        "first_party": True,
        "verified_at": "2026-08-22T17:00:00Z",
        "metadata": {"cycle": "2026"},
    }


def test_cli_search_protocol_returns_versioned_json(monkeypatch: object, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.chdir(repository)  # type: ignore[attr-defined]
    monkeypatch.setenv("OPPORTUNITYOS_DATA_DIR", str(tmp_path / "private"))  # type: ignore[attr-defined]
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_candidate()), encoding="utf-8")
    runner = CliRunner()

    initialized = runner.invoke(app, ["init", "--format", "json"])
    assert initialized.exit_code == 0, initialized.output
    assert json.loads(initialized.stdout)["initialized"] is True
    started = runner.invoke(
        app,
        [
            "run",
            "start",
            "--category",
            "research",
            "--agent",
            "hermes",
            "--model",
            "model-a",
            "--format",
            "json",
        ],
    )
    assert started.exit_code == 0, started.output
    run_id = json.loads(started.stdout)["run_id"]
    checked = runner.invoke(
        app,
        [
            "candidate",
            "check",
            "--json",
            str(candidate_path),
            "--format",
            "json",
        ],
    )
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.stdout)["is_new"] is True
    recorded = runner.invoke(
        app,
        [
            "candidate",
            "record",
            "--run",
            run_id,
            "--json",
            str(candidate_path),
            "--format",
            "json",
        ],
    )
    assert recorded.exit_code == 0, recorded.output
    finished_path = tmp_path / "summary.json"
    finished_path.write_text(json.dumps({"query_count": 2, "delivered_count": 1}), encoding="utf-8")
    finished = runner.invoke(
        app,
        ["run", "finish", run_id, "--json", str(finished_path), "--format", "json"],
    )
    assert finished.exit_code == 0, finished.output
    recent = runner.invoke(app, ["history", "recent", "--format", "json"])
    assert recent.exit_code == 0, recent.output
    assert json.loads(recent.stdout)["opportunities"][0]["title"] == "Synthetic Program"


def test_cli_profile_policy_strategy_and_portability_commands(
    monkeypatch: object, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.chdir(repository)  # type: ignore[attr-defined]
    source_root = tmp_path / "source-state"
    monkeypatch.setenv("OPPORTUNITYOS_DATA_DIR", str(source_root))  # type: ignore[attr-defined]
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--format", "json"]).exit_code == 0

    profile_patch = tmp_path / "profile-patch.json"
    profile_patch.write_text(json.dumps({"interests": ["synthetic research"]}), encoding="utf-8")
    assert (
        runner.invoke(
            app, ["profile", "patch", "--json", str(profile_patch), "--format", "json"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["profile", "show", "--format", "json"]).exit_code == 0
    profile_export = tmp_path / "profile.yaml"
    assert (
        runner.invoke(app, ["profile", "export", str(profile_export), "--format", "json"]).exit_code
        == 0
    )

    policy_patch = tmp_path / "policy-patch.json"
    policy_patch.write_text(
        json.dumps({"categories": {"research": {"deadline": {"unknown": "allow_with_warning"}}}}),
        encoding="utf-8",
    )
    assert (
        runner.invoke(
            app, ["policy", "patch", "--json", str(policy_patch), "--format", "json"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["policy", "show", "--format", "json"]).exit_code == 0

    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        json.dumps(
            {
                "reason": "A reusable source pattern was found.",
                "evidence": ["run-1"],
                "scope": "research",
                "changes": {"query_patterns": ["site:synthetic.example research"]},
                "proposed_by": "hermes",
            }
        ),
        encoding="utf-8",
    )
    assert (
        runner.invoke(
            app, ["strategy", "propose", "--json", str(proposal), "--format", "json"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["strategy", "show", "--format", "json"]).exit_code == 0
    assert runner.invoke(app, ["strategy", "history", "--format", "json"]).exit_code == 0
    assert runner.invoke(app, ["strategy", "rollback", "1", "--format", "json"]).exit_code == 0
    assert runner.invoke(app, ["history", "search", "synthetic", "--format", "json"]).exit_code == 0

    feedback = tmp_path / "feedback.json"
    feedback.write_text(json.dumps({"type": "good_source", "text": "Useful."}), encoding="utf-8")
    assert (
        runner.invoke(
            app, ["feedback", "add", "--json", str(feedback), "--format", "json"]
        ).exit_code
        == 0
    )

    archive = tmp_path / "state-export.zip"
    assert runner.invoke(app, ["export", str(archive)]).exit_code == 0
    destination_root = tmp_path / "destination-state"
    monkeypatch.setenv("OPPORTUNITYOS_DATA_DIR", str(destination_root))  # type: ignore[attr-defined]
    assert runner.invoke(app, ["import", str(archive)]).exit_code == 0

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from opportunityos.cli.main import app


def _environment(monkeypatch: object, tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("*.sqlite3\n", encoding="utf-8")
    monkeypatch.chdir(repository)  # type: ignore[attr-defined]
    monkeypatch.setenv("OPPORTUNITYOS_DATA_DIR", str(tmp_path / "private"))  # type: ignore[attr-defined]
    monkeypatch.setenv("OPPORTUNITYOS_CONFIG_DIR", str(tmp_path / "config"))  # type: ignore[attr-defined]
    return repository


def test_cli_setup_status_and_audit(monkeypatch: object, tmp_path: Path) -> None:
    _environment(monkeypatch, tmp_path)
    runner = CliRunner()
    setup = runner.invoke(app, ["setup"])
    assert setup.exit_code == 0, setup.output
    assert json.loads(setup.stdout)["integrity"] == "ok"
    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exit_code == 0, doctor.output
    assert json.loads(doctor.stdout)["result"] == "PASS"
    audit = runner.invoke(app, ["audit", "public-repo"])
    assert audit.exit_code == 0, audit.output
    assert json.loads(audit.stdout)["result"] == "PASS"


def test_cli_required_command_groups_are_visible() -> None:
    output = CliRunner().invoke(app, ["--help"])
    assert output.exit_code == 0
    for command in [
        "setup",
        "doctor",
        "profile",
        "review",
        "ingest",
        "queue",
        "next",
        "prepare",
        "scout",
        "backup",
        "restore",
        "export",
        "purge",
        "audit",
    ]:
        assert command in output.stdout

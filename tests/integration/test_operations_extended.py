from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from opportunityos.application.operations import OperationsService


def test_operations_health_backup_restore_export_and_metrics(
    context_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(OperationsService, "_hermes_executable", staticmethod(lambda: None))
    context = context_factory()
    operations = OperationsService(context)
    initialized = operations.initialize()
    assert initialized["integrity"] == "ok"
    status = operations.status()
    assert status["database"]["integrity"] == "ok"
    assert status["public_repo_audit"]["state"] == "PASS"
    assert status["hermes"]["state"] == "GATED"
    assert status["codex_oauth"]["state"] == "GATED"
    assert status["opportunityos_mcp"]["state"] == "GATED"
    assert status["discord_configuration"]["state"] == "GATED"
    assert status["discord_gateway"]["state"] == "GATED"
    assert status["live_verification"]["state"] == "GATED"
    assert status["continuous_operation"] is False
    assert operations.doctor()["result"] == "PASS"

    backup = operations.backup()
    backup_path = Path(backup["backup_path"])
    assert backup_path.is_file() and Path(backup["manifest_path"]).is_file()
    second_backup = operations.backup()
    assert second_backup["backup_path"] != backup["backup_path"]
    assert Path(second_backup["backup_path"]).is_file()
    target = context.settings.data_dir / "restored"
    restored = operations.restore(backup_path, target)
    assert Path(restored["restored_path"]).is_file()
    export_path = operations.export_json()
    assert export_path.is_file() and "audit_events" in export_path.read_text(encoding="utf-8")
    assert operations.metrics()["analytics_uploaded"] == 0


def test_hermes_fallback_discovery_and_state_distinctions(
    context_factory: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hermes_home = tmp_path / "hermes"
    if os.name == "nt":
        launcher = hermes_home / "hermes-agent" / "bin" / "hermes.exe"
    else:
        launcher = hermes_home / "hermes-agent" / "venv" / "bin" / "hermes"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"synthetic launcher")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr("opportunityos.application.operations.shutil.which", lambda _: None)

    def fake_run(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        command = arguments[1:]
        outputs = {
            ("--version",): "Hermes Agent v0.20.5\n",
            ("auth", "status", "openai-codex"): "openai-codex: logged in\n",
            ("mcp", "list"): "opportunityos  all  enabled\n",
            ("gateway", "list"): "Gateways:\n  default (current) - PID 1234\n",
        }
        return subprocess.CompletedProcess(arguments, 0, outputs[tuple(command)], "")

    monkeypatch.setattr("opportunityos.application.operations.subprocess.run", fake_run)
    status = OperationsService(context_factory()).status()

    assert OperationsService._hermes_executable() == str(launcher)
    assert status["hermes"]["state"] == "PASS"
    assert status["codex_oauth"]["state"] == "PASS"
    assert status["opportunityos_mcp"]["state"] == "PASS"
    assert status["discord_configuration"]["state"] == "GATED"
    assert status["discord_gateway"]["state"] == "PASS"
    assert status["live_verification"]["state"] == "GATED"
    assert status["continuous_operation"] is True

    def fake_mixed_mcp_output(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        command = arguments[1:]
        outputs = {
            ("auth", "status", "openai-codex"): "openai-codex: logged in\n",
            ("mcp", "list"): "opportunityos  all  disabled\nother-server  all  enabled\n",
            ("gateway", "list"): "Gateways:\n  default (current) - PID 1234\n",
        }
        return subprocess.CompletedProcess(arguments, 0, outputs[tuple(command)], "")

    monkeypatch.setattr(
        "opportunityos.application.operations.subprocess.run", fake_mixed_mcp_output
    )
    integrations = OperationsService._hermes_integrations(str(launcher))
    assert integrations["opportunityos_mcp"]["state"] == "GATED"


def test_failed_hermes_version_command_is_not_reported_as_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(OperationsService, "_hermes_executable", staticmethod(lambda: "hermes"))
    monkeypatch.setattr(
        OperationsService,
        "_run_hermes",
        staticmethod(lambda *_: subprocess.CompletedProcess(["hermes", "--version"], 1, "", "bad")),
    )

    assert OperationsService._command_version("hermes")["state"] == "FAIL"


def test_hermes_gateway_pid_metadata_is_checked_without_reading_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "gateway.pid").write_text('{"pid": 1234}', encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        OperationsService, "_process_running", staticmethod(lambda process_id: process_id == 1234)
    )

    assert OperationsService._hermes_gateway_running() is True


def test_restore_and_purge_guards(context_factory: Any) -> None:
    context = context_factory()
    operations = OperationsService(context)
    backup = operations.backup()
    backup_path = Path(backup["backup_path"])

    nonempty = context.settings.data_dir / "nonempty-target"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        operations.restore(backup_path, nonempty)

    invalid = context.settings.data_dir / "not-a-backup.txt"
    invalid.write_text("invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="SQLite backup"):
        operations.restore(invalid, context.settings.data_dir / "other-target")

    attachment = context.storage.category_path("attachments") / "old.txt"
    attachment.write_text("old", encoding="utf-8")
    old = (datetime.now(UTC) - timedelta(days=10)).timestamp()
    os.utime(attachment, (old, old))
    assert operations.purge_attachments(older_than_days=5) == 1
    with pytest.raises(ValueError, match="positive"):
        operations.purge_attachments(older_than_days=-1)
    with pytest.raises(ValueError, match="positive"):
        operations.purge_attachments(older_than_days=0)

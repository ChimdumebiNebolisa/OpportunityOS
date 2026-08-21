from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from opportunityos.application.operations import OperationsService


def test_operations_health_backup_restore_export_and_metrics(
    context_factory: Any,
) -> None:
    context = context_factory()
    operations = OperationsService(context)
    initialized = operations.initialize()
    assert initialized["integrity"] == "ok"
    status = operations.status()
    assert status["database"]["integrity"] == "ok"
    assert status["public_repo_audit"]["state"] == "PASS"
    assert status["hermes"]["state"] == "GATED"
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

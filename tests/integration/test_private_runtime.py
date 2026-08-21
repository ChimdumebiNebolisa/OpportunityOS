from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect

from opportunityos.application.context import ApplicationContext
from opportunityos.application.operations import OperationsService
from opportunityos.config.settings import load_settings
from opportunityos.infrastructure.database import Base
from opportunityos.infrastructure.storage import PrivateStorage, UnsafePathError
from opportunityos.security import audit_public_repository


def test_private_root_cannot_be_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    settings = load_settings(
        repository,
        data_dir=repository / "private",
        config_dir=tmp_path / "config",
    )
    with pytest.raises(UnsafePathError, match="cannot be inside"):
        PrivateStorage(settings)


def test_private_config_cannot_be_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="configuration directory"):
        load_settings(
            repository,
            data_dir=tmp_path / "private",
            config_dir=repository / "config",
        )


def test_private_roots_reject_symlink_traversal(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    real_data = tmp_path / "real-data"
    real_config = tmp_path / "real-config"
    real_data.mkdir()
    real_config.mkdir()
    data_link = tmp_path / "data-link"
    config_link = tmp_path / "config-link"
    try:
        os.symlink(real_data, data_link, target_is_directory=True)
        os.symlink(real_config, config_link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlink creation is unavailable: {error}")
    with pytest.raises(ValueError, match="Private data"):
        load_settings(repository, data_dir=data_link, config_dir=real_config)
    with pytest.raises(ValueError, match="Private configuration"):
        load_settings(repository, data_dir=real_data, config_dir=config_link)


def test_database_pragmas_and_integrity(context_factory: Any) -> None:
    context = context_factory()
    assert context.database.integrity_check() == "ok"
    assert context.database.pragma("foreign_keys") == 1
    assert str(context.database.pragma("journal_mode")).lower() == "wal"
    assert not context.database.path.is_relative_to(context.settings.repository_root)
    assert "alembic_version" in inspect(context.database.engine).get_table_names()


def test_existing_unstamped_schema_is_backed_up_before_migration(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    data_dir = tmp_path / "private-data"
    data_dir.mkdir()
    database_path = data_dir / "opportunityos.sqlite3"
    Base.metadata.create_all(create_engine(f"sqlite:///{database_path.as_posix()}"))

    context = ApplicationContext.create(
        repository,
        data_dir=data_dir,
        config_dir=tmp_path / "private-config",
    )
    backups = list(context.storage.category_path("backups").glob("pre-migration-*.sqlite3"))
    assert len(backups) == 1
    assert backups[0].with_suffix(".manifest.json").is_file()
    assert "alembic_version" in inspect(context.database.engine).get_table_names()


def test_public_audit_flags_secret_and_database_without_echoing_value(tmp_path: Path) -> None:
    repository = tmp_path / "audit"
    repository.mkdir()
    token = "gh" + "p_" + "A" * 24
    (repository / "bad.txt").write_text(token, encoding="utf-8")
    (repository / "runtime.sqlite3").write_bytes(b"synthetic")
    findings = audit_public_repository(repository)
    assert {finding.rule for finding in findings} == {
        "github_token",
        "prohibited_private_artifact",
    }
    assert token not in repr(findings)


def test_public_audit_flags_secret_files_and_database_sidecars(tmp_path: Path) -> None:
    repository = tmp_path / "audit-sensitive-files"
    repository.mkdir()
    (repository / ".env.local").write_text("SYNTHETIC=value", encoding="utf-8")
    (repository / "signing.key").write_text("synthetic", encoding="utf-8")
    (repository / "runtime.sqlite3-wal").write_bytes(b"synthetic")
    findings = audit_public_repository(repository)
    assert len(findings) == 3
    assert {finding.rule for finding in findings} == {"prohibited_private_artifact"}


def test_backup_restore_and_export(context_factory: Any) -> None:
    context = context_factory()
    operations = OperationsService(context)
    backup = operations.backup()
    restored = operations.restore(
        Path(backup["backup_path"]), context.storage.root / "restore-target"
    )
    assert restored["sha256"] == backup["sha256"]
    export = operations.export_json()
    assert export.is_file()
    assert context.storage.require_private(export) == export.resolve()


def test_restore_rejects_existing_target(context_factory: Any) -> None:
    context = context_factory()
    operations = OperationsService(context)
    backup = operations.backup()
    target = context.storage.root / "existing"
    target.mkdir()
    (target / "opportunityos.sqlite3").write_bytes(b"occupied")
    with pytest.raises(ValueError, match="empty"):
        operations.restore(Path(backup["backup_path"]), target)


def test_context_init_is_idempotent(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    first = ApplicationContext.create(
        repository, data_dir=tmp_path / "private", config_dir=tmp_path / "config"
    )
    second = ApplicationContext.create(
        repository, data_dir=tmp_path / "private", config_dir=tmp_path / "config"
    )
    assert first.database.integrity_check() == second.database.integrity_check() == "ok"

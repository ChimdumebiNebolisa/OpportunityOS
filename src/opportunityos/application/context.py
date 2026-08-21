"""Composition root for the local application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opportunityos.config.settings import Settings, load_settings
from opportunityos.infrastructure.database import Database
from opportunityos.infrastructure.storage import PrivateStorage


@dataclass(frozen=True)
class ApplicationContext:
    settings: Settings
    storage: PrivateStorage
    database: Database

    @classmethod
    def create(
        cls,
        repository_root: Path | None = None,
        *,
        data_dir: Path | None = None,
        config_dir: Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> ApplicationContext:
        settings = load_settings(
            repository_root,
            data_dir=data_dir,
            config_dir=config_dir,
            overrides=overrides,
        )
        storage = PrivateStorage(settings)
        storage.initialize()
        database = Database(storage.database_path)
        migration_root = settings.repository_root
        if not (migration_root / "alembic.ini").is_file():
            migration_root = Path(__file__).resolve().parents[3]
        database.migrate(migration_root, storage.category_path("backups"))
        return cls(settings, storage, database)

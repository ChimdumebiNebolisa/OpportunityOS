from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from opportunityos.infrastructure.database import Base


def test_migration_from_empty_database(tmp_path: Path) -> None:
    database = tmp_path / "migration.sqlite3"
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables


def test_migration_downgrade_and_reupgrade(tmp_path: Path) -> None:
    database = tmp_path / "roundtrip.sqlite3"
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert (
        "source_records"
        in inspect(create_engine(f"sqlite:///{database.as_posix()}")).get_table_names()
    )

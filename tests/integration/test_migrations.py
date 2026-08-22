from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert, inspect, select, text

from opportunityos.infrastructure.database import AutomationControlRow, Base, SourceRow


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


def test_v2_migration_preserves_v1_record(tmp_path: Path) -> None:
    database = tmp_path / "v1-preservation.sqlite3"
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0001_initial")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    for table_name in (
        "automation_controls",
        "strategy_snapshots",
        "brief_runs",
        "health_states",
        "follow_up_states",
        "preparation_policy_records",
        "reminder_states",
    ):
        Base.metadata.tables[table_name].drop(engine, checkfirst=True)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            insert(SourceRow).values(
                id="v1-source",
                source_type="user_statement",
                source_locator="synthetic-v1-source",
                display_name="Synthetic V1 source",
                official_status="unknown",
                retrieved_at=now,
                published_at=None,
                content_hash="a" * 64,
                mime_type="text/plain",
                local_artifact_path=None,
                trust_class="user",
                metadata_json={},
                created_at=now,
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        preserved = connection.scalar(select(SourceRow.id).where(SourceRow.id == "v1-source"))
    assert preserved == "v1-source"
    assert "reminder_states" in inspect(engine).get_table_names()


def test_v3_migration_from_v2_shape_preserves_behavioral_state(tmp_path: Path) -> None:
    database = tmp_path / "v2-preservation.sqlite3"
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0002_v2_behavior")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            insert(AutomationControlRow).values(
                key="scouts",
                enabled=True,
                reason="synthetic v2 state",
                updated_at=datetime.now(UTC),
            )
        )
    for table_name in (
        "source_registry",
        "search_branches",
        "query_strategies",
        "discovery_runs",
    ):
        Base.metadata.tables[table_name].drop(engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE scout_runs RENAME TO scout_runs_v3"))
        connection.execute(
            text(
                """
                CREATE TABLE scout_runs (
                    id VARCHAR(36) PRIMARY KEY,
                    category VARCHAR(100) NOT NULL,
                    query_plan JSON NOT NULL,
                    budget JSON NOT NULL,
                    counters JSON NOT NULL,
                    sources_considered JSON NOT NULL,
                    candidates JSON NOT NULL,
                    strong_candidates JSON NOT NULL,
                    candidate_versions JSON NOT NULL,
                    delivered_versions JSON NOT NULL,
                    errors JSON NOT NULL,
                    started_at DATETIME NOT NULL,
                    ended_at DATETIME,
                    delivery_result VARCHAR(50),
                    status VARCHAR(30) NOT NULL,
                    catch_up_from DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO scout_runs
                SELECT id, category, query_plan, budget, counters, sources_considered,
                       candidates, strong_candidates, candidate_versions, delivered_versions,
                       errors, started_at, ended_at, delivery_result, status, catch_up_from
                FROM scout_runs_v3
                """
            )
        )
        connection.execute(text("DROP TABLE scout_runs_v3"))

    command.upgrade(config, "head")
    with engine.connect() as connection:
        preserved = connection.scalar(
            select(AutomationControlRow.key).where(AutomationControlRow.key == "scouts")
        )
    tables = set(inspect(engine).get_table_names())
    assert preserved == "scouts"
    assert {"discovery_runs", "query_strategies", "search_branches", "source_registry"} <= tables
    columns = {column["name"] for column in inspect(engine).get_columns("scout_runs")}
    assert {"discovery_run_id", "branch_id"} <= columns

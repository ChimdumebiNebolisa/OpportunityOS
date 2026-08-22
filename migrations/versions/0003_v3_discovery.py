"""Add V3 stateful discovery strategy and coverage tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from opportunityos.infrastructure.database import (
    DiscoveryRunRow,
    QueryStrategyRow,
    SearchBranchRow,
    SourceRegistryRow,
)

revision = "0003_v3_discovery"
down_revision = "0002_v2_behavior"
branch_labels = None
depends_on = None

_TABLES = (DiscoveryRunRow, QueryStrategyRow, SearchBranchRow, SourceRegistryRow)


def upgrade() -> None:
    bind = op.get_bind()
    for model in _TABLES:
        model.__table__.create(bind, checkfirst=True)
    columns = {column["name"] for column in inspect(bind).get_columns("scout_runs")}
    if not {"discovery_run_id", "branch_id"} <= columns:
        with op.batch_alter_table("scout_runs") as batch:
            if "discovery_run_id" not in columns:
                batch.add_column(sa.Column("discovery_run_id", sa.String(36), nullable=True))
            if "branch_id" not in columns:
                batch.add_column(sa.Column("branch_id", sa.String(36), nullable=True))
            batch.create_index("ix_scout_runs_discovery_run_id", ["discovery_run_id"])
            batch.create_index("ix_scout_runs_branch_id", ["branch_id"])
            batch.create_foreign_key(
                "fk_scout_runs_discovery_run_id", "discovery_runs", ["discovery_run_id"], ["id"]
            )
            batch.create_foreign_key(
                "fk_scout_runs_branch_id", "search_branches", ["branch_id"], ["id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("scout_runs")}
    indexes = {index["name"] for index in inspect(bind).get_indexes("scout_runs")}
    with op.batch_alter_table("scout_runs") as batch:
        for index_name in (
            "ix_scout_runs_branch_id",
            "ix_scout_runs_discovery_run_id",
        ):
            if index_name in indexes:
                batch.drop_index(index_name)
        if "branch_id" in columns:
            batch.drop_column("branch_id")
        if "discovery_run_id" in columns:
            batch.drop_column("discovery_run_id")
    for model in reversed(_TABLES):
        model.__table__.drop(bind, checkfirst=True)

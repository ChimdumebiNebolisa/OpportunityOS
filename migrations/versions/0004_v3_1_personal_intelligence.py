"""Add V3.1 personal-intelligence run, source, and reconciliation state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from opportunityos.infrastructure.database import (
    PersonalSourceSyncStateRow,
    ProfileIntelligenceRunRow,
    ReconciliationBatchRow,
)

revision = "0004_v3_1_personal_intelligence"
down_revision = "0003_v3_discovery"
branch_labels = None
depends_on = None

_TABLES = (
    ProfileIntelligenceRunRow,
    PersonalSourceSyncStateRow,
    ReconciliationBatchRow,
)


def upgrade() -> None:
    bind = op.get_bind()
    for model in _TABLES:
        model.__table__.create(bind, checkfirst=True)
    columns = {column["name"] for column in inspect(bind).get_columns("observations")}
    additions = {
        "source_event_at": sa.Column("source_event_at", sa.DateTime(timezone=True)),
        "subject_identity": sa.Column(
            "subject_identity", sa.String(100), nullable=False, server_default="user"
        ),
        "content_fingerprint": sa.Column("content_fingerprint", sa.String(64)),
    }
    missing = [name for name in additions if name not in columns]
    if missing:
        with op.batch_alter_table("observations") as batch:
            for name in missing:
                batch.add_column(additions[name])
            if "content_fingerprint" in missing:
                batch.create_index("ix_observations_content_fingerprint", ["content_fingerprint"])
    with op.batch_alter_table("observations") as batch:
        batch.alter_column("assertion_kind", type_=sa.String(100))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("observations")}
    indexes = {index["name"] for index in inspect(bind).get_indexes("observations")}
    with op.batch_alter_table("observations") as batch:
        if "ix_observations_content_fingerprint" in indexes:
            batch.drop_index("ix_observations_content_fingerprint")
        for name in ("content_fingerprint", "subject_identity", "source_event_at"):
            if name in columns:
                batch.drop_column(name)
        batch.alter_column("assertion_kind", type_=sa.String(20))
    for model in reversed(_TABLES):
        model.__table__.drop(bind, checkfirst=True)

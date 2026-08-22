"""Add V2 behavioral policy and operational state."""

from alembic import op

from opportunityos.infrastructure.database import (
    AutomationControlRow,
    BriefRunRow,
    FollowUpStateRow,
    HealthStateRow,
    PreparationPolicyRow,
    ReminderStateRow,
    StrategySnapshotRow,
)

revision = "0002_v2_behavior"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_TABLES = (
    ReminderStateRow,
    PreparationPolicyRow,
    FollowUpStateRow,
    HealthStateRow,
    BriefRunRow,
    StrategySnapshotRow,
    AutomationControlRow,
)


def upgrade() -> None:
    for model in _TABLES:
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for model in reversed(_TABLES):
        model.__table__.drop(op.get_bind(), checkfirst=True)

"""Store execution and cancellation deadlines for training jobs."""

import sqlalchemy as sa

from alembic import op

revision = "0007_training_deadlines"
down_revision = "0006_training_leases"


def upgrade() -> None:
    op.add_column("training_jobs", sa.Column("execution_deadline_at", sa.DateTime(timezone=True)))
    op.add_column("training_jobs", sa.Column("cancel_deadline_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("training_jobs", "cancel_deadline_at")
    op.drop_column("training_jobs", "execution_deadline_at")

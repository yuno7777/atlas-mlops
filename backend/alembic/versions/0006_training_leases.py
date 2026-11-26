"""Record execution attempts and leases for training workers."""

import sqlalchemy as sa

from alembic import op

revision = "0006_training_leases"
down_revision = "0005_training_dispatch"


def upgrade() -> None:
    op.add_column("training_jobs", sa.Column("execution_token", sa.String(36)))
    op.add_column("training_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "training_jobs", sa.Column("execution_attempt", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index("ix_training_jobs_lease", "training_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_training_jobs_lease", table_name="training_jobs")
    op.drop_column("training_jobs", "execution_attempt")
    op.drop_column("training_jobs", "lease_expires_at")
    op.drop_column("training_jobs", "execution_token")

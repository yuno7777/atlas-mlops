"""Persist optional training submission idempotency keys."""

import sqlalchemy as sa

from alembic import op

revision = "0004_training_idempotency"
down_revision = "0003_modelops"


def upgrade() -> None:
    op.add_column("training_jobs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index(
        "uq_training_jobs_idempotency",
        "training_jobs",
        ["project_id", "created_by", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_training_jobs_idempotency", table_name="training_jobs")
    op.drop_column("training_jobs", "idempotency_key")

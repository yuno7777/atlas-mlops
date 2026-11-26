"""Persist training dispatch in the same transaction as job submission."""

import sqlalchemy as sa

from alembic import op

revision = "0005_training_dispatch"
down_revision = "0004_training_idempotency"


def upgrade() -> None:
    outbox = op.create_table(
        "training_dispatch",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_training_dispatch_due", "training_dispatch", ["available_at", "job_id"])
    jobs = sa.table("training_jobs", sa.column("id"), sa.column("status"), sa.column("created_at"))
    op.execute(
        outbox.insert().from_select(
            ["job_id", "available_at", "attempts"],
            sa.select(jobs.c.id, jobs.c.created_at, sa.literal(0)).where(jobs.c.status == "queued"),
        )
    )


def downgrade() -> None:
    op.drop_index("ix_training_dispatch_due", table_name="training_dispatch")
    op.drop_table("training_dispatch")

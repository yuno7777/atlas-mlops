"""release automation, fairness-ready workflow tracking, and reusable pipelines

Revision ID: 0003_modelops
Revises: 0002_platform
Create Date: 2026-11-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_modelops"
down_revision: str | None = "0002_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deployment_rollouts",
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("traffic_steps", sa.JSON(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("last_evaluation", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("step_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_version_id"], ["model_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployment_rollouts")),
    )
    op.create_index(
        "ix_deployment_rollouts_deployment_status",
        "deployment_rollouts",
        ["deployment_id", "status"],
    )
    op.create_index(
        "uq_deployment_rollouts_active",
        "deployment_rollouts",
        ["deployment_id"],
        unique=True,
        sqlite_where=sa.text("status = 'running'"),
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=False),
        sa.Column("training_job_id", sa.String(length=36), nullable=True),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("step_states", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["parent_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["training_job_id"], ["training_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(
        "ix_workflow_runs_project_created", "workflow_runs", ["project_id", "created_at"]
    )
    op.create_index("ix_workflow_runs_status_schedule", "workflow_runs", ["status", "scheduled_at"])
    op.create_index(
        "ix_workflow_runs_cache", "workflow_runs", ["project_id", "cache_key", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_cache", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_status_schedule", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_project_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("uq_deployment_rollouts_active", table_name="deployment_rollouts")
    op.drop_index("ix_deployment_rollouts_deployment_status", table_name="deployment_rollouts")
    op.drop_table("deployment_rollouts")

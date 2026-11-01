"""platform collaboration, batch, alerting and champion/challenger features

Revision ID: 0002_platform
Revises: 0001_initial
Create Date: 2026-11-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_platform"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_invites",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["accepted_by"],
            ["users.id"],
            name=op.f("fk_workspace_invites_accepted_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_workspace_invites_invited_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_invites_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_invites")),
        sa.UniqueConstraint("token_hash", name="uq_workspace_invite_token"),
    )
    with op.batch_alter_table("workspace_invites", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_workspace_invites_email"), ["email"], unique=False
        )
        batch_op.create_index(
            "ix_workspace_invites_workspace", ["workspace_id", "created_at"], unique=False
        )

    op.create_table(
        "alert_channels",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target_url", sa.String(length=1000), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=True),
        sa.Column("min_status", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_alert_channels_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_alert_channels_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_channels")),
    )
    with op.batch_alter_table("alert_channels", schema=None) as batch_op:
        batch_op.create_index(
            "ix_alert_channels_project", ["project_id", "created_at"], unique=False
        )

    op.create_table(
        "batch_predictions",
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("model_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("result_key", sa.String(length=500), nullable=True),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_batch_predictions_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.id"],
            name=op.f("fk_batch_predictions_deployment_id_deployments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_batch_predictions_model_version_id_model_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batch_predictions")),
    )
    with op.batch_alter_table("batch_predictions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_batch_predictions_deployment", ["deployment_id", "created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_batch_predictions_deployment_id"),
            ["deployment_id"],
            unique=False,
        )

    op.create_table(
        "alert_deliveries",
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("monitoring_result_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["alert_channels.id"],
            name=op.f("fk_alert_deliveries_channel_id_alert_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.id"],
            name=op.f("fk_alert_deliveries_deployment_id_deployments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["monitoring_result_id"],
            ["monitoring_results.id"],
            name=op.f("fk_alert_deliveries_monitoring_result_id_monitoring_results"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_deliveries")),
    )
    with op.batch_alter_table("alert_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_alert_deliveries_channel", ["channel_id", "created_at"], unique=False
        )

    with op.batch_alter_table("deployments", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("challenger_model_version_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "challenger_traffic_percent",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_foreign_key(
            op.f("fk_deployments_challenger_model_version_id_model_versions"),
            "model_versions",
            ["challenger_model_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("prediction_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "variant",
                sa.String(length=16),
                nullable=False,
                server_default="champion",
            )
        )
        batch_op.create_index(
            "ix_prediction_logs_deployment_variant",
            ["deployment_id", "variant", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("prediction_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_prediction_logs_deployment_variant")
        batch_op.drop_column("variant")

    with op.batch_alter_table("deployments", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_deployments_challenger_model_version_id_model_versions"),
            type_="foreignkey",
        )
        batch_op.drop_column("challenger_traffic_percent")
        batch_op.drop_column("challenger_model_version_id")

    with op.batch_alter_table("alert_deliveries", schema=None) as batch_op:
        batch_op.drop_index("ix_alert_deliveries_channel")
    op.drop_table("alert_deliveries")

    with op.batch_alter_table("batch_predictions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_batch_predictions_deployment_id"))
        batch_op.drop_index("ix_batch_predictions_deployment")
    op.drop_table("batch_predictions")

    with op.batch_alter_table("alert_channels", schema=None) as batch_op:
        batch_op.drop_index("ix_alert_channels_project")
    op.drop_table("alert_channels")

    with op.batch_alter_table("workspace_invites", schema=None) as batch_op:
        batch_op.drop_index("ix_workspace_invites_workspace")
        batch_op.drop_index(batch_op.f("ix_workspace_invites_email"))
    op.drop_table("workspace_invites")

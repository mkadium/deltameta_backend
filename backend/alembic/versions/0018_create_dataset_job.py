"""
Phase 3 — CreateDatasetJob tracking table.

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    op.create_table(
        "create_dataset_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggered_by",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_config", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pipeline_type", sa.String(50), nullable=False, server_default="ingest"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("external_job_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_create_dataset_jobs_org_id",
        "create_dataset_jobs",
        ["org_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_create_dataset_jobs_status",
        "create_dataset_jobs",
        ["status"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_create_dataset_jobs_triggered_by",
        "create_dataset_jobs",
        ["triggered_by"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_create_dataset_jobs_triggered_by", table_name="create_dataset_jobs", schema=SCHEMA)
    op.drop_index("ix_create_dataset_jobs_status", table_name="create_dataset_jobs", schema=SCHEMA)
    op.drop_index("ix_create_dataset_jobs_org_id", table_name="create_dataset_jobs", schema=SCHEMA)
    op.drop_table("create_dataset_jobs", schema=SCHEMA)


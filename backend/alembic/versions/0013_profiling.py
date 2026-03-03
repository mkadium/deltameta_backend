"""Phase 2 Module 2 — Data Profiling tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade():
    # ------------------------------------------------------------------ #
    # data_asset_profiles
    # ------------------------------------------------------------------ #
    op.create_table(
        "data_asset_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("profile_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_dap_asset_id", "data_asset_profiles", ["asset_id"], schema=SCHEMA)
    op.create_index("ix_dap_org_id", "data_asset_profiles", ["org_id"], schema=SCHEMA)
    op.create_index("ix_dap_status", "data_asset_profiles", ["status"], schema=SCHEMA)

    # ------------------------------------------------------------------ #
    # column_profiles
    # ------------------------------------------------------------------ #
    op.create_table(
        "column_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_asset_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_asset_columns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(100), nullable=True),
        sa.Column("null_count", sa.Integer, nullable=True),
        sa.Column("null_pct", sa.Float, nullable=True),
        sa.Column("distinct_count", sa.Integer, nullable=True),
        sa.Column("min_val", sa.String(512), nullable=True),
        sa.Column("max_val", sa.String(512), nullable=True),
        sa.Column("mean_val", sa.Float, nullable=True),
        sa.Column("stddev_val", sa.Float, nullable=True),
        sa.Column("top_values", JSONB, nullable=False, server_default="[]"),
        sa.Column("histogram", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_cp_profile_id", "column_profiles", ["profile_id"], schema=SCHEMA)
    op.create_index("ix_cp_asset_id", "column_profiles", ["asset_id"], schema=SCHEMA)
    op.create_index("ix_cp_column_id", "column_profiles", ["column_id"], schema=SCHEMA)


def downgrade():
    op.drop_table("column_profiles", schema=SCHEMA)
    op.drop_table("data_asset_profiles", schema=SCHEMA)

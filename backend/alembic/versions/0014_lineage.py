"""Phase 2 Module 3 — Data Lineage table

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade():
    op.create_table(
        "lineage_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edge_type", sa.String(50), nullable=False, server_default="direct"),
        sa.Column("transformation", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    # Prevent duplicate edges (same source → target within the same org)
    op.create_unique_constraint(
        "uq_lineage_edge_source_target_org",
        "lineage_edges",
        ["org_id", "source_asset_id", "target_asset_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_le_org_id", "lineage_edges", ["org_id"], schema=SCHEMA)
    op.create_index("ix_le_source_asset_id", "lineage_edges", ["source_asset_id"], schema=SCHEMA)
    op.create_index("ix_le_target_asset_id", "lineage_edges", ["target_asset_id"], schema=SCHEMA)
    op.create_index("ix_le_edge_type", "lineage_edges", ["edge_type"], schema=SCHEMA)


def downgrade():
    op.drop_table("lineage_edges", schema=SCHEMA)

"""Pre-Phase2 Fix 2: Add bots table + storage_type to storage_config

Revision ID: 0012
Revises: 0011
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    # ── storage_config: add storage_type column ──────────────────────────────
    op.add_column(
        "storage_config",
        sa.Column("storage_type", sa.String(50), nullable=False, server_default="minio"),
        schema=SCHEMA,
    )

    # ── bots table ────────────────────────────────────────────────────────────
    op.create_table(
        "bots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("bot_type", sa.String(50), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="self"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("trigger_mode", sa.String(20), nullable=False, server_default="on_demand"),
        sa.Column("cron_expr", sa.String(100), nullable=True),
        sa.Column("service_endpoint_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.service_endpoints.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(20), nullable=True),
        sa.Column("last_run_message", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_bots_org_id", "bots", ["org_id"], schema=SCHEMA)
    op.create_index("ix_bots_bot_type", "bots", ["bot_type"], schema=SCHEMA)
    op.create_index("ix_bots_is_enabled", "bots", ["is_enabled"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_bots_is_enabled", table_name="bots", schema=SCHEMA)
    op.drop_index("ix_bots_bot_type", table_name="bots", schema=SCHEMA)
    op.drop_index("ix_bots_org_id", table_name="bots", schema=SCHEMA)
    op.drop_table("bots", schema=SCHEMA)
    op.drop_column("storage_config", "storage_type", schema=SCHEMA)

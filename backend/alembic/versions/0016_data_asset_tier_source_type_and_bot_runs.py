"""Phase 2 gap fixes — DataAsset.tier + DataAsset.source_type + BotRun table

Revision ID: 0016
Revises: 0015
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    # ── DataAsset: add tier + source_type ─────────────────────────────────────
    op.add_column(
        "data_assets",
        sa.Column("tier", sa.String(10), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "data_assets",
        sa.Column(
            "source_type",
            sa.String(50),
            nullable=False,
            server_default="manual",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_data_assets_source_type",
        "data_assets",
        ["source_type"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_data_assets_tier",
        "data_assets",
        ["tier"],
        schema=SCHEMA,
    )

    # ── BotRun table ──────────────────────────────────────────────────────────
    op.create_table(
        "bot_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bot_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("trigger_source", sa.String(50), nullable=False, server_default="on_demand"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("output", JSONB, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_bot_runs_bot_id", "bot_runs", ["bot_id"], schema=SCHEMA)
    op.create_index("ix_bot_runs_org_id", "bot_runs", ["org_id"], schema=SCHEMA)
    op.create_index("ix_bot_runs_status", "bot_runs", ["status"], schema=SCHEMA)
    op.create_index("ix_bot_runs_created_at", "bot_runs", ["created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("bot_runs", schema=SCHEMA)
    op.drop_index("ix_data_assets_tier", table_name="data_assets", schema=SCHEMA)
    op.drop_index("ix_data_assets_source_type", table_name="data_assets", schema=SCHEMA)
    op.drop_column("data_assets", "tier", schema=SCHEMA)
    op.drop_column("data_assets", "source_type", schema=SCHEMA)

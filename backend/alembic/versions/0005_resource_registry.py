"""Add resource_groups and resource_definitions tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "deltameta"

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- resource_groups ---
    op.create_table(
        "resource_groups",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_resource_group_slug"),
        schema=SCHEMA,
    )
    op.create_index("ix_resource_groups_slug", "resource_groups", ["slug"], schema=SCHEMA)

    # --- resource_definitions ---
    op.create_table(
        "resource_definitions",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_id", UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(512), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("operations", JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_static", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("setting_node_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_resource_definition_key"),
        sa.ForeignKeyConstraint(
            ["group_id"], [f"{SCHEMA}.resource_groups.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["setting_node_id"], [f"{SCHEMA}.setting_nodes.id"], ondelete="SET NULL"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_resource_definitions_key", "resource_definitions", ["key"], schema=SCHEMA)
    op.create_index("ix_resource_definitions_group_id", "resource_definitions", ["group_id"], schema=SCHEMA)
    op.create_index("ix_resource_definitions_setting_node_id", "resource_definitions", ["setting_node_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_resource_definitions_setting_node_id", table_name="resource_definitions", schema=SCHEMA)
    op.drop_index("ix_resource_definitions_group_id", table_name="resource_definitions", schema=SCHEMA)
    op.drop_index("ix_resource_definitions_key", table_name="resource_definitions", schema=SCHEMA)
    op.drop_table("resource_definitions", schema=SCHEMA)

    op.drop_index("ix_resource_groups_slug", table_name="resource_groups", schema=SCHEMA)
    op.drop_table("resource_groups", schema=SCHEMA)

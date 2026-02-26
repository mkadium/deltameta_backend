"""Add setting_nodes, org_setting_overrides, user_setting_overrides, setting_policies

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "deltameta"

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # node_type stored as VARCHAR(16) — values: 'category', 'leaf'

    # --- setting_nodes: N-level self-referencing tree ---
    op.create_table(
        "setting_nodes",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("display_label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.Column(
            "node_type",
            sa.String(16),   # store as string; check constraint enforces values
            nullable=False,
            server_default="category",
        ),
        sa.Column("nav_url", sa.String(512), nullable=True),
        sa.Column("slug_path", sa.String(512), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["parent_id"], [f"{SCHEMA}.setting_nodes.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("parent_id", "slug", name="uq_setting_node_parent_slug"),
        schema=SCHEMA,
    )
    op.create_index("ix_setting_nodes_parent_id", "setting_nodes", ["parent_id"], schema=SCHEMA)
    op.create_index("ix_setting_nodes_slug", "setting_nodes", ["slug"], schema=SCHEMA)

    # --- org_setting_overrides ---
    op.create_table(
        "org_setting_overrides",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", JSONB(), nullable=True, server_default="{}"),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "node_id", name="uq_org_setting_override"),
        sa.ForeignKeyConstraint(
            ["org_id"], [f"{SCHEMA}.organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], [f"{SCHEMA}.setting_nodes.id"], ondelete="CASCADE"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_org_setting_overrides_org_id", "org_setting_overrides", ["org_id"], schema=SCHEMA)
    op.create_index("ix_org_setting_overrides_node_id", "org_setting_overrides", ["node_id"], schema=SCHEMA)

    # --- user_setting_overrides ---
    op.create_table(
        "user_setting_overrides",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "node_id", name="uq_user_setting_override"),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], [f"{SCHEMA}.setting_nodes.id"], ondelete="CASCADE"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_user_setting_overrides_user_id", "user_setting_overrides", ["user_id"], schema=SCHEMA)
    op.create_index("ix_user_setting_overrides_node_id", "user_setting_overrides", ["node_id"], schema=SCHEMA)

    # --- setting_policies — link ABAC policy to a node ---
    op.create_table(
        "setting_policies",
        sa.Column("id", UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "policy_id", name="uq_setting_policy"),
        sa.ForeignKeyConstraint(
            ["node_id"], [f"{SCHEMA}.setting_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"], [f"{SCHEMA}.policies.id"], ondelete="CASCADE"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_setting_policies_node_id", "setting_policies", ["node_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_setting_policies_node_id", table_name="setting_policies", schema=SCHEMA)
    op.drop_table("setting_policies", schema=SCHEMA)

    op.drop_index("ix_user_setting_overrides_node_id", table_name="user_setting_overrides", schema=SCHEMA)
    op.drop_index("ix_user_setting_overrides_user_id", table_name="user_setting_overrides", schema=SCHEMA)
    op.drop_table("user_setting_overrides", schema=SCHEMA)

    op.drop_index("ix_org_setting_overrides_node_id", table_name="org_setting_overrides", schema=SCHEMA)
    op.drop_index("ix_org_setting_overrides_org_id", table_name="org_setting_overrides", schema=SCHEMA)
    op.drop_table("org_setting_overrides", schema=SCHEMA)

    op.drop_index("ix_setting_nodes_slug", table_name="setting_nodes", schema=SCHEMA)
    op.drop_index("ix_setting_nodes_parent_id", table_name="setting_nodes", schema=SCHEMA)
    op.drop_table("setting_nodes", schema=SCHEMA)

"""Add nav_items and related tables with seed data

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "deltameta"

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- nav_items ---
    op.create_table(
        "nav_items",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.Column("nav_url", sa.String(512), nullable=True),
        sa.Column("slug_path", sa.String(512), nullable=True),
        sa.Column("resource_key", sa.String(128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", JSONB(), nullable=True, server_default="{}"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["parent_id"], [f"{SCHEMA}.nav_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("parent_id", "slug", name="uq_nav_item_parent_slug"),
        schema=SCHEMA,
    )
    op.create_index("ix_nav_items_parent_id", "nav_items", ["parent_id"], schema=SCHEMA)
    op.create_index("ix_nav_items_slug", "nav_items", ["slug"], schema=SCHEMA)
    op.create_index("ix_nav_items_resource_key", "nav_items", ["resource_key"], schema=SCHEMA)

    # --- nav_item_org_overrides ---
    op.create_table(
        "nav_item_org_overrides",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", JSONB(), nullable=True, server_default="{}"),
        sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "node_id", name="uq_nav_item_org_override"),
        sa.ForeignKeyConstraint(["org_id"], [f"{SCHEMA}.organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], [f"{SCHEMA}.nav_items.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_index("ix_nav_item_org_overrides_org_id", "nav_item_org_overrides", ["org_id"], schema=SCHEMA)
    op.create_index("ix_nav_item_org_overrides_node_id", "nav_item_org_overrides", ["node_id"], schema=SCHEMA)

    # --- nav_item_user_overrides ---
    op.create_table(
        "nav_item_user_overrides",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "node_id", name="uq_nav_item_user_override"),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], [f"{SCHEMA}.nav_items.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_index("ix_nav_item_user_overrides_user_id", "nav_item_user_overrides", ["user_id"], schema=SCHEMA)
    op.create_index("ix_nav_item_user_overrides_node_id", "nav_item_user_overrides", ["node_id"], schema=SCHEMA)

    # --- nav_item_policies ---
    op.create_table(
        "nav_item_policies",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", "policy_id", name="uq_nav_item_policy"),
        sa.ForeignKeyConstraint(["node_id"], [f"{SCHEMA}.nav_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], [f"{SCHEMA}.policies.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_index("ix_nav_item_policies_node_id", "nav_item_policies", ["node_id"], schema=SCHEMA)

    # --- Seed initial nav structure ---
    # Insert roots first (parent_id NULL)
    op.execute(
        sa.text("""
            INSERT INTO deltameta.nav_items (id, parent_id, slug, display_name, description, icon, nav_url, slug_path, resource_key, sort_order)
            VALUES
                ('a1000000-0000-0000-0000-000000000001', NULL, 'explore', 'Explore', 'Explore data assets', 'explore', '/explore', 'explore', 'explore', 1),
                ('a1000000-0000-0000-0000-000000000002', NULL, 'lineage', 'Lineage', 'Data lineage and lineage graphs', 'lineage', '/lineage', 'lineage', 'lineage', 2),
                ('a1000000-0000-0000-0000-000000000003', NULL, 'observability', 'Observability', 'Observability hub', 'observability', NULL, 'observability', 'observability', 3),
                ('a1000000-0000-0000-0000-000000000004', NULL, 'insights', 'Insights', 'Analytics and insights', 'insights', '/insights', 'insights', 'insights', 4),
                ('a1000000-0000-0000-0000-000000000005', NULL, 'domains', 'Domains', 'Data domains management', 'domains', NULL, 'domains', 'domains', 5),
                ('a1000000-0000-0000-0000-000000000006', NULL, 'govern', 'Govern', 'Governance hub', 'govern', NULL, 'govern', 'govern', 6)
        """)
    )
    # Observability children
    op.execute(
        sa.text("""
            INSERT INTO deltameta.nav_items (id, parent_id, slug, display_name, description, icon, nav_url, slug_path, resource_key, sort_order)
            VALUES
                ('a2000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000003', 'data-quality', 'Data Quality', 'Data quality metrics and rules', 'data-quality', '/observability/data-quality', 'observability.data_quality', 'data_quality', 1),
                ('a2000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000003', 'incidents', 'Incidents', 'Data incidents tracking', 'incidents', '/observability/incidents', 'observability.incidents', 'incidents', 2),
                ('a2000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000003', 'alerts', 'Alerts', 'Data quality and monitoring alerts', 'alerts', '/observability/alerts', 'observability.alerts', 'alerts', 3)
        """)
    )
    # Domains children
    op.execute(
        sa.text("""
            INSERT INTO deltameta.nav_items (id, parent_id, slug, display_name, description, icon, nav_url, slug_path, resource_key, sort_order)
            VALUES
                ('a3000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000005', 'domains-list', 'Domains', 'Data domains list', 'domain', '/domains', 'domains.domains', 'domains', 1),
                ('a3000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000005', 'data-products', 'Data Products', 'Data products catalog', 'data-product', '/domains/data-products', 'domains.data_products', 'data_products', 2)
        """)
    )
    # Govern children
    op.execute(
        sa.text("""
            INSERT INTO deltameta.nav_items (id, parent_id, slug, display_name, description, icon, nav_url, slug_path, resource_key, sort_order)
            VALUES
                ('a4000000-0000-0000-0000-000000000001', 'a1000000-0000-0000-0000-000000000006', 'glossary', 'Glossary', 'Business glossary', 'glossary', '/govern/glossary', 'govern.glossary', 'glossary', 1),
                ('a4000000-0000-0000-0000-000000000002', 'a1000000-0000-0000-0000-000000000006', 'classification', 'Classification', 'Data classification and tags', 'classification', '/govern/classification', 'govern.classification', 'classification', 2),
                ('a4000000-0000-0000-0000-000000000003', 'a1000000-0000-0000-0000-000000000006', 'metrics', 'Metrics', 'Business and data metrics', 'metrics', '/govern/metrics', 'govern.metrics', 'metrics', 3)
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_nav_item_policies_node_id", table_name="nav_item_policies", schema=SCHEMA)
    op.drop_table("nav_item_policies", schema=SCHEMA)

    op.drop_index("ix_nav_item_user_overrides_node_id", table_name="nav_item_user_overrides", schema=SCHEMA)
    op.drop_index("ix_nav_item_user_overrides_user_id", table_name="nav_item_user_overrides", schema=SCHEMA)
    op.drop_table("nav_item_user_overrides", schema=SCHEMA)

    op.drop_index("ix_nav_item_org_overrides_node_id", table_name="nav_item_org_overrides", schema=SCHEMA)
    op.drop_index("ix_nav_item_org_overrides_org_id", table_name="nav_item_org_overrides", schema=SCHEMA)
    op.drop_table("nav_item_org_overrides", schema=SCHEMA)

    op.drop_index("ix_nav_items_resource_key", table_name="nav_items", schema=SCHEMA)
    op.drop_index("ix_nav_items_slug", table_name="nav_items", schema=SCHEMA)
    op.drop_index("ix_nav_items_parent_id", table_name="nav_items", schema=SCHEMA)
    op.drop_table("nav_items", schema=SCHEMA)

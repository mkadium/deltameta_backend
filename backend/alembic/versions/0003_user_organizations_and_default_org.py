"""Add user_organizations table and default_org_id to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

SCHEMA = "deltameta"

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- user_organizations: many-to-many with metadata ---
    op.create_table(
        "user_organizations",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("is_org_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "org_id", name="uq_user_org"),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], [f"{SCHEMA}.organizations.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_index("ix_user_organizations_user_id", "user_organizations", ["user_id"], schema=SCHEMA)
    op.create_index("ix_user_organizations_org_id", "user_organizations", ["org_id"], schema=SCHEMA)

    # --- users: add default_org_id ---
    op.add_column(
        "users",
        sa.Column("default_org_id", UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_users_default_org_id",
        "users", "organizations",
        ["default_org_id"], ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )

    # --- Backfill: set default_org_id = org_id for all existing users ---
    op.execute(f"UPDATE {SCHEMA}.users SET default_org_id = org_id")

    # --- Backfill: insert existing users into user_organizations as org admins ---
    op.execute(f"""
        INSERT INTO {SCHEMA}.user_organizations (id, user_id, org_id, is_org_admin, is_active, joined_at)
        SELECT gen_random_uuid(), u.id, u.org_id, u.is_admin, true, u.created_at
        FROM {SCHEMA}.users u
        ON CONFLICT (user_id, org_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_constraint("fk_users_default_org_id", "users", schema=SCHEMA, type_="foreignkey")
    op.drop_column("users", "default_org_id", schema=SCHEMA)
    op.drop_index("ix_user_organizations_org_id", table_name="user_organizations", schema=SCHEMA)
    op.drop_index("ix_user_organizations_user_id", table_name="user_organizations", schema=SCHEMA)
    op.drop_table("user_organizations", schema=SCHEMA)

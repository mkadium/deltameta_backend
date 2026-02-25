"""Add domain_type/is_active to domains; contact_email/owner_id to organizations; notify_on_update to subscriptions; resource_id type change

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

SCHEMA = "deltameta"

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- organizations: add contact_email and owner_id ---
    op.add_column(
        "organizations",
        sa.Column("contact_email", sa.String(255), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "organizations",
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )

    # --- domains: add domain_type and is_active ---
    op.add_column(
        "domains",
        sa.Column("domain_type", sa.String(100), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "domains",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema=SCHEMA,
    )

    # --- subscriptions: add notify_on_update; change resource_id to UUID ---
    op.add_column(
        "subscriptions",
        sa.Column("notify_on_update", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        schema=SCHEMA,
    )

    # Change resource_id from String(255) to UUID
    # First drop existing resource_id column then re-add as UUID
    op.drop_column("subscriptions", "resource_id", schema=SCHEMA)
    op.add_column(
        "subscriptions",
        sa.Column("resource_id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        schema=SCHEMA,
    )
    # Remove the server_default after adding (it was only needed for the backfill of zero existing rows)
    op.alter_column("subscriptions", "resource_id", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    # subscriptions
    op.drop_column("subscriptions", "notify_on_update", schema=SCHEMA)
    op.drop_column("subscriptions", "resource_id", schema=SCHEMA)
    op.add_column(
        "subscriptions",
        sa.Column("resource_id", sa.String(255), nullable=False, server_default=""),
        schema=SCHEMA,
    )

    # domains
    op.drop_column("domains", "is_active", schema=SCHEMA)
    op.drop_column("domains", "domain_type", schema=SCHEMA)

    # organizations
    op.drop_column("organizations", "owner_id", schema=SCHEMA)
    op.drop_column("organizations", "contact_email", schema=SCHEMA)

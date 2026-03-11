"""
Phase 3 — OrgStorageIngestConfig table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    op.create_table(
        "org_storage_ingest_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "storage_config_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.storage_config.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bucket", sa.String(255), nullable=False),
        sa.Column("prefix", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )

    op.create_unique_constraint(
        "uq_org_storage_ingest_config_org_id",
        "org_storage_ingest_config",
        ["org_id"],
        schema=SCHEMA,
    )

    op.create_index(
        "ix_org_storage_ingest_config_org_id",
        "org_storage_ingest_config",
        ["org_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_storage_ingest_config_org_id",
        table_name="org_storage_ingest_config",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "uq_org_storage_ingest_config_org_id",
        "org_storage_ingest_config",
        schema=SCHEMA,
        type_="unique",
    )
    op.drop_table("org_storage_ingest_config", schema=SCHEMA)


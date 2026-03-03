"""Pre-Phase2 Fix 1: Add detection_patterns + auto_classify to classification_tags

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import text

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    op.add_column(
        "classification_tags",
        sa.Column("detection_patterns", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        schema=SCHEMA,
    )
    op.add_column(
        "classification_tags",
        sa.Column("auto_classify", sa.Boolean, nullable=False, server_default="false"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_classification_tags_auto_classify",
        "classification_tags",
        ["auto_classify"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_classification_tags_auto_classify", table_name="classification_tags", schema=SCHEMA)
    op.drop_column("classification_tags", "auto_classify", schema=SCHEMA)
    op.drop_column("classification_tags", "detection_patterns", schema=SCHEMA)

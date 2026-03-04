"""Phase 3 Module 0 — IngestJob + CatalogView tables

Revision ID: 0017
Revises: 0016
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    # ── IngestJob ──────────────────────────────────────────────────────────────
    op.create_table(
        "ingest_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
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
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column(
            "storage_config_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.storage_config.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bucket", sa.String(255), nullable=True),
        sa.Column("object_key", sa.String(1024), nullable=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("inferred_schema", JSONB, nullable=False, server_default="[]"),
        sa.Column("preview_rows", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "dataset_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_ingest_jobs_org_id", "ingest_jobs", ["org_id"], schema=SCHEMA)
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"], schema=SCHEMA)
    op.create_index("ix_ingest_jobs_triggered_by", "ingest_jobs", ["triggered_by"], schema=SCHEMA)

    # ── CatalogView ────────────────────────────────────────────────────────────
    op.create_table(
        "catalog_views",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.service_endpoints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_schema", sa.String(255), nullable=True),
        sa.Column("source_table", sa.String(255), nullable=True),
        sa.Column("source_object_type", sa.String(50), nullable=False, server_default="table"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),
        sa.Column("glossary_term_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("synonyms", JSONB, nullable=False, server_default="[]"),
        sa.Column("sync_mode", sa.String(20), nullable=False, server_default="on_demand"),
        sa.Column("cron_expr", sa.String(100), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="never"),
        sa.Column("sync_error", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    op.create_index("ix_catalog_views_org_id", "catalog_views", ["org_id"], schema=SCHEMA)
    op.create_index("ix_catalog_views_sync_status", "catalog_views", ["sync_status"], schema=SCHEMA)
    op.create_index("ix_catalog_views_source_connection_id", "catalog_views", ["source_connection_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("catalog_views", schema=SCHEMA)
    op.drop_table("ingest_jobs", schema=SCHEMA)

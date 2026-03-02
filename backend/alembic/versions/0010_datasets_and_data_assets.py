"""Phase 2 Module 1: datasets, data_assets, data_asset_columns,
dataset_owners, dataset_experts, data_asset_owners, data_asset_experts, data_asset_tags

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "deltameta"
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── datasets ──────────────────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.datasets (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            domain_id       UUID REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE SET NULL,
            name            VARCHAR(255) NOT NULL,
            display_name    VARCHAR(255),
            description     TEXT,
            source_type     VARCHAR(100),
            source_url      VARCHAR(512),
            tags            JSONB NOT NULL DEFAULT '[]',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_by      UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_datasets_org_id ON {SCHEMA}.datasets(org_id)"))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_datasets_domain_id ON {SCHEMA}.datasets(domain_id)"))

    # ── data_assets ────────────────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_assets (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id                  UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            dataset_id              UUID NOT NULL REFERENCES {SCHEMA}.datasets(id) ON DELETE CASCADE,
            data_product_id         UUID REFERENCES {SCHEMA}.data_products(id) ON DELETE SET NULL,
            name                    VARCHAR(255) NOT NULL,
            display_name            VARCHAR(255),
            description             TEXT,
            asset_type              VARCHAR(100) NOT NULL DEFAULT 'table',
            fully_qualified_name    VARCHAR(512),
            sensitivity             VARCHAR(50) DEFAULT 'internal',
            row_count               INTEGER,
            size_bytes              INTEGER,
            is_pii                  BOOLEAN NOT NULL DEFAULT FALSE,
            is_active               BOOLEAN NOT NULL DEFAULT TRUE,
            created_by              UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_data_assets_org_id ON {SCHEMA}.data_assets(org_id)"))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_data_assets_dataset_id ON {SCHEMA}.data_assets(dataset_id)"))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_data_assets_data_product_id ON {SCHEMA}.data_assets(data_product_id)"))

    # ── data_asset_columns ────────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_asset_columns (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id            UUID NOT NULL REFERENCES {SCHEMA}.data_assets(id) ON DELETE CASCADE,
            org_id              UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name                VARCHAR(255) NOT NULL,
            display_name        VARCHAR(255),
            description         TEXT,
            data_type           VARCHAR(100) NOT NULL DEFAULT 'varchar',
            ordinal_position    INTEGER NOT NULL DEFAULT 0,
            is_nullable         BOOLEAN NOT NULL DEFAULT TRUE,
            is_primary_key      BOOLEAN NOT NULL DEFAULT FALSE,
            is_foreign_key      BOOLEAN NOT NULL DEFAULT FALSE,
            is_pii              BOOLEAN NOT NULL DEFAULT FALSE,
            sensitivity         VARCHAR(50),
            default_value       VARCHAR(512),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_data_asset_columns_asset_id ON {SCHEMA}.data_asset_columns(asset_id)"))

    # ── M2M: dataset_owners ───────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dataset_owners (
            dataset_id  UUID NOT NULL REFERENCES {SCHEMA}.datasets(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (dataset_id, user_id)
        )
    """))

    # ── M2M: dataset_experts ──────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.dataset_experts (
            dataset_id  UUID NOT NULL REFERENCES {SCHEMA}.datasets(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (dataset_id, user_id)
        )
    """))

    # ── M2M: data_asset_owners ────────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_asset_owners (
            asset_id    UUID NOT NULL REFERENCES {SCHEMA}.data_assets(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (asset_id, user_id)
        )
    """))

    # ── M2M: data_asset_experts ───────────────────────────────────────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_asset_experts (
            asset_id    UUID NOT NULL REFERENCES {SCHEMA}.data_assets(id) ON DELETE CASCADE,
            user_id     UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (asset_id, user_id)
        )
    """))

    # ── M2M: data_asset_tags (links ClassificationTag → DataAsset) ────────────
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_asset_tags (
            asset_id    UUID NOT NULL REFERENCES {SCHEMA}.data_assets(id) ON DELETE CASCADE,
            tag_id      UUID NOT NULL REFERENCES {SCHEMA}.classification_tags(id) ON DELETE CASCADE,
            PRIMARY KEY (asset_id, tag_id)
        )
    """))


def downgrade() -> None:
    conn = op.get_bind()
    for tbl in [
        "data_asset_tags",
        "data_asset_experts",
        "data_asset_owners",
        "dataset_experts",
        "dataset_owners",
        "data_asset_columns",
        "data_assets",
        "datasets",
    ]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.{tbl} CASCADE"))

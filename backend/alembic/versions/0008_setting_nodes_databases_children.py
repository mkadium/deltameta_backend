"""Add postgres and mysql leaf nodes under Services > Databases

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-26

Aligns seed with test_settings expectations: parent=databases returns postgres leaf.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

SCHEMA = "deltameta"

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _esc(s: str) -> str:
    return s.replace("'", "''") if s else ""


def upgrade() -> None:
    conn = op.get_bind()
    # Services > Databases (b2000000-0000-0000-0000-000000000002) — add postgres, mysql
    for uid, slug, label, desc, nav_url in [
        ('b3000000-0000-0000-0000-000000000001', 'postgres', 'PostgreSQL', 'Connect to PostgreSQL database', '/integrations/postgres/config'),
        ('b3000000-0000-0000-0000-000000000002', 'mysql', 'MySQL', 'Connect to MySQL database', '/integrations/mysql/config'),
    ]:
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b2000000-0000-0000-0000-000000000002', '{slug}', '{_esc(label)}', '{_esc(desc)}', 'database', 'leaf', 'settings.services.databases.{slug}', '{nav_url}', 0)
            ON CONFLICT (id) DO NOTHING
        """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM deltameta.setting_nodes WHERE id IN ('b3000000-0000-0000-0000-000000000001', 'b3000000-0000-0000-0000-000000000002')"))

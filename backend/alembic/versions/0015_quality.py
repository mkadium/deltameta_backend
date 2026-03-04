"""Phase 2 Module 4 — Data Quality tables

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade():
    # 1. quality_test_cases
    op.create_table(
        "quality_test_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_asset_columns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("level", sa.String(20), nullable=False, server_default="table"),
        sa.Column("test_type", sa.String(50), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=True),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("glossary_term_ids", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_qtc_org_id", "quality_test_cases", ["org_id"], schema=SCHEMA)
    op.create_index("ix_qtc_asset_id", "quality_test_cases", ["asset_id"], schema=SCHEMA)
    op.create_index("ix_qtc_level", "quality_test_cases", ["level"], schema=SCHEMA)
    op.create_index("ix_qtc_test_type", "quality_test_cases", ["test_type"], schema=SCHEMA)
    op.create_index("ix_qtc_is_active", "quality_test_cases", ["is_active"], schema=SCHEMA)

    # 2. quality_test_suites
    op.create_table(
        "quality_test_suites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("suite_type", sa.String(20), nullable=False, server_default="bundle"),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("test_case_ids", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("owner_ids", JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("has_pipeline", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("trigger_mode", sa.String(20), nullable=False, server_default="on_demand"),
        sa.Column("cron_expr", sa.String(100), nullable=True),
        sa.Column("enable_debug_log", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("raise_on_error", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_qts_org_id", "quality_test_suites", ["org_id"], schema=SCHEMA)
    op.create_index("ix_qts_suite_type", "quality_test_suites", ["suite_type"], schema=SCHEMA)

    # 3. quality_test_runs
    op.create_table(
        "quality_test_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.quality_test_cases.id", ondelete="CASCADE"), nullable=True),
        sa.Column("test_suite_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.quality_test_suites.id", ondelete="CASCADE"), nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result_detail", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_qtr_org_id", "quality_test_runs", ["org_id"], schema=SCHEMA)
    op.create_index("ix_qtr_test_case_id", "quality_test_runs", ["test_case_id"], schema=SCHEMA)
    op.create_index("ix_qtr_test_suite_id", "quality_test_runs", ["test_suite_id"], schema=SCHEMA)
    op.create_index("ix_qtr_status", "quality_test_runs", ["status"], schema=SCHEMA)

    # 4. quality_incidents
    op.create_table(
        "quality_incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_case_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.quality_test_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_run_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.quality_test_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.data_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignee_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("failed_reason", sa.Text, nullable=True),
        sa.Column("aborted_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_qi_org_id", "quality_incidents", ["org_id"], schema=SCHEMA)
    op.create_index("ix_qi_test_case_id", "quality_incidents", ["test_case_id"], schema=SCHEMA)
    op.create_index("ix_qi_asset_id", "quality_incidents", ["asset_id"], schema=SCHEMA)
    op.create_index("ix_qi_status", "quality_incidents", ["status"], schema=SCHEMA)


def downgrade():
    op.drop_table("quality_incidents", schema=SCHEMA)
    op.drop_table("quality_test_runs", schema=SCHEMA)
    op.drop_table("quality_test_suites", schema=SCHEMA)
    op.drop_table("quality_test_cases", schema=SCHEMA)

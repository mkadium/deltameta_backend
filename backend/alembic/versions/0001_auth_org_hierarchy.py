"""Auth & Organization Hierarchy — initial schema + seed

Revision ID: 0001
Revises:
Create Date: 2026-02-25
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "deltameta"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Create schema
    # ------------------------------------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE deltameta.sso_provider_enum AS ENUM (
                'default','google','cognito','azure','ldap','oauth2'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE deltameta.team_type_enum AS ENUM (
                'business_unit','division','department','group'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ------------------------------------------------------------------
    # organizations
    # ------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], schema=SCHEMA)

    # ------------------------------------------------------------------
    # auth_config
    # ------------------------------------------------------------------
    op.create_table(
        "auth_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("jwt_expiry_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("max_failed_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("lockout_duration_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column("sso_provider", sa.String(50), nullable=False, server_default="default"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    # Cast the string column to the enum type (must drop default first, then re-add)
    op.execute(f"ALTER TABLE {SCHEMA}.auth_config ALTER COLUMN sso_provider DROP DEFAULT")
    op.execute(f"""
        ALTER TABLE {SCHEMA}.auth_config
        ALTER COLUMN sso_provider TYPE {SCHEMA}.sso_provider_enum
        USING sso_provider::{SCHEMA}.sso_provider_enum
    """)
    op.execute(f"ALTER TABLE {SCHEMA}.auth_config ALTER COLUMN sso_provider SET DEFAULT 'default'::{SCHEMA}.sso_provider_enum")

    # ------------------------------------------------------------------
    # users (before domains so domain FK can reference users)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", UUID(as_uuid=True), nullable=True),  # FK added after domains table
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(128), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("image", sa.String(512), nullable=True),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_global_admin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_users_email", "users", ["email"], schema=SCHEMA)
    op.create_index("ix_users_username", "users", ["username"], schema=SCHEMA)

    # ------------------------------------------------------------------
    # domains
    # ------------------------------------------------------------------
    op.create_table(
        "domains",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )

    # Now add the FK from users.domain_id → domains.id
    op.create_foreign_key(
        "fk_users_domain_id",
        "users", "domains",
        ["domain_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # teams
    # ------------------------------------------------------------------
    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_team_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.domains.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("team_type", sa.String(50), nullable=False, server_default="group"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("public_team_view", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    # Cast the string column to the enum type (must drop default first, then re-add)
    op.execute(f"ALTER TABLE {SCHEMA}.teams ALTER COLUMN team_type DROP DEFAULT")
    op.execute(f"""
        ALTER TABLE {SCHEMA}.teams
        ALTER COLUMN team_type TYPE {SCHEMA}.team_type_enum
        USING team_type::{SCHEMA}.team_type_enum
    """)
    op.execute(f"ALTER TABLE {SCHEMA}.teams ALTER COLUMN team_type SET DEFAULT 'group'::{SCHEMA}.team_type_enum")

    # ------------------------------------------------------------------
    # policies
    # ------------------------------------------------------------------
    op.create_table(
        "policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("operations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("conditions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # roles
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system_role", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # Association tables
    # ------------------------------------------------------------------
    op.create_table(
        "role_policies",
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
        schema=SCHEMA,
    )

    op.create_table(
        "user_teams",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), primary_key=True),
        schema=SCHEMA,
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.roles.id", ondelete="CASCADE"), primary_key=True),
        schema=SCHEMA,
    )

    op.create_table(
        "user_policies",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.policies.id", ondelete="CASCADE"), primary_key=True),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # org_profiler_config
    # ------------------------------------------------------------------
    op.create_table(
        "org_profiler_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("datatype", sa.String(128), nullable=False),
        sa.Column("metric_types", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )

    # ------------------------------------------------------------------
    # Seed: default org + global admin user + auth_config + system roles
    # ------------------------------------------------------------------
    from passlib.context import CryptContext
    import os

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    admin_email = os.getenv("GLOBAL_ADMIN_EMAIL", "admin@deltameta.io")
    admin_password = os.getenv("GLOBAL_ADMIN_PASSWORD", "Admin@123")
    admin_name = os.getenv("GLOBAL_ADMIN_NAME", "Global Admin")

    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    auth_config_id = str(uuid.uuid4())
    role_admin_id = str(uuid.uuid4())
    role_viewer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    op.execute(f"""
        INSERT INTO {SCHEMA}.organizations (id, name, slug, description, is_active, is_default, created_at, updated_at)
        VALUES ('{org_id}', 'Default Organization', 'default-org', 'Auto-created default organization', true, true, '{now}', '{now}')
    """)

    hashed_pw = pwd_context.hash(admin_password)
    conn = op.get_bind()
    conn.execute(
        sa.text(f"""
            INSERT INTO {SCHEMA}.users (id, org_id, name, display_name, email, username, hashed_password,
                is_admin, is_global_admin, is_active, is_verified, failed_attempts, created_at, updated_at)
            VALUES (
                '{user_id}', '{org_id}', '{admin_name}', '{admin_name}',
                '{admin_email}', 'admin',
                :hashed_pw,
                true, true, true, true, 0, '{now}', '{now}'
            )
        """),
        {"hashed_pw": hashed_pw},
    )

    op.execute(f"""
        UPDATE {SCHEMA}.organizations SET created_by = '{user_id}' WHERE id = '{org_id}'
    """)

    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.auth_config (id, org_id, jwt_expiry_minutes, max_failed_attempts, lockout_duration_minutes, sso_provider, updated_at)
        VALUES ('{auth_config_id}', '{org_id}', 60, 5, 15, 'default'::{SCHEMA}.sso_provider_enum, '{now}')
    """))

    # System roles: org_admin, viewer
    op.execute(f"""
        INSERT INTO {SCHEMA}.roles (id, org_id, name, description, is_system_role, created_at, updated_at)
        VALUES
            ('{role_admin_id}', '{org_id}', 'org_admin', 'Organization administrator', true, '{now}', '{now}'),
            ('{role_viewer_id}', '{org_id}', 'viewer', 'Read-only viewer', true, '{now}', '{now}')
    """)

    # Assign admin role to global admin user
    op.execute(f"""
        INSERT INTO {SCHEMA}.user_roles (user_id, role_id)
        VALUES ('{user_id}', '{role_admin_id}')
    """)


def downgrade() -> None:
    SCHEMA = "deltameta"
    op.drop_table("subscriptions", schema=SCHEMA)
    op.drop_table("org_profiler_config", schema=SCHEMA)
    op.drop_table("user_policies", schema=SCHEMA)
    op.drop_table("user_roles", schema=SCHEMA)
    op.drop_table("user_teams", schema=SCHEMA)
    op.drop_table("role_policies", schema=SCHEMA)
    op.drop_table("roles", schema=SCHEMA)
    op.drop_table("policies", schema=SCHEMA)
    op.drop_table("teams", schema=SCHEMA)
    op.drop_constraint("fk_users_domain_id", "users", schema=SCHEMA, type_="foreignkey")
    op.drop_table("domains", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
    op.drop_table("auth_config", schema=SCHEMA)
    op.drop_table("organizations", schema=SCHEMA)
    op.execute("DROP TYPE IF EXISTS deltameta.team_type_enum")
    op.execute("DROP TYPE IF EXISTS deltameta.sso_provider_enum")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")

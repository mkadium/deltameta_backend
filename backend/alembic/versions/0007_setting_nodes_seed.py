"""Seed setting_nodes with OpenMetadata-style Settings hierarchy

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-26

Hierarchy:
  Settings (root)
    ├── Services (APIs, Databases, Storages, Drive)
    ├── Applications (AutoPilot, Data Insights, etc.)
    ├── Notifications (Alerts)
    ├── Organization, Team & User Management (Organization, Teams, Users, Admins, Online Users)
    ├── Access Control (Roles, Policies, Permission Debugger)
    ├── Preferences (Email, Login Config, Health Check, etc.)
    ├── Custom Properties (API Collection, Tables, etc.)
    ├── Bots
    ├── Personas
    └── SSO (Google, Azure AD, Okta, etc.)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

SCHEMA = "deltameta"

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _run_seed()


def _esc(s: str) -> str:
    """Escape single quotes for SQL."""
    return s.replace("'", "''") if s else ""


def _run_seed():
    """Execute seed inserts. Uses ON CONFLICT (id) DO NOTHING for idempotency."""
    conn = op.get_bind()
    # Root
    conn.execute(sa.text("""
        INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, sort_order)
        VALUES ('b0000000-0000-0000-0000-000000000001', NULL, 'settings', 'Settings', 'Platform and application settings', 'settings', 'category', 0)
        ON CONFLICT (id) DO NOTHING
    """))
    # Level 1 children of Settings
    level1 = [
        ('b1000000-0000-0000-0000-000000000001', 'services', 'Services', 'Set up connectors and ingest metadata from diverse sources', 'category', 1),
        ('b1000000-0000-0000-0000-000000000002', 'applications', 'Applications', 'Improve your data using Applications for MetaPilot, Data Insights, and Search Indexing', 'category', 2),
        ('b1000000-0000-0000-0000-000000000003', 'notifications', 'Notifications', 'Set up notifications to receive real-time updates and timely alerts', 'category', 3),
        ('b1000000-0000-0000-0000-000000000004', 'organization-team-user-management', 'Organization, Team & User Management', 'Streamline access to users, teams and Organization in OpenMetadata', 'category', 4),
        ('b1000000-0000-0000-0000-000000000005', 'access-control', 'Access Control', 'Align with your organizational hierarchy and team access with roles and policies', 'category', 5),
        ('b1000000-0000-0000-0000-000000000006', 'preferences', 'Preferences', 'Tailor the OpenMetadata UX to suit your organizational and team needs', 'category', 6),
        ('b1000000-0000-0000-0000-000000000007', 'custom-properties', 'Custom Properties', 'Capture custom metadata to enrich your data assets by extending the attributes', 'category', 7),
        ('b1000000-0000-0000-0000-000000000008', 'bots', 'Bots', 'Create well-defined bots with scoped access permissions', 'leaf', 8),
        ('b1000000-0000-0000-0000-000000000009', 'personas', 'Personas', 'Enhance and customize the user experience with Personas', 'leaf', 9),
        ('b1000000-0000-0000-0000-000000000010', 'sso', 'SSO', 'Configure single sign-on and identity providers', 'category', 10),
    ]
    for uid, slug, label, desc, ntype, order in level1:
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, sort_order)
            VALUES ('{uid}', 'b0000000-0000-0000-0000-000000000001', '{slug}', '{_esc(label)}', '{_esc(desc)}', '{slug}', '{ntype}', 'settings.{slug}', {order})
            ON CONFLICT (id) DO NOTHING
        """))

    # Services children
    services_children = [
        ('b2000000-0000-0000-0000-000000000001', 'apis', 'APIs', 'Ingest metadata from the most popular API services', 'category'),
        ('b2000000-0000-0000-0000-000000000002', 'databases', 'Databases', 'Ingest metadata from the most popular database services', 'category'),
        ('b2000000-0000-0000-0000-000000000003', 'storages', 'Storages', 'Ingest metadata from the most popular storage services', 'category'),
        ('b2000000-0000-0000-0000-000000000004', 'drive', 'Drive', 'Ingest metadata from the most popular drive services', 'category'),
    ]
    for uid, slug, label, desc, ntype in services_children:
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000001', '{slug}', '{_esc(label)}', '{_esc(desc)}', '{slug}', '{ntype}', 'settings.services.{slug}', 0)
            ON CONFLICT (id) DO NOTHING
        """))

    # Applications children (leaves)
    app_children = [
        ('autopilot', 'AutoPilot', 'AI-powered metadata automation and suggestions'),
        ('data-contract-validation', 'Data Contract Validation', 'Validate data contracts and schema compliance'),
        ('data-insights', 'Data Insights', 'Analytics and insights across your data assets'),
        ('data-retention', 'Data Retention', 'Configure and manage data retention policies'),
        ('mcp-server', 'MCP Server', 'Model Context Protocol server integrations'),
        ('search-indexing', 'Search Indexing', 'Index and search across your metadata'),
        ('cache-refresh', 'Cache Refresh', 'Refresh and manage metadata caches'),
    ]
    for i, (slug, label, desc) in enumerate(app_children):
        uid = f'b2000000-0000-0000-0000-0000000000{10+i:02d}'
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000002', '{slug}', '{_esc(label)}', '{_esc(desc)}', 'application', 'leaf', 'settings.applications.{slug}', '/settings/applications/{slug}', {i})
            ON CONFLICT (id) DO NOTHING
        """))

    # Notifications > Alerts
    conn.execute(sa.text("""
        INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
        VALUES ('b2000000-0000-0000-0000-000000000020', 'b1000000-0000-0000-0000-000000000003', 'alerts', 'Alerts', 'Set up notifications to receive real-time updates and timely alerts', 'bell', 'leaf', 'settings.notifications.alerts', '/settings/notifications/alerts', 0)
        ON CONFLICT (id) DO NOTHING
    """))

    # Organization, Team & User Management children
    org_children = [
        ('b2000000-0000-0000-0000-000000000021', 'organization', 'Organization', 'Organization Handler', 'leaf', '/settings/organization'),
        ('b2000000-0000-0000-0000-000000000022', 'teams', 'Teams', 'Represent your entire organizational structure with hierarchical teams', 'leaf', '/settings/teams'),
        ('b2000000-0000-0000-0000-000000000023', 'users', 'Users', 'View and manage regular users in your organization. For admin users, please visit the Admin page', 'leaf', '/settings/users'),
        ('b2000000-0000-0000-0000-000000000024', 'admins', 'Admins', 'View and manage admin users in your organization. For regular users, please visit the Users page', 'leaf', '/settings/admins'),
        ('b2000000-0000-0000-0000-000000000025', 'online-users', 'Online Users', 'View users who have been active recently in the system', 'leaf', '/settings/online-users'),
    ]
    for uid, slug, label, desc, ntype, nav_url in org_children:
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000004', '{slug}', '{_esc(label)}', '{_esc(desc)}', '{slug}', '{ntype}', 'settings.organization-team-user-management.{slug}', '{nav_url}', 0)
            ON CONFLICT (id) DO NOTHING
        """))

    # Access Control children
    ac_children = [
        ('b2000000-0000-0000-0000-000000000031', 'roles', 'Roles', 'Assign comprehensive role based access to Users or Teams', 'leaf', '/settings/access-control/roles'),
        ('b2000000-0000-0000-0000-000000000032', 'policies', 'Policies', 'Define policies with a set of rules for fine-grained access control', 'leaf', '/settings/access-control/policies'),
        ('b2000000-0000-0000-0000-000000000033', 'permission-debugger', 'Permission Debugger', 'Debug and understand user permissions across roles, teams, etc', 'leaf', '/settings/access-control/permission-debugger'),
    ]
    for uid, slug, label, desc, ntype, nav_url in ac_children:
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000005', '{slug}', '{_esc(label)}', '{_esc(desc)}', '{slug}', '{ntype}', 'settings.access-control.{slug}', '{nav_url}', 0)
            ON CONFLICT (id) DO NOTHING
        """))

    # Preferences children (leaves)
    prefs = [
        ('email', 'Email', 'Configure email notifications and SMTP settings'),
        ('login-configuration', 'Login Configuration', 'Customize login and authentication flow'),
        ('health-check', 'Health Check', 'Configure health check and monitoring endpoints'),
        ('profiler-configuration', 'Profiler Configuration', 'Set up data profiling configurations'),
        ('search', 'Search', 'Configure search behavior and indexing'),
        ('lineage', 'Lineage', 'Configure data lineage settings'),
        ('deltameta-url', 'DeltaMeta URL', 'Configure DeltaMeta instance URL and endpoints'),
        ('data-asset-rules', 'Data Asset Rules', 'Define rules for data asset classification'),
        ('theme', 'Theme', 'Customize UI theme and appearance'),
    ]
    for i, (slug, label, desc) in enumerate(prefs):
        uid = f'b2000000-0000-0000-0000-0000000000{40+i:02d}'
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000006', '{slug}', '{_esc(label)}', '{_esc(desc)}', 'preferences', 'leaf', 'settings.preferences.{slug}', '/settings/preferences/{slug}', {i})
            ON CONFLICT (id) DO NOTHING
        """))

    # Custom Properties children (leaves)
    custom_props = [
        'api-collection', 'api-endpoint', 'charts', 'containers', 'dashboard-data-models', 'dashboards',
        'data-product', 'database', 'database-schema', 'directories', 'domain', 'files', 'glossary-term',
        'metric', 'ml-models', 'pipelines', 'search-index', 'spreadsheets', 'stored-procedures', 'tables', 'topics', 'worksheets'
    ]
    labels = {
        'api-collection': 'API Collection', 'api-endpoint': 'API Endpoint', 'charts': 'Charts', 'containers': 'Containers',
        'dashboard-data-models': 'Dashboard Data Models', 'dashboards': 'Dashboards', 'data-product': 'Data Product',
        'database': 'Database', 'database-schema': 'Database Schema', 'directories': 'Directories', 'domain': 'Domain',
        'files': 'Files', 'glossary-term': 'Glossary Term', 'metric': 'Metric', 'ml-models': 'ML Models',
        'pipelines': 'Pipelines', 'search-index': 'Search Index', 'spreadsheets': 'Spreadsheets',
        'stored-procedures': 'Stored Procedures', 'tables': 'Tables', 'topics': 'Topics', 'worksheets': 'Worksheets',
    }
    for i, slug in enumerate(custom_props):
        label = labels.get(slug, slug.replace('-', ' ').title())
        uid = f'b2000000-0000-0000-0000-0000000000{50+i:02d}'
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000007', '{slug}', '{_esc(label)}', 'Define custom properties for {_esc(label)}', 'property', 'leaf', 'settings.custom-properties.{slug}', '/settings/custom-properties/{slug}', {i})
            ON CONFLICT (id) DO NOTHING
        """))

    # SSO children (leaves)
    sso_providers = [
        ('google', 'Google', 'Sign in with Google'),
        ('azure-ad', 'Azure AD', 'Sign in with Microsoft Azure Active Directory'),
        ('okta', 'Okta', 'Sign in with Okta'),
        ('keycloak', 'Keycloak', 'Sign in with Keycloak'),
        ('saml', 'SAML', 'SAML 2.0 based single sign-on'),
        ('aws-cognito', 'AWS Cognito', 'Sign in with Amazon Cognito'),
        ('custom-oidc', 'Custom OIDC', 'Custom OpenID Connect provider'),
        ('ldap', 'LDAP', 'LDAP directory authentication'),
        ('auth0', 'Auth0', 'Sign in with Auth0'),
        ('default', 'Default', 'Default local authentication'),
    ]
    for i, (slug, label, desc) in enumerate(sso_providers):
        uid = f'b2000000-0000-0000-0000-0000000000{80+i:02d}'
        conn.execute(sa.text(f"""
            INSERT INTO deltameta.setting_nodes (id, parent_id, slug, display_label, description, icon, node_type, slug_path, nav_url, sort_order)
            VALUES ('{uid}', 'b1000000-0000-0000-0000-000000000010', '{slug}', '{_esc(label)}', '{_esc(desc)}', 'sso', 'leaf', 'settings.sso.{slug}', '/settings/sso/{slug}', {i})
            ON CONFLICT (id) DO NOTHING
        """))


def downgrade() -> None:
    """Remove seeded nodes. Deleting root cascades to all children via FK ON DELETE CASCADE."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM deltameta.setting_nodes WHERE id = 'b0000000-0000-0000-0000-000000000001'"))

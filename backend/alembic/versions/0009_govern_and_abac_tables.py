"""Govern & ABAC Phase 1: subject_areas, org_roles, org_policies, team_roles,
team_policies, storage_config, scheduled_tasks, activity_feeds, iceberg schema,
change_requests, lookup tables, glossary, classification, data_products,
catalog_domains, metrics, service_endpoints

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "deltameta"
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create iceberg schema
    conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS iceberg"))

    # 2. Rename domains -> subject_areas
    conn.execute(sa.text(f"ALTER TABLE IF EXISTS {SCHEMA}.domains RENAME TO subject_areas"))
    # Rename FK constraint names if they exist (best-effort)
    conn.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema = '{SCHEMA}' AND table_name = 'subject_areas'
                AND constraint_name = 'domains_org_id_fkey'
            ) THEN
                ALTER TABLE {SCHEMA}.subject_areas RENAME CONSTRAINT domains_org_id_fkey TO subject_areas_org_id_fkey;
            END IF;
        END $$;
    """))
    conn.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema = '{SCHEMA}' AND table_name = 'subject_areas'
                AND constraint_name = 'domains_owner_id_fkey'
            ) THEN
                ALTER TABLE {SCHEMA}.subject_areas RENAME CONSTRAINT domains_owner_id_fkey TO subject_areas_owner_id_fkey;
            END IF;
        END $$;
    """))

    # 3. Add display_name and domain_type (as enum-like check) to subject_areas
    conn.execute(sa.text(f"""
        ALTER TABLE {SCHEMA}.subject_areas
            ADD COLUMN IF NOT EXISTS display_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS domain_type VARCHAR(100)
    """))

    # 4. Update FK in users pointing to domains
    conn.execute(sa.text(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = '{SCHEMA}' AND table_name = 'users' AND column_name = 'domain_id'
            ) THEN
                -- drop old FK constraint pointing to domains (now renamed)
                ALTER TABLE {SCHEMA}.users DROP CONSTRAINT IF EXISTS users_domain_id_fkey;
                -- no need to re-add, column name stays; FK may need manual re-add in prod
            END IF;
        END $$;
    """))

    # 5. org_roles M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.org_roles (
            org_id  UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES {SCHEMA}.roles(id) ON DELETE CASCADE,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (org_id, role_id)
        )
    """))

    # 6. org_policies M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.org_policies (
            org_id     UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            policy_id  UUID NOT NULL REFERENCES {SCHEMA}.policies(id) ON DELETE CASCADE,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (org_id, policy_id)
        )
    """))

    # 7. team_roles M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.team_roles (
            team_id UUID NOT NULL REFERENCES {SCHEMA}.teams(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES {SCHEMA}.roles(id) ON DELETE CASCADE,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, role_id)
        )
    """))

    # 8. team_policies M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.team_policies (
            team_id   UUID NOT NULL REFERENCES {SCHEMA}.teams(id) ON DELETE CASCADE,
            policy_id UUID NOT NULL REFERENCES {SCHEMA}.policies(id) ON DELETE CASCADE,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (team_id, policy_id)
        )
    """))

    # 9. storage_config
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.storage_config (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            provider    VARCHAR(50) NOT NULL DEFAULT 'minio',
            endpoint    VARCHAR(512),
            bucket      VARCHAR(255),
            access_key  VARCHAR(255),
            secret_key  VARCHAR(512),
            region      VARCHAR(100),
            extra       JSONB NOT NULL DEFAULT '{{}}',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 10. service_endpoints
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.service_endpoints (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id       UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            service_name VARCHAR(100) NOT NULL,
            base_url     VARCHAR(512) NOT NULL,
            extra        JSONB NOT NULL DEFAULT '{{}}',
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (org_id, service_name)
        )
    """))

    # 11. scheduled_tasks
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.scheduled_tasks (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            entity_type   VARCHAR(100) NOT NULL,
            entity_id     UUID,
            task_name     VARCHAR(255) NOT NULL,
            schedule_type VARCHAR(50) NOT NULL DEFAULT 'manual',
            cron_expr     VARCHAR(100),
            next_run_at   TIMESTAMPTZ,
            last_run_at   TIMESTAMPTZ,
            last_status   VARCHAR(50),
            payload       JSONB NOT NULL DEFAULT '{{}}',
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_by    UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 12. activity_feeds
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.activity_feeds (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            actor_id    UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            entity_type VARCHAR(100) NOT NULL,
            entity_id   UUID,
            action      VARCHAR(100) NOT NULL,
            details     JSONB NOT NULL DEFAULT '{{}}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS idx_activity_feeds_entity ON {SCHEMA}.activity_feeds(entity_type, entity_id)"))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS idx_activity_feeds_org ON {SCHEMA}.activity_feeds(org_id, created_at DESC)"))

    # 13. change_requests
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.change_requests (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            entity_type   VARCHAR(100) NOT NULL,
            entity_id     UUID NOT NULL,
            field_name    VARCHAR(255) NOT NULL,
            current_value TEXT,
            new_value     TEXT NOT NULL,
            title         VARCHAR(500),
            description   TEXT,
            status        VARCHAR(50) NOT NULL DEFAULT 'open',
            requested_by  UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            resolved_by   UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            resolved_at   TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 14. change_request_assignees
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.change_request_assignees (
            change_request_id UUID NOT NULL REFERENCES {SCHEMA}.change_requests(id) ON DELETE CASCADE,
            user_id           UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (change_request_id, user_id)
        )
    """))

    # 15. lookup_categories
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.lookup_categories (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name        VARCHAR(255) NOT NULL,
            slug        VARCHAR(255) NOT NULL,
            description TEXT,
            is_system   BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (org_id, slug)
        )
    """))

    # 16. lookup_values
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.lookup_values (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            category_id UUID NOT NULL REFERENCES {SCHEMA}.lookup_categories(id) ON DELETE CASCADE,
            org_id      UUID REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            label       VARCHAR(255) NOT NULL,
            value       VARCHAR(255) NOT NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 17. catalog_domains (governance domains in the data catalog, not IAM domains)
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.catalog_domains (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name            VARCHAR(255) NOT NULL,
            display_name    VARCHAR(255),
            description     TEXT,
            domain_type     VARCHAR(100),
            icon            VARCHAR(512),
            color           VARCHAR(50),
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_by      UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 18. catalog_domain_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.catalog_domain_owners (
            domain_id UUID NOT NULL REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE CASCADE,
            user_id   UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (domain_id, user_id)
        )
    """))

    # 19. catalog_domain_experts M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.catalog_domain_experts (
            domain_id UUID NOT NULL REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE CASCADE,
            user_id   UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (domain_id, user_id)
        )
    """))

    # 20. data_products
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_products (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id       UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            domain_id    UUID REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE SET NULL,
            name         VARCHAR(255) NOT NULL,
            display_name VARCHAR(255),
            description  TEXT,
            version      VARCHAR(50) NOT NULL DEFAULT '0.1',
            status       VARCHAR(50) NOT NULL DEFAULT 'draft',
            is_active    BOOLEAN NOT NULL DEFAULT TRUE,
            created_by   UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 21. data_product_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_product_owners (
            product_id UUID NOT NULL REFERENCES {SCHEMA}.data_products(id) ON DELETE CASCADE,
            user_id    UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (product_id, user_id)
        )
    """))

    # 22. data_product_experts M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.data_product_experts (
            product_id UUID NOT NULL REFERENCES {SCHEMA}.data_products(id) ON DELETE CASCADE,
            user_id    UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (product_id, user_id)
        )
    """))

    # 23. glossaries
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossaries (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name        VARCHAR(255) NOT NULL,
            display_name VARCHAR(255),
            description TEXT,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_by  UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (org_id, name)
        )
    """))

    # 24. glossary_terms
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossary_terms (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            glossary_id     UUID NOT NULL REFERENCES {SCHEMA}.glossaries(id) ON DELETE CASCADE,
            org_id          UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name            VARCHAR(255) NOT NULL,
            display_name    VARCHAR(255),
            description     TEXT,
            icon_url        VARCHAR(512),
            color           VARCHAR(50),
            mutually_exclusive BOOLEAN NOT NULL DEFAULT FALSE,
            synonyms        JSONB NOT NULL DEFAULT '[]',
            references_data JSONB NOT NULL DEFAULT '[]',
            likes_count     INTEGER NOT NULL DEFAULT 0,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_by      UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 25. glossary_term_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossary_term_owners (
            term_id UUID NOT NULL REFERENCES {SCHEMA}.glossary_terms(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (term_id, user_id)
        )
    """))

    # 26. glossary_term_reviewers M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossary_term_reviewers (
            term_id UUID NOT NULL REFERENCES {SCHEMA}.glossary_terms(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (term_id, user_id)
        )
    """))

    # 27. glossary_term_related M2M (related terms)
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossary_term_related (
            term_id         UUID NOT NULL REFERENCES {SCHEMA}.glossary_terms(id) ON DELETE CASCADE,
            related_term_id UUID NOT NULL REFERENCES {SCHEMA}.glossary_terms(id) ON DELETE CASCADE,
            PRIMARY KEY (term_id, related_term_id)
        )
    """))

    # 28. glossary_term_likes
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.glossary_term_likes (
            term_id    UUID NOT NULL REFERENCES {SCHEMA}.glossary_terms(id) ON DELETE CASCADE,
            user_id    UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (term_id, user_id)
        )
    """))

    # 29. classifications
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classifications (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id             UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name               VARCHAR(255) NOT NULL,
            display_name       VARCHAR(255),
            description        TEXT,
            mutually_exclusive BOOLEAN NOT NULL DEFAULT FALSE,
            is_active          BOOLEAN NOT NULL DEFAULT TRUE,
            created_by         UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (org_id, name)
        )
    """))

    # 30. classification_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classification_owners (
            classification_id UUID NOT NULL REFERENCES {SCHEMA}.classifications(id) ON DELETE CASCADE,
            user_id           UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (classification_id, user_id)
        )
    """))

    # 31. classification_domain_refs M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classification_domain_refs (
            classification_id UUID NOT NULL REFERENCES {SCHEMA}.classifications(id) ON DELETE CASCADE,
            domain_id         UUID NOT NULL REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE CASCADE,
            PRIMARY KEY (classification_id, domain_id)
        )
    """))

    # 32. classification_tags
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classification_tags (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            classification_id UUID NOT NULL REFERENCES {SCHEMA}.classifications(id) ON DELETE CASCADE,
            org_id            UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name              VARCHAR(255) NOT NULL,
            display_name      VARCHAR(255),
            description       TEXT,
            icon_url          VARCHAR(512),
            color             VARCHAR(50),
            is_active         BOOLEAN NOT NULL DEFAULT TRUE,
            created_by        UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 33. classification_tag_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classification_tag_owners (
            tag_id  UUID NOT NULL REFERENCES {SCHEMA}.classification_tags(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (tag_id, user_id)
        )
    """))

    # 34. classification_tag_domain_refs M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.classification_tag_domain_refs (
            tag_id    UUID NOT NULL REFERENCES {SCHEMA}.classification_tags(id) ON DELETE CASCADE,
            domain_id UUID NOT NULL REFERENCES {SCHEMA}.catalog_domains(id) ON DELETE CASCADE,
            PRIMARY KEY (tag_id, domain_id)
        )
    """))

    # 35. metrics
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.govern_metrics (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id           UUID NOT NULL REFERENCES {SCHEMA}.organizations(id) ON DELETE CASCADE,
            name             VARCHAR(255) NOT NULL,
            display_name     VARCHAR(255),
            description      TEXT,
            granularity      VARCHAR(50),
            metric_type      VARCHAR(100),
            language         VARCHAR(50),
            measurement_unit VARCHAR(100),
            code             TEXT,
            is_active        BOOLEAN NOT NULL DEFAULT TRUE,
            created_by       UUID REFERENCES {SCHEMA}.users(id) ON DELETE SET NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # 36. govern_metric_owners M2M
    conn.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.govern_metric_owners (
            metric_id UUID NOT NULL REFERENCES {SCHEMA}.govern_metrics(id) ON DELETE CASCADE,
            user_id   UUID NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            PRIMARY KEY (metric_id, user_id)
        )
    """))

    # 37. Seed default lookup categories
    for slug, name, desc in [
        ("domain_type",      "Domain Type",        "Types for catalog domains"),
        ("metric_type",      "Metric Type",         "Types for govern metrics"),
        ("metric_granularity","Metric Granularity", "Time granularity for metrics"),
        ("measurement_unit", "Measurement Unit",    "Units for metric values"),
        ("metric_language",  "Metric Language",     "Code language for metrics"),
    ]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_categories (id, org_id, name, slug, description, is_system)
            VALUES (gen_random_uuid(), NULL, '{name}', '{slug}', '{desc}', TRUE)
            ON CONFLICT (org_id, slug) DO NOTHING
        """))

    # Seed domain_type values
    for label, value in [
        ("Aggregate", "aggregate"),
        ("Consumer Aligned", "consumer_aligned"),
        ("Source Aligned", "source_aligned"),
    ]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_values (id, category_id, org_id, label, value)
            SELECT gen_random_uuid(), id, NULL, '{label}', '{value}'
            FROM {SCHEMA}.lookup_categories WHERE slug = 'domain_type' AND org_id IS NULL
            ON CONFLICT DO NOTHING
        """))

    # Seed metric_type values
    for label, value in [
        ("Average","average"),("Count","count"),("Max","max"),("Median","median"),
        ("Min","min"),("Mode","mode"),("Other","other"),("Percentage","percentage"),
        ("Ratio","ratio"),("Standard Deviation","standard_deviation"),
        ("Sum","sum"),("Variance","variance"),
    ]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_values (id, category_id, org_id, label, value)
            SELECT gen_random_uuid(), id, NULL, '{label}', '{value}'
            FROM {SCHEMA}.lookup_categories WHERE slug = 'metric_type' AND org_id IS NULL
            ON CONFLICT DO NOTHING
        """))

    # Seed metric_granularity values
    for label in ["Day","Hour","Minute","Month","Quarter","Second","Week","Year"]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_values (id, category_id, org_id, label, value)
            SELECT gen_random_uuid(), id, NULL, '{label}', '{label.lower()}'
            FROM {SCHEMA}.lookup_categories WHERE slug = 'metric_granularity' AND org_id IS NULL
            ON CONFLICT DO NOTHING
        """))

    # Seed measurement_unit values
    for label in ["Count","Dollars","Events","Percentage","Request","Size","Timestamp","Transactions"]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_values (id, category_id, org_id, label, value)
            SELECT gen_random_uuid(), id, NULL, '{label}', '{label.lower()}'
            FROM {SCHEMA}.lookup_categories WHERE slug = 'measurement_unit' AND org_id IS NULL
            ON CONFLICT DO NOTHING
        """))

    # Seed metric_language values
    for label in ["Python","SQL","JavaScript"]:
        conn.execute(sa.text(f"""
            INSERT INTO {SCHEMA}.lookup_values (id, category_id, org_id, label, value)
            SELECT gen_random_uuid(), id, NULL, '{label}', '{label.lower()}'
            FROM {SCHEMA}.lookup_categories WHERE slug = 'metric_language' AND org_id IS NULL
            ON CONFLICT DO NOTHING
        """))

    # Seed built-in PersonalData classification (global, no org)
    conn.execute(sa.text(f"""
        DO $$
        DECLARE v_org_id UUID;
        BEGIN
            SELECT id INTO v_org_id FROM {SCHEMA}.organizations LIMIT 1;
            IF v_org_id IS NOT NULL THEN
                INSERT INTO {SCHEMA}.classifications (id, org_id, name, display_name, description, mutually_exclusive)
                VALUES (
                    '10000000-0000-0000-0000-000000000001',
                    v_org_id,
                    'PersonalData',
                    'Personal Data',
                    'Tags for classifying personal data sensitivity',
                    TRUE
                ) ON CONFLICT DO NOTHING;

                INSERT INTO {SCHEMA}.classification_tags (id, classification_id, org_id, name, display_name, description)
                VALUES
                    ('10000000-0000-0000-0000-000000000011', '10000000-0000-0000-0000-000000000001', v_org_id, 'Personal', 'Personal', 'Personal data'),
                    ('10000000-0000-0000-0000-000000000012', '10000000-0000-0000-0000-000000000001', v_org_id, 'SpecialCategory', 'Special Category', 'Special category personal data')
                ON CONFLICT DO NOTHING;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    for tbl in [
        "govern_metric_owners", "govern_metrics",
        "classification_tag_domain_refs", "classification_tag_owners", "classification_tags",
        "classification_domain_refs", "classification_owners", "classifications",
        "glossary_term_likes", "glossary_term_related", "glossary_term_reviewers",
        "glossary_term_owners", "glossary_terms", "glossaries",
        "data_product_experts", "data_product_owners", "data_products",
        "catalog_domain_experts", "catalog_domain_owners", "catalog_domains",
        "lookup_values", "lookup_categories",
        "change_request_assignees", "change_requests",
        "activity_feeds", "scheduled_tasks",
        "service_endpoints", "storage_config",
        "team_policies", "team_roles", "org_policies", "org_roles",
    ]:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {SCHEMA}.{tbl} CASCADE"))

    conn.execute(sa.text(f"ALTER TABLE IF EXISTS {SCHEMA}.subject_areas RENAME TO domains"))
    conn.execute(sa.text("DROP SCHEMA IF EXISTS iceberg CASCADE"))

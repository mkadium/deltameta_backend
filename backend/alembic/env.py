import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make the app importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.settings import settings
from app.auth.models import Base
import app.setting_nodes.models  # register SettingNode models in Base.metadata
import app.resources.models  # register ResourceGroup/ResourceDefinition in Base.metadata

# Alembic Config object
config = context.config

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy metadata for autogenerate support
target_metadata = Base.metadata

SCHEMA = "deltameta"


def get_database_url() -> str:
    """Build the async database URL from settings."""
    if settings.primary_database_url:
        return settings.primary_database_url
    if settings.primary_db_host:
        return (
            f"postgresql+asyncpg://{settings.primary_db_user}:{settings.primary_db_password}"
            f"@{settings.primary_db_host}:{settings.primary_db_port}/{settings.primary_db_name}"
        )
    raise RuntimeError("No database URL configured. Set PRIMARY_DATABASE_URL or PRIMARY_DB_* vars in .env")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    connection.execute(text(f"SET search_path TO {SCHEMA}, public"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        transaction_per_migration=False,
    )
    # Run without wrapping in begin_transaction so DDL commits immediately
    context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against a live async DB connection."""
    db_url = get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = db_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )

    async with connectable.connect() as connection:
        await connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

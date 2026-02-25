import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Import your models' MetaData object here for 'autogenerate' support
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "backend"))

from app.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = AsyncEngine(
        config.get_section(config.config_ini_section)["sqlalchemy.url"]
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)


def run_migrations_online():
    # From alembic docs: use an Async engine when available
    connectable = AsyncEngine(
        config.get_section(config.config_ini_section)["sqlalchemy.url"]
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    # prefer the async path if possible
    try:
        asyncio.run(run_async_migrations())
    except Exception:
        run_migrations_online()


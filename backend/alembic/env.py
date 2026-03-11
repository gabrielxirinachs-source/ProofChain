"""

Alembic is the migration tool for SQLAlchemy.
Think of it like Git for your database schema:
  - `alembic revision --autogenerate` → detects model changes, writes a migration file
  - `alembic upgrade head` → applies all pending migrations to the DB

This file tells Alembic:
  1. Where our DB is (from settings)
  2. What our schema looks like (via Base.metadata)
  3. How to run migrations asynchronously (since we use asyncpg)
"""
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# ── Import our models so Alembic can "see" the schema ─────────────────────────
# This is why app/models/__init__.py imports everything —
# one import here pulls in all table definitions.
from app.db.session import Base
from app.models import *  # noqa: F401, F403 — intentional wildcard for Alembic discovery
from app.core.config import get_settings

settings = get_settings()

# Alembic config object (reads alembic.ini)
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our schema
target_metadata = Base.metadata

# Override the sqlalchemy.url from alembic.ini with our settings
# (so we don't duplicate DB config)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL scripts)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (required for asyncpg driver)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No connection pooling during migrations
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
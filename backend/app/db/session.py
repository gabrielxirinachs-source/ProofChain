"""

This module manages the database connection pool and provides
a session factory for interacting with Postgres.

Key concepts:
  - AsyncEngine: non-blocking DB driver — won't freeze your API while
    waiting for a slow query
  - AsyncSession: the unit of work; one per request, disposed after
  - get_db(): a FastAPI dependency — automatically opens and closes
    a session for each request using Python's `yield`
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pgvector.sqlalchemy import Vector  # noqa: F401 — registers the type

from app.core.config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
# The engine manages the connection pool (reuses connections instead of
# opening a new one on every request — critical for performance).
#
# pool_pre_ping=True: tests each connection before using it, so stale
# connections from the pool don't cause cryptic errors.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # Logs every SQL query in development
    pool_pre_ping=True,
    pool_size=10,              # Max simultaneous DB connections
    max_overflow=20,
)

# ── Session Factory ───────────────────────────────────────────────────────────
# AsyncSessionLocal is a factory — calling it creates a new session.
# expire_on_commit=False: keeps objects usable after commit (important
# for async code where you might access attributes after the transaction).
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Class ────────────────────────────────────────────────────────────────
# All SQLAlchemy models inherit from this.
# It provides the metadata registry that Alembic uses for migrations.
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────────────
async def get_db():
    """
    Yields a database session for a single request, then closes it.

    Usage in a route:
        from fastapi import Depends
        from app.db.session import get_db

        @router.get("/example")
        async def my_route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
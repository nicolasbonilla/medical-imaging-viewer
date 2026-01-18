"""
PostgreSQL Database Connection and Session Management.

Implements async SQLAlchemy with connection pooling for high-performance
database operations following ISO 27001 security guidelines.

@module core.database
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.database import Base

logger = logging.getLogger(__name__)
settings = get_settings()

# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url(async_driver: bool = True) -> str:
    """
    Construct database URL from settings.

    Supports both TCP connections (localhost) and Unix socket connections
    (Cloud SQL via /cloudsql/... path).

    Args:
        async_driver: If True, use asyncpg driver. If False, use psycopg2.
    """
    driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"

    # Check if DB_HOST is a Unix socket path (Cloud SQL)
    if settings.DB_HOST.startswith("/cloudsql/"):
        # For Cloud SQL Unix socket connection
        # asyncpg uses 'host' query param for socket path
        return (
            f"{driver}://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@/{settings.DB_NAME}?host={settings.DB_HOST}"
        )
    else:
        # Standard TCP connection
        return (
            f"{driver}://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )


def get_engine() -> AsyncEngine:
    """
    Get or create the async SQLAlchemy engine.

    Returns singleton engine instance with connection pooling configured
    for production use.
    """
    global _engine

    if _engine is None:
        database_url = get_database_url(async_driver=True)

        # Engine configuration with pooling
        # For production: use pool_size and max_overflow
        # For testing: use NullPool
        if settings.ENVIRONMENT == "testing":
            _engine = create_async_engine(
                database_url,
                poolclass=NullPool,
                echo=settings.DB_ECHO,
            )
        else:
            _engine = create_async_engine(
                database_url,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT,
                pool_recycle=settings.DB_POOL_RECYCLE,
                pool_pre_ping=True,  # Health check on checkout
                echo=settings.DB_ECHO,
            )

        logger.info(
            "Database engine created",
            extra={
                "host": settings.DB_HOST,
                "database": settings.DB_NAME,
                "pool_size": settings.DB_POOL_SIZE if settings.ENVIRONMENT != "testing" else "NullPool"
            }
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for database sessions.

    Usage in FastAPI routes:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...

    Yields:
        AsyncSession: Database session with automatic cleanup.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions (for non-FastAPI use).

    Usage:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.

    Should be called on application startup in development.
    In production, use Alembic migrations instead.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db() -> None:
    """
    Close database connection pool.

    Should be called on application shutdown.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connection pool closed")


async def check_db_connection() -> bool:
    """
    Health check for database connection.

    Returns:
        bool: True if connection is healthy.
    """
    try:
        async with get_db_context() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Alias for backward compatibility
get_async_db = get_db_session

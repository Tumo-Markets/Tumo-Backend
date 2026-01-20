from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Base

# Create async engine
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    poolclass=NullPool if settings.env == "test" else None,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database by creating all tables
    """
    logger.info("Creating database tables...")

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✓ Database tables created successfully!")
    logger.info("\nCreated tables:")
    for table_name in Base.metadata.tables.keys():
        logger.info(f"  - {table_name}")


async def close_db() -> None:
    """Close database connection."""
    await engine.dispose()

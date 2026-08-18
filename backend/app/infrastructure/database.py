"""SQLAlchemy async engine/session management and database health checks.

Phase 1 only needs connectivity, pooling, and a health probe — the domain schema is
introduced in Phase 2. Kept as a small module now so later phases add models/repositories
around this foundation rather than re-deriving it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

logger = logging.getLogger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_pre_ping=True,
    )


class Database:
    """Owns the engine/sessionmaker lifecycle for the application."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.engine: AsyncEngine = create_engine(settings)
        self.session_factory = async_sessionmaker(
            bind=self.engine, expire_on_commit=False, autoflush=False
        )

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def check_connection(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - readiness probe must never raise
            logger.exception("Database readiness check failed")
            return False

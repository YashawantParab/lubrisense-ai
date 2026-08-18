"""Direct connectivity tests for the infrastructure adapters, independent of the API layer."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient


@pytest.mark.asyncio
async def test_database_check_connection_succeeds() -> None:
    database = Database(get_settings())
    try:
        assert await database.check_connection() is True
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_redis_check_connection_succeeds() -> None:
    redis_client = RedisClient(get_settings())
    try:
        assert await redis_client.check_connection() is True
    finally:
        await redis_client.close()

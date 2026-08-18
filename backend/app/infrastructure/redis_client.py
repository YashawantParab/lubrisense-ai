"""Redis connectivity abstraction.

Phase 1 scope is connectivity and a health probe only — caching/business logic on top of
Redis is introduced by later phases that actually need it (rate limiting, feature caches,
job queues, etc.).
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self, settings: Settings) -> None:
        self._client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def check_connection(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:  # noqa: BLE001 - readiness probe must never raise
            logger.exception("Redis readiness check failed")
            return False

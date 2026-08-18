"""Health and readiness evaluation logic, kept out of route handlers.

`liveness` answers "is the process itself functioning" (always true if this code runs).
`readiness` answers "can this instance safely serve traffic" by checking critical
dependencies. The two are deliberately different: a process can be alive but not ready
(e.g., database briefly unreachable), and Phase 1 keeps that distinction real rather than
collapsing both into one check.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    healthy: bool


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    dependencies: list[DependencyStatus]


def check_liveness() -> bool:
    return True


async def check_readiness(database: Database, redis_client: RedisClient) -> ReadinessResult:
    dependencies = [
        DependencyStatus(name="database", healthy=await database.check_connection()),
        DependencyStatus(name="redis", healthy=await redis_client.check_connection()),
    ]
    ready = all(dep.healthy for dep in dependencies)
    return ReadinessResult(ready=ready, dependencies=dependencies)

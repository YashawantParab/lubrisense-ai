"""Health and readiness evaluation logic, kept out of route handlers.

`liveness` answers "is the process itself functioning" (always true if this code runs).
`readiness` answers "can this instance safely serve traffic" by checking critical
dependencies. The two are deliberately different: a process can be alive but not ready
(e.g., database briefly unreachable), and Phase 1 keeps that distinction real rather than
collapsing both into one check.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.redis_client import RedisClient

#: Environments where Redis is not provisioned (docs/HOSTED_DEPLOYMENT.md §7/§13) — the
#: hosted demo runs no worker processes and no reviewer-facing code path reads Redis
#: today, so it is a soft dependency there. Every other environment (including
#: `production`) keeps Redis required, matching existing intended behavior.
_REDIS_OPTIONAL_ENVIRONMENTS = ("hosted_demo",)


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    healthy: bool
    required: bool


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    dependencies: list[DependencyStatus]


def check_liveness() -> bool:
    return True


async def check_readiness(
    database: Database, redis_client: RedisClient, settings: Settings
) -> ReadinessResult:
    redis_required = settings.app_env not in _REDIS_OPTIONAL_ENVIRONMENTS
    dependencies = [
        DependencyStatus(
            name="database", healthy=await database.check_connection(), required=True
        ),
        DependencyStatus(
            name="redis",
            healthy=await redis_client.check_connection(),
            required=redis_required,
        ),
    ]
    ready = all(dep.healthy for dep in dependencies if dep.required)
    return ReadinessResult(ready=ready, dependencies=dependencies)

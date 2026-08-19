"""`ToolContext` — everything a tool function needs, bundled once per `AgentService.chat`
call rather than threaded through individually."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ToolContext:
    session: AsyncSession
    tenant_id: uuid.UUID

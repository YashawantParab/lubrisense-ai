"""`AgentSession` repository — tenant-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AgentSession


class AgentSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, agent_session: AgentSession) -> AgentSession:
        self.session.add(agent_session)
        await self.session.flush()
        await self.session.refresh(agent_session)
        return agent_session

    async def get(self, tenant_id: uuid.UUID, session_id: uuid.UUID) -> AgentSession | None:
        result = await self.session.execute(
            select(AgentSession).where(
                AgentSession.tenant_id == tenant_id, AgentSession.id == session_id
            )
        )
        return result.scalar_one_or_none()

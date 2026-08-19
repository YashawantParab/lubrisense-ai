"""`AgentMessage` repository — tenant-scoped, append-only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AgentMessage


class AgentMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, message: AgentMessage) -> AgentMessage:
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def list_for_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[AgentMessage]:
        result = await self.session.execute(
            select(AgentMessage)
            .where(AgentMessage.tenant_id == tenant_id, AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at)
        )
        return list(result.scalars().all())

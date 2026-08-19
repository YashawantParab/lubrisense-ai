"""`AgentToolCall` repository — tenant-scoped, append-only audit trail (Phase 19 brief
§19.10)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AgentToolCall


class AgentToolCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, tool_call: AgentToolCall) -> AgentToolCall:
        self.session.add(tool_call)
        await self.session.flush()
        await self.session.refresh(tool_call)
        return tool_call

    async def list_for_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[AgentToolCall]:
        result = await self.session.execute(
            select(AgentToolCall)
            .where(AgentToolCall.tenant_id == tenant_id, AgentToolCall.session_id == session_id)
            .order_by(AgentToolCall.created_at)
        )
        return list(result.scalars().all())

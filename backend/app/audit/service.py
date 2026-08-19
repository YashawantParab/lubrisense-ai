"""`AuditService.record()` — the single write path for `AuditEvent` (Phase 25 brief
§25.1/§25.4). No update/delete method exists anywhere in this package."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.repository import AuditEventRepository
from app.auth.models import Principal
from app.core.context import get_correlation_id
from app.domain.enums import AuditActorType
from app.domain.models import AuditEvent


@dataclass(frozen=True)
class AuditActor:
    actor_id: str
    actor_type: AuditActorType
    role: str | None = None

    @classmethod
    def from_principal(cls, principal: Principal) -> AuditActor:
        return cls(
            actor_id=principal.user_id,
            actor_type=principal.actor_type,
            role=principal.role.value,
        )

    @classmethod
    def system(cls, actor_id: str) -> AuditActor:
        return cls(actor_id=actor_id, actor_type=AuditActorType.SYSTEM, role=None)

    @classmethod
    def agent(cls, actor_id: str) -> AuditActor:
        return cls(actor_id=actor_id, actor_type=AuditActorType.AGENT, role=None)


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditEventRepository(session)

    async def record(
        self,
        tenant_id: uuid.UUID,
        *,
        actor: AuditActor,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | str,
        source: str,
        before_summary: str | None = None,
        after_summary: str | None = None,
        reason: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            role=actor.role,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            correlation_id=correlation_id or get_correlation_id() or "unknown",
            request_id=request_id,
            before_summary=before_summary,
            after_summary=after_summary,
            reason=reason,
            source=source,
            occurred_at=datetime.now(UTC),
        )
        return await self._repo.add(event)

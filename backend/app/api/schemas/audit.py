from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AuditActorType


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: str
    actor_type: AuditActorType
    role: str | None
    action: str
    entity_type: str
    entity_id: str
    correlation_id: str
    request_id: str | None
    before_summary: str | None
    after_summary: str | None
    reason: str | None
    source: str
    occurred_at: datetime
    created_at: datetime

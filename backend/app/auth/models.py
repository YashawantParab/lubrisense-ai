"""Authenticated identity — the value every request handler and service ultimately
receives, regardless of how the identity was established."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.enums import AuditActorType, UserRole


@dataclass(frozen=True)
class Principal:
    """The authenticated identity for one request.

    `actor_type` is almost always `HUMAN` for anything reaching this dataclass (a real
    person via a demo-issued token, or the backward-compatible fallback principal — see
    `app.api.deps.get_current_principal`). `SYSTEM`/`AGENT` actor types are used directly
    by `app.audit.service.AuditService` for events the API layer did not originate (a
    worker cycle, or the guarded agent preparing a draft) — see `docs/AUDITABILITY.md`.
    """

    user_id: str
    tenant_id: uuid.UUID
    role: UserRole
    display_name: str
    actor_type: AuditActorType = AuditActorType.HUMAN

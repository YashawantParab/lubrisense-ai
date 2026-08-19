from __future__ import annotations

from app.domain.models import CommissioningSession
from app.repositories.base import TenantScopedRepository


class CommissioningSessionRepository(TenantScopedRepository[CommissioningSession]):
    model = CommissioningSession

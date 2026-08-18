from __future__ import annotations

from app.domain.models import LubricationPoint
from app.repositories.base import TenantScopedRepository


class LubricationPointRepository(TenantScopedRepository[LubricationPoint]):
    model = LubricationPoint

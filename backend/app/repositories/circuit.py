from __future__ import annotations

from app.domain.models import Circuit
from app.repositories.base import TenantScopedRepository


class CircuitRepository(TenantScopedRepository[Circuit]):
    model = Circuit

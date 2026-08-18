from __future__ import annotations

from app.domain.models import Gateway
from app.repositories.base import TenantScopedRepository


class GatewayRepository(TenantScopedRepository[Gateway]):
    model = Gateway

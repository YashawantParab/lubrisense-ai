"""AssetHierarchyService — the full Customer -> Site -> Plant -> ProductionLine -> Machine
tree for one tenant, in the shape the hierarchy navigation UI needs.

Deliberately shallow: it stops at Machine and does not include bearings/lubrication
systems/sensors — that detail belongs to the machine-hierarchy endpoint
(MachineService.get_hierarchy) once a user has drilled into a specific machine. Returning
the full equipment tree for every machine in the fleet from this endpoint would not scale
(see docs/ASSET_HIERARCHY.md §"Performance").
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import CustomerAccount
from app.repositories.customer_account import CustomerAccountRepository


class AssetHierarchyService:
    def __init__(self, session: AsyncSession) -> None:
        self._customers = CustomerAccountRepository(session)

    async def get_full_hierarchy(self, tenant_id: uuid.UUID) -> list[CustomerAccount]:
        return await self._customers.list_with_full_hierarchy(tenant_id)

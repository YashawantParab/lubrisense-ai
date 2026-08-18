"""MachineRepository.

`get_with_equipment` is the one place in the repository layer that departs from plain
CRUD: the machine-hierarchy endpoint (docs/ASSET_HIERARCHY.md) needs a machine's bearings
and full lubrication-system chain (reservoirs/pumps/controllers/distributors/circuits/
lubrication points) in one round trip. It uses `selectinload` chains deliberately — see
TECHNICAL_DECISIONS.md (hierarchy query/loading strategy ADR) for why, and what an N+1
query would have looked like instead.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models import Circuit, LubricationSystem, Machine
from app.repositories.base import TenantScopedRepository


class MachineRepository(TenantScopedRepository[Machine]):
    model = Machine

    async def get_by_asset_code(self, tenant_id: uuid.UUID, asset_code: str) -> Machine | None:
        stmt = select(Machine).where(
            Machine.tenant_id == tenant_id, Machine.asset_code == asset_code
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_equipment(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> Machine | None:
        lubrication_systems = selectinload(Machine.lubrication_systems)
        stmt = (
            select(Machine)
            .where(Machine.tenant_id == tenant_id, Machine.id == machine_id)
            .options(
                selectinload(Machine.bearings),
                lubrication_systems.selectinload(LubricationSystem.reservoirs),
                lubrication_systems.selectinload(LubricationSystem.pumps),
                lubrication_systems.selectinload(LubricationSystem.controllers),
                lubrication_systems.selectinload(LubricationSystem.distributors),
                lubrication_systems.selectinload(LubricationSystem.circuits).selectinload(
                    Circuit.lubrication_points
                ),
            )
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

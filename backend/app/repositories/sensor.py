from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import or_, select

from app.domain.enums import SensorType
from app.domain.models import Sensor
from app.repositories.base import TenantScopedRepository


class SensorRepository(TenantScopedRepository[Sensor]):
    model = Sensor

    async def get_by_sensor_code(self, tenant_id: uuid.UUID, sensor_code: str) -> Sensor | None:
        stmt = select(Sensor).where(
            Sensor.tenant_id == tenant_id, Sensor.sensor_code == sensor_code
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_machine_and_type(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID, sensor_type: SensorType
    ) -> Sensor | None:
        """The one machine-direct sensor of this type, if any (e.g. `MACHINE_POWER`,
        `RPM` — attached via `Sensor.machine_id`, not through a bearing/lubrication-system
        component). Returns the lowest `id` if more than one somehow exists, the same
        deterministic-tiebreak convention `BaselineEngine.refresh_machine_cycle` already
        uses for its own representative-sensor choice."""
        stmt = (
            select(Sensor)
            .where(
                Sensor.tenant_id == tenant_id,
                Sensor.machine_id == machine_id,
                Sensor.sensor_type == sensor_type,
            )
            .order_by(Sensor.id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_ids(
        self, tenant_id: uuid.UUID, sensor_ids: Iterable[uuid.UUID]
    ) -> list[Sensor]:
        """Bulk lookup for read models that already have a set of sensor IDs from another
        source (e.g. `SensorQualityStateRepository.list_for_tenant`) and need the sensor's
        own metadata (code/name/type) without one query per sensor."""
        ids = list(sensor_ids)
        if not ids:
            return []
        stmt = select(Sensor).where(Sensor.tenant_id == tenant_id, Sensor.id.in_(ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_attached_to(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_ids: Iterable[uuid.UUID] = (),
        bearing_ids: Iterable[uuid.UUID] = (),
        lubrication_system_ids: Iterable[uuid.UUID] = (),
        reservoir_ids: Iterable[uuid.UUID] = (),
        pump_ids: Iterable[uuid.UUID] = (),
        circuit_ids: Iterable[uuid.UUID] = (),
    ) -> list[Sensor]:
        """All sensors attached to any of the given entities, across the six attachment
        columns (see docs/ASSET_HIERARCHY.md — sensor attachment strategy). Used to
        assemble a machine's full sensor inventory, since sensors relate to a machine
        through several different physical entities, not a single foreign key."""
        machine_ids, bearing_ids = list(machine_ids), list(bearing_ids)
        lubrication_system_ids, reservoir_ids = list(lubrication_system_ids), list(reservoir_ids)
        pump_ids, circuit_ids = list(pump_ids), list(circuit_ids)

        clauses = []
        if machine_ids:
            clauses.append(Sensor.machine_id.in_(machine_ids))
        if bearing_ids:
            clauses.append(Sensor.bearing_id.in_(bearing_ids))
        if lubrication_system_ids:
            clauses.append(Sensor.lubrication_system_id.in_(lubrication_system_ids))
        if reservoir_ids:
            clauses.append(Sensor.reservoir_id.in_(reservoir_ids))
        if pump_ids:
            clauses.append(Sensor.pump_id.in_(pump_ids))
        if circuit_ids:
            clauses.append(Sensor.circuit_id.in_(circuit_ids))

        if not clauses:
            return []

        stmt = select(Sensor).where(Sensor.tenant_id == tenant_id, or_(*clauses))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

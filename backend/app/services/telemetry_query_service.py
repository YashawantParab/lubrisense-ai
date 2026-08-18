"""Read-only telemetry query service (Phase 6 brief §30/§31).

Confirms the target sensor/machine actually exists for the tenant before querying
`telemetry` — an empty result for a real sensor with no readings yet is a normal, valid
response; querying a sensor/machine id that doesn't exist for this tenant is a 404, not an
empty list, so a caller can tell the difference.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SensorType
from app.domain.models import Telemetry
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.repositories.telemetry import TelemetryRepository
from app.services.errors import NotFoundError


class TelemetryQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._telemetry_repo = TelemetryRepository(session)
        self._sensor_repo = SensorRepository(session)
        self._machine_repo = MachineRepository(session)

    async def get_by_sensor(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        measurement_type: SensorType | None,
        limit: int,
    ) -> list[Telemetry]:
        sensor = await self._sensor_repo.get(tenant_id, sensor_id)
        if sensor is None:
            raise NotFoundError("SENSOR_NOT_FOUND", "Sensor not found.")
        return await self._telemetry_repo.get_by_sensor_time_range(
            tenant_id,
            sensor_id,
            start=start,
            end=end,
            measurement_type=measurement_type,
            limit=limit,
        )

    async def get_latest_by_sensor(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> Telemetry | None:
        sensor = await self._sensor_repo.get(tenant_id, sensor_id)
        if sensor is None:
            raise NotFoundError("SENSOR_NOT_FOUND", "Sensor not found.")
        return await self._telemetry_repo.get_latest_by_sensor(tenant_id, sensor_id)

    async def get_by_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime | None,
        end: datetime | None,
        measurement_type: SensorType | None,
        limit: int,
    ) -> list[Telemetry]:
        machine = await self._machine_repo.get(tenant_id, machine_id)
        if machine is None:
            raise NotFoundError("MACHINE_NOT_FOUND", "Machine not found.")
        return await self._telemetry_repo.get_by_machine_time_range(
            tenant_id,
            machine_id,
            start=start,
            end=end,
            measurement_type=measurement_type,
            limit=limit,
        )

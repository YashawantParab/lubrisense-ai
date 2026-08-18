from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import SensorStatus, SensorType
from app.domain.models import Sensor
from app.repositories.pagination import Page, PageParams
from app.repositories.sensor import SensorRepository
from app.services.errors import NotFoundError


@dataclass(frozen=True)
class SensorFilters:
    sensor_type: SensorType | None = None
    status: SensorStatus | None = None


class SensorService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SensorRepository(session)

    async def get(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> Sensor:
        sensor = await self._repo.get(tenant_id, sensor_id)
        if sensor is None:
            raise NotFoundError("SENSOR_NOT_FOUND", "Sensor not found.")
        return sensor

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        params: PageParams | None = None,
        filters: SensorFilters | None = None,
    ) -> Page[Sensor]:
        clauses = []
        if filters is not None:
            if filters.sensor_type is not None:
                clauses.append(Sensor.sensor_type == filters.sensor_type)
            if filters.status is not None:
                clauses.append(Sensor.status == filters.status)
        return await self._repo.list(tenant_id, params=params, filters=clauses)

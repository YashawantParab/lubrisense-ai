"""Backs `app/api/v1/baselines.py` (Phase 8 brief §32) — tenant-scoped read access to
baseline profiles, current-baseline resolution + deviation, and readiness summaries.
Mirrors `app.data_quality.services.quality_query_service.QualityQueryService`'s shape.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext
from app.baselines.repositories.baseline_profile_repository import BaselineProfileRepository
from app.baselines.services.deviation_service import DeviationLookup, evaluate
from app.baselines.services.summary_service import BaselineSummaryService, Readiness
from app.domain.models import BaselineProfile, Sensor
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository


class SensorNotFoundError(Exception):
    pass


class MachineNotFoundError(Exception):
    pass


class BaselineQueryService:
    def __init__(self, session: AsyncSession, policy: BaselinePolicy) -> None:
        self.session = session
        self.policy = policy
        self._profile_repo = BaselineProfileRepository(session)
        self._sensor_repo = SensorRepository(session)
        self._machine_repo = MachineRepository(session)
        self._summary = BaselineSummaryService(session)

    async def _get_sensor(self, tenant_id: uuid.UUID, sensor_id: uuid.UUID) -> Sensor:
        sensor = await self._sensor_repo.get(tenant_id, sensor_id)
        if sensor is None:
            raise SensorNotFoundError(str(sensor_id))
        return sensor

    async def list_for_sensor(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> tuple[list[BaselineProfile], Readiness]:
        await self._get_sensor(tenant_id, sensor_id)
        profiles = await self._profile_repo.list_current_for_sensor(tenant_id, sensor_id)
        readiness = await self._summary.sensor_readiness(tenant_id, sensor_id)
        return profiles, readiness

    async def get_current(
        self,
        tenant_id: uuid.UUID,
        sensor_id: uuid.UUID,
        *,
        operating_state: str | None,
        cycle_phase: str | None,
        value: float | None,
    ) -> DeviationLookup:
        sensor = await self._get_sensor(tenant_id, sensor_id)
        context = BaselineContext(operating_state=operating_state, cycle_phase=cycle_phase)
        return await evaluate(self.session, self.policy, tenant_id, sensor, context, value)

    async def list_for_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> tuple[list[BaselineProfile], Readiness]:
        machine = await self._machine_repo.get(tenant_id, machine_id)
        if machine is None:
            raise MachineNotFoundError(str(machine_id))
        profiles = await self._profile_repo.list_current_for_machine(tenant_id, machine_id)
        readiness = await self._summary.machine_readiness(tenant_id, machine_id)
        return profiles, readiness

    async def tenant_summary(self, tenant_id: uuid.UUID) -> dict[str, int]:
        return await self._summary.tenant_summary(tenant_id)

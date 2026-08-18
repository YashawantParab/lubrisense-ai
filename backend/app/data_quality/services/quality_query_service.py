"""Read-only query service backing `app/api/v1/data_quality.py` (Phase 7 brief §32-§34).

Same not-found-vs-empty-result convention as `TelemetryQueryService` (Phase 6): querying a
sensor/machine that doesn't exist for this tenant is a 404, not an empty/default response.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import IssueSeverity, IssueStatus
from app.domain.models import QualityIssue, SensorQualityState
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.services.errors import NotFoundError


class QualityQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._state_repo = SensorQualityStateRepository(session)
        self._issue_repo = QualityIssueRepository(session)
        self._sensor_repo = SensorRepository(session)
        self._machine_repo = MachineRepository(session)

    async def get_sensor_state(
        self, tenant_id: uuid.UUID, sensor_id: uuid.UUID
    ) -> tuple[SensorQualityState | None, list[QualityIssue]]:
        """`None` state with a sensor that legitimately exists but has never been observed
        yet is a valid response, distinct from a 404 for a sensor that doesn't exist at
        all."""
        sensor = await self._sensor_repo.get(tenant_id, sensor_id)
        if sensor is None:
            raise NotFoundError("SENSOR_NOT_FOUND", "Sensor not found.")
        state = await self._state_repo.get(tenant_id, sensor_id)
        issues = await self._issue_repo.list_issues(
            tenant_id, sensor_id=sensor_id, status=IssueStatus.ACTIVE, limit=100
        )
        recovering = await self._issue_repo.list_issues(
            tenant_id, sensor_id=sensor_id, status=IssueStatus.RECOVERING, limit=100
        )
        return state, issues + recovering

    async def get_machine_summary(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> tuple[list[SensorQualityState], list[QualityIssue]]:
        machine = await self._machine_repo.get(tenant_id, machine_id)
        if machine is None:
            raise NotFoundError("MACHINE_NOT_FOUND", "Machine not found.")
        states = await self._state_repo.list_for_machine(tenant_id, machine_id)
        issues = await self._issue_repo.list_issues(
            tenant_id, machine_id=machine_id, status=IssueStatus.ACTIVE, limit=200
        )
        return states, issues

    async def list_issues(
        self,
        tenant_id: uuid.UUID,
        *,
        sensor_id: uuid.UUID | None = None,
        machine_id: uuid.UUID | None = None,
        severity: IssueSeverity | None = None,
        status: IssueStatus | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[QualityIssue]:
        return await self._issue_repo.list_issues(
            tenant_id,
            sensor_id=sensor_id,
            machine_id=machine_id,
            severity=severity,
            status=status,
            start=start,
            end=end,
            limit=limit,
        )

    async def get_tenant_summary(self, tenant_id: uuid.UUID) -> dict[str, object]:
        sensor_counts = await self._state_repo.count_by_state(tenant_id)
        issue_counts = await self._issue_repo.count_active_by_severity(tenant_id)
        return {
            "sensors_by_quality_state": sensor_counts,
            "active_issues_by_severity": issue_counts,
            "total_sensors_tracked": sum(sensor_counts.values()),
            "total_active_issues": sum(issue_counts.values()),
        }

"""Read-only query service backing `app/api/v1/data_quality.py` (Phase 7 brief §32-§34).

Same not-found-vs-empty-result convention as `TelemetryQueryService` (Phase 6): querying a
sensor/machine that doesn't exist for this tenant is a 404, not an empty/default response.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.config.policy import QualityPolicy, load_quality_policy
from app.data_quality.repositories.quality_issue_repository import QualityIssueRepository
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import Eligibility, IssueSeverity, IssueStatus, QualityState
from app.domain.models import QualityIssue, Sensor, SensorQualityState
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.services.errors import NotFoundError


@lru_cache(maxsize=1)
def _cached_quality_policy() -> QualityPolicy:
    """The policy file is read-only, versioned config (`policy_version` is what actually
    changes between revisions, not this process's view of the file) — re-parsing the same
    YAML on every fleet-list request would be pure overhead. A process restart picks up a
    changed `DATA_QUALITY_POLICY_PATH`/file, same as every other cached-settings pattern in
    this codebase (`app.core.config.get_settings`)."""
    return load_quality_policy()


@dataclass(frozen=True)
class SensorQualityRecord:
    """One sensor's current trust state joined with its own metadata and active
    issue(s) — the read model the fleet-wide Data Quality page needs and the per-issue
    `quality_issue` table alone cannot answer (a fully trusted sensor has no issue row at
    all)."""

    sensor: Sensor
    state: SensorQualityState
    active_issues: list[QualityIssue]
    expected_reporting_interval_seconds: float | None


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

    async def list_fleet_sensor_records(
        self,
        tenant_id: uuid.UUID,
        *,
        machine_id: uuid.UUID | None = None,
        quality_state: QualityState | None = None,
        eligibility: Eligibility | None = None,
        limit: int = 500,
    ) -> list[SensorQualityRecord]:
        """Every sensor this tenant has ever evaluated (Phase 7 §6 — `sensor_quality_state`
        is one continuously-upserted row per sensor, the only place the current state of a
        *trusted* sensor with no active issue lives), joined with its own metadata and
        active issue(s). This is the read model the fleet-wide Data Quality view needs and
        `list_issues` alone structurally cannot provide, since a fully trusted sensor never
        has an issue row at all."""
        states = await self._state_repo.list_for_tenant(tenant_id, limit=limit)
        if machine_id is not None:
            states = [s for s in states if s.machine_id == machine_id]
        if quality_state is not None:
            states = [s for s in states if s.quality_state == quality_state]
        if eligibility is not None:
            states = [s for s in states if s.eligibility == eligibility]
        if not states:
            return []

        sensor_ids = [s.sensor_id for s in states]
        sensors = await self._sensor_repo.list_by_ids(tenant_id, sensor_ids)
        sensors_by_id = {sensor.id: sensor for sensor in sensors}
        issues_by_sensor: dict[uuid.UUID, list[QualityIssue]] = {}
        for issue in await self._issue_repo.list_active_for_sensors(tenant_id, sensor_ids):
            issues_by_sensor.setdefault(issue.sensor_id, []).append(issue)

        policy = _cached_quality_policy()
        records: list[SensorQualityRecord] = []
        for state in states:
            sensor = sensors_by_id.get(state.sensor_id)
            if sensor is None:
                continue
            records.append(
                SensorQualityRecord(
                    sensor=sensor,
                    state=state,
                    active_issues=issues_by_sensor.get(state.sensor_id, []),
                    expected_reporting_interval_seconds=policy.expected_interval_seconds_for(
                        sensor.sensor_type.value
                    ),
                )
            )
        return records

    async def get_tenant_summary(self, tenant_id: uuid.UUID) -> dict[str, object]:
        sensor_counts = await self._state_repo.count_by_state(tenant_id)
        issue_counts = await self._issue_repo.count_active_by_severity(tenant_id)
        return {
            "sensors_by_quality_state": sensor_counts,
            "active_issues_by_severity": issue_counts,
            "total_sensors_tracked": sum(sensor_counts.values()),
            "total_active_issues": sum(issue_counts.values()),
        }

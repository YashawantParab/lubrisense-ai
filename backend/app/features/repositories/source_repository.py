"""Bulk source loading for one point-in-time feature vector."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import BaselineState, IssueStatus, RuleFindingState
from app.domain.models import (
    BaselineProfile,
    Bearing,
    Circuit,
    LubricationSystem,
    Machine,
    Pump,
    QualityIssue,
    Reservoir,
    RuleFinding,
    Sensor,
    SensorQualityState,
    Telemetry,
)
from app.features.domain.context import (
    BaselineSnapshot,
    FeatureContext,
    QualityIssueSnapshot,
    RuleSnapshot,
    SensorDescriptor,
    TelemetryPoint,
)


class FeatureSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_source_timestamp(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> datetime | None:
        result: datetime | None = await self.session.scalar(
            select(func.max(Telemetry.source_timestamp)).where(
                Telemetry.tenant_id == tenant_id, Telemetry.machine_id == machine_id
            )
        )
        return result

    async def load_context(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        *,
        start: datetime,
        as_of: datetime,
        maximum_rows: int,
    ) -> FeatureContext | None:
        machine = await self.session.scalar(
            select(Machine).where(Machine.tenant_id == tenant_id, Machine.id == machine_id)
        )
        if machine is None:
            return None

        sensors = await self._registered_sensors(tenant_id, machine_id)
        quality_rows = await self.session.execute(
            select(SensorQualityState).where(
                SensorQualityState.tenant_id == tenant_id,
                SensorQualityState.machine_id == machine_id,
            )
        )
        eligibility = {row.sensor_id: row.eligibility.value for row in quality_rows.scalars().all()}

        telemetry_result = await self.session.execute(
            select(Telemetry)
            .where(
                Telemetry.tenant_id == tenant_id,
                Telemetry.machine_id == machine_id,
                Telemetry.source_timestamp >= start,
                Telemetry.source_timestamp <= as_of,
            )
            # Keep the most recent bounded slice. Every downstream operation remains
            # event-time based and explicitly sorts the observations it needs.
            .order_by(
                Telemetry.source_timestamp.desc(),
                Telemetry.sensor_id.desc(),
                Telemetry.sequence_number.desc(),
            )
            .limit(maximum_rows)
        )
        telemetry = list(telemetry_result.scalars().all())
        points = tuple(
            TelemetryPoint(
                event_id=row.event_id,
                sensor_id=row.sensor_id,
                measurement_type=row.measurement_type.value,
                value=row.value,
                unit=row.unit,
                quality=row.quality.value,
                eligibility=eligibility.get(row.sensor_id, "INELIGIBLE"),
                source_timestamp=row.source_timestamp,
                edge_received_timestamp=row.edge_received_timestamp,
                operating_state=row.operating_state,
                firmware_version=row.firmware_version,
                controller_version=row.controller_version,
            )
            for row in telemetry
        )

        baseline_rows = await self.session.execute(
            select(BaselineProfile).where(
                BaselineProfile.tenant_id == tenant_id,
                BaselineProfile.machine_id == machine_id,
                BaselineProfile.state == BaselineState.ACTIVE,
                BaselineProfile.activated_at.is_not(None),
                BaselineProfile.activated_at <= as_of,
                or_(BaselineProfile.window_end.is_(None), BaselineProfile.window_end <= as_of),
            )
        )
        baselines = tuple(
            self._baseline_snapshot(row) for row in baseline_rows.scalars().all() if row.statistics
        )

        rule_rows = await self.session.execute(
            select(RuleFinding).where(
                RuleFinding.tenant_id == tenant_id,
                RuleFinding.machine_id == machine_id,
                RuleFinding.activated_at.is_not(None),
                RuleFinding.activated_at <= as_of,
                or_(RuleFinding.resolved_at.is_(None), RuleFinding.resolved_at > as_of),
                RuleFinding.state.in_((RuleFindingState.ACTIVE, RuleFindingState.RESOLVED)),
            )
        )
        rules = tuple(
            RuleSnapshot(
                finding_type=row.finding_type.value,
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                evidence_strength=row.evidence_strength.value,
                first_detected_at=row.first_detected_at,
            )
            for row in rule_rows.scalars().all()
        )

        issue_rows = await self.session.execute(
            select(QualityIssue).where(
                QualityIssue.tenant_id == tenant_id,
                QualityIssue.machine_id == machine_id,
                QualityIssue.first_seen <= as_of,
                or_(QualityIssue.window_end.is_(None), QualityIssue.window_end <= as_of),
                or_(QualityIssue.status != IssueStatus.RESOLVED, QualityIssue.resolved_at <= as_of),
            )
        )
        issues = tuple(
            QualityIssueSnapshot(
                issue_type=row.issue_type.value,
                evidence_timestamp=row.window_end or row.first_seen,
            )
            for row in issue_rows.scalars().all()
            if (row.window_end or row.first_seen) >= start
        )

        return FeatureContext(
            tenant_id=tenant_id,
            machine_id=machine_id,
            machine_type=machine.machine_type.value,
            criticality=machine.criticality.value,
            as_of_timestamp=as_of,
            sensors=tuple(
                SensorDescriptor(sensor_id=s.id, measurement_type=s.sensor_type.value)
                for s in sensors
            ),
            points=points,
            baselines=baselines,
            rules=rules,
            quality_issues=issues,
            telemetry_rows_scanned=len(telemetry),
        )

    async def _registered_sensors(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[Sensor]:
        bearing_ids = select(Bearing.id).where(
            Bearing.tenant_id == tenant_id, Bearing.machine_id == machine_id
        )
        system_ids = select(LubricationSystem.id).where(
            LubricationSystem.tenant_id == tenant_id, LubricationSystem.machine_id == machine_id
        )
        reservoir_ids = select(Reservoir.id).where(
            Reservoir.tenant_id == tenant_id, Reservoir.lubrication_system_id.in_(system_ids)
        )
        pump_ids = select(Pump.id).where(
            Pump.tenant_id == tenant_id, Pump.lubrication_system_id.in_(system_ids)
        )
        circuit_ids = select(Circuit.id).where(
            Circuit.tenant_id == tenant_id, Circuit.lubrication_system_id.in_(system_ids)
        )
        result = await self.session.execute(
            select(Sensor).where(
                Sensor.tenant_id == tenant_id,
                or_(
                    Sensor.machine_id == machine_id,
                    Sensor.bearing_id.in_(bearing_ids),
                    Sensor.lubrication_system_id.in_(system_ids),
                    Sensor.reservoir_id.in_(reservoir_ids),
                    Sensor.pump_id.in_(pump_ids),
                    Sensor.circuit_id.in_(circuit_ids),
                ),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _baseline_snapshot(row: BaselineProfile) -> BaselineSnapshot:
        if row.strategy.value == "CONTEXTUAL_ASSET_BASELINE":
            source_kind = "EXACT_CONTEXT"
        elif row.strategy.value == "ROLLING_ASSET_BASELINE":
            source_kind = "SENSOR_LEVEL"
        else:
            source_kind = "ENGINEERING_REFERENCE"
        return BaselineSnapshot(
            profile_id=row.id,
            sensor_id=row.sensor_id,
            measurement_type=row.measurement_type.value,
            strategy=row.strategy.value,
            source_kind=source_kind,
            version=row.version,
            config_version=row.config_version,
            metric_kind=row.metric_kind.value,
            context=row.context,
            statistics=row.statistics or {},
            window_end=row.window_end,
        )

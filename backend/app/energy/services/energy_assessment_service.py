"""On-demand energy-assessment orchestration (Lubrication Efficiency Intelligence, Pass
1 — docs/LUBRICATION_EFFICIENCY_INTELLIGENCE.md §4-§9, ADR-176), mirroring
`app.ml.services.ml_inference_service.MLInferenceOrchestrationService`'s own "compute
latest, persist, return" shape.

Builds no new expected-value algorithm: expected power comes directly from
`app.baselines.services.deviation_service.evaluate`, the exact same contextual-baseline
resolution + deviation classification every other baselined measurement type already
uses. This module only adds the residual arithmetic (`app.energy.domain.residual`) and
assessment-status bookkeeping around that real, reused evidence.

Deliberately excluded from this pass (see the design doc's own implementation
sequence): lubrication attribution, carbon estimation, maintenance-verification,
Condition/Decision Intelligence wiring. This service produces energy evidence only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import BaselinePolicy
from app.baselines.domain.context import BaselineContext
from app.baselines.domain.statistics import RobustStatistics
from app.baselines.services.deviation_service import evaluate as evaluate_deviation
from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import BaselineSourceKind, QualityState, SensorType
from app.domain.models import EnergyAssessment
from app.energy.domain.residual import compute_residual, determine_status
from app.energy.repositories.energy_assessment_repository import EnergyAssessmentRepository
from app.repositories.machine import MachineRepository
from app.repositories.sensor import SensorRepository
from app.repositories.telemetry import TelemetryRepository

#: Bumped only when this service's own computation logic changes (not when the
#: underlying baseline/quality data changes) — same convention as
#: `ConditionIntelligencePolicy.engine_version`, kept as a plain literal here rather than
#: a versioned policy file since this pass introduces no configurable thresholds of its
#: own (every threshold used is `app.baselines`' existing, already-versioned policy).
ENGINE_VERSION = "1"


class EnergyMachineNotFoundError(LookupError):
    pass


class EnergyPowerSensorNotFoundError(LookupError):
    """No `MACHINE_POWER` sensor is commissioned for this machine yet — a real
    commissioning-state fact, not a transient/quality problem, so it is raised rather
    than persisted as an `INSUFFICIENT_DATA` row (there is no valid `power_sensor_id` to
    record one against)."""


class EnergyAssessmentService:
    def __init__(self, session: AsyncSession, baseline_policy: BaselinePolicy) -> None:
        self._session = session
        self._policy = baseline_policy
        self._machines = MachineRepository(session)
        self._sensors = SensorRepository(session)
        self._telemetry = TelemetryRepository(session)
        self._quality_states = SensorQualityStateRepository(session)
        self._assessments = EnergyAssessmentRepository(session)

    async def assess_machine(self, tenant_id: uuid.UUID, machine_id: uuid.UUID) -> EnergyAssessment:
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise EnergyMachineNotFoundError(str(machine_id))

        sensor = await self._sensors.get_by_machine_and_type(
            tenant_id, machine_id, SensorType.MACHINE_POWER
        )
        if sensor is None:
            raise EnergyPowerSensorNotFoundError(str(machine_id))

        now = datetime.now(UTC)
        latest_reading = await self._telemetry.get_latest_by_sensor(tenant_id, sensor.id)
        quality_row = await self._quality_states.get(tenant_id, sensor.id)
        # Absent a `SensorQualityState` row at all (the data-quality worker has not yet
        # evaluated this sensor), default to TRUSTED — the same "trust by default absent
        # contrary evidence" convention `BaselineEngine.refresh_sensor` already uses for
        # `eligibility`.
        quality_state = (
            quality_row.quality_state if quality_row is not None else QualityState.TRUSTED
        )

        # Deliberately tracked separately from `actual_power_kw`: "no reading exists yet"
        # (INSUFFICIENT_DATA) and "a reading exists but is untrustworthy"
        # (DATA_QUALITY_LIMITED) are different real states `determine_status` must be
        # able to tell apart — collapsing both into "actual_power_kw is None" made the
        # latter unreachable (caught by this module's own test suite).
        has_power_reading = latest_reading is not None
        actual_power_kw = (
            latest_reading.value
            if latest_reading is not None and quality_state != QualityState.UNUSABLE
            else None
        )
        operating_state = latest_reading.operating_state if latest_reading is not None else None

        expected_power_kw: float | None = None
        expected_lower_kw: float | None = None
        expected_upper_kw: float | None = None
        residual_kw: float | None = None
        residual_pct: float | None = None
        baseline_profile_id: uuid.UUID | None = None

        deviation = None
        resolved_source = None
        if actual_power_kw is not None:
            lookup = await evaluate_deviation(
                self._session,
                self._policy,
                tenant_id,
                sensor,
                BaselineContext(operating_state=operating_state),
                actual_power_kw,
            )
            deviation = lookup.deviation
            resolved_source = lookup.resolved.source
            profile = lookup.resolved.profile
            if profile is not None and profile.statistics is not None:
                stats = RobustStatistics(**profile.statistics)
                expected_power_kw = stats.median
                expected_lower_kw = stats.p05
                expected_upper_kw = stats.p95
                baseline_profile_id = profile.id
                residual_kw, residual_pct = compute_residual(actual_power_kw, expected_power_kw)

        status = determine_status(
            has_power_reading=has_power_reading,
            quality_state=quality_state,
            deviation=deviation,
            residual_kw=residual_kw,
        )

        assessment = EnergyAssessment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            machine_id=machine_id,
            power_sensor_id=sensor.id,
            as_of_timestamp=now,
            actual_power_kw=actual_power_kw,
            expected_power_kw=expected_power_kw,
            expected_lower_kw=expected_lower_kw,
            expected_upper_kw=expected_upper_kw,
            residual_kw=residual_kw,
            residual_pct=residual_pct,
            status=status,
            data_quality_state=quality_state,
            baseline_source=resolved_source or BaselineSourceKind.NONE,
            baseline_profile_id=baseline_profile_id,
            operating_state=operating_state,
            engine_version=ENGINE_VERSION,
        )
        await self._assessments.insert(assessment)
        await self._session.commit()
        return assessment

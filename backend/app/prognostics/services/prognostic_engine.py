"""`PrognosticEngine` — extrapolates real, already-persisted Phase 12 `StateEstimate`
history into a forward-looking forecast per `(state_type, horizon)` (Phase 15 brief).
Never reads `simulator` or any future/ground-truth value — only historical/current
inference-time data, exactly like every other intelligence layer in this platform.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PrognosticAssessment, StateEstimate
from app.prognostics.config.policy import PrognosticsPolicy, load_prognostics_policy
from app.prognostics.domain.models import StateEstimateSnapshot
from app.prognostics.observability import METRICS
from app.prognostics.repositories.prognostic_assessment_repository import (
    PrognosticAssessmentRepository,
)
from app.prognostics.services.forecast import forecast_one
from app.repositories.machine import MachineRepository
from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository


class PrognosticEngineMachineNotFoundError(LookupError):
    pass


def _snapshot(row: StateEstimate) -> StateEstimateSnapshot:
    return StateEstimateSnapshot(
        id=row.id,
        state_type=row.state_type.value,
        as_of_timestamp=row.as_of_timestamp,
        level=row.state_value,
        rate=row.state_rate,
        trend=row.trend.value,
        uncertainty=row.uncertainty.value,
        prediction_only=row.prediction_only,
    )


class PrognosticEngine:
    def __init__(self, session: AsyncSession, policy: PrognosticsPolicy | None = None) -> None:
        self._session = session
        self._policy = policy or load_prognostics_policy()
        self._machines = MachineRepository(session)
        self._state_estimates = StateEstimateRepository(session)
        self._assessments = PrognosticAssessmentRepository(session)
        self._state_config = load_state_estimation_config()

    async def forecast_machine(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> list[PrognosticAssessment]:
        machine = await self._machines.get(tenant_id, machine_id)
        if machine is None:
            raise PrognosticEngineMachineNotFoundError(str(machine_id))

        now = datetime.now(UTC)
        results: list[PrognosticAssessment] = []
        for state_type in self._state_config.states:
            current_row = await self._state_estimates.get_latest(
                tenant_id, machine_id, state_type, self._state_config.estimator_version
            )
            if current_row is None:
                continue
            history_rows = await self._state_estimates.list_for_machine(
                tenant_id, machine_id, state_type=state_type, limit=10
            )
            history = [_snapshot(row) for row in history_rows if row.id != current_row.id][:5]
            current = _snapshot(current_row)

            for horizon_name, horizon_seconds in self._policy.horizons.items():
                forecast = forecast_one(current, history, horizon_seconds, self._policy)
                crossing_time = (
                    now + timedelta(seconds=forecast.threshold_crossing_seconds)
                    if forecast.threshold_crossing_seconds is not None
                    else None
                )
                assessment = PrognosticAssessment(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    machine_id=machine_id,
                    component_id=None,
                    state_estimate_id=current_row.id,
                    state_type=state_type,
                    horizon=horizon_name,
                    status=forecast.status,
                    as_of_timestamp=now,
                    current_state=current.level,
                    trend=current.trend,
                    predicted_state_at_horizon=forecast.predicted_state_at_horizon,
                    estimated_threshold_crossing_time=crossing_time,
                    uncertainty=forecast.uncertainty,
                    data_sufficient=forecast.data_sufficient,
                    limitations=list(forecast.limitations),
                    engine_version=self._policy.engine_version,
                    config_version=self._policy.config_version,
                )
                persisted = await self._assessments.insert(assessment)
                results.append(persisted)
                METRICS.increment("prognostic_assessments_created")
                if forecast.status == "NO_RELIABLE_FORECAST":
                    METRICS.increment("prognostic_no_reliable_forecast")
        return results

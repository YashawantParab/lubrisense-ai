"""On-demand state-estimation orchestration (Phase 12 brief §18), mirroring
`app.ml.services.ml_inference_service.MLInferenceOrchestrationService`'s "latest" pattern:
compute the current Phase 10 `STATE_ESTIMATION_V1` feature vector, load each state type's
prior posterior (if any), run its filter, persist, return.

This is the ONLY place backend code builds a `StateEstimator` for the online path — filter
math never lives in an API route handler (mirrors ADR-011's rule for `ml_service`).
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import StateType
from app.domain.models import StateEstimate
from app.features.config.policy import FeaturePolicy
from app.features.domain.models import FeatureComputationResult
from app.features.services.feature_engine import FeatureEngine, FeatureMachineNotFoundError
from app.state_estimation.config.policy import StateEstimationConfig, load_state_estimation_config
from app.state_estimation.domain.models import PriorEstimate
from app.state_estimation.models.estimator import FeatureTick, StateEstimator
from app.state_estimation.observability import METRICS
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

_STATE_TYPES: tuple[str, ...] = tuple(member.value for member in StateType)


class StateEstimationMachineNotFoundError(LookupError):
    pass


def _feature_tick(computed: FeatureComputationResult) -> FeatureTick:
    quality_state = str(computed.quality_summary.get("state", "NO_TRUSTED_DATA"))
    return FeatureTick(
        tenant_id=computed.tenant_id,
        machine_id=computed.machine_id,
        feature_vector_id=computed.feature_vector_id,
        feature_set=computed.feature_set,
        feature_set_version=computed.feature_set_version,
        as_of_timestamp=computed.as_of_timestamp,
        feature_values=computed.feature_values,
        missing_features=computed.missing_features,
        quality_state=quality_state,
    )


def _prior_from_row(row: StateEstimate | None) -> PriorEstimate | None:
    if row is None:
        return None
    covariance = row.covariance_summary
    return PriorEstimate(
        as_of_timestamp=row.as_of_timestamp,
        level=row.state_value,
        rate=row.state_rate,
        p00=float(covariance["p00"]),
        p01=float(covariance["p01"]),
        p11=float(covariance["p11"]),
    )


class StateEstimationService:
    def __init__(
        self,
        session: AsyncSession,
        feature_policy: FeaturePolicy,
        config: StateEstimationConfig | None = None,
    ) -> None:
        self._session = session
        self._feature_engine = FeatureEngine(session, feature_policy)
        self._repo = StateEstimateRepository(session)
        self._config = config or load_state_estimation_config()

    def _estimator_for(self, state_type: str) -> StateEstimator:
        state_config = self._config.state_config(state_type)
        return StateEstimator(
            estimator_id=state_type,
            estimator_version=self._config.estimator_version,
            config_version=self._config.config_version,
            state_type=state_type,
            config=state_config,
            gap=self._config.gap,
            uncertainty=self._config.uncertainty,
        )

    async def compute_and_persist_latest(
        self, tenant_id: uuid.UUID, machine_id: uuid.UUID
    ) -> dict[str, StateEstimate]:
        started = time.perf_counter()
        try:
            computed = await self._feature_engine.compute_latest(
                tenant_id, machine_id, self._config.feature_set
            )
        except FeatureMachineNotFoundError as exc:
            METRICS.increment("state_estimation_failures")
            raise StateEstimationMachineNotFoundError(str(machine_id)) from exc
        tick = _feature_tick(computed)
        if tick.quality_state == "CAUTION":
            METRICS.increment("quality_suppressed_observations")

        results: dict[str, StateEstimate] = {}
        try:
            for state_type in _STATE_TYPES:
                prior_row = await self._repo.get_latest(
                    tenant_id, machine_id, state_type, self._config.estimator_version
                )
                prior = _prior_from_row(prior_row)
                estimator = self._estimator_for(state_type)
                result = estimator.step(prior, tick)
                row, _inserted = await self._repo.persist(result)
                results[state_type] = row
                METRICS.increment("state_estimates_computed")
                if result.prediction_only:
                    METRICS.increment("prediction_only_updates")
                if result.uncertainty == "HIGH":
                    METRICS.increment("high_uncertainty_estimates")
        except Exception:
            METRICS.increment("state_estimation_failures")
            raise
        METRICS.set_gauge("state_estimation_duration_seconds", time.perf_counter() - started)
        return results

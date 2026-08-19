"""Historical replay (Phase 12 brief §19): runs the same sequential filter used by
`StateEstimationService`'s online "latest" path, but over an ordered sequence of already-
materialized Phase 10 `STATE_ESTIMATION_V1` feature vectors instead of one on-demand
computation. Unlike Phase 10/11's stateless, embarrassingly-parallel point-in-time
recomputation, this MUST process ticks in ascending time order — each step's prior depends
on the previous step's posterior (see the corresponding ADR in TECHNICAL_DECISIONS.md).

Never reads `simulator` or any ground-truth field — only `FeatureVector` rows already
persisted by Phase 10's own (unchanged) materialization pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import StateType
from app.domain.models import FeatureVector, StateEstimate
from app.features.repositories.feature_repository import FeatureRepository
from app.state_estimation.config.policy import StateEstimationConfig, load_state_estimation_config
from app.state_estimation.domain.models import PriorEstimate
from app.state_estimation.models.estimator import FeatureTick, StateEstimator
from app.state_estimation.repositories.state_estimate_repository import StateEstimateRepository

_STATE_TYPES: tuple[str, ...] = tuple(member.value for member in StateType)


def _tick_from_vector(vector: FeatureVector) -> FeatureTick:
    quality_state = str(vector.quality_summary.get("state", "NO_TRUSTED_DATA"))
    return FeatureTick(
        tenant_id=vector.tenant_id,
        machine_id=vector.machine_id,
        feature_vector_id=vector.id,
        feature_set=vector.feature_set,
        feature_set_version=vector.feature_set_version,
        as_of_timestamp=vector.as_of_timestamp,
        feature_values=vector.feature_values,
        missing_features=vector.missing_features,
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


class ReplayService:
    def __init__(self, session: AsyncSession, config: StateEstimationConfig | None = None) -> None:
        self._session = session
        self._feature_vectors = FeatureRepository(session)
        self._estimates = StateEstimateRepository(session)
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

    async def replay_machine(
        self,
        tenant_id: uuid.UUID,
        machine_id: uuid.UUID,
        start: datetime,
        end: datetime,
        *,
        limit: int = 1000,
    ) -> dict[str, int]:
        """Replays every persisted `STATE_ESTIMATION_V1` vector for one machine in
        `[start, end]`, ascending. Returns `{state_type: estimates_persisted}`."""
        vectors = await self._feature_vectors.list_for_machine(
            tenant_id,
            machine_id,
            feature_set=self._config.feature_set,
            start=start,
            end=end,
            limit=limit,
        )
        ordered = sorted(vectors, key=lambda v: v.as_of_timestamp)

        counts: dict[str, int] = {}
        for state_type in _STATE_TYPES:
            estimator = self._estimator_for(state_type)
            db_prior_row = await self._estimates.get_latest(
                tenant_id, machine_id, state_type, self._config.estimator_version
            )
            prior = _prior_from_row(db_prior_row)
            if (
                prior is not None
                and ordered
                and prior.as_of_timestamp >= ordered[0].as_of_timestamp
            ):
                # A persisted prior at or after this window's first tick would produce a
                # non-positive dt for the first step — start this replay fresh instead of
                # silently feeding the filter a backwards-in-time gap.
                prior = None

            inserted = 0
            for vector in ordered:
                tick = _tick_from_vector(vector)
                result = estimator.step(prior, tick)
                _row, was_inserted = await self._estimates.persist(result)
                prior = result.to_prior()
                if was_inserted:
                    inserted += 1
            counts[state_type] = inserted
        return counts

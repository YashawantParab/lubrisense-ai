"""`StateEstimator` — wires the pure Kalman math in `app.state_estimation.models.kalman` to
one state type's configuration and one tick's Phase 10 feature vector (Phase 12 brief §2,
§6). This is the ONLY module that turns a raw `*.robust_deviation` feature into a Kalman
observation `z`/`R` pair — the calibration transform described in
`state_estimation_v1.yaml`'s comments and docs/STATE_ESTIMATION.md "Observation model".

Ground-truth boundary (Phase 12 brief §1): this module's only inputs are a `PriorEstimate`
(this estimator's own prior output) and a Phase 10 feature-vector-shaped object
(`feature_values`/`missing_features`/`quality_summary`/`as_of_timestamp`/...). It has no
import of `simulator` and no parameter through which simulator hidden state could enter —
enforced structurally, and checked by
`tests/state_estimation/test_ground_truth_leakage.py`.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.state_estimation.config.policy import GapPolicy, StateTypeConfig, UncertaintyThresholds
from app.state_estimation.domain.models import PriorEstimate, StateEstimateResult
from app.state_estimation.models import kalman


@dataclass(frozen=True, slots=True)
class FeatureTick:
    """The minimal, label-free slice of one Phase 10 `FeatureComputationResult` the
    estimator actually needs — decoupled from `app.features`'s own dataclass so this
    package never imports it directly (kept import-light; the caller in
    `app.state_estimation.services` does the one-line field mapping)."""

    tenant_id: uuid.UUID
    machine_id: uuid.UUID
    feature_vector_id: uuid.UUID
    feature_set: str
    feature_set_version: str
    as_of_timestamp: datetime
    feature_values: Mapping[str, object]
    missing_features: Sequence[str]
    quality_state: str  # FeatureComputationResult.quality_summary["state"]


class StateEstimator:
    """Quality-aware update (Phase 12 brief §9) uses the feature vector's own aggregate
    `quality_summary.state` (`TRUSTED`/`CAUTION`/`NO_TRUSTED_DATA`, Phase 10's own
    vocabulary) to decide whether to inflate every present channel's R this tick, rather
    than a per-sensor eligibility Phase 10 does not currently expose per feature value —
    reusing Phase 10's own quality signal rather than re-deriving one (matching ADR-080's
    precedent: Phase 9/10 both reuse Phase 7/8 quality/baseline output directly instead of
    adding a parallel policy layer). A feature missing from `feature_values` already means
    Phase 10 itself suppressed an `INELIGIBLE` reading (`docs/FEATURE_ENGINEERING.md`), so
    `ELIGIBLE` vs. `ELIGIBLE_WITH_CAUTION` vs. `INELIGIBLE` (Phase 12 brief §9) maps onto
    present-and-TRUSTED / present-and-CAUTION / missing exactly, with no separate lookup
    needed here."""

    def __init__(
        self,
        *,
        estimator_id: str,
        estimator_version: str,
        config_version: str,
        state_type: str,
        config: StateTypeConfig,
        gap: GapPolicy,
        uncertainty: UncertaintyThresholds,
    ) -> None:
        self._estimator_id = estimator_id
        self._estimator_version = estimator_version
        self._config_version = config_version
        self._state_type = state_type
        self._config = config
        self._gap = gap
        self._uncertainty = uncertainty

    def _initial_kalman_state(self) -> kalman.State:
        return kalman.State(
            level=0.0,
            rate=0.0,
            p00=self._config.initial_level_variance,
            p01=0.0,
            p11=self._config.initial_rate_variance,
        )

    def _uncertainty_category(self, p00: float) -> str:
        if p00 <= self._uncertainty.low_max_variance:
            return "LOW"
        if p00 <= self._uncertainty.moderate_max_variance:
            return "MODERATE"
        return "HIGH"

    def _trend(self, rate: float, uncertainty_category: str) -> str:
        if uncertainty_category == "HIGH":
            return "UNKNOWN"
        if rate > self._config.trend_rate_threshold:
            return "DETERIORATING"
        if rate < -self._config.trend_rate_threshold:
            return "IMPROVING"
        return "STABLE"

    def step(self, prior: PriorEstimate | None, tick: FeatureTick) -> StateEstimateResult:
        # --- 1. dt / predict -------------------------------------------------------
        if prior is None:
            state = self._initial_kalman_state()
            dt_seconds = 0.0
            gap_since_prior = 0.0
        else:
            raw_dt = (tick.as_of_timestamp - prior.as_of_timestamp).total_seconds()
            gap_since_prior = max(raw_dt, 0.0)
            dt_seconds = min(max(raw_dt, self._gap.min_dt_seconds), self._gap.max_dt_seconds)
            prior_state = kalman.State(
                level=prior.level, rate=prior.rate, p00=prior.p00, p01=prior.p01, p11=prior.p11
            )
            rate_retention = math.exp(-dt_seconds / self._config.rate_decay_tau_seconds)
            state = kalman.predict(
                prior_state,
                dt_seconds,
                rate_retention,
                self._config.process_noise.q_level,
                self._config.process_noise.q_rate,
            )

        # --- 2. gather + apply available observation channels -----------------------
        used: list[str] = []
        missing: list[str] = []
        is_caution = tick.quality_state == "CAUTION"
        for channel in self._config.channels:
            if channel.feature_name in tick.missing_features:
                missing.append(channel.feature_name)
                continue
            raw = tick.feature_values.get(channel.feature_name)
            if raw is None or not isinstance(raw, int | float):
                missing.append(channel.feature_name)
                continue
            normalized = min(abs(float(raw)) / channel.mad_scale, 1.0)
            variance = channel.base_variance
            if is_caution:
                variance *= self._config.caution_inflation_factor
            result = kalman.update(state, normalized, variance)
            state = result.state
            used.append(channel.feature_name)

        prediction_only = len(used) < self._config.minimum_observations

        # --- 3. constraints -----------------------------------------------------------
        state = kalman.clip_state(state, self._config.level_bounds, self._config.rate_bound)

        # --- 4. explainability derivations --------------------------------------------
        uncertainty_category = self._uncertainty_category(state.p00)
        if prediction_only and gap_since_prior > self._gap.max_prediction_only_gap_seconds:
            # Only overrides while still blind (no observation *this* tick) — a long gap
            # that just ended with a real, trusted observation has already had its
            # uncertainty reduced by that update's own Kalman gain; forcing HIGH here
            # regardless would undo the update and contradict the filter's own math (a
            # fresh good reading legitimately restores confidence, gap or no gap).
            uncertainty_category = "HIGH"
        trend = self._trend(state.rate, uncertainty_category)

        return StateEstimateResult(
            tenant_id=tick.tenant_id,
            machine_id=tick.machine_id,
            component_id=None,
            state_type=self._state_type,
            as_of_timestamp=tick.as_of_timestamp,
            state_value=state.level,
            state_rate=state.rate,
            trend=trend,
            uncertainty=uncertainty_category,
            covariance_summary={"p00": state.p00, "p01": state.p01, "p11": state.p11},
            estimator_id=self._estimator_id,
            estimator_version=self._estimator_version,
            config_version=self._config_version,
            feature_set=tick.feature_set,
            feature_set_version=tick.feature_set_version,
            feature_vector_id=tick.feature_vector_id,
            dt_seconds=dt_seconds,
            prediction_only=prediction_only,
            observations_used=tuple(used),
            observations_missing=tuple(missing),
            quality_summary={"state": tick.quality_state},
        )

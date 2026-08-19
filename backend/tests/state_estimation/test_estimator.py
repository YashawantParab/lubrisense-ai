"""`StateEstimator` behavior tests (Phase 12 brief §35): quality-aware R handling,
ineligible/missing-observation suppression, prediction-only updates, uncertainty growth
during an outage, variable dt, and independent bearing/delivery separation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from app.state_estimation.config.policy import load_state_estimation_config
from app.state_estimation.models.estimator import FeatureTick, StateEstimator

TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()
CONFIG = load_state_estimation_config()


def _estimator(state_type: str) -> StateEstimator:
    state_config = CONFIG.state_config(state_type)
    return StateEstimator(
        estimator_id=state_type,
        estimator_version=CONFIG.estimator_version,
        config_version=CONFIG.config_version,
        state_type=state_type,
        config=state_config,
        gap=CONFIG.gap,
        uncertainty=CONFIG.uncertainty,
    )


def _tick(
    as_of: datetime,
    feature_values: Mapping[str, object] | None = None,
    missing_features: tuple[str, ...] = (),
    quality_state: str = "TRUSTED",
) -> FeatureTick:
    return FeatureTick(
        tenant_id=TENANT,
        machine_id=MACHINE,
        feature_vector_id=uuid.uuid4(),
        feature_set="STATE_ESTIMATION_V1",
        feature_set_version="1.0.1",
        as_of_timestamp=as_of,
        feature_values=feature_values or {},
        missing_features=missing_features,
        quality_state=quality_state,
    )


def test_first_tick_with_no_prior_initializes_from_config() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    result = est.step(None, _tick(datetime(2026, 1, 1, tzinfo=UTC)))
    assert result.dt_seconds == 0.0
    assert result.state_value == pytest.approx(0.0)


def test_missing_feature_is_skipped_not_fabricated() -> None:
    """A channel absent from `feature_values` (or listed in `missing_features`) must never
    be treated as 0 — it is simply not used this tick (Phase 12 brief §10)."""
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    result = est.step(
        None, _tick(t0, feature_values={}, missing_features=("pressure.robust_deviation",))
    )
    assert "pressure.robust_deviation" not in result.observations_used
    assert "pressure.robust_deviation" in result.observations_missing


def test_partial_observations_do_not_crash_and_use_what_is_available() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {"pressure.robust_deviation": 2.0, "pump_current.robust_deviation": 1.5}
    missing = ("flow.robust_deviation", "reservoir_level.robust_deviation")
    result = est.step(None, _tick(t0, feature_values=fv, missing_features=missing))
    assert set(result.observations_used) == {
        "pressure.robust_deviation",
        "pump_current.robust_deviation",
    }
    assert set(result.observations_missing) == set(missing)
    assert result.prediction_only is False


def test_zero_available_channels_is_prediction_only() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    all_missing = tuple(
        c.feature_name for c in CONFIG.states["LUBRICATION_DELIVERY_STATE"].channels
    )
    result = est.step(None, _tick(t0, feature_values={}, missing_features=all_missing))
    assert result.prediction_only is True
    assert result.observations_used == ()


def test_caution_quality_inflates_variance_and_reduces_kalman_gain() -> None:
    """Same observed deviation, but under CAUTION quality, should move the posterior level
    less than under TRUSTED quality — the R-inflation mechanism (Phase 12 brief §9)."""
    est_trusted = _estimator("LUBRICATION_DELIVERY_STATE")
    est_caution = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {"pressure.robust_deviation": 6.0}
    missing = (
        "flow.robust_deviation",
        "pump_current.robust_deviation",
        "reservoir_level.robust_deviation",
    )

    trusted_result = est_trusted.step(None, _tick(t0, fv, missing, quality_state="TRUSTED"))
    caution_result = est_caution.step(None, _tick(t0, fv, missing, quality_state="CAUTION"))

    assert caution_result.state_value < trusted_result.state_value


def test_ineligible_reading_never_substituted_with_zero() -> None:
    """A channel present in `feature_values` as an explicit 0.0 is a real reading of zero
    deviation, distinct from a missing one — this test proves the estimator does not
    conflate "no data" with "observed value is 0"."""
    est_missing = _estimator("LUBRICATION_DELIVERY_STATE")
    est_zero = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    channels = tuple(c.feature_name for c in CONFIG.states["LUBRICATION_DELIVERY_STATE"].channels)

    missing_result = est_missing.step(None, _tick(t0, {}, channels))
    zero_result = est_zero.step(None, _tick(t0, {c: 0.0 for c in channels}, ()))
    assert missing_result.prediction_only is True
    assert zero_result.prediction_only is False
    # An explicit all-zero reading pulls the posterior variance down (an update happened);
    # a missing tick leaves the prior (initial) variance untouched.
    assert zero_result.covariance_summary["p00"] < missing_result.covariance_summary["p00"]


def test_uncertainty_increases_during_a_long_gap_without_observations() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {c.feature_name: 0.5 for c in CONFIG.states["LUBRICATION_DELIVERY_STATE"].channels}
    first = est.step(None, _tick(t0, fv))
    assert first.uncertainty == "LOW"

    outage_tick = _tick(
        t0 + timedelta(hours=48), {}, tuple(fv.keys()), quality_state="NO_TRUSTED_DATA"
    )
    outage_result = est.step(first.to_prior(), outage_tick)
    assert outage_result.prediction_only is True
    assert outage_result.uncertainty == "HIGH"
    assert outage_result.trend == "UNKNOWN"


def test_fresh_observation_after_a_long_gap_restores_confidence() -> None:
    """A long gap followed by a real, trusted observation must not be forced to HIGH
    uncertainty just because the *gap* was long — the update this tick already reduced
    the posterior variance via its own Kalman gain, and that legitimately restored
    confidence (unlike a gap that is *still* ongoing with no observation this tick,
    which correctly stays HIGH — see the outage tests below)."""
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {c.feature_name: 0.5 for c in CONFIG.states["LUBRICATION_DELIVERY_STATE"].channels}
    first = est.step(None, _tick(t0, fv))
    assert first.uncertainty == "LOW"

    resumed_tick = _tick(t0 + timedelta(hours=48), fv, quality_state="TRUSTED")
    resumed_result = est.step(first.to_prior(), resumed_tick)
    assert resumed_result.prediction_only is False
    assert resumed_result.uncertainty != "HIGH"


def test_outage_does_not_fabricate_a_confident_trend() -> None:
    """Communication failure must show up as HIGH uncertainty / UNKNOWN trend, never a
    confident DETERIORATING or IMPROVING claim (Phase 12 brief §27)."""
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    prior = None
    fv = {"pressure.robust_deviation": 3.0, "pump_current.robust_deviation": 2.0}
    missing = ("flow.robust_deviation", "reservoir_level.robust_deviation")
    for i in range(5):
        result = est.step(prior, _tick(t0 + timedelta(seconds=600 * i), fv, missing))
        prior = result.to_prior()

    outage = est.step(
        prior,
        _tick(
            t0 + timedelta(hours=36),
            {},
            (
                "pressure.robust_deviation",
                "pump_current.robust_deviation",
                "flow.robust_deviation",
                "reservoir_level.robust_deviation",
            ),
            quality_state="NO_TRUSTED_DATA",
        ),
    )
    assert outage.trend == "UNKNOWN"
    assert outage.uncertainty == "HIGH"


def test_variable_dt_is_reflected_in_result() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {"pressure.robust_deviation": 0.5}
    missing = (
        "flow.robust_deviation",
        "pump_current.robust_deviation",
        "reservoir_level.robust_deviation",
    )
    first = est.step(None, _tick(t0, fv, missing))
    second = est.step(first.to_prior(), _tick(t0 + timedelta(seconds=45), fv, missing))
    assert second.dt_seconds == pytest.approx(45.0)


def test_gap_is_clamped_to_configured_maximum() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fv = {"pressure.robust_deviation": 0.5}
    missing = (
        "flow.robust_deviation",
        "pump_current.robust_deviation",
        "reservoir_level.robust_deviation",
    )
    first = est.step(None, _tick(t0, fv, missing))
    far_future = t0 + timedelta(days=30)
    second = est.step(first.to_prior(), _tick(far_future, fv, missing))
    assert second.dt_seconds == pytest.approx(CONFIG.gap.max_dt_seconds)


def test_state_value_stays_within_configured_bounds() -> None:
    est = _estimator("LUBRICATION_DELIVERY_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    prior = None
    for i in range(20):
        fv = {"pressure.robust_deviation": 500.0, "pump_current.robust_deviation": 500.0}
        result = est.step(
            prior,
            _tick(
                t0 + timedelta(seconds=600 * i),
                fv,
                ("flow.robust_deviation", "reservoir_level.robust_deviation"),
            ),
        )
        prior = result.to_prior()
        assert 0.0 <= result.state_value <= 1.0


def test_bearing_and_delivery_states_are_independent() -> None:
    """Independent-bearing scenario shape (Phase 12 brief §26): bearing evidence deviates
    while delivery-relevant channels stay nominal — delivery state must remain near
    nominal while bearing state deteriorates."""
    delivery_est = _estimator("LUBRICATION_DELIVERY_STATE")
    bearing_est = _estimator("BEARING_CONDITION_STATE")
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    delivery_prior = None
    bearing_prior = None
    for i in range(15):
        ts = t0 + timedelta(seconds=600 * i)
        delivery_fv = {
            "pressure.robust_deviation": 0.3,
            "flow.robust_deviation": 0.2,
            "pump_current.robust_deviation": 0.2,
            "reservoir_level.robust_deviation": 0.3,
        }
        bearing_fv = {"bearing_temp.robust_deviation": 8.0, "vibration_rms.robust_deviation": 7.0}

        delivery_result = delivery_est.step(delivery_prior, _tick(ts, delivery_fv))
        delivery_prior = delivery_result.to_prior()
        bearing_result = bearing_est.step(bearing_prior, _tick(ts, bearing_fv))
        bearing_prior = bearing_result.to_prior()

    assert delivery_result.state_value < 0.15
    assert bearing_result.state_value > 0.5

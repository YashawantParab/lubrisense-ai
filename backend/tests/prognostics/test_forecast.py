"""Pure forecast logic tests (Phase 15 brief §15.3, §15.7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.prognostics.config.policy import load_prognostics_policy
from app.prognostics.domain.models import StateEstimateSnapshot
from app.prognostics.services.forecast import data_sufficiency_check, forecast_one

POLICY = load_prognostics_policy()


def _snapshot(
    level: float = 0.3,
    rate: float = 0.0,
    trend: str = "STABLE",
    uncertainty: str = "LOW",
    prediction_only: bool = False,
) -> StateEstimateSnapshot:
    return StateEstimateSnapshot(
        id=uuid.uuid4(),
        state_type="LUBRICATION_DELIVERY_STATE",
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        level=level,
        rate=rate,
        trend=trend,
        uncertainty=uncertainty,
        prediction_only=prediction_only,
    )


def _history(count: int, rate: float = 0.0001) -> list[StateEstimateSnapshot]:
    return [_snapshot(rate=rate) for _ in range(count)]


def test_prediction_only_current_is_insufficient() -> None:
    sufficient, reasons = data_sufficiency_check(
        _snapshot(prediction_only=True), _history(3), POLICY
    )
    assert sufficient is False
    assert any("prediction-only" in r for r in reasons)


def test_high_uncertainty_current_is_insufficient() -> None:
    sufficient, reasons = data_sufficiency_check(_snapshot(uncertainty="HIGH"), _history(3), POLICY)
    assert sufficient is False
    assert any("HIGH" in r for r in reasons)


def test_short_history_is_insufficient() -> None:
    sufficient, reasons = data_sufficiency_check(_snapshot(), _history(1), POLICY)
    assert sufficient is False
    assert any("required" in r for r in reasons)


def test_rate_sign_flip_is_unstable() -> None:
    history = [_snapshot(rate=0.001), _snapshot(rate=-0.001), _snapshot(rate=0.001)]
    sufficient, reasons = data_sufficiency_check(_snapshot(rate=0.001), history, POLICY)
    assert sufficient is False
    assert any("unstable" in r.lower() for r in reasons)


def test_sufficient_when_trusted_consistent_and_enough_history() -> None:
    history = _history(4, rate=0.0002)
    sufficient, reasons = data_sufficiency_check(_snapshot(rate=0.0002), history, POLICY)
    assert sufficient is True
    assert reasons == []


def test_forecast_one_no_reliable_forecast_when_insufficient() -> None:
    result = forecast_one(_snapshot(prediction_only=True), _history(1), 3600.0, POLICY)
    assert result.status == "NO_RELIABLE_FORECAST"
    assert result.predicted_state_at_horizon is None
    assert result.uncertainty == "HIGH"
    assert result.data_sufficient is False


def test_forecast_one_extrapolates_linearly_from_posterior() -> None:
    current = _snapshot(level=0.3, rate=0.0001, trend="DETERIORATING")
    result = forecast_one(current, _history(4, rate=0.0001), 3600.0, POLICY)
    assert result.status == "OK"
    assert result.predicted_state_at_horizon == pytest.approx(0.3 + 0.0001 * 3600.0)


def test_forecast_one_clips_to_level_bounds() -> None:
    current = _snapshot(level=0.99, rate=0.01, trend="DETERIORATING")
    result = forecast_one(current, _history(4, rate=0.01), 86400.0, POLICY)
    assert result.predicted_state_at_horizon == pytest.approx(1.0)


def test_healthy_stable_state_never_produces_a_threshold_crossing() -> None:
    current = _snapshot(level=0.05, rate=0.0, trend="STABLE")
    result = forecast_one(current, _history(4, rate=0.0), 86400.0, POLICY)
    assert result.status == "OK"
    assert result.threshold_crossing_seconds is None


def test_deteriorating_trend_below_threshold_estimates_a_crossing() -> None:
    current = _snapshot(level=0.5, rate=0.0001, trend="DETERIORATING")
    result = forecast_one(current, _history(4, rate=0.0001), 3600.0, POLICY)
    expected = (POLICY.degradation_threshold - 0.5) / 0.0001
    assert result.threshold_crossing_seconds == pytest.approx(expected)


def test_crossing_further_than_max_horizon_is_not_reported() -> None:
    current = _snapshot(level=0.01, rate=1e-8, trend="DETERIORATING")
    result = forecast_one(current, _history(4, rate=1e-8), 3600.0, POLICY)
    assert result.threshold_crossing_seconds is None


def test_already_above_threshold_does_not_report_a_future_crossing() -> None:
    current = _snapshot(level=0.9, rate=0.0001, trend="DETERIORATING")
    result = forecast_one(current, _history(4, rate=0.0001), 3600.0, POLICY)
    assert result.threshold_crossing_seconds is None


def test_negative_rate_never_reports_a_crossing() -> None:
    current = _snapshot(level=0.5, rate=-0.0001, trend="IMPROVING")
    result = forecast_one(current, _history(4, rate=-0.0001), 3600.0, POLICY)
    assert result.threshold_crossing_seconds is None

"""Pure evaluation-metric function tests (`app.state_estimation.evaluation.metrics`).

Caught a real bug during live verification: `smoothness` used `zip(..., strict=True)` on
two lists that are deliberately different lengths (a sliding pairwise window), which always
raised `ValueError`. These tests exist so that specific class of bug — and any future one
in this module — is caught before a live script run, not during one.
"""

from __future__ import annotations

import pytest

from app.state_estimation.evaluation.metrics import (
    detection_lead_lag,
    mean_absolute_error,
    pearson_correlation,
    root_mean_squared_error,
    smoothness,
    trend_agreement_rate,
)


def test_mae_zero_for_identical_series() -> None:
    assert mean_absolute_error([0.1, 0.5, 0.9], [0.1, 0.5, 0.9]) == pytest.approx(0.0)


def test_mae_computes_expected_value() -> None:
    assert mean_absolute_error([0.0, 1.0], [0.5, 0.5]) == pytest.approx(0.5)


def test_mae_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        mean_absolute_error([0.1], [0.1, 0.2])


def test_mae_rejects_empty_series() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        mean_absolute_error([], [])


def test_rmse_zero_for_identical_series() -> None:
    assert root_mean_squared_error([0.2, 0.7], [0.2, 0.7]) == pytest.approx(0.0)


def test_rmse_penalizes_larger_errors_more_than_mae() -> None:
    estimated = [0.0, 0.0, 1.0]
    truth = [0.0, 0.0, 0.0]
    assert root_mean_squared_error(estimated, truth) >= mean_absolute_error(estimated, truth)


def test_pearson_correlation_perfect_positive() -> None:
    corr = pearson_correlation([0.0, 0.5, 1.0], [0.0, 0.5, 1.0])
    assert corr == pytest.approx(1.0)


def test_pearson_correlation_perfect_negative() -> None:
    corr = pearson_correlation([0.0, 0.5, 1.0], [1.0, 0.5, 0.0])
    assert corr == pytest.approx(-1.0)


def test_pearson_correlation_none_for_zero_variance_series() -> None:
    """A perfectly flat series (e.g. a HEALTHY run's ground truth) has undefined
    correlation — must return None, never a fabricated 0.0 or 1.0."""
    assert pearson_correlation([0.1, 0.2, 0.3], [0.5, 0.5, 0.5]) is None


def test_pearson_correlation_none_for_too_few_points() -> None:
    assert pearson_correlation([0.1], [0.2]) is None


def test_trend_agreement_rate_all_agree() -> None:
    assert trend_agreement_rate(
        ["STABLE", "DETERIORATING"], ["STABLE", "DETERIORATING"]
    ) == pytest.approx(1.0)


def test_trend_agreement_rate_unknown_never_counts_as_agreement() -> None:
    """An estimator declining to claim a direction (UNKNOWN) is not the same as being
    right, even if truth also happens to be flat/STABLE-labeled."""
    rate = trend_agreement_rate(["UNKNOWN", "UNKNOWN"], ["UNKNOWN", "STABLE"])
    assert rate == pytest.approx(0.0)


def test_trend_agreement_rate_partial() -> None:
    rate = trend_agreement_rate(
        ["DETERIORATING", "STABLE", "IMPROVING"], ["DETERIORATING", "DETERIORATING", "IMPROVING"]
    )
    assert rate == pytest.approx(2 / 3)


def test_smoothness_zero_for_constant_series() -> None:
    assert smoothness([0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.0)


def test_smoothness_computes_mean_absolute_tick_to_tick_change() -> None:
    assert smoothness([0.0, 0.2, 0.1]) == pytest.approx((0.2 + 0.1) / 2)


def test_smoothness_rejects_single_point_series() -> None:
    with pytest.raises(ValueError, match="at least two points"):
        smoothness([0.5])


def test_smoothness_handles_a_realistic_length_mismatch_prone_series() -> None:
    """Regression test for the strict-zip bug: an odd-length series must not raise."""
    series = [0.01, 0.05, 0.2, 0.4, 0.6, 0.7, 0.71]
    assert smoothness(series) > 0.0


def test_detection_lead_lag_positive_when_estimator_crosses_first() -> None:
    estimated = [0.1, 0.6, 0.9]
    truth = [0.1, 0.2, 0.6]
    timestamps = [0.0, 100.0, 200.0]
    result = detection_lead_lag(estimated, truth, timestamps, threshold=0.5)
    assert result.lead_seconds == pytest.approx(100.0)
    assert result.estimator_crossing_index == 1
    assert result.truth_crossing_index == 2


def test_detection_lead_lag_none_when_threshold_never_crossed() -> None:
    result = detection_lead_lag([0.1, 0.2], [0.1, 0.2], [0.0, 60.0], threshold=0.9)
    assert result.lead_seconds is None

"""Pure-function tests for `app.energy.domain.residual` — mirrors
`tests/baselines/test_deviation.py`'s own no-fixture, no-database style."""

from __future__ import annotations

from app.baselines.domain.deviation import DeviationResult, not_enough_data
from app.domain.enums import DeviationClassification, EnergyAssessmentStatus, QualityState
from app.energy.domain.residual import compute_residual, determine_status


def _deviation(classification: DeviationClassification) -> DeviationResult:
    return DeviationResult(
        classification=classification,
        standardized_distance=0.0,
        quantile_position=0.5,
        method="robust_mad",
    )


class TestComputeResidual:
    def test_positive_residual_when_actual_above_expected(self) -> None:
        residual_kw, residual_pct = compute_residual(actual_power_kw=55.0, expected_power_kw=50.0)
        assert residual_kw == 5.0
        assert residual_pct is not None
        assert residual_pct == 10.0

    def test_negative_residual_when_actual_below_expected(self) -> None:
        residual_kw, residual_pct = compute_residual(actual_power_kw=45.0, expected_power_kw=50.0)
        assert residual_kw == -5.0
        assert residual_pct == -10.0

    def test_zero_expected_power_never_produces_a_percentage(self) -> None:
        # brief's own "do not calculate misleading percentages when denominator is
        # invalid" — a zero (or negative) expected value makes a ratio meaningless.
        residual_kw, residual_pct = compute_residual(actual_power_kw=10.0, expected_power_kw=0.0)
        assert residual_kw == 10.0
        assert residual_pct is None

    def test_negative_expected_power_never_produces_a_percentage(self) -> None:
        residual_kw, residual_pct = compute_residual(actual_power_kw=10.0, expected_power_kw=-5.0)
        assert residual_kw == 15.0
        assert residual_pct is None


class TestDetermineStatus:
    def test_no_power_reading_is_insufficient_data(self) -> None:
        status = determine_status(
            has_power_reading=False,
            quality_state=QualityState.TRUSTED,
            deviation=None,
            residual_kw=None,
        )
        assert status == EnergyAssessmentStatus.INSUFFICIENT_DATA

    def test_unusable_sensor_is_data_quality_limited_even_with_a_reading(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.UNUSABLE,
            deviation=_deviation(DeviationClassification.WITHIN_EXPECTED_RANGE),
            residual_kw=0.0,
        )
        assert status == EnergyAssessmentStatus.DATA_QUALITY_LIMITED

    def test_no_resolved_baseline_is_insufficient_baseline(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.TRUSTED,
            deviation=None,
            residual_kw=None,
        )
        assert status == EnergyAssessmentStatus.INSUFFICIENT_BASELINE

    def test_not_enough_data_classification_is_insufficient_baseline(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.TRUSTED,
            deviation=not_enough_data(),
            residual_kw=None,
        )
        assert status == EnergyAssessmentStatus.INSUFFICIENT_BASELINE

    def test_within_expected_range(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.TRUSTED,
            deviation=_deviation(DeviationClassification.WITHIN_EXPECTED_RANGE),
            residual_kw=0.1,
        )
        assert status == EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE

    def test_strong_positive_deviation_is_elevated_energy_demand(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.TRUSTED,
            deviation=_deviation(DeviationClassification.STRONG_DEVIATION),
            residual_kw=8.0,
        )
        assert status == EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND

    def test_mild_negative_deviation_is_below_expected_range(self) -> None:
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.TRUSTED,
            deviation=_deviation(DeviationClassification.MILD_DEVIATION),
            residual_kw=-3.0,
        )
        assert status == EnergyAssessmentStatus.BELOW_EXPECTED_RANGE

    def test_caution_quality_still_computes_a_directional_status(self) -> None:
        # USABLE_WITH_CAUTION reduces confidence (carried by `data_quality_state` on the
        # persisted row) but does not by itself block computing a real residual/status —
        # only UNUSABLE does.
        status = determine_status(
            has_power_reading=True,
            quality_state=QualityState.USABLE_WITH_CAUTION,
            deviation=_deviation(DeviationClassification.STRONG_DEVIATION),
            residual_kw=6.0,
        )
        assert status == EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND

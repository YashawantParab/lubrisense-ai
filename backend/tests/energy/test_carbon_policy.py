"""Pure tests for `app.energy.domain.carbon` — carbon eligibility/calculation policy
(Lubrication Efficiency Intelligence, Pass 4, ADR-176). No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import CarbonEstimateStatus, EmissionFactorMethod
from app.energy.domain.carbon import (
    CarbonEligibilityInput,
    EmissionFactorSnapshot,
    evaluate_carbon,
    is_valid_factor,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_PERIOD_START = _T0
_PERIOD_END = _T0 + timedelta(hours=1)


def _valid_factor(**overrides: object) -> EmissionFactorSnapshot:
    base: dict[str, object] = {
        "id": "factor-1",
        "factor_value": 0.4,
        "factor_unit": "kg_co2e_per_kwh",
        "method": EmissionFactorMethod.LOCATION_BASED,
        "source_name": "Demo factor",
        "source_reference": None,
        "jurisdiction": "Demo region",
        "effective_from": _T0 - timedelta(days=30),
        "effective_to": None,
        "is_active": True,
    }
    base.update(overrides)
    return EmissionFactorSnapshot(**base)  # type: ignore[arg-type]


def _input(**overrides: object) -> CarbonEligibilityInput:
    base: dict[str, object] = {
        "qualified_avoided_energy_kwh": 10.0,
        "observed_period_start": _PERIOD_START,
        "observed_period_end": _PERIOD_END,
        "factor": _valid_factor(),
        "comparison_confidence_is_high": True,
    }
    base.update(overrides)
    return CarbonEligibilityInput(**base)  # type: ignore[arg-type]


class TestIsValidFactor:
    def test_active_positive_correct_unit_is_valid(self) -> None:
        assert is_valid_factor(_valid_factor()) is True

    def test_inactive_factor_is_invalid(self) -> None:
        assert is_valid_factor(_valid_factor(is_active=False)) is False

    def test_wrong_unit_is_invalid(self) -> None:
        assert is_valid_factor(_valid_factor(factor_unit="lbs_co2_per_kwh")) is False

    def test_zero_value_is_invalid(self) -> None:
        assert is_valid_factor(_valid_factor(factor_value=0.0)) is False

    def test_negative_value_is_invalid(self) -> None:
        assert is_valid_factor(_valid_factor(factor_value=-0.1)) is False

    def test_non_finite_value_is_invalid(self) -> None:
        assert is_valid_factor(_valid_factor(factor_value=float("inf"))) is False
        assert is_valid_factor(_valid_factor(factor_value=float("nan"))) is False


class TestEvaluateCarbon:
    def test_no_qualified_energy_is_not_eligible(self) -> None:
        result = evaluate_carbon(_input(qualified_avoided_energy_kwh=None))
        assert result.status == CarbonEstimateStatus.NOT_ELIGIBLE
        assert result.estimated_co2e_kg is None

    def test_no_observed_period_is_not_eligible(self) -> None:
        result = evaluate_carbon(_input(observed_period_start=None))
        assert result.status == CarbonEstimateStatus.NOT_ELIGIBLE
        assert result.estimated_co2e_kg is None

    def test_no_factor_configured(self) -> None:
        result = evaluate_carbon(_input(factor=None))
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_CONFIGURED
        assert result.estimated_co2e_kg is None

    def test_invalid_factor_is_not_applicable(self) -> None:
        result = evaluate_carbon(_input(factor=_valid_factor(is_active=False)))
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_APPLICABLE
        assert result.estimated_co2e_kg is None

    def test_factor_effective_after_period_start_is_not_applicable(self) -> None:
        result = evaluate_carbon(
            _input(factor=_valid_factor(effective_from=_PERIOD_END + timedelta(hours=1)))
        )
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_APPLICABLE

    def test_factor_expired_before_period_end_is_not_applicable(self) -> None:
        result = evaluate_carbon(
            _input(
                factor=_valid_factor(
                    effective_from=_T0 - timedelta(days=60),
                    effective_to=_PERIOD_START - timedelta(minutes=1),
                )
            )
        )
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_APPLICABLE

    def test_factor_partially_overlapping_period_is_not_applicable(self) -> None:
        """The period crosses the factor's own effective_to boundary mid-period — this
        implementation does not attempt multi-segment integration (documented policy),
        so it must refuse rather than silently use a partially-applicable factor."""
        result = evaluate_carbon(
            _input(
                factor=_valid_factor(
                    effective_from=_T0 - timedelta(days=30),
                    effective_to=_PERIOD_START + timedelta(minutes=30),
                )
            )
        )
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_APPLICABLE

    def test_valid_factor_covering_period_computes_estimate(self) -> None:
        result = evaluate_carbon(_input(qualified_avoided_energy_kwh=10.0))
        assert result.status == CarbonEstimateStatus.ESTIMATE_AVAILABLE
        assert result.estimated_co2e_kg == 4.0  # 10 kWh * 0.4 kg/kWh

    def test_formula_is_linear_multiplication(self) -> None:
        result = evaluate_carbon(
            _input(qualified_avoided_energy_kwh=25.0, factor=_valid_factor(factor_value=0.5))
        )
        assert result.estimated_co2e_kg == 12.5

    def test_low_confidence_energy_outcome_is_limited_estimate(self) -> None:
        result = evaluate_carbon(_input(comparison_confidence_is_high=False))
        assert result.status == CarbonEstimateStatus.LIMITED_ESTIMATE
        assert result.estimated_co2e_kg is not None
        assert result.limitations

    def test_zero_avoided_energy_is_not_eligible_not_a_zero_estimate(self) -> None:
        """`0.0` is falsy but semantically distinct from `None` — must still be treated
        as a valid (if trivial) qualified figure, not rejected as missing."""
        result = evaluate_carbon(_input(qualified_avoided_energy_kwh=0.0))
        assert result.status == CarbonEstimateStatus.ESTIMATE_AVAILABLE
        assert result.estimated_co2e_kg == 0.0

    def test_never_manufactures_estimate_without_factor_regardless_of_energy_magnitude(
        self,
    ) -> None:
        result = evaluate_carbon(_input(qualified_avoided_energy_kwh=100000.0, factor=None))
        assert result.status == CarbonEstimateStatus.FACTOR_NOT_CONFIGURED
        assert result.estimated_co2e_kg is None

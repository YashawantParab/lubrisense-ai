"""Pure tests for `app.portfolio.domain.energy_bucket` (Portfolio Intelligence Pass 1,
ADR-177). Includes the two required, load-bearing scenarios: IDF-01-shaped opportunity
and BE-201-shaped qualified recovery."""

from __future__ import annotations

from app.domain.enums import (
    AttributionLevel,
    EnergyAssessmentStatus,
    EnergyOutcomeStatus,
    EnergyPortfolioBucket,
)
from app.portfolio.domain.energy_bucket import derive_energy_bucket


def test_no_energy_data_is_insufficient() -> None:
    for status in (
        EnergyAssessmentStatus.INSUFFICIENT_DATA,
        EnergyAssessmentStatus.INSUFFICIENT_BASELINE,
        EnergyAssessmentStatus.DATA_QUALITY_LIMITED,
        None,
    ):
        result = derive_energy_bucket(
            energy_status=status,
            attribution_level=None,
            latest_outcome_status=None,
            has_completed_maintenance=False,
        )
        assert result == EnergyPortfolioBucket.INSUFFICIENT_ENERGY_DATA


def test_within_expected_range_is_normal() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        attribution_level=None,
        latest_outcome_status=None,
        has_completed_maintenance=False,
    )
    assert result == EnergyPortfolioBucket.NORMAL_ENERGY_BEHAVIOR


def test_below_expected_range_is_normal() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.BELOW_EXPECTED_RANGE,
        attribution_level=None,
        latest_outcome_status=None,
        has_completed_maintenance=False,
    )
    assert result == EnergyPortfolioBucket.NORMAL_ENERGY_BEHAVIOR


def test_idf01_shaped_elevated_energy_with_no_evidence_attribution_is_active_elevated() -> None:
    """Elevated energy, but attribution has not yet been supported by independent
    evidence — an opportunity, never described as attribution-supported."""
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
        attribution_level=AttributionLevel.NO_EVIDENCE,
        latest_outcome_status=None,
        has_completed_maintenance=False,
    )
    assert result == EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY


def test_idf01_shaped_elevated_energy_with_possible_attribution_is_supported_opportunity() -> None:
    """IDF-01's real Pass-2 shape: ELEVATED_ENERGY_DEMAND + POSSIBLE attribution, no
    completed maintenance — an attribution-supported opportunity, never a recovery."""
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
        attribution_level=AttributionLevel.POSSIBLE,
        latest_outcome_status=None,
        has_completed_maintenance=False,
    )
    assert result == EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY


def test_completed_maintenance_no_outcome_yet_is_awaiting_verification() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
        attribution_level=AttributionLevel.POSSIBLE,
        latest_outcome_status=None,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.OUTCOME_AWAITING_VERIFICATION


def test_be201_shaped_qualified_recovery() -> None:
    """BE-201's real Pass-3 shape: a QUALIFIED_RECOVERY outcome exists."""
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        attribution_level=AttributionLevel.NO_EVIDENCE,
        latest_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.QUALIFIED_ENERGY_RECOVERY


def test_probable_recovery_is_never_qualified() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        attribution_level=None,
        latest_outcome_status=EnergyOutcomeStatus.PROBABLE_RECOVERY,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.INCONCLUSIVE_OUTCOME
    assert result != EnergyPortfolioBucket.QUALIFIED_ENERGY_RECOVERY


def test_deteriorated_outcome_is_its_own_bucket_not_inconclusive() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
        attribution_level=None,
        latest_outcome_status=EnergyOutcomeStatus.DETERIORATED,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.OUTCOME_DETERIORATED


def test_inconclusive_outcome_status_maps_to_inconclusive_bucket() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        attribution_level=None,
        latest_outcome_status=EnergyOutcomeStatus.INCONCLUSIVE,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.INCONCLUSIVE_OUTCOME


def test_no_material_change_outcome_falls_through_to_current_state() -> None:
    result = derive_energy_bucket(
        energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        attribution_level=None,
        latest_outcome_status=EnergyOutcomeStatus.NO_MATERIAL_CHANGE,
        has_completed_maintenance=True,
    )
    assert result == EnergyPortfolioBucket.NORMAL_ENERGY_BEHAVIOR

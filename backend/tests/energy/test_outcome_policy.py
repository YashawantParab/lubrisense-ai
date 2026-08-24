"""Pure tests for `app.energy.domain.outcome` — energy-outcome classification, avoided
-energy integration, maintenance relevance, and the lubrication-association claim
hierarchy (Lubrication Efficiency Intelligence, Pass 3, ADR-176)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import (
    AttributionLevel,
    ComparabilityStatus,
    DeviationClassification,
    EnergyEstimateStatus,
    EnergyOutcomeStatus,
    LubricationAssociationStatus,
    MaintenanceActionType,
    RecommendedAction,
)
from app.energy.domain.outcome import (
    classify_energy_outcome,
    derive_lubrication_association,
    determine_energy_estimate_status,
    determine_maintenance_relevance,
    integrate_avoided_energy_kwh,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


class TestClassifyEnergyOutcome:
    def test_comparability_insufficient_data_wins_regardless_of_residuals(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.INSUFFICIENT_DATA,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            post_residual_kw=0.0,
        )
        assert status == EnergyOutcomeStatus.INSUFFICIENT_DATA

    def test_not_comparable_is_inconclusive(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            post_residual_kw=0.0,
        )
        assert status == EnergyOutcomeStatus.INCONCLUSIVE

    def test_no_pre_elevation_is_no_material_change(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            pre_residual_kw=0.2,
            post_classification=DeviationClassification.STRONG_DEVIATION,
            post_residual_kw=10.0,
        )
        assert status == EnergyOutcomeStatus.NO_MATERIAL_CHANGE

    def test_full_recovery_under_full_comparability_is_qualified(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            post_residual_kw=0.1,
        )
        assert status == EnergyOutcomeStatus.QUALIFIED_RECOVERY

    def test_full_recovery_under_partial_comparability_is_probable_not_qualified(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.PARTIALLY_COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            post_residual_kw=0.1,
        )
        assert status == EnergyOutcomeStatus.PROBABLE_RECOVERY

    def test_partial_improvement_strong_to_mild_is_probable_recovery(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.MILD_DEVIATION,
            post_residual_kw=3.0,
        )
        assert status == EnergyOutcomeStatus.PROBABLE_RECOVERY

    def test_unchanged_elevated_tier_is_no_material_change(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.MILD_DEVIATION,
            pre_residual_kw=3.0,
            post_classification=DeviationClassification.MILD_DEVIATION,
            post_residual_kw=3.1,
        )
        assert status == EnergyOutcomeStatus.NO_MATERIAL_CHANGE

    def test_worse_after_intervention_is_deteriorated(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.MILD_DEVIATION,
            pre_residual_kw=3.0,
            post_classification=DeviationClassification.STRONG_DEVIATION,
            post_residual_kw=10.0,
        )
        assert status == EnergyOutcomeStatus.DETERIORATED

    def test_negative_residual_is_never_treated_as_elevated(self) -> None:
        # A "STRONG_DEVIATION" classification with a negative residual is a below
        # -expected reading, not excess demand — must not count as pre-elevation.
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=-8.0,
            post_classification=DeviationClassification.WITHIN_EXPECTED_RANGE,
            post_residual_kw=0.0,
        )
        assert status == EnergyOutcomeStatus.NO_MATERIAL_CHANGE

    def test_saturated_strong_tier_still_detects_deterioration_via_residual_magnitude(
        self,
    ) -> None:
        """STRONG_DEVIATION is the top classification tier — both pre and post can land
        there even though the residual itself nearly doubled. The tiers alone would
        report NO_MATERIAL_CHANGE; the magnitude tiebreaker must catch this."""
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=4.0,
            post_classification=DeviationClassification.STRONG_DEVIATION,
            post_residual_kw=16.0,
        )
        assert status == EnergyOutcomeStatus.DETERIORATED

    def test_saturated_strong_tier_detects_improvement_via_residual_magnitude(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=16.0,
            post_classification=DeviationClassification.STRONG_DEVIATION,
            post_residual_kw=4.0,
        )
        assert status == EnergyOutcomeStatus.PROBABLE_RECOVERY

    def test_saturated_strong_tier_small_change_is_no_material_change(self) -> None:
        status = classify_energy_outcome(
            comparability_status=ComparabilityStatus.COMPARABLE,
            pre_classification=DeviationClassification.STRONG_DEVIATION,
            pre_residual_kw=10.0,
            post_classification=DeviationClassification.STRONG_DEVIATION,
            post_residual_kw=10.5,
        )
        assert status == EnergyOutcomeStatus.NO_MATERIAL_CHANGE


class TestEnergyEstimateStatus:
    def test_estimated_only_for_qualified_recovery(self) -> None:
        assert (
            determine_energy_estimate_status(EnergyOutcomeStatus.QUALIFIED_RECOVERY)
            == EnergyEstimateStatus.ESTIMATED
        )

    def test_probable_recovery_is_not_qualified(self) -> None:
        assert (
            determine_energy_estimate_status(EnergyOutcomeStatus.PROBABLE_RECOVERY)
            == EnergyEstimateStatus.NOT_QUALIFIED
        )

    def test_deteriorated_is_not_qualified(self) -> None:
        assert (
            determine_energy_estimate_status(EnergyOutcomeStatus.DETERIORATED)
            == EnergyEstimateStatus.NOT_QUALIFIED
        )

    def test_inconclusive_is_not_comparable(self) -> None:
        assert (
            determine_energy_estimate_status(EnergyOutcomeStatus.INCONCLUSIVE)
            == EnergyEstimateStatus.NOT_COMPARABLE
        )

    def test_insufficient_data_propagates(self) -> None:
        assert (
            determine_energy_estimate_status(EnergyOutcomeStatus.INSUFFICIENT_DATA)
            == EnergyEstimateStatus.INSUFFICIENT_DATA
        )


class TestAvoidedEnergyIntegration:
    def test_never_negative_even_when_post_worse_than_pre(self) -> None:
        samples = [(_T0, 20.0), (_T0 + timedelta(hours=1), 25.0)]
        result = integrate_avoided_energy_kwh(5.0, samples)
        assert result == 0.0

    def test_trapezoidal_integration_of_constant_improvement(self) -> None:
        # pre residual 10 kW, post residual flat at 0 kW for 2 hours -> improvement is a
        # constant 10 kW for 2 hours = 20 kWh.
        samples = [(_T0, 0.0), (_T0 + timedelta(hours=2), 0.0)]
        result = integrate_avoided_energy_kwh(10.0, samples)
        assert abs(result - 20.0) < 1e-9

    def test_sign_crossing_between_two_samples_clamps_each_endpoint_not_the_crossing_point(
        self,
    ) -> None:
        """The clamp is applied at each sample's own improvement value, then trapezoidal
        interpolation runs on those clamped endpoints — it does not solve for the exact
        zero-crossing instant between two real samples (a deliberate simplification for
        dense real telemetry sampling, documented in `integrate_avoided_energy_kwh`'s own
        docstring). Here pre=5kW, post ramps 0kW -> 10kW over 1h: endpoint improvements
        are +5kW and clamp(5-10)=0kW, so trapezoidal gives 0.5*(5+0)*1h = 2.5 kWh — not
        the smaller 1.25 kWh an exact-crossing method would compute."""
        samples = [(_T0, 0.0), (_T0 + timedelta(hours=1), 10.0)]
        result = integrate_avoided_energy_kwh(5.0, samples)
        assert abs(result - 2.5) < 1e-6

    def test_irregular_timestamps_handled_directly(self) -> None:
        samples = [
            (_T0, 0.0),
            (_T0 + timedelta(minutes=5), 0.0),
            (_T0 + timedelta(minutes=65), 0.0),
        ]
        result = integrate_avoided_energy_kwh(6.0, samples)
        # 5 min at 6kW improvement + 60 min at 6kW improvement = 65/60 hours * 6kW.
        assert abs(result - (65.0 / 60.0) * 6.0) < 1e-6

    def test_fewer_than_two_samples_returns_zero(self) -> None:
        assert integrate_avoided_energy_kwh(10.0, []) == 0.0
        assert integrate_avoided_energy_kwh(10.0, [(_T0, 0.0)]) == 0.0

    def test_unsorted_input_is_sorted_before_integrating(self) -> None:
        samples = [(_T0 + timedelta(hours=2), 0.0), (_T0, 0.0)]
        result = integrate_avoided_energy_kwh(10.0, samples)
        assert abs(result - 20.0) < 1e-9


class TestMaintenanceRelevance:
    def test_relevant_action_with_corrective_step_is_relevant(self) -> None:
        relevant, reason = determine_maintenance_relevance(
            RecommendedAction.INSPECT_LUBRICATION_PATH, (MaintenanceActionType.CLEANED,)
        )
        assert relevant is True
        assert reason is None

    def test_unrelated_recommended_action_is_not_relevant(self) -> None:
        relevant, reason = determine_maintenance_relevance(
            RecommendedAction.VERIFY_SENSOR, (MaintenanceActionType.INSPECTED,)
        )
        assert relevant is False
        assert reason is not None

    def test_inspection_only_without_corrective_step_is_not_relevant(self) -> None:
        relevant, reason = determine_maintenance_relevance(
            RecommendedAction.INSPECT_LUBRICATION_PATH, (MaintenanceActionType.INSPECTED,)
        )
        assert relevant is False
        assert reason is not None

    def test_no_action_required_is_not_relevant(self) -> None:
        relevant, _reason = determine_maintenance_relevance(
            RecommendedAction.CHECK_PUMP, (MaintenanceActionType.NO_ACTION_REQUIRED,)
        )
        assert relevant is False


class TestLubricationAssociationClaimHierarchy:
    def test_no_material_change_is_not_applicable(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.NO_MATERIAL_CHANGE,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.STRONG,
        )
        assert level == LubricationAssociationStatus.NOT_APPLICABLE

    def test_deteriorated_is_not_applicable(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.DETERIORATED,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.STRONG,
        )
        assert level == LubricationAssociationStatus.NOT_APPLICABLE

    def test_probable_recovery_caps_at_level_1_even_with_strong_pre_attribution(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.PROBABLE_RECOVERY,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.STRONG,
        )
        assert level == LubricationAssociationStatus.OBSERVED_ENERGY_CHANGE

    def test_qualified_recovery_with_irrelevant_maintenance_caps_at_level_2(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
            maintenance_relevant=False,
            pre_attribution_level=AttributionLevel.STRONG,
        )
        assert level == LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY

    def test_qualified_recovery_with_no_evidence_pre_attribution_caps_at_level_2(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.NO_EVIDENCE,
        )
        assert level == LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY

    def test_qualified_recovery_with_no_pre_attribution_at_all_caps_at_level_2(self) -> None:
        level, _text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
            maintenance_relevant=True,
            pre_attribution_level=None,
        )
        assert level == LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY

    def test_qualified_recovery_relevant_maintenance_and_possible_pre_attribution_reaches_level_3(
        self,
    ) -> None:
        level, text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.POSSIBLE,
        )
        assert level == LubricationAssociationStatus.LUBRICATION_ASSOCIATED_RECOVERY
        assert "POSSIBLE" in text

    def test_never_upgrades_wording_beyond_the_frozen_pre_attribution_level(self) -> None:
        """Temporal-integrity regression: the explanation text must describe the
        *historical* attribution level exactly as given, never a stronger one — this is
        the whole point of freezing `pre_attribution_level` before the intervention."""
        _level, text = derive_lubrication_association(
            energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
            maintenance_relevant=True,
            pre_attribution_level=AttributionLevel.POSSIBLE,
        )
        assert "STRONG" not in text
        assert "MODERATE" not in text
        assert "consistent with the previously POSSIBLE" in text

    def test_repeated_calls_with_same_frozen_input_are_deterministic(self) -> None:
        results = {
            derive_lubrication_association(
                energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
                maintenance_relevant=True,
                pre_attribution_level=AttributionLevel.POSSIBLE,
            )
            for _ in range(5)
        }
        assert len(results) == 1

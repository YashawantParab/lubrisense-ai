"""Pure-function tests for `app.energy.domain.attribution.derive_attribution` — mirrors
`tests/baselines/test_deviation.py`'s own no-fixture, no-database style. Covers the
formal attribution principle (energy deviation necessary, never sufficient), evidence
-family independence/deduplication, contradiction handling, data-quality caps, and ML
governance."""

from __future__ import annotations

from app.domain.enums import AttributionLevel, BaselineSourceKind, EnergyAssessmentStatus
from app.energy.domain.attribution import (
    AttributionContext,
    MLSignal,
    RuleFindingSignal,
    StateEstimateSignal,
    derive_attribution,
)

_BASE_KWARGS = {
    "energy_data_quality": "TRUSTED",
    "residual_kw": 5.0,
    "residual_pct": 13.0,
    "baseline_source": BaselineSourceKind.EXACT_CONTEXT,
}


def _ctx(**overrides: object) -> AttributionContext:
    kwargs = {**_BASE_KWARGS, "energy_status": EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND}
    kwargs.update(overrides)
    return AttributionContext(**kwargs)  # type: ignore[arg-type]


def _friction_finding() -> RuleFindingSignal:
    return RuleFindingSignal(
        finding_type="BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE", state="ACTIVE"
    )


def _delivery_finding() -> RuleFindingSignal:
    return RuleFindingSignal(finding_type="PRESSURE_ABOVE_CONTEXTUAL_BASELINE", state="ACTIVE")


class TestEnergyDeviationNecessaryNeverSufficient:
    def test_elevated_energy_alone_with_no_independent_evidence_is_no_evidence(self) -> None:
        result = derive_attribution(_ctx())
        assert result.level == AttributionLevel.NO_EVIDENCE

    def test_within_expected_range_is_no_evidence_regardless_of_other_signals(self) -> None:
        result = derive_attribution(
            _ctx(
                energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
            )
        )
        assert result.level == AttributionLevel.NO_EVIDENCE
        assert any("no elevated energy" in f.lower() for f in result.limiting_factors)

    def test_below_expected_range_is_no_evidence(self) -> None:
        result = derive_attribution(_ctx(energy_status=EnergyAssessmentStatus.BELOW_EXPECTED_RANGE))
        assert result.level == AttributionLevel.NO_EVIDENCE

    def test_insufficient_baseline_is_no_evidence(self) -> None:
        result = derive_attribution(
            _ctx(energy_status=EnergyAssessmentStatus.INSUFFICIENT_BASELINE)
        )
        assert result.level == AttributionLevel.NO_EVIDENCE

    def test_insufficient_data_is_no_evidence(self) -> None:
        result = derive_attribution(_ctx(energy_status=EnergyAssessmentStatus.INSUFFICIENT_DATA))
        assert result.level == AttributionLevel.NO_EVIDENCE

    def test_data_quality_limited_energy_is_no_evidence(self) -> None:
        result = derive_attribution(_ctx(energy_status=EnergyAssessmentStatus.DATA_QUALITY_LIMITED))
        assert result.level == AttributionLevel.NO_EVIDENCE


class TestEvidenceFamilies:
    def test_one_family_is_possible_not_moderate(self) -> None:
        result = derive_attribution(_ctx(rule_findings=(_friction_finding(),)))
        assert result.level == AttributionLevel.POSSIBLE

    def test_two_independent_families_no_contradiction_is_at_least_moderate(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
            )
        )
        assert result.level in (AttributionLevel.MODERATE, AttributionLevel.STRONG)

    def test_multiple_findings_in_same_family_still_count_as_one_family(self) -> None:
        """Deduplication: two friction findings (bearing temp + vibration) must not
        count as two independent families — only one other family (delivery) is present,
        so this must land on MODERATE at most, never STRONG from friction alone."""
        result = derive_attribution(
            _ctx(
                rule_findings=(
                    _friction_finding(),
                    RuleFindingSignal(
                        finding_type="VIBRATION_ABOVE_CONTEXTUAL_BASELINE", state="ACTIVE"
                    ),
                ),
                condition_type="BEARING_CONDITION_DEGRADATION",
            )
        )
        # Only ONE family (BEARING_FRICTION) supports here — delivery is absent — so this
        # must be POSSIBLE, not MODERATE/STRONG, proving the two same-family findings did
        # not get double-counted as two families.
        assert result.level == AttributionLevel.POSSIBLE

    def test_state_estimate_in_same_family_does_not_add_a_third_family(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(),),
                state_estimates=(
                    StateEstimateSignal(
                        state_type="BEARING_CONDITION_STATE",
                        trend="DETERIORATING",
                        uncertainty="LOW",
                        meaningfully_elevated=True,
                    ),
                ),
            )
        )
        # Still only BEARING_FRICTION — the state estimate reinforces the same family, it
        # does not create a second one — so still POSSIBLE, not MODERATE.
        assert result.level == AttributionLevel.POSSIBLE


class TestContradictionHandling:
    def test_independent_bearing_condition_caps_at_possible_even_with_friction_evidence(
        self,
    ) -> None:
        """The core IDF-01-shaped case: elevated energy + real bearing/friction evidence,
        but the synthesized condition explicitly attributes it to an independent,
        non-lubrication cause. Must not reach MODERATE/STRONG."""
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(),),
                condition_type="INDEPENDENT_BEARING_CONDITION",
            )
        )
        assert result.level == AttributionLevel.POSSIBLE
        assert any("independent" in c.lower() for c in result.contradicting_evidence)

    def test_independent_bearing_condition_caps_even_with_two_raw_families(self) -> None:
        """Even if both raw families happen to be present, an explicit contradiction
        still hard-caps at POSSIBLE — contradiction outranks family count."""
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="INDEPENDENT_BEARING_CONDITION",
            )
        )
        assert result.level == AttributionLevel.POSSIBLE

    def test_normal_operation_condition_contradicts(self) -> None:
        result = derive_attribution(
            _ctx(rule_findings=(_friction_finding(),), condition_type="NORMAL_OPERATION")
        )
        assert result.level == AttributionLevel.POSSIBLE
        assert result.contradicting_evidence

    def test_energy_high_but_all_other_signals_normal_is_no_evidence(self) -> None:
        """Section 11's literal example: energy elevated, but no compatible independent
        evidence at all and condition says normal -> NO_EVIDENCE, not POSSIBLE."""
        result = derive_attribution(_ctx(condition_type="NORMAL_OPERATION"))
        assert result.level == AttributionLevel.NO_EVIDENCE


class TestDataQualityGating:
    def test_poor_lubrication_bearing_sensor_quality_caps_at_possible(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
                condition_data_trustworthiness="CAUTION",
            )
        )
        assert result.level == AttributionLevel.POSSIBLE
        assert result.data_quality_state != "TRUSTED"

    def test_no_trusted_lubrication_data_caps_at_possible(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
                condition_data_trustworthiness="NO_TRUSTED_DATA",
            )
        )
        assert result.level == AttributionLevel.POSSIBLE

    def test_degraded_data_quality_surfaced_even_with_no_energy_deviation(self) -> None:
        """AF-101-shaped case: no current elevated energy, but bearing instrumentation is
        independently known-degraded — this must still be visible as a limiting factor,
        even though the top-line level is NO_EVIDENCE (nothing to attribute yet)."""
        result = derive_attribution(
            _ctx(
                energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
                condition_data_trustworthiness="NO_TRUSTED_DATA",
            )
        )
        assert result.level == AttributionLevel.NO_EVIDENCE
        assert any("data quality" in f.lower() for f in result.limiting_factors)

    def test_coarse_baseline_fallback_is_a_limiting_factor_not_silently_ignored(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(),),
                baseline_source=BaselineSourceKind.SENSOR_LEVEL,
            )
        )
        assert any("fallback" in f.lower() for f in result.limiting_factors)


class TestStrongIsHardToReach:
    def test_strong_requires_condition_support_exact_context_and_trusted_data(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
                baseline_source=BaselineSourceKind.EXACT_CONTEXT,
                condition_data_trustworthiness="TRUSTED",
            )
        )
        assert result.level == AttributionLevel.STRONG

    def test_two_families_without_condition_support_is_moderate_not_strong(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="AMBIGUOUS_CONDITION",
            )
        )
        assert result.level == AttributionLevel.MODERATE

    def test_two_families_with_coarse_baseline_is_moderate_not_strong(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
                baseline_source=BaselineSourceKind.OPERATING_STATE,
            )
        )
        assert result.level == AttributionLevel.MODERATE


class TestMLGovernance:
    def test_experimental_ml_evidence_cannot_manufacture_strong_or_moderate_attribution(
        self,
    ) -> None:
        """Even an ML prediction that hints toward a lubrication condition must never be
        counted as an independent family — with zero real raw evidence, this stays
        NO_EVIDENCE regardless of what an EXPERIMENT-lifecycle model predicted."""
        result = derive_attribution(
            _ctx(
                ml_signals=(
                    MLSignal(
                        model_id="FAILURE_CLASSIFICATION_V1",
                        predicted_class="RESTRICTION",
                        anomalous=None,
                        is_experimental=True,
                        condition_hint="DEVELOPING_RESTRICTION_PATTERN",
                    ),
                ),
            )
        )
        assert result.level == AttributionLevel.NO_EVIDENCE

    def test_experimental_ml_evidence_is_labeled_non_authoritative(self) -> None:
        result = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(),),
                ml_signals=(
                    MLSignal(
                        model_id="LUBRICATION_ANOMALY_V1",
                        predicted_class=None,
                        anomalous=True,
                        is_experimental=True,
                        condition_hint=None,
                    ),
                ),
            )
        )
        assert any(
            "experimental" in s.lower() and "not decision-authoritative" in s.lower()
            for s in result.supporting_evidence
        )

    def test_ml_evidence_never_increases_family_count_even_with_two_raw_families_present(
        self,
    ) -> None:
        """A third (ML) mention alongside two real families must not push the result past
        what the two real families alone would earn."""
        with_ml = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
                ml_signals=(
                    MLSignal(
                        model_id="FAILURE_CLASSIFICATION_V1",
                        predicted_class="RESTRICTION",
                        anomalous=None,
                        is_experimental=True,
                        condition_hint="DEVELOPING_RESTRICTION_PATTERN",
                    ),
                ),
            )
        )
        without_ml = derive_attribution(
            _ctx(
                rule_findings=(_friction_finding(), _delivery_finding()),
                condition_type="DEVELOPING_RESTRICTION_PATTERN",
            )
        )
        assert with_ml.level == without_ml.level


def test_policy_version_is_always_set() -> None:
    result = derive_attribution(_ctx())
    assert result.policy_version

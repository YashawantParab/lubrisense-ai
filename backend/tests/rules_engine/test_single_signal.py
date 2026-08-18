"""Unit tests for `app.rules_engine.rules.single_signal` and `.quality` — pure functions,
no database."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.domain.enums import DeviationClassification, EvidenceStrength, RuleFindingType
from app.rules_engine.config.policy import load_rules_policy
from app.rules_engine.domain.context import ReservoirSignalEvaluation, SignalEvaluation
from app.rules_engine.rules.quality import check_insufficient_trusted_data
from app.rules_engine.rules.single_signal import (
    check_flow_below_contextual_baseline,
    check_pressure_above_contextual_baseline,
    check_reservoir_level_low,
)

POLICY = load_rules_policy()


def _signal(
    *,
    measurement_type: str = "PRESSURE",
    value: float = 20.0,
    median: float = 10.0,
    classification: DeviationClassification = DeviationClassification.STRONG_DEVIATION,
    eligible: bool = True,
    caution: bool = False,
) -> SignalEvaluation:
    return SignalEvaluation(
        measurement_type=measurement_type,
        component_type="CIRCUIT",
        component_id=uuid.uuid4(),
        sample_count_in_window=30,
        eligible=eligible,
        caution=caution,
        latest_value=value,
        latest_event_id=uuid.uuid4(),
        latest_timestamp=datetime.now(UTC),
        latest_operating_state="RUNNING_NORMAL_LOAD",
        baseline_profile_id=uuid.uuid4(),
        baseline_version=1,
        baseline_median=median,
        deviation_classification=classification,
        deviation_distance=5.0,
    )


def test_pressure_above_baseline_fires_when_value_exceeds_median() -> None:
    signal = _signal(value=20.0, median=10.0)
    finding = check_pressure_above_contextual_baseline(signal, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    assert finding.evidence_strength == EvidenceStrength.STRONG


def test_pressure_above_baseline_does_not_fire_when_value_is_below_median() -> None:
    """Directional: a strong deviation *below* the median is not this finding (it would be
    a below-baseline signal instead) — brief §11's rules are directional, not "any
    deviation"."""
    signal = _signal(value=1.0, median=10.0)
    finding = check_pressure_above_contextual_baseline(signal, POLICY)
    assert finding is None


def test_flow_below_baseline_fires_when_value_is_below_median() -> None:
    signal = _signal(measurement_type="FLOW", value=1.0, median=10.0)
    finding = check_flow_below_contextual_baseline(signal, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE


def test_no_finding_when_deviation_within_expected_range() -> None:
    signal = _signal(classification=DeviationClassification.WITHIN_EXPECTED_RANGE)
    assert check_pressure_above_contextual_baseline(signal, POLICY) is None


def test_no_finding_when_signal_ineligible() -> None:
    signal = _signal(eligible=False)
    assert check_pressure_above_contextual_baseline(signal, POLICY) is None


def test_caution_caps_evidence_strength_at_moderate() -> None:
    """A STRONG deviation from an ELIGIBLE_WITH_CAUTION sensor is capped, never silently
    excluded (Phase 9 brief §4: "evidence strength reduced or annotated")."""
    signal = _signal(classification=DeviationClassification.STRONG_DEVIATION, caution=True)
    finding = check_pressure_above_contextual_baseline(signal, POLICY)
    assert finding is not None
    assert finding.evidence_strength == EvidenceStrength.MODERATE
    assert finding.quality_context["caution"] is True


def _reservoir(*, level: float | None = 15.0, eligible: bool = True) -> ReservoirSignalEvaluation:
    return ReservoirSignalEvaluation(
        component_type="LUBRICATION_SYSTEM",
        component_id=uuid.uuid4(),
        eligible=eligible,
        latest_level_percent=level,
        latest_timestamp=datetime.now(UTC),
        recent_depletion_rate_percent_per_hour=None,
        baseline_profile_id=None,
        baseline_version=None,
        baseline_depletion_rate_percent_per_hour=None,
        deviation_classification=None,
        deviation_distance=None,
    )


def test_reservoir_level_low_warning_band() -> None:
    finding = check_reservoir_level_low(_reservoir(level=15.0), POLICY)
    assert finding is not None
    assert finding.evidence_strength == EvidenceStrength.MODERATE


def test_reservoir_level_low_critical_band() -> None:
    finding = check_reservoir_level_low(_reservoir(level=5.0), POLICY)
    assert finding is not None
    assert finding.evidence_strength == EvidenceStrength.STRONG


def test_reservoir_level_normal_does_not_fire() -> None:
    assert check_reservoir_level_low(_reservoir(level=80.0), POLICY) is None


def test_reservoir_level_low_suppressed_when_ineligible() -> None:
    assert check_reservoir_level_low(_reservoir(level=1.0, eligible=False), POLICY) is None


def test_insufficient_trusted_data_fires_below_minimum_fraction() -> None:
    machine_id = uuid.uuid4()
    finding = check_insufficient_trusted_data(
        machine_id,
        tracked_sensor_count=8,
        eligible_sensor_fraction=0.2,
        policy=POLICY,
    )
    assert finding is not None
    assert finding.finding_type == RuleFindingType.INSUFFICIENT_TRUSTED_DATA
    assert finding.component_id == machine_id


def test_insufficient_trusted_data_does_not_fire_above_minimum_fraction() -> None:
    finding = check_insufficient_trusted_data(
        uuid.uuid4(), tracked_sensor_count=8, eligible_sensor_fraction=0.9, policy=POLICY
    )
    assert finding is None


def test_insufficient_trusted_data_does_not_fire_with_zero_tracked_sensors() -> None:
    finding = check_insufficient_trusted_data(
        uuid.uuid4(), tracked_sensor_count=0, eligible_sensor_fraction=0.0, policy=POLICY
    )
    assert finding is None

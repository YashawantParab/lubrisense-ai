"""Unit tests for `app.rules_engine.rules.cross_signal` and `.bearing` — pure functions,
no database. These are the mandatory differentiation rules (Phase 9 brief §13/§14/§39)."""

from __future__ import annotations

import uuid

from app.domain.enums import EvidenceStrength, RuleCategory, RuleFindingType
from app.rules_engine.config.policy import load_rules_policy
from app.rules_engine.domain.results import RuleFindingCandidate
from app.rules_engine.rules.bearing import check_independent_bearing_pattern
from app.rules_engine.rules.cross_signal import (
    check_leakage_pattern,
    check_lubrication_path_degradation_pattern,
    check_pump_degradation_pattern,
    check_restriction_pattern,
)

POLICY = load_rules_policy()


def _candidate(
    finding_type: RuleFindingType, *, strength: EvidenceStrength = EvidenceStrength.MODERATE
) -> RuleFindingCandidate:
    return RuleFindingCandidate(
        finding_type=finding_type,
        rule_id=finding_type.value.lower(),
        rule_version="1",
        category=RuleCategory.HYDRAULIC,
        component_type="CIRCUIT",
        component_id=uuid.uuid4(),
        evidence_strength=strength,
        message="test",
        evidence={},
        limitations=[],
        source_event_ids=[],
        baseline_version_ids=[],
        quality_context={},
    )


def test_restriction_pattern_fires_on_flow_below_and_pressure_above() -> None:
    findings = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        ),
        RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
        ),
    }
    finding = check_restriction_pattern(findings, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN


def test_restriction_pattern_does_not_fire_on_flow_alone() -> None:
    findings = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        )
    }
    assert check_restriction_pattern(findings, POLICY) is None


def test_restriction_pattern_escalates_with_supporting_evidence() -> None:
    without_support = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        ),
        RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
        ),
    }
    with_support = {
        **without_support,
        RuleFindingType.PUMP_CURRENT_ABOVE_BASELINE: _candidate(
            RuleFindingType.PUMP_CURRENT_ABOVE_BASELINE
        ),
    }
    base = check_restriction_pattern(without_support, POLICY)
    escalated = check_restriction_pattern(with_support, POLICY)
    assert base is not None and escalated is not None
    assert escalated.evidence_strength == EvidenceStrength.STRONG
    assert base.evidence_strength == EvidenceStrength.MODERATE


def test_leakage_pattern_fires_on_flow_below_and_depletion_abnormal_without_pressure() -> None:
    findings = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        ),
        RuleFindingType.RESERVOIR_DEPLETION_ABNORMAL: _candidate(
            RuleFindingType.RESERVOIR_DEPLETION_ABNORMAL
        ),
    }
    finding = check_leakage_pattern(findings, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.FLOW_PRESSURE_LEAKAGE_PATTERN


def test_leakage_pattern_excluded_when_pressure_also_elevated() -> None:
    """Mandatory: leakage must not fire when pressure is also above baseline — that
    signature belongs to restriction instead (Phase 9 brief §13/§37)."""
    findings = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        ),
        RuleFindingType.RESERVOIR_DEPLETION_ABNORMAL: _candidate(
            RuleFindingType.RESERVOIR_DEPLETION_ABNORMAL
        ),
        RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
        ),
    }
    assert check_leakage_pattern(findings, POLICY) is None
    # But restriction *does* still see its own required combination satisfied.
    restriction = check_restriction_pattern(findings, POLICY)
    assert restriction is not None


def test_pump_degradation_pattern_excluded_when_pressure_elevated() -> None:
    """Mandatory: pump degradation (slow rise, no elevated peak) must not fire when
    pressure is elevated — that belongs to restriction instead (brief §14/§38)."""
    findings = {
        RuleFindingType.PRESSURE_BUILD_SLOW: _candidate(RuleFindingType.PRESSURE_BUILD_SLOW),
        RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
        ),
    }
    assert check_pump_degradation_pattern(findings, POLICY) is None


def test_pump_degradation_pattern_fires_without_elevated_pressure() -> None:
    findings = {
        RuleFindingType.PRESSURE_BUILD_SLOW: _candidate(RuleFindingType.PRESSURE_BUILD_SLOW)
    }
    finding = check_pump_degradation_pattern(findings, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.PUMP_DEGRADATION_PATTERN


def test_lubrication_path_degradation_requires_minimum_distinct_signals() -> None:
    one_signal = {
        RuleFindingType.PUMP_RUNTIME_ABOVE_BASELINE: _candidate(
            RuleFindingType.PUMP_RUNTIME_ABOVE_BASELINE
        )
    }
    assert check_lubrication_path_degradation_pattern(one_signal, False, POLICY) is None

    two_signals = {
        **one_signal,
        RuleFindingType.CYCLE_DURATION_ABOVE_BASELINE: _candidate(
            RuleFindingType.CYCLE_DURATION_ABOVE_BASELINE
        ),
    }
    finding = check_lubrication_path_degradation_pattern(two_signals, False, POLICY)
    assert finding is not None
    assert finding.finding_type == RuleFindingType.LUBRICATION_PATH_DEGRADATION_PATTERN


def test_lubrication_path_degradation_suppressed_when_specific_pattern_already_matched() -> None:
    """Never double-count the same evidence into both a specific pattern and the generic
    catch-all (Phase 9 brief §15)."""
    two_signals = {
        RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.FLOW_BELOW_CONTEXTUAL_BASELINE
        ),
        RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE: _candidate(
            RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
        ),
    }
    assert check_lubrication_path_degradation_pattern(two_signals, True, POLICY) is None


def test_independent_bearing_pattern_fires_when_lubrication_normal() -> None:
    bearing_id = uuid.uuid4()
    temp = _candidate(RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE)
    finding = check_independent_bearing_pattern(
        bearing_id, temp, None, lubrication_signals_normal=True, policy=POLICY
    )
    assert finding is not None
    assert finding.finding_type == RuleFindingType.INDEPENDENT_BEARING_CONDITION_PATTERN
    assert finding.component_id == bearing_id


def test_independent_bearing_pattern_suppressed_when_lubrication_abnormal() -> None:
    """Mandatory (brief §39): must NOT fire while a lubrication-system signal is also
    active — that is a lubrication-caused consequence, not an independent bearing issue."""
    temp = _candidate(RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE)
    finding = check_independent_bearing_pattern(
        uuid.uuid4(), temp, None, lubrication_signals_normal=False, policy=POLICY
    )
    assert finding is None


def test_independent_bearing_pattern_escalates_with_both_signals() -> None:
    bearing_id = uuid.uuid4()
    temp = _candidate(RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE)
    vibration = _candidate(RuleFindingType.VIBRATION_ABOVE_CONTEXTUAL_BASELINE)
    temp_only = check_independent_bearing_pattern(
        bearing_id, temp, None, lubrication_signals_normal=True, policy=POLICY
    )
    both = check_independent_bearing_pattern(
        bearing_id, temp, vibration, lubrication_signals_normal=True, policy=POLICY
    )
    assert temp_only is not None and both is not None
    assert both.evidence_strength == EvidenceStrength.STRONG
    assert temp_only.evidence_strength == EvidenceStrength.MODERATE


def test_independent_bearing_pattern_noop_with_no_signals() -> None:
    assert (
        check_independent_bearing_pattern(
            uuid.uuid4(), None, None, lubrication_signals_normal=True, policy=POLICY
        )
        is None
    )

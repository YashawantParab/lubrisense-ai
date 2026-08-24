"""Pure tests for `app.portfolio.domain.priority` (Portfolio Intelligence Pass 1,
ADR-177)."""

from __future__ import annotations

from app.domain.enums import (
    ActionReadinessState,
    ConditionConfidence,
    ConditionSeverity,
    ConditionType,
    Criticality,
    DecisionPriority,
    EnergyAssessmentStatus,
    PortfolioPriority,
)
from app.portfolio.domain.priority import PriorityInput, derive_priority

_BASE_KWARGS: dict[str, object] = {
    "action_readiness": ActionReadinessState.MONITORING_ONLY,
    "condition_type": ConditionType.NORMAL_OPERATION,
    "condition_severity": ConditionSeverity.INFO,
    "condition_confidence": ConditionConfidence.HIGH,
    "criticality": Criticality.MEDIUM,
    "has_open_incident": False,
    "incident_severity": None,
    "has_open_maintenance": False,
    "maintenance_priority": None,
    "energy_status": None,
    "attribution_level_is_supporting": False,
}


def _input(**overrides: object) -> PriorityInput:
    kwargs = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return PriorityInput(**kwargs)  # type: ignore[arg-type]


def test_healthy_machine_is_monitor() -> None:
    result = derive_priority(_input())
    assert result.priority == PortfolioPriority.MONITOR
    assert result.reasons


def test_assessment_blocked_is_data_limited_regardless_of_other_signals() -> None:
    result = derive_priority(
        _input(
            action_readiness=ActionReadinessState.ASSESSMENT_BLOCKED,
            condition_severity=ConditionSeverity.CRITICAL,
            has_open_incident=True,
            incident_severity=ConditionSeverity.CRITICAL,
        )
    )
    assert result.priority == PortfolioPriority.DATA_LIMITED


def test_not_yet_assessed_is_data_limited() -> None:
    result = derive_priority(_input(action_readiness=ActionReadinessState.NOT_YET_ASSESSED))
    assert result.priority == PortfolioPriority.DATA_LIMITED


def test_critical_condition_severity_is_critical_attention() -> None:
    result = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.CRITICAL,
            condition_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        )
    )
    assert result.priority == PortfolioPriority.CRITICAL_ATTENTION
    assert any("CRITICAL" in r for r in result.reasons)


def test_warning_severity_is_attention() -> None:
    result = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.WARNING,
        )
    )
    assert result.priority == PortfolioPriority.ATTENTION


def test_high_severity_is_high_attention() -> None:
    result = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.HIGH,
        )
    )
    assert result.priority == PortfolioPriority.HIGH_ATTENTION


def test_energy_alone_never_exceeds_attention() -> None:
    result = derive_priority(_input(energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND))
    assert result.priority == PortfolioPriority.ATTENTION
    assert any("energy" in r.lower() for r in result.reasons)


def test_energy_never_outranks_a_critical_reliability_issue() -> None:
    """Energy/carbon evidence must never push a machine above what reliability evidence
    alone already justifies."""
    without_energy = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.CRITICAL,
        )
    )
    with_energy = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.CRITICAL,
            energy_status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
            attribution_level_is_supporting=True,
        )
    )
    assert without_energy.priority == with_energy.priority == PortfolioPriority.CRITICAL_ATTENTION


def test_energy_does_not_downgrade_an_existing_attention_level() -> None:
    result = derive_priority(
        _input(
            action_readiness=ActionReadinessState.HUMAN_ACTION_REQUIRED,
            condition_severity=ConditionSeverity.HIGH,
            energy_status=EnergyAssessmentStatus.WITHIN_EXPECTED_RANGE,
        )
    )
    assert result.priority == PortfolioPriority.HIGH_ATTENTION


def test_open_critical_incident_is_critical_attention() -> None:
    result = derive_priority(
        _input(has_open_incident=True, incident_severity=ConditionSeverity.CRITICAL)
    )
    assert result.priority == PortfolioPriority.CRITICAL_ATTENTION


def test_urgent_maintenance_is_critical_attention() -> None:
    result = derive_priority(
        _input(has_open_maintenance=True, maintenance_priority=DecisionPriority.URGENT)
    )
    assert result.priority == PortfolioPriority.CRITICAL_ATTENTION


def test_critical_asset_criticality_escalates_high_to_critical() -> None:
    result = derive_priority(
        _input(condition_severity=ConditionSeverity.HIGH, criticality=Criticality.CRITICAL)
    )
    assert result.priority == PortfolioPriority.CRITICAL_ATTENTION


def test_criticality_alone_never_manufactures_a_diagnosis() -> None:
    """A perfectly healthy CRITICAL-criticality asset stays at MONITOR — criticality is
    a modifier, never an independent source of attention."""
    result = derive_priority(_input(criticality=Criticality.CRITICAL))
    assert result.priority == PortfolioPriority.MONITOR


def test_low_confidence_caps_below_critical_attention() -> None:
    result = derive_priority(
        _input(
            condition_severity=ConditionSeverity.CRITICAL,
            condition_confidence=ConditionConfidence.LOW,
        )
    )
    assert result.priority == PortfolioPriority.HIGH_ATTENTION
    assert any("confidence LOW" in r for r in result.reasons)


def test_reasons_are_never_a_bare_score() -> None:
    result = derive_priority(_input(condition_severity=ConditionSeverity.CRITICAL))
    for reason in result.reasons:
        assert not reason.replace(".", "", 1).isdigit()


def test_policy_version_is_always_set() -> None:
    result = derive_priority(_input())
    assert result.policy_version == "1"

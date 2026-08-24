"""Pure tests for `app.portfolio.domain.action_readiness` (Portfolio Intelligence Pass 1,
ADR-177)."""

from __future__ import annotations

from app.domain.enums import ActionReadinessState, ConditionConfidence, ConditionType
from app.portfolio.domain.action_readiness import derive_action_readiness


def test_no_condition_assessment_is_not_yet_assessed() -> None:
    result = derive_action_readiness(
        has_condition_assessment=False,
        condition_type=None,
        condition_confidence=None,
        has_open_workflow=False,
    )
    assert result == ActionReadinessState.NOT_YET_ASSESSED


def test_blocked_condition_type_is_assessment_blocked() -> None:
    for blocked in (
        ConditionType.SENSOR_OR_DATA_QUALITY_LIMITATION,
        ConditionType.INSUFFICIENT_EVIDENCE,
        ConditionType.AMBIGUOUS_CONDITION,
    ):
        result = derive_action_readiness(
            has_condition_assessment=True,
            condition_type=blocked,
            condition_confidence=ConditionConfidence.LOW,
            has_open_workflow=False,
        )
        assert result == ActionReadinessState.ASSESSMENT_BLOCKED


def test_blocked_condition_outranks_open_workflow() -> None:
    result = derive_action_readiness(
        has_condition_assessment=True,
        condition_type=ConditionType.INSUFFICIENT_EVIDENCE,
        condition_confidence=None,
        has_open_workflow=True,
    )
    assert result == ActionReadinessState.ASSESSMENT_BLOCKED


def test_open_workflow_is_human_action_required() -> None:
    result = derive_action_readiness(
        has_condition_assessment=True,
        condition_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        condition_confidence=ConditionConfidence.HIGH,
        has_open_workflow=True,
    )
    assert result == ActionReadinessState.HUMAN_ACTION_REQUIRED


def test_low_confidence_without_workflow_is_data_limited() -> None:
    result = derive_action_readiness(
        has_condition_assessment=True,
        condition_type=ConditionType.NORMAL_OPERATION,
        condition_confidence=ConditionConfidence.LOW,
        has_open_workflow=False,
    )
    assert result == ActionReadinessState.DATA_LIMITED


def test_normal_operation_trusted_confidence_no_workflow_is_monitoring_only() -> None:
    result = derive_action_readiness(
        has_condition_assessment=True,
        condition_type=ConditionType.NORMAL_OPERATION,
        condition_confidence=ConditionConfidence.HIGH,
        has_open_workflow=False,
    )
    assert result == ActionReadinessState.MONITORING_ONLY

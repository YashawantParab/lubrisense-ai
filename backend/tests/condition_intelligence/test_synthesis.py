"""Pure `synthesize()` logic tests (Phase 13 brief §13.6-§13.10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.condition_intelligence.config.policy import load_condition_intelligence_policy
from app.condition_intelligence.domain.models import ConditionEvidence, EvidenceItem
from app.condition_intelligence.services.synthesis import synthesize

POLICY = load_condition_intelligence_policy()
TENANT = uuid.uuid4()
MACHINE = uuid.uuid4()


def _evidence(
    items: tuple[EvidenceItem, ...] = (),
    *,
    rule_finding_ids: tuple[str, ...] = (),
    ml_result_ids: tuple[str, ...] = (),
    state_estimate_ids: tuple[str, ...] = (),
    instrumentation_coverage: dict[str, object] | None = None,
    quality_context: dict[str, object] | None = None,
    limitations: tuple[str, ...] = (),
) -> ConditionEvidence:
    return ConditionEvidence(
        tenant_id=TENANT,
        machine_id=MACHINE,
        as_of_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        criticality="MEDIUM",
        items=items,
        quality_context=quality_context or {"state": "TRUSTED"},
        instrumentation_coverage=instrumentation_coverage
        or {"registered_sensor_count": 5, "unusable_sensor_count": 0},
        baseline_versions={},
        rule_finding_ids=rule_finding_ids,
        ml_result_ids=ml_result_ids,
        state_estimate_ids=state_estimate_ids,
        limitations=limitations,
    )


def _item(
    source_type: str,
    strength: str,
    condition_hint: str | None,
    description: str = "evidence",
    severity: str | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        source_type=source_type,
        source_id=str(uuid.uuid4()),
        strength=strength,
        condition_hint=condition_hint,
        description=description,
        severity=severity,
    )


def test_zero_evidence_sources_is_insufficient_evidence() -> None:
    result = synthesize(_evidence(), POLICY)
    assert result.condition_type == "INSUFFICIENT_EVIDENCE"
    assert result.confidence == "LOW"


def test_checked_but_nothing_abnormal_is_normal_operation_not_insufficient() -> None:
    """Regression test for a real bug: a source that WAS checked and found nothing
    abnormal (e.g. a stable state estimate) must not be conflated with no evidence at
    all."""
    items = (_item("STATE_ESTIMATE", "SUPPORTING", "NORMAL_OPERATION", "stable"),)
    result = synthesize(_evidence(items, state_estimate_ids=("se-1",)), POLICY)
    assert result.condition_type == "NORMAL_OPERATION"
    assert result.confidence == "HIGH"


def test_normal_operation_confidence_moderate_without_explicit_normal_vote() -> None:
    """Sources were checked (rule findings exist) but none voted anything, and none
    explicitly voted NORMAL_OPERATION either — still NORMAL_OPERATION, but MODERATE."""
    result = synthesize(_evidence(rule_finding_ids=("rf-1",)), POLICY)
    assert result.condition_type == "NORMAL_OPERATION"
    assert result.confidence == "MODERATE"


def test_zero_registered_sensors_is_insufficient_evidence_via_quality_gate() -> None:
    result = synthesize(
        _evidence(
            instrumentation_coverage={"registered_sensor_count": 0, "unusable_sensor_count": 0}
        ),
        POLICY,
    )
    assert result.condition_type == "INSUFFICIENT_EVIDENCE"


def test_majority_unusable_sensors_triggers_quality_limitation() -> None:
    result = synthesize(
        _evidence(
            instrumentation_coverage={"registered_sensor_count": 4, "unusable_sensor_count": 3}
        ),
        POLICY,
    )
    assert result.condition_type == "SENSOR_OR_DATA_QUALITY_LIMITATION"


def test_quality_gate_takes_priority_over_any_other_evidence() -> None:
    items = (_item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),)
    result = synthesize(
        _evidence(
            items,
            rule_finding_ids=("rf-1",),
            instrumentation_coverage={"registered_sensor_count": 4, "unusable_sensor_count": 4},
        ),
        POLICY,
    )
    assert result.condition_type == "SENSOR_OR_DATA_QUALITY_LIMITATION"


def test_single_strong_vote_with_corroboration_is_high_confidence() -> None:
    items = (
        _item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),
        _item("STATE_ESTIMATE", "SUPPORTING", "LUBRICATION_DELIVERY_DEGRADATION"),
    )
    result = synthesize(_evidence(items, rule_finding_ids=("rf-1",)), POLICY)
    assert result.condition_type == "DEVELOPING_RESTRICTION_PATTERN"
    assert result.confidence == "HIGH"


def test_lone_strong_vote_without_corroboration_is_moderate_confidence() -> None:
    items = (_item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),)
    result = synthesize(_evidence(items, rule_finding_ids=("rf-1",)), POLICY)
    assert result.condition_type == "DEVELOPING_RESTRICTION_PATTERN"
    assert result.confidence == "MODERATE"


def test_lone_supporting_vote_is_low_confidence() -> None:
    items = (_item("RULE_FINDING", "SUPPORTING", "PUMP_PERFORMANCE_DEGRADATION"),)
    result = synthesize(_evidence(items, rule_finding_ids=("rf-1",)), POLICY)
    assert result.condition_type == "PUMP_PERFORMANCE_DEGRADATION"
    assert result.confidence == "LOW"


def test_two_supporting_votes_from_distinct_sources_reach_moderate() -> None:
    items = (
        _item("RULE_FINDING", "SUPPORTING", "PUMP_PERFORMANCE_DEGRADATION"),
        _item("ML_RESULT", "SUPPORTING", "PUMP_PERFORMANCE_DEGRADATION"),
    )
    result = synthesize(
        _evidence(items, rule_finding_ids=("rf-1",), ml_result_ids=("ml-1",)), POLICY
    )
    assert result.confidence == "MODERATE"


def test_experimental_ml_evidence_never_establishes_a_condition_alone() -> None:
    """Phase 13 brief §13.3: EXPERIMENT-status ML output must not independently create a
    strong final condition."""
    items = (_item("ML_RESULT", "EXPERIMENTAL", "DEVELOPING_RESTRICTION_PATTERN"),)
    result = synthesize(_evidence(items, ml_result_ids=("ml-1",)), POLICY)
    assert result.condition_type == "NORMAL_OPERATION"


def test_weak_evidence_never_establishes_a_condition_alone() -> None:
    items = (_item("STATE_ESTIMATE", "WEAK", "LUBRICATION_DELIVERY_DEGRADATION"),)
    result = synthesize(_evidence(items, state_estimate_ids=("se-1",)), POLICY)
    assert result.condition_type == "NORMAL_OPERATION"


def test_conflicting_hypotheses_produce_ambiguous_condition() -> None:
    """Phase 13 brief §13.8: rules suggest one thing, ML suggests another distinct
    unrelated fault -> disagreement must be surfaced, not silently resolved."""
    items = (
        _item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),
        _item("ML_RESULT", "SUPPORTING", "POSSIBLE_LEAKAGE_PATTERN"),
    )
    result = synthesize(
        _evidence(items, rule_finding_ids=("rf-1",), ml_result_ids=("ml-1",)), POLICY
    )
    assert result.condition_type == "AMBIGUOUS_CONDITION"
    assert result.confidence in ("LOW", "MODERATE")


def test_rules_vote_fault_ml_votes_normal_is_ambiguous() -> None:
    items = (
        _item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),
        _item("ML_RESULT", "SUPPORTING", "NORMAL_OPERATION"),
    )
    result = synthesize(
        _evidence(items, rule_finding_ids=("rf-1",), ml_result_ids=("ml-1",)), POLICY
    )
    assert result.condition_type == "AMBIGUOUS_CONDITION"


def test_delivery_and_bearing_coexistence_is_not_ambiguous() -> None:
    """Phase 13 brief §13.10: independent bearing evidence coexisting with delivery
    evidence is expected, not a conflict."""
    items = (
        _item("RULE_FINDING", "STRONG", "DEVELOPING_RESTRICTION_PATTERN"),
        _item("RULE_FINDING", "STRONG", "INDEPENDENT_BEARING_CONDITION"),
    )
    result = synthesize(_evidence(items, rule_finding_ids=("rf-1", "rf-2")), POLICY)
    assert result.condition_type == "DEVELOPING_RESTRICTION_PATTERN"
    assert any("bearing" in w.lower() for w in result.why)


def test_severity_borrowed_from_contributing_rule_finding() -> None:
    items = (
        _item(
            "RULE_FINDING",
            "STRONG",
            "DEVELOPING_RESTRICTION_PATTERN",
            severity="CRITICAL",
        ),
    )
    result = synthesize(_evidence(items, rule_finding_ids=("rf-1",)), POLICY)
    assert result.severity == "CRITICAL"


def test_severity_falls_back_to_default_when_no_rule_finding_present() -> None:
    items = (_item("ML_RESULT", "SUPPORTING", "PUMP_PERFORMANCE_DEGRADATION"),)
    result = synthesize(_evidence(items, ml_result_ids=("ml-1",)), POLICY)
    assert result.severity == POLICY.default_severity["PUMP_PERFORMANCE_DEGRADATION"]


@pytest.mark.parametrize(
    "condition_type",
    [
        "NORMAL_OPERATION",
        "LUBRICATION_DELIVERY_DEGRADATION",
        "DEVELOPING_RESTRICTION_PATTERN",
        "DELIVERY_BLOCKAGE_PATTERN",
        "POSSIBLE_LEAKAGE_PATTERN",
        "PUMP_PERFORMANCE_DEGRADATION",
        "LOW_LUBRICANT_AVAILABILITY",
        "BEARING_CONDITION_DEGRADATION",
        "INDEPENDENT_BEARING_CONDITION",
        "SENSOR_OR_DATA_QUALITY_LIMITATION",
        "INSUFFICIENT_EVIDENCE",
        "AMBIGUOUS_CONDITION",
    ],
)
def test_every_condition_type_has_a_default_severity(condition_type: str) -> None:
    assert condition_type in POLICY.default_severity

"""Shared evidence-seeding helpers for Phase 16/17/20 integration tests — mirrors
`tests/condition_intelligence/test_condition_engine.py`'s local `_active_rule_finding`
helper and `tests/rules_engine/helpers.py`'s pattern of writing real rows directly rather
than replaying full upstream pipelines."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    EvidenceStrength,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
    StateTrend,
    StateType,
    StateUncertaintyCategory,
)
from app.domain.models import RuleFinding, StateEstimate


async def active_rule_finding(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    finding_type: RuleFindingType,
    severity: RuleFindingSeverity = RuleFindingSeverity.WARNING,
) -> RuleFinding:
    now = datetime.now(UTC)
    finding = RuleFinding(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        machine_id=machine_id,
        component_id=None,
        component_type="MACHINE",
        finding_type=finding_type,
        rule_id=finding_type.value.lower(),
        rule_version="1.0.0",
        config_version="1.0.0",
        category=RuleCategory.HYDRAULIC,
        severity=severity,
        state=RuleFindingState.ACTIVE,
        evidence_strength=EvidenceStrength.STRONG,
        criticality_at_detection="MEDIUM",
        message=f"Test finding for {finding_type.value}",
        evidence={},
        limitations=[],
        quality_context={},
        baseline_version_ids=[],
        source_event_ids=[],
        window_start=now - timedelta(minutes=30),
        window_end=now,
        candidate_stable_cycles=3,
        first_detected_at=now - timedelta(minutes=30),
        last_detected_at=now,
        activated_at=now - timedelta(minutes=20),
        resolved_at=None,
    )
    session.add(finding)
    await session.flush()
    return finding


async def _state_estimate(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    state_type: StateType,
    state_value: float,
    trend: StateTrend,
) -> StateEstimate:
    row = StateEstimate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        machine_id=machine_id,
        component_id=None,
        state_type=state_type,
        as_of_timestamp=datetime.now(UTC),
        state_value=state_value,
        state_rate=0.01,
        trend=trend,
        uncertainty=StateUncertaintyCategory.MODERATE,
        covariance_summary={},
        estimator_id="test-estimator",
        estimator_version="1.0.0",
        config_version="1.0.0",
        feature_set="STATE_ESTIMATION_V1",
        feature_set_version="1.0.1",
        feature_vector_id=uuid.uuid4(),
        dt_seconds=60.0,
        prediction_only=False,
        observations_used=["test.robust_deviation"],
        observations_missing=[],
        quality_summary={},
    )
    session.add(row)
    await session.flush()
    return row


async def deteriorating_state_estimate(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    state_type: StateType,
    state_value: float = 0.6,
) -> StateEstimate:
    """A trustworthy, meaningfully-deteriorating state estimate — real evidence
    `ConditionEngine` will vote a specific/generic condition hint from (see
    `condition_engine._evidence_from_state_estimate`)."""
    return await _state_estimate(
        session,
        tenant_id=tenant_id,
        machine_id=machine_id,
        state_type=state_type,
        state_value=state_value,
        trend=StateTrend.DETERIORATING,
    )


async def stable_state_estimate(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    machine_id: uuid.UUID,
    state_type: StateType,
    state_value: float = 0.05,
) -> StateEstimate:
    """A trustworthy, stable state estimate — real evidence `ConditionEngine` votes
    `NORMAL_OPERATION` (SUPPORTING) from."""
    return await _state_estimate(
        session,
        tenant_id=tenant_id,
        machine_id=machine_id,
        state_type=state_type,
        state_value=state_value,
        trend=StateTrend.STABLE,
    )

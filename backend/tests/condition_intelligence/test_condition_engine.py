"""Database integration: `ConditionEngine.assess()` against real Postgres — a real
`RuleFinding`, a real quality-limited machine, and a real fresh/uninstrumented machine.
Mirrors `tests/state_estimation/test_persistence_and_replay.py`'s pattern."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.services.condition_engine import ConditionEngine
from app.domain.enums import (
    Eligibility,
    EvidenceStrength,
    QualityState,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
    SensorType,
)
from app.domain.models import RuleFinding
from tests.rules_engine.helpers import build_machine_with_topology, make_topology_sensor


async def _active_rule_finding(
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


@pytest.mark.asyncio
async def test_assess_with_no_evidence_at_all_is_insufficient_evidence(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, _circuit, _bearing = await build_machine_with_topology(db_session)
    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)
    assert assessment.condition_type.value == "INSUFFICIENT_EVIDENCE"
    assert assessment.lifecycle_state.value == "DETECTED"


@pytest.mark.asyncio
async def test_assess_unknown_machine_raises() -> None:
    from app.condition_intelligence.services.condition_engine import (
        ConditionEngineMachineNotFoundError,
    )
    from app.core.config import get_settings
    from app.infrastructure.database import Database

    database = Database(get_settings())
    try:
        async with database.session() as session:
            engine = ConditionEngine(session)
            with pytest.raises(ConditionEngineMachineNotFoundError):
                await engine.assess(uuid.uuid4(), uuid.uuid4())
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_assess_with_cross_signal_rule_finding_produces_matching_condition(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await _active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.WARNING,
    )

    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)

    assert assessment.condition_type.value == "DEVELOPING_RESTRICTION_PATTERN"
    assert assessment.severity.value == "WARNING"
    assert len(assessment.rule_finding_ids) == 1


@pytest.mark.asyncio
async def test_assess_critical_restriction_finding_maps_to_blockage(
    db_session: AsyncSession,
) -> None:
    """Phase 13's severity_override: a CRITICAL restriction-pattern finding is treated as
    blockage-pattern evidence instead."""
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await _active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.FLOW_PRESSURE_RESTRICTION_PATTERN,
        severity=RuleFindingSeverity.CRITICAL,
    )

    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)
    assert assessment.condition_type.value == "DELIVERY_BLOCKAGE_PATTERN"
    assert assessment.severity.value == "CRITICAL"


@pytest.mark.asyncio
async def test_assess_persists_lifecycle_across_consecutive_calls(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await _active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.PUMP_DEGRADATION_PATTERN,
    )

    engine = ConditionEngine(db_session)
    first = await engine.assess(tenant.id, machine.id)
    second = await engine.assess(tenant.id, machine.id)

    assert first.condition_type.value == "PUMP_PERFORMANCE_DEGRADATION"
    assert first.lifecycle_state.value == "DETECTED"
    assert second.condition_type.value == "PUMP_PERFORMANCE_DEGRADATION"
    assert second.lifecycle_state.value == "DEVELOPING"
    assert second.first_detected_at == first.first_detected_at


@pytest.mark.asyncio
async def test_assess_majority_unusable_sensors_is_quality_limitation(
    db_session: AsyncSession,
) -> None:
    from app.data_quality.repositories.sensor_quality_state_repository import (
        SensorQualityStateRepository,
    )

    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    sensor = await make_topology_sensor(
        db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id
    )
    quality_repo = SensorQualityStateRepository(db_session)
    await quality_repo.upsert(
        tenant.id,
        sensor.id,
        machine_id=machine.id,
        quality_state=QualityState.UNUSABLE,
        eligibility=Eligibility.INELIGIBLE,
        staleness_status="FRESH",
        clock_status="NORMAL",
        active_issue_count=1,
    )
    await db_session.flush()

    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)
    assert assessment.condition_type.value == "SENSOR_OR_DATA_QUALITY_LIMITATION"

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
    StateType,
)
from app.domain.models import RuleFinding
from tests.incidents.helpers import stable_state_estimate
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


@pytest.mark.asyncio
async def test_stable_elevated_state_estimate_does_not_block_delivery_bearing_coexistence(
    db_session: AsyncSession,
) -> None:
    """Regression test for the hosted-Neon flagship-seed blocker: a `LUBRICATION_DELIVERY_
    STATE` estimate that has already climbed to a meaningfully elevated level and then
    plateaued (STABLE — a Kalman filter's evidence channel can fully saturate against a
    freshly-computed, tightly-clustered contextual baseline within moments of a restriction
    developing, well before the filter's *rate* crosses the DETERIORATING threshold) must
    not cast a `NORMAL_OPERATION` vote that turns co-active, compatible pressure + bearing
    rule-finding evidence into a spurious `AMBIGUOUS_CONDITION` instead of the single
    `DEVELOPING_RESTRICTION_PATTERN` hypothesis the rest of the evidence actually supports
    (Phase 13 brief §13.10's delivery+bearing coexistence carve-out). Reproduces the exact
    evidence shape `seed_flagship_story.py` produced against a freshly migrated Postgres
    database with no prior baseline history."""
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await _active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE,
        severity=RuleFindingSeverity.HIGH,
    )
    await _active_rule_finding(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        finding_type=RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE,
        severity=RuleFindingSeverity.HIGH,
    )
    # Meaningfully elevated (well above policy's minimum_meaningful_level=0.15) but STABLE
    # — the filter has already saturated and stopped rising, exactly as observed on a
    # freshly seeded database.
    await stable_state_estimate(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        state_type=StateType.LUBRICATION_DELIVERY_STATE,
        state_value=0.54,
    )

    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)

    assert assessment.condition_type.value == "DEVELOPING_RESTRICTION_PATTERN"
    assert assessment.condition_type.value != "AMBIGUOUS_CONDITION"
    assert any("bearing" in why.lower() for why in assessment.evidence_summary["why"])


@pytest.mark.asyncio
async def test_stable_elevated_state_estimate_alone_stays_normal_operation(
    db_session: AsyncSession,
) -> None:
    """Companion regression test: without any co-active fault evidence, a lone STABLE
    state estimate that reads modestly elevated straight from a cold start (this filter's
    own `minimum_observations: 1` policy lets uncertainty read LOW after a single real
    observation, well before the level has had time to settle — exactly what
    `seed_healthy_machine.py` produces on a fresh database) must still land on
    `NORMAL_OPERATION`, not a fabricated fault — the healthy comparison machine must never
    produce an incident."""
    tenant, machine, _system, circuit, _bearing = await build_machine_with_topology(db_session)
    await make_topology_sensor(db_session, tenant, SensorType.PRESSURE, circuit_id=circuit.id)
    await stable_state_estimate(
        db_session,
        tenant_id=tenant.id,
        machine_id=machine.id,
        state_type=StateType.LUBRICATION_DELIVERY_STATE,
        state_value=0.2,
    )

    engine = ConditionEngine(db_session)
    assessment = await engine.assess(tenant.id, machine.id)

    assert assessment.condition_type.value == "NORMAL_OPERATION"

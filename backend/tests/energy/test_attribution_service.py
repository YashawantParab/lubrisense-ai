"""Integration tests for `AttributionService` against live Postgres. Mirrors
`tests/energy/test_energy_assessment_service.py`'s own convention: drive the real
service against real inserted evidence, never fake the DB layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.domain.enums import (
    AttributionLevel,
    ConditionConfidence,
    ConditionLifecycle,
    ConditionSeverity,
    ConditionType,
    Eligibility,
    EvidenceStrength,
    RuleCategory,
    RuleFindingSeverity,
    RuleFindingState,
    RuleFindingType,
    SensorType,
)
from app.domain.models import ConditionAssessment, RuleFinding
from app.energy.services.attribution_service import (
    AttributionEnergyAssessmentNotFoundError,
    AttributionMachineNotFoundError,
    AttributionService,
)
from app.energy.services.energy_assessment_service import EnergyAssessmentService
from tests.baselines.helpers import build_hierarchy, insert_rows, set_eligibility, telemetry_row
from tests.factories import make_tenant

POLICY = load_baseline_policy()


def _times(start: datetime, count: int, step_seconds: float = 5.0) -> list[datetime]:
    return [start + timedelta(seconds=step_seconds * i) for i in range(count)]


async def _seed_elevated_power(
    session: AsyncSession, tenant, machine, sensor, *, baseline_value: float, actual_value: float
) -> None:
    now = datetime.now(UTC)
    start = now - timedelta(hours=1)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=baseline_value,
            measurement_type=SensorType.MACHINE_POWER,
        )
        for t in _times(start, 40)
    ]
    await insert_rows(session, rows)
    await set_eligibility(session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    engine = BaselineEngine(session, POLICY)
    for _ in range(3):
        await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))
    await insert_rows(
        session,
        [
            telemetry_row(
                tenant_id=tenant.id,
                sensor_id=sensor.id,
                machine_id=machine.id,
                source_timestamp=now,
                value=actual_value,
                measurement_type=SensorType.MACHINE_POWER,
            )
        ],
    )
    await session.commit()


async def _add_rule_finding(
    session: AsyncSession, tenant, machine, finding_type: RuleFindingType
) -> None:
    now = datetime.now(UTC)
    finding = RuleFinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        component_id=None,
        component_type="MACHINE",
        finding_type=finding_type,
        rule_id=f"test-rule-{finding_type.value}",
        rule_version="1",
        config_version="1",
        category=RuleCategory.BEARING_CONDITION,
        severity=RuleFindingSeverity.HIGH,
        state=RuleFindingState.ACTIVE,
        evidence_strength=EvidenceStrength.STRONG,
        message="test finding",
        first_detected_at=now,
        last_detected_at=now,
        activated_at=now,
    )
    session.add(finding)
    await session.commit()


async def _add_condition(
    session: AsyncSession, tenant, machine, condition_type: ConditionType
) -> ConditionAssessment:
    condition = ConditionAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        component_id=None,
        condition_type=condition_type,
        lifecycle_state=ConditionLifecycle.DETECTED,
        severity=ConditionSeverity.HIGH,
        confidence=ConditionConfidence.MODERATE,
        as_of_timestamp=datetime.now(UTC),
        first_detected_at=datetime.now(UTC),
        evidence_summary={
            "what_is_happening": "test",
            "why": [],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "data_trustworthiness": "TRUSTED",
            "unknowns": [],
        },
        rule_finding_ids=[],
        ml_result_ids=[],
        state_estimate_ids=[],
        quality_context={},
        baseline_versions={},
        instrumentation_coverage={},
        limitations=[],
        recommended_next_evidence=None,
        policy_version="1",
        engine_version="1",
    )
    session.add(condition)
    await session.commit()
    return condition


@pytest.mark.asyncio
async def test_no_independent_evidence_is_no_evidence(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await _seed_elevated_power(
        db_session, tenant, machine, sensor, baseline_value=50.0, actual_value=90.0
    )
    await EnergyAssessmentService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    result = await AttributionService(db_session).assess_machine(tenant.id, machine.id)

    assert result.attribution_level == AttributionLevel.NO_EVIDENCE
    assert result.energy_residual_kw is not None
    assert result.energy_residual_kw > 0


@pytest.mark.asyncio
async def test_independent_bearing_condition_caps_at_possible(db_session: AsyncSession) -> None:
    """The real, end-to-end IDF-01-shaped case: elevated power, a real ACTIVE bearing
    -temperature finding, but the synthesized condition explicitly says the deterioration
    is independent of lubrication — attribution must not exceed POSSIBLE."""
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await _seed_elevated_power(
        db_session, tenant, machine, sensor, baseline_value=38.0, actual_value=43.0
    )
    await EnergyAssessmentService(db_session, POLICY).assess_machine(tenant.id, machine.id)
    await _add_rule_finding(
        db_session, tenant, machine, RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE
    )
    await _add_condition(db_session, tenant, machine, ConditionType.INDEPENDENT_BEARING_CONDITION)

    result = await AttributionService(db_session).assess_machine(tenant.id, machine.id)

    assert result.attribution_level == AttributionLevel.POSSIBLE
    assert result.contradicting_evidence
    assert result.condition_assessment_id is not None


@pytest.mark.asyncio
async def test_two_independent_families_with_supporting_condition_reaches_moderate_or_strong(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await _seed_elevated_power(
        db_session, tenant, machine, sensor, baseline_value=50.0, actual_value=90.0
    )
    await EnergyAssessmentService(db_session, POLICY).assess_machine(tenant.id, machine.id)
    await _add_rule_finding(
        db_session, tenant, machine, RuleFindingType.BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE
    )
    await _add_rule_finding(
        db_session, tenant, machine, RuleFindingType.PRESSURE_ABOVE_CONTEXTUAL_BASELINE
    )
    await _add_condition(db_session, tenant, machine, ConditionType.DEVELOPING_RESTRICTION_PATTERN)

    result = await AttributionService(db_session).assess_machine(tenant.id, machine.id)

    assert result.attribution_level in (AttributionLevel.MODERATE, AttributionLevel.STRONG)


@pytest.mark.asyncio
async def test_no_energy_assessment_raises(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await db_session.commit()

    with pytest.raises(AttributionEnergyAssessmentNotFoundError):
        await AttributionService(db_session).assess_machine(tenant.id, machine.id)


@pytest.mark.asyncio
async def test_machine_not_found_raises(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()

    with pytest.raises(AttributionMachineNotFoundError):
        await AttributionService(db_session).assess_machine(tenant.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession) -> None:
    tenant_a, machine_a, sensor_a = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await _seed_elevated_power(
        db_session, tenant_a, machine_a, sensor_a, baseline_value=50.0, actual_value=90.0
    )
    await EnergyAssessmentService(db_session, POLICY).assess_machine(tenant_a.id, machine_a.id)

    tenant_b = await make_tenant(db_session)
    await db_session.commit()

    with pytest.raises(AttributionMachineNotFoundError):
        await AttributionService(db_session).assess_machine(tenant_b.id, machine_a.id)


@pytest.mark.asyncio
async def test_attribution_does_not_alter_condition_intelligence(db_session: AsyncSession) -> None:
    """Non-circularity: running attribution must never write to `condition_assessment` —
    evidence flows condition -> attribution only, per the design doc's own boundary."""
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await _seed_elevated_power(
        db_session, tenant, machine, sensor, baseline_value=50.0, actual_value=90.0
    )
    await EnergyAssessmentService(db_session, POLICY).assess_machine(tenant.id, machine.id)
    condition = await _add_condition(db_session, tenant, machine, ConditionType.NORMAL_OPERATION)

    from sqlalchemy import select

    before = (
        (
            await db_session.execute(
                select(ConditionAssessment).where(ConditionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )

    await AttributionService(db_session).assess_machine(tenant.id, machine.id)

    after = (
        (
            await db_session.execute(
                select(ConditionAssessment).where(ConditionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(before) == len(after) == 1
    assert after[0].id == condition.id
    assert after[0].condition_type == ConditionType.NORMAL_OPERATION


def test_energy_residual_evidence_is_never_imported_by_condition_intelligence() -> None:
    """Regression test proving ENERGY_RESIDUAL evidence stays non-voting: nothing under
    `app.condition_intelligence` may import `app.energy` — a static, structural guarantee
    stronger than any single runtime assertion could be."""
    import pathlib

    condition_intelligence_dir = (
        pathlib.Path(__file__).parent.parent.parent / "app" / "condition_intelligence"
    )
    offending: list[str] = []
    for path in condition_intelligence_dir.rglob("*.py"):
        text = path.read_text()
        if "app.energy" in text or "from app import energy" in text:
            offending.append(str(path))
    assert not offending, f"app.condition_intelligence must never import app.energy: {offending}"


def test_decision_intelligence_never_imports_energy_attribution() -> None:
    import pathlib

    decision_intelligence_dir = (
        pathlib.Path(__file__).parent.parent.parent / "app" / "decision_intelligence"
    )
    offending: list[str] = []
    for path in decision_intelligence_dir.rglob("*.py"):
        text = path.read_text()
        if "app.energy" in text:
            offending.append(str(path))
    assert not offending, f"app.decision_intelligence must never import app.energy: {offending}"

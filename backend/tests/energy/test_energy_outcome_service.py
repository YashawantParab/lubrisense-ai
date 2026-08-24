"""Integration tests for `EnergyOutcomeService` against live Postgres (Lubrication
Efficiency Intelligence, Pass 3, ADR-176). Mirrors `test_attribution_service.py`'s own
convention: drive the real service against real inserted evidence, never fake the DB
layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.baselines.config.policy import load_baseline_policy
from app.baselines.services.baseline_engine import BaselineEngine
from app.domain.enums import (
    AttributionLevel,
    BaselineSourceKind,
    ConditionConfidence,
    ConditionLifecycle,
    ConditionSeverity,
    ConditionType,
    DecisionPriority,
    Eligibility,
    EnergyAssessmentStatus,
    IncidentState,
    MaintenanceActionType,
    MaintenanceState,
    QualityState,
    RecommendedAction,
    RecommendedWindow,
    SensorType,
)
from app.domain.models import (
    ConditionAssessment,
    DecisionAssessment,
    EnergyAssessment,
    Incident,
    LubricationEnergyAttribution,
    Machine,
    MaintenanceAction,
    MaintenanceCase,
)
from app.energy.services.energy_outcome_service import (
    EnergyOutcomeMachineNotFoundError,
    EnergyOutcomeNoInterventionError,
    EnergyOutcomeNoPowerSensorError,
    EnergyOutcomeService,
)
from tests.baselines.helpers import build_hierarchy, insert_rows, set_eligibility, telemetry_row
from tests.factories import make_tenant

POLICY = load_baseline_policy()


def _times(start: datetime, count: int, step_seconds: float) -> list[datetime]:
    return [start + timedelta(seconds=step_seconds * i) for i in range(count)]


async def _seed_power_window(
    session: AsyncSession,
    tenant,
    machine,
    sensor,
    *,
    values: list[float],
    start: datetime,
    step_seconds: float,
) -> None:
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=v,
            measurement_type=SensorType.MACHINE_POWER,
        )
        for t, v in zip(_times(start, len(values), step_seconds), values, strict=True)
    ]
    await insert_rows(session, rows)


async def _build_baseline(
    session: AsyncSession, tenant, machine, sensor, healthy_value: float
) -> None:
    now = datetime.now(UTC)
    start = now - timedelta(hours=3)
    rows = [
        telemetry_row(
            tenant_id=tenant.id,
            sensor_id=sensor.id,
            machine_id=machine.id,
            source_timestamp=t,
            value=healthy_value,
            measurement_type=SensorType.MACHINE_POWER,
        )
        for t in _times(start, 100, 60.0)
    ]
    await insert_rows(session, rows)
    engine = BaselineEngine(session, POLICY)
    for _ in range(3):
        await engine.refresh_sensor(tenant.id, sensor, now, window_override=(start, now))


async def _completed_case(
    session: AsyncSession,
    tenant,
    machine: Machine,
    *,
    completed_at: datetime,
    recommended_action: RecommendedAction = RecommendedAction.INSPECT_LUBRICATION_PATH,
    action_type: MaintenanceActionType = MaintenanceActionType.CLEANED,
) -> MaintenanceCase:
    now = datetime.now(UTC)
    incident = Incident(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        component_id=None,
        correlation_key=f"test-{uuid.uuid4()}",
        incident_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        title="test incident",
        summary="test",
        severity=ConditionSeverity.HIGH,
        priority=DecisionPriority.HIGH,
        state=IncidentState.RESOLVED,
        first_detected_at=now,
        last_updated_at=now,
        resolved_at=completed_at,
        condition_assessment_ids=[],
        decision_assessment_ids=[],
        prognostic_assessment_ids=[],
        rule_finding_ids=[],
        ml_result_ids=[],
        state_estimate_ids=[],
        evidence_refs={},
        policy_version="1",
        engine_version="1",
    )
    session.add(incident)
    await session.flush()

    case = MaintenanceCase(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        incident_id=incident.id,
        machine_id=machine.id,
        component_id=None,
        condition_assessment_id=uuid.uuid4(),
        decision_assessment_id=uuid.uuid4(),
        recommended_action=recommended_action,
        recommended_window=RecommendedWindow.WITHIN_HOURS,
        priority=DecisionPriority.HIGH,
        human_review_required=True,
        state=MaintenanceState.COMPLETED,
        checklist=[],
        checklist_template_id="test",
        started_at=completed_at - timedelta(minutes=30),
        completed_at=completed_at,
        policy_version="1",
    )
    session.add(case)
    await session.flush()

    action = MaintenanceAction(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        maintenance_case_id=case.id,
        action_type=action_type,
        notes="test action",
        recorded_by="tester",
        recorded_at=completed_at - timedelta(minutes=5),
    )
    session.add(action)
    await session.commit()
    return case


async def _add_attribution(
    session: AsyncSession,
    tenant,
    machine,
    sensor,
    *,
    level: AttributionLevel,
    as_of_timestamp: datetime,
) -> LubricationEnergyAttribution:
    assessment = EnergyAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        power_sensor_id=sensor.id,
        as_of_timestamp=as_of_timestamp,
        actual_power_kw=35.0,
        expected_power_kw=30.0,
        expected_lower_kw=28.0,
        expected_upper_kw=32.0,
        residual_kw=5.0,
        residual_pct=16.7,
        status=EnergyAssessmentStatus.ELEVATED_ENERGY_DEMAND,
        data_quality_state=QualityState.TRUSTED,
        baseline_source=BaselineSourceKind.EXACT_CONTEXT,
        baseline_profile_id=None,
        operating_state="RUNNING_NORMAL_LOAD",
        engine_version="1",
    )
    session.add(assessment)
    await session.flush()

    row = LubricationEnergyAttribution(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        energy_assessment_id=assessment.id,
        as_of_timestamp=as_of_timestamp,
        attribution_level=level,
        energy_residual_kw=5.0,
        energy_residual_pct=15.0,
        supporting_evidence=[],
        contradicting_evidence=[],
        limiting_factors=[],
        alternative_explanations=[],
        data_quality_state="TRUSTED",
        condition_assessment_id=None,
        policy_version="1",
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_no_completed_case_raises(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await db_session.commit()

    with pytest.raises(EnergyOutcomeNoInterventionError):
        await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)


@pytest.mark.asyncio
async def test_machine_not_found_raises(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()

    with pytest.raises(EnergyOutcomeMachineNotFoundError):
        await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_no_power_sensor_raises(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(db_session, sensor_type=SensorType.PRESSURE)
    await _completed_case(db_session, tenant, machine, completed_at=datetime.now(UTC))

    with pytest.raises(EnergyOutcomeNoPowerSensorError):
        await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)


@pytest.mark.asyncio
async def test_full_recovery_is_qualified_with_avoided_energy(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[40.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()

    case = await _completed_case(db_session, tenant, machine, completed_at=intervention)
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.POSSIBLE,
        as_of_timestamp=intervention - timedelta(minutes=20),
    )

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.maintenance_case_id == case.id
    assert result.comparability_status.value == "COMPARABLE"
    assert result.energy_outcome_status.value == "QUALIFIED_RECOVERY"
    assert result.estimated_avoided_energy_kwh is not None
    assert result.estimated_avoided_energy_kwh > 0
    assert result.pre_attribution_level == AttributionLevel.POSSIBLE
    assert result.lubrication_association_status.value == "LUBRICATION_ASSOCIATED_RECOVERY"


@pytest.mark.asyncio
async def test_irrelevant_maintenance_never_reaches_lubrication_associated(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[40.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()

    await _completed_case(
        db_session,
        tenant,
        machine,
        completed_at=intervention,
        recommended_action=RecommendedAction.VERIFY_SENSOR,
        action_type=MaintenanceActionType.INSPECTED,
    )
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.STRONG,
        as_of_timestamp=intervention - timedelta(minutes=20),
    )

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.maintenance_relevant is False
    assert result.energy_outcome_status.value == "QUALIFIED_RECOVERY"
    assert result.lubrication_association_status.value == "QUALIFIED_ENERGY_RECOVERY"


@pytest.mark.asyncio
async def test_no_evidence_pre_attribution_never_becomes_lubrication_associated(
    db_session: AsyncSession,
) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[40.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.NO_EVIDENCE,
        as_of_timestamp=intervention - timedelta(minutes=20),
    )

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.lubrication_association_status.value != "LUBRICATION_ASSOCIATED_RECOVERY"


@pytest.mark.asyncio
async def test_temporal_integrity_ignores_attribution_computed_after_intervention(
    db_session: AsyncSession,
) -> None:
    """A STRONG attribution computed AFTER the intervention must never be used as the
    `pre_attribution_level` — only the attribution at or before `intervention_timestamp`
    counts (design doc §"temporal attribution integrity")."""
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[40.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.POSSIBLE,
        as_of_timestamp=intervention - timedelta(minutes=20),
    )
    # A later, stronger attribution — must be ignored for this outcome's pre-attribution.
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.STRONG,
        as_of_timestamp=intervention + timedelta(minutes=30),
    )

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.pre_attribution_level == AttributionLevel.POSSIBLE
    assert "STRONG" not in " ".join(result.supporting_evidence + result.alternative_explanations)


@pytest.mark.asyncio
async def test_no_pre_elevation_is_no_material_change(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[30.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.energy_outcome_status.value == "NO_MATERIAL_CHANGE"
    assert result.estimated_avoided_energy_kwh is None


@pytest.mark.asyncio
async def test_deterioration_is_reported_never_hidden(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)

    intervention = datetime.now(UTC)
    pre_start = intervention - timedelta(minutes=40)
    await _seed_power_window(
        db_session, tenant, machine, sensor, values=[34.0] * 10, start=pre_start, step_seconds=120.0
    )
    post_start = intervention + timedelta(minutes=5)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[46.0] * 10,
        start=post_start,
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)

    assert result.energy_outcome_status.value == "DETERIORATED"
    assert result.estimated_avoided_energy_kwh is None
    assert result.contradicting_evidence


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession) -> None:
    tenant_a, machine_a, sensor_a = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant_a.id, sensor_a.id, machine_a.id, Eligibility.ELIGIBLE)
    await _completed_case(db_session, tenant_a, machine_a, completed_at=datetime.now(UTC))

    tenant_b = await make_tenant(db_session)
    await db_session.commit()

    with pytest.raises(EnergyOutcomeMachineNotFoundError):
        await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant_b.id, machine_a.id)


@pytest.mark.asyncio
async def test_does_not_alter_condition_or_decision_intelligence(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)
    intervention = datetime.now(UTC)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[40.0] * 10,
        start=intervention - timedelta(minutes=40),
        step_seconds=120.0,
    )
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=intervention + timedelta(minutes=5),
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)

    condition = ConditionAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        component_id=None,
        condition_type=ConditionType.NORMAL_OPERATION,
        lifecycle_state=ConditionLifecycle.RESOLVED,
        severity=ConditionSeverity.INFO,
        confidence=ConditionConfidence.HIGH,
        as_of_timestamp=datetime.now(UTC),
        first_detected_at=datetime.now(UTC),
        evidence_summary={},
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
    db_session.add(condition)
    await db_session.commit()

    before_conditions = (
        (
            await db_session.execute(
                select(ConditionAssessment).where(ConditionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )
    before_decisions = (
        (
            await db_session.execute(
                select(DecisionAssessment).where(DecisionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )

    result = await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)
    assert result.condition_outcome_status == ConditionLifecycle.RESOLVED

    after_conditions = (
        (
            await db_session.execute(
                select(ConditionAssessment).where(ConditionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )
    after_decisions = (
        (
            await db_session.execute(
                select(DecisionAssessment).where(DecisionAssessment.machine_id == machine.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(before_conditions) == len(after_conditions) == 1
    assert len(before_decisions) == len(after_decisions) == 0


@pytest.mark.asyncio
async def test_does_not_alter_lubrication_energy_attribution(db_session: AsyncSession) -> None:
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)
    intervention = datetime.now(UTC)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[40.0] * 10,
        start=intervention - timedelta(minutes=40),
        step_seconds=120.0,
    )
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=intervention + timedelta(minutes=5),
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)
    await _add_attribution(
        db_session,
        tenant,
        machine,
        sensor,
        level=AttributionLevel.POSSIBLE,
        as_of_timestamp=intervention - timedelta(minutes=20),
    )

    before = (
        (
            await db_session.execute(
                select(LubricationEnergyAttribution).where(
                    LubricationEnergyAttribution.machine_id == machine.id
                )
            )
        )
        .scalars()
        .all()
    )
    await EnergyOutcomeService(db_session, POLICY).assess_machine(tenant.id, machine.id)
    after = (
        (
            await db_session.execute(
                select(LubricationEnergyAttribution).where(
                    LubricationEnergyAttribution.machine_id == machine.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(before) == len(after) == 1


@pytest.mark.asyncio
async def test_idempotent_recompute_produces_consistent_new_row(db_session: AsyncSession) -> None:
    """Compute-and-persist, append-only (same convention as EnergyAssessment/
    LubricationEnergyAttribution) — re-running never errors and always yields the same
    classification from the same underlying evidence."""
    tenant, machine, sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    await set_eligibility(db_session, tenant.id, sensor.id, machine.id, Eligibility.ELIGIBLE)
    await _build_baseline(db_session, tenant, machine, sensor, healthy_value=30.0)
    intervention = datetime.now(UTC)
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[40.0] * 10,
        start=intervention - timedelta(minutes=40),
        step_seconds=120.0,
    )
    await _seed_power_window(
        db_session,
        tenant,
        machine,
        sensor,
        values=[30.0] * 10,
        start=intervention + timedelta(minutes=5),
        step_seconds=120.0,
    )
    await db_session.commit()
    await _completed_case(db_session, tenant, machine, completed_at=intervention)

    service = EnergyOutcomeService(db_session, POLICY)
    first = await service.assess_machine(tenant.id, machine.id)
    second = await service.assess_machine(tenant.id, machine.id)

    assert first.id != second.id
    assert first.energy_outcome_status == second.energy_outcome_status
    assert first.comparability_status == second.comparability_status

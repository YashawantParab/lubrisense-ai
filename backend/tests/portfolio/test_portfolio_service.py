"""Integration tests for `PortfolioService` against live Postgres (Portfolio
Intelligence Pass 1, ADR-177). Builds small, isolated multi-site/multi-area
organizations per test — never relies on the shared hosted-demo tenant's own debris."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_quality.repositories.sensor_quality_state_repository import (
    SensorQualityStateRepository,
)
from app.domain.enums import (
    ConditionConfidence,
    ConditionLifecycle,
    ConditionSeverity,
    ConditionType,
    Criticality,
    DecisionPriority,
    Eligibility,
    IncidentState,
    MaintenanceState,
    QualityState,
    RecommendedAction,
    RecommendedWindow,
    SensorType,
)
from app.domain.models import (
    ConditionAssessment,
    Incident,
    MaintenanceCase,
    Plant,
    Sensor,
    Site,
    Tenant,
)
from app.portfolio.services.portfolio_service import (
    PortfolioAreaNotFoundError,
    PortfolioService,
    PortfolioSiteNotFoundError,
)
from tests.factories import (
    make_customer,
    make_machine,
    make_plant,
    make_production_line,
    make_sensor,
    make_site,
    make_tenant,
)


async def _add_condition(
    session: AsyncSession,
    tenant: Tenant,
    machine_id: uuid.UUID,
    *,
    condition_type: ConditionType,
    severity: ConditionSeverity,
    confidence: ConditionConfidence = ConditionConfidence.HIGH,
    lifecycle_state: ConditionLifecycle = ConditionLifecycle.DETECTED,
) -> ConditionAssessment:
    now = datetime.now(UTC)
    condition = ConditionAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine_id,
        component_id=None,
        condition_type=condition_type,
        lifecycle_state=lifecycle_state,
        severity=severity,
        confidence=confidence,
        as_of_timestamp=now,
        first_detected_at=now,
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
    session.add(condition)
    await session.commit()
    return condition


async def _add_open_incident(
    session: AsyncSession, tenant: Tenant, machine_id: uuid.UUID, *, severity: ConditionSeverity
) -> Incident:
    now = datetime.now(UTC)
    incident = Incident(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine_id,
        component_id=None,
        correlation_key=f"test-{uuid.uuid4()}",
        incident_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        title="test incident",
        summary="test",
        severity=severity,
        priority=DecisionPriority.HIGH,
        state=IncidentState.OPEN,
        first_detected_at=now,
        last_updated_at=now,
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
    await session.commit()
    return incident


async def _add_maintenance_case(
    session: AsyncSession,
    tenant: Tenant,
    machine_id: uuid.UUID,
    incident_id: uuid.UUID,
    *,
    state: MaintenanceState,
    priority: DecisionPriority = DecisionPriority.PLANNED,
    completed_at: datetime | None = None,
) -> MaintenanceCase:
    case = MaintenanceCase(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        incident_id=incident_id,
        machine_id=machine_id,
        component_id=None,
        condition_assessment_id=uuid.uuid4(),
        decision_assessment_id=uuid.uuid4(),
        recommended_action=RecommendedAction.INSPECT_LUBRICATION_PATH,
        recommended_window=RecommendedWindow.WITHIN_HOURS,
        priority=priority,
        human_review_required=True,
        state=state,
        checklist=[],
        checklist_template_id="test",
        completed_at=completed_at,
        policy_version="1",
    )
    session.add(case)
    await session.commit()
    return case


async def _set_sensor_quality(
    session: AsyncSession,
    tenant: Tenant,
    machine_id: uuid.UUID,
    sensor: Sensor,
    *,
    quality_state: QualityState,
) -> None:
    repo = SensorQualityStateRepository(session)
    await repo.upsert(
        tenant.id,
        sensor.id,
        machine_id=machine_id,
        quality_state=quality_state,
        eligibility=Eligibility.ELIGIBLE,
        last_observed_at=datetime.now(UTC),
    )
    await session.commit()


class _Org:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.sites: dict[str, Site] = {}
        self.plants: dict[str, Plant] = {}
        self.machines: dict[str, object] = {}
        self.sensors: dict[str, Sensor] = {}


async def _build_org(session: AsyncSession) -> _Org:
    """One tenant, two sites, two areas per site, one machine per (site, area) —
    deliberately small and fully controlled."""
    tenant = await make_tenant(session)
    customer = await make_customer(session, tenant)
    org = _Org(tenant)

    for site_key, area_names in (
        ("SITE_A", ("Crushing", "Grinding")),
        ("SITE_B", ("Bulk Material Handling",)),
    ):
        site = await make_site(session, tenant, customer)
        plant = await make_plant(session, tenant, site)
        line = await make_production_line(session, tenant, plant)
        org.sites[site_key] = site
        org.plants[site_key] = plant
        for area in area_names:
            machine = await make_machine(session, tenant, line)
            machine.metadata_ = {"area": area}
            sensor = await make_sensor(
                session, tenant, sensor_type=SensorType.PRESSURE, machine_id=machine.id
            )
            await session.commit()
            key = f"{site_key}:{area}"
            org.machines[key] = machine
            org.sensors[key] = sensor
    return org


@pytest.mark.asyncio
async def test_empty_portfolio_returns_zero_everything(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()
    service = PortfolioService(db_session)

    summary = await service.organization_summary(tenant.id)

    assert summary.portfolio.sites == 0
    assert summary.portfolio.areas == 0
    assert summary.portfolio.monitored_assets == 0
    assert summary.reliability.monitored_assets == 0
    assert summary.top_attention_assets == ()
    assert summary.recent_outcomes == ()


@pytest.mark.asyncio
async def test_organization_totals_match_machine_count_no_double_counting(
    db_session: AsyncSession,
) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    # Two open incidents for the SAME machine must not double-count the asset.
    await _add_open_incident(db_session, org.tenant, machine.id, severity=ConditionSeverity.HIGH)
    await _add_open_incident(db_session, org.tenant, machine.id, severity=ConditionSeverity.WARNING)

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    assert summary.portfolio.monitored_assets == 3
    assert summary.reliability.monitored_assets == 3
    assert summary.maintenance.open_actions == 0  # incidents, not maintenance cases
    assert summary.organization_name == org.tenant.name


@pytest.mark.asyncio
async def test_organization_sites_and_areas_counted_correctly(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    service = PortfolioService(db_session)

    summary = await service.organization_summary(org.tenant.id)

    assert summary.portfolio.sites == 2
    assert summary.portfolio.areas == 3


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession) -> None:
    org_a = await _build_org(db_session)
    tenant_b = await make_tenant(db_session)
    await db_session.commit()

    service = PortfolioService(db_session)
    summary_b = await service.organization_summary(tenant_b.id)

    assert summary_b.portfolio.monitored_assets == 0
    summary_a = await service.organization_summary(org_a.tenant.id)
    assert summary_a.portfolio.monitored_assets == 3


@pytest.mark.asyncio
async def test_site_isolation_no_cross_site_leakage(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    service = PortfolioService(db_session)

    site_a = org.sites["SITE_A"]
    summary = await service.site_summary(org.tenant.id, site_a.id)

    assert summary.asset_count == 2  # Crushing + Grinding, not SITE_B's Bulk machine
    assert summary.site_id == site_a.id


@pytest.mark.asyncio
async def test_site_not_found_raises(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    service = PortfolioService(db_session)
    with pytest.raises(PortfolioSiteNotFoundError):
        await service.site_summary(org.tenant.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_area_not_found_raises(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    service = PortfolioService(db_session)
    with pytest.raises(PortfolioAreaNotFoundError):
        await service.area_summary(org.tenant.id, "Nonexistent Area")


@pytest.mark.asyncio
async def test_area_spans_sites_correctly(db_session: AsyncSession) -> None:
    """Areas are an org-wide grouping, not nested under one site — two machines in
    different sites but the same area label belong to the same AreaPerformanceSummary."""
    org = await _build_org(db_session)
    tenant = org.tenant
    customer_site = org.sites["SITE_A"]
    plant = await make_plant(db_session, tenant, customer_site)
    line = await make_production_line(db_session, tenant, plant)
    extra_machine = await make_machine(db_session, tenant, line)
    extra_machine.metadata_ = {"area": "Bulk Material Handling"}
    await db_session.commit()

    service = PortfolioService(db_session)
    summary = await service.area_summary(tenant.id, "Bulk Material Handling")

    assert summary.asset_count == 2
    assert set(summary.site_codes) == {org.sites["SITE_A"].code, org.sites["SITE_B"].code}


@pytest.mark.asyncio
async def test_condition_distribution_and_criticality_behavior(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    machine.criticality = Criticality.CRITICAL
    await db_session.commit()
    await _add_condition(
        db_session,
        org.tenant,
        machine.id,
        condition_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        severity=ConditionSeverity.HIGH,
    )

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    assert summary.reliability.condition_distribution.get("DEVELOPING_RESTRICTION_PATTERN") == 1
    # HIGH severity + CRITICAL criticality escalates to CRITICAL_ATTENTION.
    assert summary.reliability.critical_attention_assets == 1


@pytest.mark.asyncio
async def test_attention_queue_ordering(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    critical_machine = org.machines["SITE_A:Crushing"]
    warning_machine = org.machines["SITE_A:Grinding"]
    await _add_condition(
        db_session,
        org.tenant,
        critical_machine.id,
        condition_type=ConditionType.DELIVERY_BLOCKAGE_PATTERN,
        severity=ConditionSeverity.CRITICAL,
    )
    await _add_condition(
        db_session,
        org.tenant,
        warning_machine.id,
        condition_type=ConditionType.DEVELOPING_RESTRICTION_PATTERN,
        severity=ConditionSeverity.WARNING,
    )
    # A genuinely healthy, already-assessed machine — MONITOR priority, distinct from
    # an unassessed one (which correctly reads DATA_LIMITED, not MONITOR).
    healthy_machine = org.machines["SITE_B:Bulk Material Handling"]
    await _add_condition(
        db_session,
        org.tenant,
        healthy_machine.id,
        condition_type=ConditionType.NORMAL_OPERATION,
        severity=ConditionSeverity.INFO,
    )

    service = PortfolioService(db_session)
    queue = await service.attention_queue(org.tenant.id)

    assert queue[0].ref.machine_id == critical_machine.id
    assert queue[0].priority.value == "CRITICAL_ATTENTION"
    assert any(a.ref.machine_id == warning_machine.id for a in queue)
    # A healthy MONITOR-priority machine never appears in the attention queue.
    assert not any(a.ref.machine_id == healthy_machine.id for a in queue)


@pytest.mark.asyncio
async def test_maintenance_outcome_completion_is_not_automatic_success(
    db_session: AsyncSession,
) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    incident = await _add_open_incident(
        db_session, org.tenant, machine.id, severity=ConditionSeverity.HIGH
    )
    await _add_maintenance_case(
        db_session,
        org.tenant,
        machine.id,
        incident.id,
        state=MaintenanceState.COMPLETED,
        completed_at=datetime.now(UTC),
    )

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    # No EnergyOutcomeVerification exists for this machine -> outcome not yet assessed,
    # never assumed to be a qualified recovery.
    assert summary.maintenance.outcome_distribution.get("COMPLETED_OUTCOME_NOT_ASSESSED") == 1
    assert "COMPLETED_QUALIFIED_RECOVERY" not in summary.maintenance.outcome_distribution


@pytest.mark.asyncio
async def test_open_maintenance_case_is_open_action(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    incident = await _add_open_incident(
        db_session, org.tenant, machine.id, severity=ConditionSeverity.WARNING
    )
    await _add_maintenance_case(
        db_session, org.tenant, machine.id, incident.id, state=MaintenanceState.PLANNED
    )

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    assert summary.maintenance.open_actions == 1
    assert summary.maintenance.outcome_distribution.get("OPEN_ACTION") == 1


@pytest.mark.asyncio
async def test_data_trust_distribution_and_blocked_critical_asset_visibility(
    db_session: AsyncSession,
) -> None:
    org = await _build_org(db_session)
    critical_machine = org.machines["SITE_A:Crushing"]
    critical_machine.criticality = Criticality.CRITICAL
    await db_session.commit()
    sensor = org.sensors["SITE_A:Crushing"]
    await _set_sensor_quality(
        db_session, org.tenant, critical_machine.id, sensor, quality_state=QualityState.UNUSABLE
    )

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    assert summary.data_trust.distribution.get("ASSESSMENT_BLOCKED", 0) >= 1
    # A site with mostly-fine sensors must still surface the one blocked critical asset.
    assert summary.data_trust.critical_assets_limited == 1


@pytest.mark.asyncio
async def test_action_readiness_distribution(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    await _add_condition(
        db_session,
        org.tenant,
        machine.id,
        condition_type=ConditionType.NORMAL_OPERATION,
        severity=ConditionSeverity.INFO,
    )

    service = PortfolioService(db_session)
    summary = await service.organization_summary(org.tenant.id)

    assert summary.action_readiness.distribution.get("MONITORING_ONLY") == 1
    assert summary.action_readiness.distribution.get("NOT_YET_ASSESSED") == 2


@pytest.mark.asyncio
async def test_recent_outcomes_include_resolved_condition(db_session: AsyncSession) -> None:
    org = await _build_org(db_session)
    machine = org.machines["SITE_A:Crushing"]
    await _add_condition(
        db_session,
        org.tenant,
        machine.id,
        condition_type=ConditionType.NORMAL_OPERATION,
        severity=ConditionSeverity.INFO,
        lifecycle_state=ConditionLifecycle.RESOLVED,
    )

    service = PortfolioService(db_session)
    outcomes = await service.recent_outcomes(org.tenant.id)

    assert any(
        o.outcome_type == "CONDITION_RESOLVED" and o.ref.machine_id == machine.id for o in outcomes
    )


@pytest.mark.asyncio
async def test_energy_and_carbon_sections_empty_without_any_energy_data(
    db_session: AsyncSession,
) -> None:
    org = await _build_org(db_session)
    service = PortfolioService(db_session)

    summary = await service.organization_summary(org.tenant.id)

    assert summary.energy_efficiency.qualified_recovery_count == 0
    assert summary.energy_efficiency.qualified_avoided_energy_kwh_total == 0.0
    assert summary.carbon.qualified_recovery_count == 0
    assert summary.carbon.estimated_co2e_kg_total == 0.0
    assert summary.carbon.carbon_outcomes_missing_factor == 0
    # No EnergyAssessment at all -> every machine reads INSUFFICIENT_ENERGY_DATA.
    assert summary.energy_efficiency.distribution.get("INSUFFICIENT_ENERGY_DATA") == 3
    # No machine has ever had an EnergyAssessment row computed (no power sensor
    # commissioned) -> the real "assessable" denominator is 0, not 3 (Enterprise
    # Product Rebuild §6 — distinct from "assessed but insufficient data").
    assert summary.energy_efficiency.energy_assessable_assets == 0

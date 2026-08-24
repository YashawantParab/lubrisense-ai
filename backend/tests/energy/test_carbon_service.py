"""Integration tests for `CarbonService`/`EmissionFactorService` against live Postgres
(Lubrication Efficiency Intelligence, Pass 4, ADR-176). Mirrors
`test_energy_outcome_service.py`'s own convention."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    CarbonEstimateStatus,
    ComparabilityStatus,
    ComparisonConfidence,
    EmissionFactorMethod,
    EnergyEstimateStatus,
    EnergyOutcomeStatus,
    LubricationAssociationStatus,
    MetricProvenance,
    SensorType,
)
from app.domain.models import (
    ConditionAssessment,
    DecisionAssessment,
    EnergyOutcomeVerification,
    LubricationEnergyAttribution,
)
from app.energy.services.carbon_service import (
    CarbonOutcomeNotFoundError,
    CarbonService,
)
from app.energy.services.emission_factor_service import (
    EmissionFactorInvalidError,
    EmissionFactorService,
    EmissionFactorSiteNotFoundError,
)
from tests.baselines.helpers import build_hierarchy
from tests.energy.test_energy_outcome_service import _completed_case
from tests.factories import make_tenant


async def _add_outcome(
    session: AsyncSession,
    tenant,
    machine,
    *,
    energy_outcome_status: EnergyOutcomeStatus,
    estimated_avoided_energy_kwh: float | None,
    energy_estimate_status: EnergyEstimateStatus,
    comparison_confidence: ComparisonConfidence = ComparisonConfidence.HIGH,
    post_window_start: datetime | None = None,
    post_window_end: datetime | None = None,
) -> EnergyOutcomeVerification:
    now = datetime.now(UTC)
    case = await _completed_case(session, tenant, machine, completed_at=now)
    row = EnergyOutcomeVerification(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        machine_id=machine.id,
        maintenance_case_id=case.id,
        incident_id=case.incident_id,
        intervention_timestamp=now,
        pre_window_start=now - timedelta(minutes=47),
        pre_window_end=now - timedelta(minutes=2),
        post_window_start=post_window_start or (now + timedelta(minutes=2)),
        post_window_end=post_window_end or (now + timedelta(minutes=32)),
        pre_mean_actual_power_kw=40.0,
        pre_mean_expected_power_kw=30.0,
        pre_mean_residual_kw=10.0,
        pre_mean_residual_pct=33.3,
        post_mean_actual_power_kw=30.0,
        post_mean_expected_power_kw=30.0,
        post_mean_residual_kw=0.0,
        post_mean_residual_pct=0.0,
        residual_change_kw=10.0,
        residual_change_pct=33.3,
        comparability_status=ComparabilityStatus.COMPARABLE,
        comparison_confidence=comparison_confidence,
        energy_outcome_status=energy_outcome_status,
        estimated_avoided_energy_kwh=estimated_avoided_energy_kwh,
        energy_estimate_status=energy_estimate_status,
        pre_attribution_id=None,
        pre_attribution_level=None,
        condition_outcome_status=None,
        maintenance_relevant=True,
        lubrication_association_status=LubricationAssociationStatus.QUALIFIED_ENERGY_RECOVERY,
        supporting_evidence=[],
        contradicting_evidence=[],
        limiting_factors=[],
        alternative_explanations=[],
        provenance={},
        policy_version="1",
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_configure_requires_positive_factor_value(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)

    service = EmissionFactorService(db_session)
    with pytest.raises(EmissionFactorInvalidError):
        await service.configure(
            tenant.id,
            site_id,
            factor_value=-1.0,
            source_name="test",
            source_reference=None,
            jurisdiction=None,
            provenance=MetricProvenance.DEMO_ESTIMATE,
        )


@pytest.mark.asyncio
async def test_configure_unknown_site_raises(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()
    service = EmissionFactorService(db_session)
    with pytest.raises(EmissionFactorSiteNotFoundError):
        await service.configure(
            tenant.id,
            uuid.uuid4(),
            factor_value=0.4,
            source_name="test",
            source_reference=None,
            jurisdiction=None,
            provenance=MetricProvenance.DEMO_ESTIMATE,
        )


@pytest.mark.asyncio
async def test_configure_deactivates_prior_active_factor(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)
    service = EmissionFactorService(db_session)

    first = await service.configure(
        tenant.id,
        site_id,
        factor_value=0.4,
        source_name="first",
        source_reference=None,
        jurisdiction=None,
        provenance=MetricProvenance.DEMO_ESTIMATE,
    )
    second = await service.configure(
        tenant.id,
        site_id,
        factor_value=0.5,
        source_name="second",
        source_reference=None,
        jurisdiction=None,
        provenance=MetricProvenance.DEMO_ESTIMATE,
    )

    await db_session.refresh(first)
    assert first.is_active is False
    assert first.effective_to is not None
    assert second.is_active is True

    active = await service.get_active(tenant.id, site_id)
    assert active is not None
    assert active.id == second.id


@pytest.mark.asyncio
async def test_carbon_unavailable_without_configured_factor(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    outcome = await _add_outcome(
        db_session,
        tenant,
        machine,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        estimated_avoided_energy_kwh=10.0,
        energy_estimate_status=EnergyEstimateStatus.ESTIMATED,
    )

    result = await CarbonService(db_session).assess_for_outcome(tenant.id, outcome.id)

    assert result.estimate_status == CarbonEstimateStatus.FACTOR_NOT_CONFIGURED
    assert result.estimated_co2e_kg is None


@pytest.mark.asyncio
async def test_carbon_unavailable_for_unqualified_outcome_even_with_factor(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)
    await EmissionFactorService(db_session).configure(
        tenant.id,
        site_id,
        factor_value=0.4,
        source_name="test",
        source_reference=None,
        jurisdiction=None,
        provenance=MetricProvenance.DEMO_ESTIMATE,
        effective_from=datetime.now(UTC) - timedelta(days=365),
    )
    outcome = await _add_outcome(
        db_session,
        tenant,
        machine,
        energy_outcome_status=EnergyOutcomeStatus.PROBABLE_RECOVERY,
        estimated_avoided_energy_kwh=None,
        energy_estimate_status=EnergyEstimateStatus.NOT_QUALIFIED,
    )

    result = await CarbonService(db_session).assess_for_outcome(tenant.id, outcome.id)

    assert result.estimate_status == CarbonEstimateStatus.NOT_ELIGIBLE
    assert result.estimated_co2e_kg is None


@pytest.mark.asyncio
async def test_carbon_available_for_qualified_outcome_with_factor(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)
    await EmissionFactorService(db_session).configure(
        tenant.id,
        site_id,
        factor_value=0.4,
        source_name="test factor",
        source_reference="internal-test",
        jurisdiction="Demo region",
        provenance=MetricProvenance.DEMO_ESTIMATE,
        method=EmissionFactorMethod.LOCATION_BASED,
        effective_from=datetime.now(UTC) - timedelta(days=365),
    )
    outcome = await _add_outcome(
        db_session,
        tenant,
        machine,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        estimated_avoided_energy_kwh=10.0,
        energy_estimate_status=EnergyEstimateStatus.ESTIMATED,
    )

    result = await CarbonService(db_session).assess_for_outcome(tenant.id, outcome.id)

    assert result.estimate_status == CarbonEstimateStatus.ESTIMATE_AVAILABLE
    assert result.estimated_co2e_kg == pytest.approx(4.0)
    assert result.provenance["source_name"] == "test factor"
    assert result.provenance["provenance"] == "DEMO_ESTIMATE"


@pytest.mark.asyncio
async def test_low_confidence_outcome_is_limited_estimate(db_session: AsyncSession) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)
    await EmissionFactorService(db_session).configure(
        tenant.id,
        site_id,
        factor_value=0.4,
        source_name="test",
        source_reference=None,
        jurisdiction=None,
        provenance=MetricProvenance.DEMO_ESTIMATE,
        effective_from=datetime.now(UTC) - timedelta(days=365),
    )
    outcome = await _add_outcome(
        db_session,
        tenant,
        machine,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        estimated_avoided_energy_kwh=10.0,
        energy_estimate_status=EnergyEstimateStatus.ESTIMATED,
        comparison_confidence=ComparisonConfidence.MODERATE,
    )

    result = await CarbonService(db_session).assess_for_outcome(tenant.id, outcome.id)

    assert result.estimate_status == CarbonEstimateStatus.LIMITED_ESTIMATE
    assert result.estimated_co2e_kg is not None


@pytest.mark.asyncio
async def test_outcome_not_found_raises(db_session: AsyncSession) -> None:
    tenant = await make_tenant(db_session)
    await db_session.commit()
    with pytest.raises(CarbonOutcomeNotFoundError):
        await CarbonService(db_session).assess_for_outcome(tenant.id, uuid.uuid4())


@pytest.mark.asyncio
async def test_tenant_isolation_on_outcome(db_session: AsyncSession) -> None:
    tenant_a, machine_a, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    outcome = await _add_outcome(
        db_session,
        tenant_a,
        machine_a,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        estimated_avoided_energy_kwh=10.0,
        energy_estimate_status=EnergyEstimateStatus.ESTIMATED,
    )
    tenant_b = await make_tenant(db_session)
    await db_session.commit()

    with pytest.raises(CarbonOutcomeNotFoundError):
        await CarbonService(db_session).assess_for_outcome(tenant_b.id, outcome.id)


@pytest.mark.asyncio
async def test_carbon_estimation_does_not_alter_energy_outcome_or_condition_decision(
    db_session: AsyncSession,
) -> None:
    tenant, machine, _sensor = await build_hierarchy(
        db_session, sensor_type=SensorType.MACHINE_POWER
    )
    site_id = await _site_id_for_machine(db_session, tenant.id, machine.id)
    await EmissionFactorService(db_session).configure(
        tenant.id,
        site_id,
        factor_value=0.4,
        source_name="test",
        source_reference=None,
        jurisdiction=None,
        provenance=MetricProvenance.DEMO_ESTIMATE,
        effective_from=datetime.now(UTC) - timedelta(days=365),
    )
    outcome = await _add_outcome(
        db_session,
        tenant,
        machine,
        energy_outcome_status=EnergyOutcomeStatus.QUALIFIED_RECOVERY,
        estimated_avoided_energy_kwh=10.0,
        energy_estimate_status=EnergyEstimateStatus.ESTIMATED,
    )

    before_outcomes = (
        (
            await db_session.execute(
                select(EnergyOutcomeVerification).where(
                    EnergyOutcomeVerification.machine_id == machine.id
                )
            )
        )
        .scalars()
        .all()
    )
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
    before_attributions = (
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

    await CarbonService(db_session).assess_for_outcome(tenant.id, outcome.id)

    after_outcomes = (
        (
            await db_session.execute(
                select(EnergyOutcomeVerification).where(
                    EnergyOutcomeVerification.machine_id == machine.id
                )
            )
        )
        .scalars()
        .all()
    )
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
    after_attributions = (
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

    assert len(before_outcomes) == len(after_outcomes) == 1
    assert before_outcomes[0].energy_outcome_status == after_outcomes[0].energy_outcome_status
    assert len(before_conditions) == len(after_conditions) == 0
    assert len(before_decisions) == len(after_decisions) == 0
    assert len(before_attributions) == len(after_attributions) == 0


async def _site_id_for_machine(
    session: AsyncSession, tenant_id: uuid.UUID, machine_id: uuid.UUID
) -> uuid.UUID:
    from app.domain.models import Machine, Plant, ProductionLine

    stmt = (
        select(Plant.site_id)
        .join(ProductionLine, ProductionLine.plant_id == Plant.id)
        .join(Machine, Machine.production_line_id == ProductionLine.id)
        .where(Plant.tenant_id == tenant_id, Machine.id == machine_id)
    )
    site_id = await session.scalar(stmt)
    assert site_id is not None
    return site_id

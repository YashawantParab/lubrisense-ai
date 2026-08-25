"""Organization/site/area portfolio-performance orchestration (Portfolio Intelligence
Pass 1 — post-roadmap capability extension, docs/PORTFOLIO_INTELLIGENCE.md, ADR-177).

**Query-count discipline (design doc §"performance")**: `_load_data` issues a fixed,
small number of tenant-wide queries (hierarchy join, latest condition per machine, all
incidents, all maintenance cases, fleet sensor-quality records, latest energy assessment/
attribution/outcome/carbon-estimate per machine) — nine total, regardless of fleet size —
then joins everything in Python by `machine_id`. Every public method on `PortfolioService`
calls `_load_data` exactly once per request and reuses its `_PortfolioData` bundle for any
further per-section computation, instead of re-querying the same tenant-wide table. No
route in this module issues one query per machine. `organization_summary` issues one
additional fixed lookup (the tenant row itself, for `organization_name`) — still
fleet-size-independent.

**Read-only**: this service never computes/writes `EnergyAssessment`,
`LubricationEnergyAttribution`, `EnergyOutcomeVerification`, or `CarbonImpactEstimate` —
it only reads each one's already-persisted `fleet_latest`. A portfolio GET request must
never have the side effect of inserting new evidence rows.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.condition_intelligence.repositories.condition_assessment_repository import (
    ConditionAssessmentRepository,
)
from app.data_quality.services.quality_query_service import QualityQueryService
from app.domain.enums import (
    CarbonEstimateStatus,
    ConditionLifecycle,
    Criticality,
    DataTrustCategory,
    EnergyOutcomeStatus,
    EnergyPortfolioBucket,
    IncidentState,
    MaintenanceState,
    MetricProvenance,
    PortfolioPriority,
    QualityState,
    RecommendedWindow,
)
from app.domain.models import (
    CarbonImpactEstimate,
    ConditionAssessment,
    EnergyAssessment,
    EnergyOutcomeVerification,
    Incident,
    Machine,
    MaintenanceCase,
    Plant,
    ProductionLine,
    Site,
    Tenant,
)
from app.energy.services.attribution_query_service import AttributionQueryService
from app.energy.services.carbon_query_service import CarbonQueryService
from app.energy.services.energy_outcome_query_service import EnergyOutcomeQueryService
from app.energy.services.energy_query_service import EnergyQueryService
from app.incidents.repositories.incident_repository import IncidentRepository
from app.maintenance.repositories.maintenance_case_repository import MaintenanceCaseRepository
from app.portfolio.domain.action_readiness import derive_action_readiness
from app.portfolio.domain.data_trust import derive_data_trust_category, overall_quality_state
from app.portfolio.domain.energy_bucket import derive_energy_bucket
from app.portfolio.domain.maintenance_outcome import derive_maintenance_outcome_bucket
from app.portfolio.domain.priority import PriorityInput, derive_priority
from app.portfolio.models import (
    ActionReadinessSection,
    AreaPerformanceSummary,
    AssetRef,
    AttentionAsset,
    CarbonSection,
    DataTrustSection,
    EnergyAsset,
    EnergySection,
    MachineSnapshot,
    MaintenanceSection,
    OrganizationPerformanceSummary,
    PortfolioSection,
    RecentOutcome,
    ReliabilitySection,
    SitePerformanceSummary,
)

POLICY_VERSION = "1"

_OPEN_INCIDENT_STATES = frozenset(
    {
        IncidentState.OPEN,
        IncidentState.ACKNOWLEDGED,
        IncidentState.INVESTIGATING,
        IncidentState.ACTION_PLANNED,
        IncidentState.REOPENED,
    }
)
_OPEN_MAINTENANCE_STATES = frozenset(
    {
        MaintenanceState.REVIEW_REQUIRED,
        MaintenanceState.NOT_STARTED,
        MaintenanceState.PLANNED,
        MaintenanceState.IN_PROGRESS,
        MaintenanceState.AWAITING_VERIFICATION,
    }
)


class PortfolioSiteNotFoundError(LookupError):
    pass


class PortfolioAreaNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class _PortfolioData:
    """Everything one portfolio request needs, fetched exactly once — every public
    method below calls `_load_data` a single time and reuses its raw lists for any
    further per-section computation, rather than re-querying the same tenant-wide table
    (design doc §"performance")."""

    snapshots: list[MachineSnapshot]
    conditions: list[ConditionAssessment]
    all_maintenance: list[MaintenanceCase]
    outcome_by_machine: dict[uuid.UUID, EnergyOutcomeVerification]
    carbon_rows: list[CarbonImpactEstimate]
    energy_by_machine: dict[uuid.UUID, EnergyAssessment]


class PortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._conditions = ConditionAssessmentRepository(session)
        self._incidents = IncidentRepository(session)
        self._maintenance = MaintenanceCaseRepository(session)
        self._quality = QualityQueryService(session)
        self._energy = EnergyQueryService(session)
        self._attribution = AttributionQueryService(session)
        self._outcomes = EnergyOutcomeQueryService(session)
        self._carbon = CarbonQueryService(session)

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------

    async def _load_data(self, tenant_id: uuid.UUID) -> _PortfolioData:
        hierarchy_rows = (
            await self._session.execute(
                select(Machine, ProductionLine, Plant, Site)
                .join(ProductionLine, ProductionLine.id == Machine.production_line_id)
                .join(Plant, Plant.id == ProductionLine.plant_id)
                .join(Site, Site.id == Plant.site_id)
                .where(Machine.tenant_id == tenant_id)
            )
        ).all()
        if not hierarchy_rows:
            return _PortfolioData(
                snapshots=[],
                conditions=[],
                all_maintenance=[],
                outcome_by_machine={},
                carbon_rows=[],
                energy_by_machine={},
            )

        conditions = await self._conditions.list_latest_for_tenant(tenant_id)
        condition_by_machine: dict[uuid.UUID, ConditionAssessment] = {
            c.machine_id: c for c in conditions
        }

        all_incidents = await self._incidents.list_for_tenant(tenant_id, limit=1000)
        open_incidents_by_machine: dict[uuid.UUID, list[Incident]] = defaultdict(list)
        for incident in all_incidents:
            if incident.state in _OPEN_INCIDENT_STATES:
                open_incidents_by_machine[incident.machine_id].append(incident)

        all_maintenance = await self._maintenance.list_for_tenant(tenant_id, limit=1000)
        open_maintenance_by_machine: dict[uuid.UUID, list[MaintenanceCase]] = defaultdict(list)
        completed_maintenance_by_machine: dict[uuid.UUID, list[MaintenanceCase]] = defaultdict(list)
        for case in all_maintenance:
            if case.state in _OPEN_MAINTENANCE_STATES:
                open_maintenance_by_machine[case.machine_id].append(case)
            elif case.state == MaintenanceState.COMPLETED:
                completed_maintenance_by_machine[case.machine_id].append(case)

        sensor_records = await self._quality.list_fleet_sensor_records(tenant_id, limit=2000)
        quality_states_by_machine: dict[uuid.UUID, list[QualityState]] = defaultdict(list)
        for record in sensor_records:
            if record.state.machine_id is not None:
                quality_states_by_machine[record.state.machine_id].append(
                    record.state.quality_state
                )

        energy_by_machine = {a.machine_id: a for a in await self._energy.fleet_latest(tenant_id)}
        attribution_by_machine = {
            a.machine_id: a for a in await self._attribution.fleet_latest(tenant_id)
        }
        outcome_by_machine = {o.machine_id: o for o in await self._outcomes.fleet_latest(tenant_id)}
        carbon_rows = await self._carbon.fleet_latest(tenant_id)
        carbon_by_machine = {c.machine_id: c for c in carbon_rows}

        snapshots: list[MachineSnapshot] = []
        for machine, _line, plant, site in hierarchy_rows:
            area = str(machine.metadata_.get("area") or plant.plant_type or "Unspecified Area")
            ref = AssetRef(
                machine_id=machine.id,
                asset_code=machine.asset_code,
                name=machine.name,
                site_id=site.id,
                site_code=site.code,
                site_name=site.name,
                area=area,
                criticality=machine.criticality,
            )

            condition = condition_by_machine.get(machine.id)
            open_incidents = open_incidents_by_machine.get(machine.id, [])
            open_maintenance = open_maintenance_by_machine.get(machine.id, [])
            has_completed_maintenance = machine.id in completed_maintenance_by_machine

            overall_quality = overall_quality_state(
                list(quality_states_by_machine.get(machine.id, []))
            )
            has_open_workflow = bool(open_incidents) or bool(open_maintenance)
            action_readiness = derive_action_readiness(
                has_condition_assessment=condition is not None,
                condition_type=condition.condition_type if condition else None,
                condition_confidence=condition.confidence if condition else None,
                has_open_workflow=has_open_workflow,
            )
            data_trust = derive_data_trust_category(
                overall_quality=overall_quality, has_open_workflow=has_open_workflow
            )

            worst_incident = _worst_incident(open_incidents)
            worst_maintenance = _worst_maintenance(open_maintenance)
            energy = energy_by_machine.get(machine.id)
            attribution = attribution_by_machine.get(machine.id)
            priority_result = derive_priority(
                PriorityInput(
                    action_readiness=action_readiness,
                    condition_type=condition.condition_type if condition else None,
                    condition_severity=condition.severity if condition else None,
                    condition_confidence=condition.confidence if condition else None,
                    criticality=machine.criticality,
                    has_open_incident=bool(open_incidents),
                    incident_severity=worst_incident.severity if worst_incident else None,
                    has_open_maintenance=bool(open_maintenance),
                    maintenance_priority=worst_maintenance.priority if worst_maintenance else None,
                    energy_status=energy.status if energy else None,
                    attribution_level_is_supporting=bool(
                        attribution and attribution.attribution_level.value != "NO_EVIDENCE"
                    ),
                )
            )

            outcome = outcome_by_machine.get(machine.id)
            energy_bucket = derive_energy_bucket(
                energy_status=energy.status if energy else None,
                attribution_level=attribution.attribution_level if attribution else None,
                latest_outcome_status=outcome.energy_outcome_status if outcome else None,
                has_completed_maintenance=has_completed_maintenance,
            )

            carbon = carbon_by_machine.get(machine.id)
            carbon_linked = (
                carbon is not None
                and outcome is not None
                and carbon.energy_outcome_verification_id == outcome.id
            )

            snapshots.append(
                MachineSnapshot(
                    ref=ref,
                    machine_type=machine.machine_type,
                    condition_type=condition.condition_type if condition else None,
                    condition_severity=condition.severity if condition else None,
                    action_readiness=action_readiness,
                    data_trust=data_trust,
                    priority=priority_result.priority,
                    priority_reasons=priority_result.reasons,
                    has_open_incident=bool(open_incidents),
                    has_open_maintenance=bool(open_maintenance),
                    energy_status=energy.status if energy else None,
                    attribution_level=attribution.attribution_level if attribution else None,
                    energy_bucket=energy_bucket,
                    latest_outcome_status=outcome.energy_outcome_status if outcome else None,
                    latest_outcome_avoided_kwh=(
                        outcome.estimated_avoided_energy_kwh if outcome else None
                    ),
                    latest_outcome_lubrication_association=(
                        outcome.lubrication_association_status if outcome else None
                    ),
                    carbon_status=carbon.estimate_status if carbon_linked and carbon else None,
                    carbon_estimated_kg=(
                        carbon.estimated_co2e_kg if carbon_linked and carbon else None
                    ),
                )
            )
        return _PortfolioData(
            snapshots=snapshots,
            conditions=conditions,
            all_maintenance=all_maintenance,
            outcome_by_machine=outcome_by_machine,
            carbon_rows=carbon_rows,
            energy_by_machine=energy_by_machine,
        )

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    async def organization_summary(self, tenant_id: uuid.UUID) -> OrganizationPerformanceSummary:
        data = await self._load_data(tenant_id)
        snapshots = data.snapshots
        as_of = datetime.now(UTC)

        tenant = (
            await self._session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one()

        sites = {s.ref.site_id for s in snapshots}
        areas = {s.ref.area for s in snapshots}

        reliability = _reliability_section(snapshots)
        maintenance = _maintenance_section(snapshots, data.all_maintenance, data.outcome_by_machine)
        action_readiness = _action_readiness_section(snapshots)
        energy = _energy_section(snapshots)
        carbon = _carbon_section(snapshots)
        data_trust = _data_trust_section(snapshots)
        recent = _recent_outcomes(data, snapshots, limit=10)
        top_attention = _top_attention(snapshots, limit=10)

        return OrganizationPerformanceSummary(
            tenant_id=tenant_id,
            organization_name=tenant.name,
            as_of=as_of,
            portfolio=PortfolioSection(
                sites=len(sites), areas=len(areas), monitored_assets=len(snapshots)
            ),
            reliability=reliability,
            maintenance=maintenance,
            action_readiness=action_readiness,
            energy_efficiency=energy,
            carbon=carbon,
            data_trust=data_trust,
            recent_outcomes=tuple(recent),
            top_attention_assets=tuple(top_attention),
            provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
            policy_version=POLICY_VERSION,
        )

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------

    async def site_summaries(self, tenant_id: uuid.UUID) -> list[SitePerformanceSummary]:
        data = await self._load_data(tenant_id)
        by_site: dict[uuid.UUID, list[MachineSnapshot]] = defaultdict(list)
        for snap in data.snapshots:
            by_site[snap.ref.site_id].append(snap)
        results = [
            _build_site_summary(site_id, site_snapshots, data)
            for site_id, site_snapshots in by_site.items()
        ]
        return sorted(results, key=lambda s: s.site_code)

    async def site_summary(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> SitePerformanceSummary:
        data = await self._load_data(tenant_id)
        snapshots = [s for s in data.snapshots if s.ref.site_id == site_id]
        if not snapshots:
            raise PortfolioSiteNotFoundError(str(site_id))
        return _build_site_summary(site_id, snapshots, data)

    # ------------------------------------------------------------------
    # Areas
    # ------------------------------------------------------------------

    async def area_summaries(self, tenant_id: uuid.UUID) -> list[AreaPerformanceSummary]:
        data = await self._load_data(tenant_id)
        by_area: dict[str, list[MachineSnapshot]] = defaultdict(list)
        for snap in data.snapshots:
            by_area[snap.ref.area].append(snap)
        return sorted(
            (_build_area_summary(area, area_snapshots) for area, area_snapshots in by_area.items()),
            key=lambda a: a.area,
        )

    async def area_summary(self, tenant_id: uuid.UUID, area: str) -> AreaPerformanceSummary:
        data = await self._load_data(tenant_id)
        snapshots = [s for s in data.snapshots if s.ref.area == area]
        if not snapshots:
            raise PortfolioAreaNotFoundError(area)
        return _build_area_summary(area, snapshots)

    # ------------------------------------------------------------------
    # Attention queue / recent outcomes (organization-wide)
    # ------------------------------------------------------------------

    async def attention_queue(
        self, tenant_id: uuid.UUID, *, limit: int = 50
    ) -> list[AttentionAsset]:
        data = await self._load_data(tenant_id)
        return _top_attention(data.snapshots, limit=limit)

    async def recent_outcomes(
        self, tenant_id: uuid.UUID, *, limit: int = 20
    ) -> list[RecentOutcome]:
        data = await self._load_data(tenant_id)
        return _recent_outcomes(data, data.snapshots, limit=limit)

    async def energy_queue(self, tenant_id: uuid.UUID, *, limit: int = 200) -> list[EnergyAsset]:
        """Every energy-*assessable* machine (`energy_status is not None`), for the
        fleet Energy & Efficiency workspace (Enterprise Product Rebuild §7) — never a
        machine with no commissioned power sensor at all. Ordered most-actionable first
        so an opportunity/outcome-in-progress never scrolls below a normal-behavior row."""
        data = await self._load_data(tenant_id)
        return _energy_queue(data.snapshots, data.energy_by_machine, limit=limit)


# ------------------------------------------------------------------
# Pure helpers (no I/O) — kept in-module since they operate directly on
# MachineSnapshot/_PortfolioData, not on ORM rows.
# ------------------------------------------------------------------


def _maintenance_section(
    snapshots: list[MachineSnapshot],
    all_maintenance: list[MaintenanceCase],
    outcome_by_machine: dict[uuid.UUID, EnergyOutcomeVerification],
) -> MaintenanceSection:
    machine_ids = {s.ref.machine_id for s in snapshots}
    distribution = _maintenance_outcome_distribution(
        all_maintenance, outcome_by_machine, machine_ids
    )
    open_actions = sum(1 for s in snapshots if s.has_open_maintenance)
    overdue = _count_overdue(all_maintenance)
    sites_with_unresolved = len({s.ref.site_id for s in snapshots if s.has_open_incident})
    return MaintenanceSection(
        open_actions=open_actions,
        overdue_actions=overdue,
        sites_with_unresolved_incidents=sites_with_unresolved,
        outcome_distribution=distribution,
    )


def _maintenance_outcome_distribution(
    all_cases: list[MaintenanceCase],
    outcome_by_machine: dict[uuid.UUID, EnergyOutcomeVerification],
    machine_ids: set[uuid.UUID],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for case in all_cases:
        if case.machine_id not in machine_ids:
            continue
        outcome = outcome_by_machine.get(case.machine_id)
        bucket = derive_maintenance_outcome_bucket(
            maintenance_state=case.state,
            energy_outcome_status=outcome.energy_outcome_status if outcome else None,
        )
        if bucket is not None:
            counts[bucket.value] += 1
    return dict(counts)


def _count_overdue(all_cases: list[MaintenanceCase]) -> int:
    """A non-terminal case is "overdue" when it was recommended for immediate action
    (`RecommendedWindow.NOW`) but has not even started, or its own `planned_for` date
    has passed — a deliberately conservative definition given this reference
    architecture has no dedicated due-date/SLA tracking system
    (docs/PORTFOLIO_INTELLIGENCE.md §"maintenance aggregation")."""
    now = datetime.now(UTC)
    count = 0
    for case in all_cases:
        if case.state not in _OPEN_MAINTENANCE_STATES:
            continue
        if (
            case.recommended_window == RecommendedWindow.NOW
            and case.state in (MaintenanceState.REVIEW_REQUIRED, MaintenanceState.NOT_STARTED)
            or case.planned_for is not None
            and case.planned_for < now
        ):
            count += 1
    return count


def _recent_outcomes(
    data: _PortfolioData, snapshots: list[MachineSnapshot], *, limit: int
) -> list[RecentOutcome]:
    ref_by_machine = {s.ref.machine_id: s.ref for s in snapshots}
    events: list[RecentOutcome] = []

    for condition in data.conditions:
        ref = ref_by_machine.get(condition.machine_id)
        if ref is None:
            continue
        if condition.lifecycle_state == ConditionLifecycle.RESOLVED:
            events.append(
                RecentOutcome(
                    outcome_type="CONDITION_RESOLVED",
                    ref=ref,
                    occurred_at=condition.as_of_timestamp,
                    summary=f"Condition resolved: {condition.condition_type.value}",
                    provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
                )
            )
        elif condition.lifecycle_state == ConditionLifecycle.IMPROVING:
            events.append(
                RecentOutcome(
                    outcome_type="CONDITION_IMPROVING",
                    ref=ref,
                    occurred_at=condition.as_of_timestamp,
                    summary=f"Condition improving: {condition.condition_type.value}",
                    provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
                )
            )

    for case in data.all_maintenance:
        if case.state != MaintenanceState.COMPLETED:
            continue
        ref = ref_by_machine.get(case.machine_id)
        if ref is None or case.completed_at is None:
            continue
        events.append(
            RecentOutcome(
                outcome_type="MAINTENANCE_COMPLETED",
                ref=ref,
                occurred_at=case.completed_at,
                summary=f"Maintenance completed: {case.recommended_action.value}",
                provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
            )
        )

    for outcome in data.outcome_by_machine.values():
        ref = ref_by_machine.get(outcome.machine_id)
        if ref is None or outcome.energy_outcome_status != EnergyOutcomeStatus.QUALIFIED_RECOVERY:
            continue
        kwh = outcome.estimated_avoided_energy_kwh
        events.append(
            RecentOutcome(
                outcome_type="QUALIFIED_ENERGY_RECOVERY",
                ref=ref,
                occurred_at=outcome.created_at,
                summary=(
                    f"Qualified energy recovery observed (~{kwh:.1f} kWh)"
                    if kwh is not None
                    else "Qualified energy recovery observed"
                ),
                provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
            )
        )

    for estimate in data.carbon_rows:
        ref = ref_by_machine.get(estimate.machine_id)
        if ref is None or estimate.estimate_status not in (
            CarbonEstimateStatus.ESTIMATE_AVAILABLE,
            CarbonEstimateStatus.LIMITED_ESTIMATE,
        ):
            continue
        co2e = estimate.estimated_co2e_kg
        events.append(
            RecentOutcome(
                outcome_type="CARBON_ESTIMATE_PRODUCED",
                ref=ref,
                occurred_at=estimate.created_at,
                summary=(
                    f"Estimated CO2e impact computed (~{co2e:.2f} kg)"
                    if co2e is not None
                    else "Estimated CO2e impact computed"
                ),
                provenance=MetricProvenance.DEMO_ESTIMATE.value,
            )
        )

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:limit]


def _worst_incident(incidents: list[Incident]) -> Incident | None:
    if not incidents:
        return None
    order = {"CRITICAL": 3, "HIGH": 2, "WARNING": 1, "INFO": 0}
    return max(incidents, key=lambda i: order.get(i.severity.value, 0))


def _worst_maintenance(cases: list[MaintenanceCase]) -> MaintenanceCase | None:
    if not cases:
        return None
    order = {"URGENT": 3, "HIGH": 2, "PLANNED": 1, "MONITOR": 0}
    return max(cases, key=lambda c: order.get(c.priority.value, 0))


def _counter_dict(values: Iterable[str]) -> dict[str, int]:
    return dict(Counter(values))


def _condition_distribution(snapshots: list[MachineSnapshot]) -> dict[str, int]:
    return _counter_dict(
        s.condition_type.value if s.condition_type is not None else "NOT_YET_ASSESSED"
        for s in snapshots
    )


def _reliability_section(snapshots: list[MachineSnapshot]) -> ReliabilitySection:
    attention_priorities = (
        PortfolioPriority.ATTENTION,
        PortfolioPriority.HIGH_ATTENTION,
        PortfolioPriority.CRITICAL_ATTENTION,
    )
    return ReliabilitySection(
        monitored_assets=len(snapshots),
        attention_assets=sum(1 for s in snapshots if s.priority in attention_priorities),
        critical_attention_assets=sum(
            1 for s in snapshots if s.priority == PortfolioPriority.CRITICAL_ATTENTION
        ),
        healthy_assets=sum(1 for s in snapshots if s.priority == PortfolioPriority.MONITOR),
        condition_distribution=_condition_distribution(snapshots),
        priority_distribution=_counter_dict(s.priority.value for s in snapshots),
    )


def _action_readiness_section(snapshots: list[MachineSnapshot]) -> ActionReadinessSection:
    return ActionReadinessSection(
        monitored_assets=len(snapshots),
        distribution=_counter_dict(s.action_readiness.value for s in snapshots),
    )


def _energy_section(snapshots: list[MachineSnapshot]) -> EnergySection:
    qualified = [
        s
        for s in snapshots
        if s.latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY
        and s.latest_outcome_avoided_kwh is not None
    ]
    return EnergySection(
        monitored_assets=len(snapshots),
        distribution=_counter_dict(s.energy_bucket.value for s in snapshots),
        active_opportunities=sum(
            1
            for s in snapshots
            if s.energy_bucket
            in (
                EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY,
                EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY,
            )
        ),
        attribution_supported_opportunities=sum(
            1
            for s in snapshots
            if s.energy_bucket == EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY
        ),
        qualified_recovery_count=len(qualified),
        qualified_avoided_energy_kwh_total=sum(
            s.latest_outcome_avoided_kwh for s in qualified if s.latest_outcome_avoided_kwh
        ),
        energy_assessable_assets=sum(1 for s in snapshots if s.energy_status is not None),
    )


def _carbon_section(snapshots: list[MachineSnapshot]) -> CarbonSection:
    qualified = [
        s for s in snapshots if s.latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY
    ]
    available = [
        s
        for s in qualified
        if s.carbon_status
        in (CarbonEstimateStatus.ESTIMATE_AVAILABLE, CarbonEstimateStatus.LIMITED_ESTIMATE)
        and s.carbon_estimated_kg is not None
    ]
    missing_factor = sum(
        1
        for s in qualified
        if s.carbon_status
        in (CarbonEstimateStatus.FACTOR_NOT_CONFIGURED, CarbonEstimateStatus.FACTOR_NOT_APPLICABLE)
    )
    return CarbonSection(
        qualified_recovery_count=len(qualified),
        carbon_estimate_available_count=len(available),
        carbon_outcomes_missing_factor=missing_factor,
        estimated_co2e_kg_total=sum(
            s.carbon_estimated_kg for s in available if s.carbon_estimated_kg
        ),
    )


def _data_trust_section(snapshots: list[MachineSnapshot]) -> DataTrustSection:
    limited_categories = (DataTrustCategory.ASSESSMENT_BLOCKED, DataTrustCategory.ACTION_BLOCKED)
    critical_limited = sum(
        1
        for s in snapshots
        if s.ref.criticality in (Criticality.HIGH, Criticality.CRITICAL)
        and s.data_trust in limited_categories
    )
    return DataTrustSection(
        monitored_assets=len(snapshots),
        distribution=_counter_dict(s.data_trust.value for s in snapshots),
        critical_assets_limited=critical_limited,
    )


def _top_attention(snapshots: list[MachineSnapshot], *, limit: int) -> list[AttentionAsset]:
    order = {
        PortfolioPriority.CRITICAL_ATTENTION: 3,
        PortfolioPriority.HIGH_ATTENTION: 2,
        PortfolioPriority.ATTENTION: 1,
        PortfolioPriority.DATA_LIMITED: 0,
        PortfolioPriority.MONITOR: -1,
    }
    ranked = sorted(
        (s for s in snapshots if s.priority != PortfolioPriority.MONITOR),
        key=lambda s: order.get(s.priority, -1),
        reverse=True,
    )
    return [
        AttentionAsset(
            ref=s.ref,
            priority=s.priority,
            reasons=s.priority_reasons,
            condition_type=s.condition_type,
            condition_severity=s.condition_severity,
        )
        for s in ranked[:limit]
    ]


_ENERGY_QUEUE_ORDER = {
    EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY: 6,
    EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY: 5,
    EnergyPortfolioBucket.OUTCOME_AWAITING_VERIFICATION: 4,
    EnergyPortfolioBucket.OUTCOME_DETERIORATED: 3,
    EnergyPortfolioBucket.QUALIFIED_ENERGY_RECOVERY: 2,
    EnergyPortfolioBucket.INCONCLUSIVE_OUTCOME: 1,
    EnergyPortfolioBucket.NORMAL_ENERGY_BEHAVIOR: 0,
    EnergyPortfolioBucket.INSUFFICIENT_ENERGY_DATA: -1,
}


def _energy_queue(
    snapshots: list[MachineSnapshot],
    energy_by_machine: dict[uuid.UUID, EnergyAssessment],
    *,
    limit: int,
) -> list[EnergyAsset]:
    assessable = [s for s in snapshots if s.energy_status is not None]
    ranked = sorted(
        assessable, key=lambda s: _ENERGY_QUEUE_ORDER.get(s.energy_bucket, -1), reverse=True
    )
    rows: list[EnergyAsset] = []
    for s in ranked[:limit]:
        energy = energy_by_machine.get(s.ref.machine_id)
        rows.append(
            EnergyAsset(
                ref=s.ref,
                energy_bucket=s.energy_bucket,
                energy_status=s.energy_status,
                attribution_level=s.attribution_level,
                actual_power_kw=energy.actual_power_kw if energy else None,
                expected_power_kw=energy.expected_power_kw if energy else None,
                residual_pct=energy.residual_pct if energy else None,
                latest_outcome_status=s.latest_outcome_status,
                latest_outcome_avoided_kwh=s.latest_outcome_avoided_kwh,
                carbon_status=s.carbon_status,
                carbon_estimated_kg=s.carbon_estimated_kg,
            )
        )
    return rows


def _build_site_summary(
    site_id: uuid.UUID, snapshots: list[MachineSnapshot], data: _PortfolioData
) -> SitePerformanceSummary:
    ref0 = snapshots[0].ref
    machine_ids = {s.ref.machine_id for s in snapshots}
    recent = _recent_outcomes(data, snapshots, limit=5)
    return SitePerformanceSummary(
        site_id=site_id,
        site_code=ref0.site_code,
        site_name=ref0.site_name,
        as_of=datetime.now(UTC),
        asset_count=len(snapshots),
        condition_distribution=_condition_distribution(snapshots),
        attention_count=sum(
            1
            for s in snapshots
            if s.priority
            in (
                PortfolioPriority.ATTENTION,
                PortfolioPriority.HIGH_ATTENTION,
                PortfolioPriority.CRITICAL_ATTENTION,
            )
        ),
        critical_attention_count=sum(
            1 for s in snapshots if s.priority == PortfolioPriority.CRITICAL_ATTENTION
        ),
        active_incidents=sum(1 for s in snapshots if s.has_open_incident),
        open_maintenance_actions=sum(1 for s in snapshots if s.has_open_maintenance),
        action_readiness_distribution=_counter_dict(s.action_readiness.value for s in snapshots),
        data_trust_distribution=_counter_dict(s.data_trust.value for s in snapshots),
        active_energy_opportunities=sum(
            1
            for s in snapshots
            if s.energy_bucket
            in (
                EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY,
                EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY,
            )
        ),
        attribution_supported_opportunities=sum(
            1
            for s in snapshots
            if s.energy_bucket == EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY
        ),
        qualified_recovery_count=sum(
            1
            for s in snapshots
            if s.latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY
        ),
        qualified_avoided_energy_kwh_total=sum(
            s.latest_outcome_avoided_kwh
            for s in snapshots
            if s.latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY
            and s.latest_outcome_avoided_kwh is not None
        ),
        carbon_estimate_available_count=sum(
            1
            for s in snapshots
            if s.carbon_status
            in (CarbonEstimateStatus.ESTIMATE_AVAILABLE, CarbonEstimateStatus.LIMITED_ESTIMATE)
        ),
        estimated_co2e_kg_total=sum(
            s.carbon_estimated_kg
            for s in snapshots
            if s.carbon_status
            in (CarbonEstimateStatus.ESTIMATE_AVAILABLE, CarbonEstimateStatus.LIMITED_ESTIMATE)
            and s.carbon_estimated_kg is not None
        ),
        open_maintenance_outcome_distribution=_maintenance_outcome_distribution(
            data.all_maintenance, data.outcome_by_machine, machine_ids
        ),
        recent_outcomes=tuple(recent),
        top_attention_assets=tuple(_top_attention(snapshots, limit=5)),
        provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
        policy_version=POLICY_VERSION,
        energy_assessable_assets=sum(1 for s in snapshots if s.energy_status is not None),
    )


def _build_area_summary(area: str, snapshots: list[MachineSnapshot]) -> AreaPerformanceSummary:
    qualified = [
        s for s in snapshots if s.latest_outcome_status == EnergyOutcomeStatus.QUALIFIED_RECOVERY
    ]
    available = [
        s
        for s in qualified
        if s.carbon_status
        in (CarbonEstimateStatus.ESTIMATE_AVAILABLE, CarbonEstimateStatus.LIMITED_ESTIMATE)
        and s.carbon_estimated_kg is not None
    ]
    return AreaPerformanceSummary(
        area=area,
        as_of=datetime.now(UTC),
        site_codes=tuple(sorted({s.ref.site_code for s in snapshots})),
        asset_count=len(snapshots),
        condition_distribution=_condition_distribution(snapshots),
        attention_count=sum(
            1
            for s in snapshots
            if s.priority
            in (
                PortfolioPriority.ATTENTION,
                PortfolioPriority.HIGH_ATTENTION,
                PortfolioPriority.CRITICAL_ATTENTION,
            )
        ),
        critical_attention_count=sum(
            1 for s in snapshots if s.priority == PortfolioPriority.CRITICAL_ATTENTION
        ),
        action_readiness_distribution=_counter_dict(s.action_readiness.value for s in snapshots),
        data_trust_distribution=_counter_dict(s.data_trust.value for s in snapshots),
        active_energy_opportunities=sum(
            1
            for s in snapshots
            if s.energy_bucket
            in (
                EnergyPortfolioBucket.ACTIVE_ELEVATED_ENERGY,
                EnergyPortfolioBucket.ATTRIBUTION_SUPPORTED_OPPORTUNITY,
            )
        ),
        qualified_recovery_count=len(qualified),
        qualified_avoided_energy_kwh_total=sum(
            s.latest_outcome_avoided_kwh for s in qualified if s.latest_outcome_avoided_kwh
        ),
        estimated_co2e_kg_total=sum(
            s.carbon_estimated_kg for s in available if s.carbon_estimated_kg
        ),
        provenance=MetricProvenance.MEASURED_PLATFORM_METRIC.value,
        policy_version=POLICY_VERSION,
    )

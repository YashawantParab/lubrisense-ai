"""`CustomerOverviewService` — customer/site/fleet-level aggregates over persisted
platform data (Phase 21). Every number here is a real query result; nothing is
fabricated, and nothing represents commercial ROI (CLAUDE.md "Customer / Business
Thinking" — see `app.product_metrics` for the separate, explicitly-labelled DEMO/
CONFIGURED-target values that *are* allowed to be estimates).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_services.models import (
    AssetCoverageSummary,
    CustomerOverview,
    FleetOverview,
    OperationalSummary,
    ServiceBurdenSummary,
    SiteOverview,
)
from app.customer_services.policy import DEFAULT_POLICY, CustomerServicePolicy
from app.domain.enums import (
    ConditionSeverity,
    CustomerOperationalStatus,
    DecisionPriority,
    FeedbackClassification,
    IncidentState,
    IssueStatus,
    MaintenanceState,
    TechnicianFindingResult,
)
from app.domain.models import (
    Bearing,
    ConditionAssessment,
    CustomerAccount,
    FeedbackRecord,
    Incident,
    LubricationSystem,
    Machine,
    MaintenanceCase,
    MLInferenceResult,
    Plant,
    ProductionLine,
    QualityIssue,
    Sensor,
    Site,
    StateEstimate,
    TechnicianFinding,
    Telemetry,
)
from app.services.errors import NotFoundError

_OPEN_INCIDENT_STATES = (
    IncidentState.OPEN,
    IncidentState.ACKNOWLEDGED,
    IncidentState.INVESTIGATING,
    IncidentState.ACTION_PLANNED,
    IncidentState.REOPENED,
)
_ATTENTION_SEVERITIES = (ConditionSeverity.HIGH, ConditionSeverity.CRITICAL)
_ATTENTION_PRIORITIES = (DecisionPriority.HIGH, DecisionPriority.URGENT)
_OPEN_MAINTENANCE_STATES = (
    MaintenanceState.REVIEW_REQUIRED,
    MaintenanceState.NOT_STARTED,
    MaintenanceState.PLANNED,
    MaintenanceState.IN_PROGRESS,
    MaintenanceState.AWAITING_VERIFICATION,
)


def instrumented_machine_ids_subquery(machine_ids: list[uuid.UUID] | None = None):  # type: ignore[no-untyped-def]
    """Machine ids with >=1 attached `Sensor`, following every attachment path a sensor
    can take (direct machine, bearing, lubrication system, or one of its reservoir/pump/
    circuit children) — see `Sensor.attached_entity_type` and docs/ASSET_HIERARCHY.md."""
    direct = select(Sensor.machine_id.label("machine_id")).where(Sensor.machine_id.is_not(None))
    via_bearing = (
        select(Bearing.machine_id.label("machine_id"))
        .join(Sensor, Sensor.bearing_id == Bearing.id)
    )
    via_lubrication_system = (
        select(LubricationSystem.machine_id.label("machine_id"))
        .join(Sensor, Sensor.lubrication_system_id == LubricationSystem.id)
    )
    union = direct.union(via_bearing, via_lubrication_system).subquery()
    stmt = select(union.c.machine_id).distinct()
    if machine_ids is not None:
        stmt = stmt.where(union.c.machine_id.in_(machine_ids))
    return stmt


class CustomerOverviewService:
    def __init__(self, session: AsyncSession, policy: CustomerServicePolicy | None = None) -> None:
        self._session = session
        self._policy = policy or DEFAULT_POLICY

    async def _machine_ids_for_customer(
        self, tenant_id: uuid.UUID, customer_account_id: uuid.UUID
    ) -> list[uuid.UUID]:
        stmt = (
            select(Machine.id)
            .join(ProductionLine, ProductionLine.id == Machine.production_line_id)
            .join(Plant, Plant.id == ProductionLine.plant_id)
            .join(Site, Site.id == Plant.site_id)
            .where(Site.tenant_id == tenant_id, Site.customer_account_id == customer_account_id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def _machine_ids_for_site(
        self, tenant_id: uuid.UUID, site_id: uuid.UUID
    ) -> list[uuid.UUID]:
        stmt = (
            select(Machine.id)
            .join(ProductionLine, ProductionLine.id == Machine.production_line_id)
            .join(Plant, Plant.id == ProductionLine.plant_id)
            .where(Plant.tenant_id == tenant_id, Plant.site_id == site_id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def _asset_coverage(
        self, tenant_id: uuid.UUID, machine_ids: list[uuid.UUID]
    ) -> AssetCoverageSummary:
        total = len(machine_ids)
        if total == 0:
            return AssetCoverageSummary(0, 0, 0, 0, 0, 0, 0, 0, 0)

        instrumented = len(
            (
                await self._session.scalars(instrumented_machine_ids_subquery(machine_ids))
            ).all()
        )

        freshness_cutoff = datetime.now(UTC) - timedelta(
            minutes=self._policy.telemetry_freshness_window_minutes
        )
        recent_telemetry_stmt = (
            select(Telemetry.machine_id)
            .where(
                Telemetry.tenant_id == tenant_id,
                Telemetry.machine_id.in_(machine_ids),
                Telemetry.source_timestamp >= freshness_cutoff,
            )
            .distinct()
        )
        with_recent_telemetry = len((await self._session.scalars(recent_telemetry_stmt)).all())

        with_condition_stmt = (
            select(ConditionAssessment.machine_id)
            .where(
                ConditionAssessment.tenant_id == tenant_id,
                ConditionAssessment.machine_id.in_(machine_ids),
            )
            .distinct()
        )
        with_condition = len((await self._session.scalars(with_condition_stmt)).all())

        with_ml_stmt = (
            select(MLInferenceResult.machine_id)
            .where(
                MLInferenceResult.tenant_id == tenant_id,
                MLInferenceResult.machine_id.in_(machine_ids),
            )
            .distinct()
        )
        with_ml = len((await self._session.scalars(with_ml_stmt)).all())

        with_state_stmt = (
            select(StateEstimate.machine_id)
            .where(
                StateEstimate.tenant_id == tenant_id, StateEstimate.machine_id.in_(machine_ids)
            )
            .distinct()
        )
        with_state = len((await self._session.scalars(with_state_stmt)).all())

        open_quality_issue_stmt = select(func.count(func.distinct(QualityIssue.sensor_id))).where(
            QualityIssue.tenant_id == tenant_id,
            QualityIssue.status.in_((IssueStatus.ACTIVE, IssueStatus.RECOVERING)),
            QualityIssue.machine_id.in_(machine_ids),
        )
        open_quality_issues = await self._session.scalar(open_quality_issue_stmt) or 0

        return AssetCoverageSummary(
            total_machines=total,
            instrumented_machines=instrumented,
            machines_without_instrumentation=total - instrumented,
            machines_with_recent_telemetry=with_recent_telemetry,
            machines_without_recent_telemetry=total - with_recent_telemetry,
            machines_with_condition_assessment=with_condition,
            machines_with_ml_result=with_ml,
            machines_with_state_estimate=with_state,
            machines_with_open_data_quality_issues=open_quality_issues,
        )

    async def _operations(
        self, tenant_id: uuid.UUID, machine_ids: list[uuid.UUID]
    ) -> OperationalSummary:
        if not machine_ids:
            return OperationalSummary(0, 0, 0, 0, 0)

        active_incidents_stmt = select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.machine_id.in_(machine_ids),
            Incident.state.in_(_OPEN_INCIDENT_STATES),
        )
        active_incidents = await self._session.scalar(active_incidents_stmt) or 0

        attention_incidents_stmt = select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.machine_id.in_(machine_ids),
            Incident.state.in_(_OPEN_INCIDENT_STATES),
            or_(
                Incident.severity.in_(_ATTENTION_SEVERITIES),
                Incident.priority.in_(_ATTENTION_PRIORITIES),
            ),
        )
        attention_incidents = await self._session.scalar(attention_incidents_stmt) or 0

        open_cases_stmt = select(func.count()).select_from(MaintenanceCase).where(
            MaintenanceCase.tenant_id == tenant_id,
            MaintenanceCase.machine_id.in_(machine_ids),
            MaintenanceCase.state.in_(_OPEN_MAINTENANCE_STATES),
        )
        open_cases = await self._session.scalar(open_cases_stmt) or 0

        findings_cutoff = datetime.now(UTC) - timedelta(
            days=self._policy.recent_findings_window_days
        )
        recent_findings_stmt = (
            select(func.count())
            .select_from(TechnicianFinding)
            .join(MaintenanceCase, MaintenanceCase.id == TechnicianFinding.maintenance_case_id)
            .where(
                TechnicianFinding.tenant_id == tenant_id,
                MaintenanceCase.machine_id.in_(machine_ids),
                TechnicianFinding.result == TechnicianFindingResult.CONFIRMED,
                TechnicianFinding.recorded_at >= findings_cutoff,
            )
        )
        recent_findings = await self._session.scalar(recent_findings_stmt) or 0

        return OperationalSummary(
            active_incidents=active_incidents,
            attention_required_incidents=attention_incidents,
            open_high_or_urgent_decisions=attention_incidents,
            open_maintenance_cases=open_cases,
            recent_technician_confirmed_findings=recent_findings,
        )

    async def _service_burden(
        self, tenant_id: uuid.UUID, machine_ids: list[uuid.UUID]
    ) -> ServiceBurdenSummary:
        if not machine_ids:
            return ServiceBurdenSummary(0, None, 0, 0, 0, 0, None, None)

        open_incidents_stmt = select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.machine_id.in_(machine_ids),
            Incident.state.in_(_OPEN_INCIDENT_STATES),
        )
        open_incidents = await self._session.scalar(open_incidents_stmt) or 0

        monitored_machines = len(
            (await self._session.scalars(instrumented_machine_ids_subquery(machine_ids))).all()
        )
        incidents_per_machine = (
            open_incidents / monitored_machines if monitored_machines else None
        )

        open_cases_stmt = select(func.count()).select_from(MaintenanceCase).where(
            MaintenanceCase.tenant_id == tenant_id,
            MaintenanceCase.machine_id.in_(machine_ids),
            MaintenanceCase.state.in_(_OPEN_MAINTENANCE_STATES),
        )
        open_cases = await self._session.scalar(open_cases_stmt) or 0

        unresolved_cases_stmt = select(func.count()).select_from(MaintenanceCase).where(
            MaintenanceCase.tenant_id == tenant_id,
            MaintenanceCase.machine_id.in_(machine_ids),
            MaintenanceCase.state != MaintenanceState.COMPLETED,
            MaintenanceCase.state != MaintenanceState.CANCELLED,
        )
        unresolved_cases = await self._session.scalar(unresolved_cases_stmt) or 0

        fp_stmt = (
            select(func.count())
            .select_from(FeedbackRecord)
            .join(MaintenanceCase, MaintenanceCase.id == FeedbackRecord.maintenance_case_id)
            .where(
                FeedbackRecord.tenant_id == tenant_id,
                MaintenanceCase.machine_id.in_(machine_ids),
                FeedbackRecord.classification == FeedbackClassification.FALSE_POSITIVE,
            )
        )
        false_positives = await self._session.scalar(fp_stmt) or 0

        tp_stmt = (
            select(func.count())
            .select_from(FeedbackRecord)
            .join(MaintenanceCase, MaintenanceCase.id == FeedbackRecord.maintenance_case_id)
            .where(
                FeedbackRecord.tenant_id == tenant_id,
                MaintenanceCase.machine_id.in_(machine_ids),
                FeedbackRecord.classification == FeedbackClassification.TRUE_POSITIVE,
            )
        )
        true_positives = await self._session.scalar(tp_stmt) or 0

        ack_seconds_stmt = (
            select(
                func.avg(
                    func.extract("epoch", Incident.acknowledged_at)
                    - func.extract("epoch", Incident.first_detected_at)
                )
            )
            .select_from(Incident)
            .where(
                Incident.tenant_id == tenant_id,
                Incident.machine_id.in_(machine_ids),
                Incident.acknowledged_at.is_not(None),
            )
        )
        mean_ack_seconds = await self._session.scalar(ack_seconds_stmt)

        resolve_seconds_stmt = (
            select(
                func.avg(
                    func.extract("epoch", Incident.resolved_at)
                    - func.extract("epoch", Incident.first_detected_at)
                )
            )
            .select_from(Incident)
            .where(
                Incident.tenant_id == tenant_id,
                Incident.machine_id.in_(machine_ids),
                Incident.resolved_at.is_not(None),
            )
        )
        mean_resolve_seconds = await self._session.scalar(resolve_seconds_stmt)

        return ServiceBurdenSummary(
            open_incidents=open_incidents,
            incidents_per_monitored_machine=incidents_per_machine,
            open_maintenance_cases=open_cases,
            unresolved_maintenance_cases=unresolved_cases,
            false_positive_feedback_count=false_positives,
            true_positive_feedback_count=true_positives,
            mean_acknowledge_time_minutes=(
                mean_ack_seconds / 60 if mean_ack_seconds is not None else None
            ),
            mean_resolution_time_minutes=(
                mean_resolve_seconds / 60 if mean_resolve_seconds is not None else None
            ),
        )

    def _classify_status(
        self, coverage: AssetCoverageSummary, operations: OperationalSummary
    ) -> tuple[CustomerOperationalStatus, list[str]]:
        """Categorical precedence policy (Phase 21 brief §21.4) — most severe condition
        wins, evaluated top to bottom. See docs/CUSTOMER_SERVICES.md for the rationale.
        """
        if coverage.total_machines == 0:
            return CustomerOperationalStatus.UNKNOWN, ["No machines registered."]

        reasons: list[str] = []

        if operations.attention_required_incidents > 0:
            reasons.append(
                f"{operations.attention_required_incidents} open incident(s) at "
                "HIGH/CRITICAL severity or HIGH/URGENT priority."
            )
            return CustomerOperationalStatus.ATTENTION_REQUIRED, reasons

        visibility_ratio = coverage.instrumentation_coverage_ratio
        freshness_ratio = coverage.telemetry_freshness_ratio
        if (
            visibility_ratio is not None
            and visibility_ratio < self._policy.minimum_visibility_ratio
        ) or (
            freshness_ratio is not None
            and freshness_ratio < self._policy.minimum_visibility_ratio
        ):
            reasons.append(
                f"Instrumentation coverage {visibility_ratio:.0%} / telemetry freshness "
                f"{freshness_ratio:.0%} below the "
                f"{self._policy.minimum_visibility_ratio:.0%} visibility threshold."
                if visibility_ratio is not None and freshness_ratio is not None
                else "Insufficient instrumentation/telemetry visibility."
            )
            return CustomerOperationalStatus.DEGRADED_VISIBILITY, reasons

        if operations.open_maintenance_cases > 0:
            reasons.append(
                f"{operations.open_maintenance_cases} open maintenance case(s) in progress."
            )
            return CustomerOperationalStatus.MAINTENANCE_ACTIVE, reasons

        reasons.append("No attention-required incidents, adequate visibility, no open cases.")
        return CustomerOperationalStatus.HEALTHY, reasons

    async def customer_overview(
        self, tenant_id: uuid.UUID, customer_account_id: uuid.UUID
    ) -> CustomerOverview:
        customer = await self._session.get(CustomerAccount, customer_account_id)
        if customer is None or customer.tenant_id != tenant_id:
            raise NotFoundError("CUSTOMER_ACCOUNT_NOT_FOUND", "Customer account not found.")

        machine_ids = await self._machine_ids_for_customer(tenant_id, customer_account_id)
        total_sites = await self._session.scalar(
            select(func.count())
            .select_from(Site)
            .where(Site.tenant_id == tenant_id, Site.customer_account_id == customer_account_id)
        ) or 0

        coverage = await self._asset_coverage(tenant_id, machine_ids)
        operations = await self._operations(tenant_id, machine_ids)
        burden = await self._service_burden(tenant_id, machine_ids)
        status, reasons = self._classify_status(coverage, operations)

        return CustomerOverview(
            customer_account_id=customer_account_id,
            name=customer.name,
            status=status,
            status_reasons=reasons,
            total_sites=total_sites,
            total_machines=len(machine_ids),
            asset_coverage=coverage,
            operations=operations,
            service_burden=burden,
            generated_at=datetime.now(UTC),
        )

    async def site_overview(self, tenant_id: uuid.UUID, site_id: uuid.UUID) -> SiteOverview:
        site = await self._session.get(Site, site_id)
        if site is None or site.tenant_id != tenant_id:
            raise NotFoundError("SITE_NOT_FOUND", "Site not found.")

        machine_ids = await self._machine_ids_for_site(tenant_id, site_id)
        coverage = await self._asset_coverage(tenant_id, machine_ids)
        operations = await self._operations(tenant_id, machine_ids)
        status, reasons = self._classify_status(coverage, operations)

        return SiteOverview(
            site_id=site_id,
            name=site.name,
            status=status,
            status_reasons=reasons,
            total_machines=len(machine_ids),
            asset_coverage=coverage,
            operations=operations,
            generated_at=datetime.now(UTC),
        )

    async def fleet_overview(self, tenant_id: uuid.UUID) -> FleetOverview:
        machine_ids = list(
            (
                await self._session.scalars(
                    select(Machine.id).where(Machine.tenant_id == tenant_id)
                )
            ).all()
        )
        total_customers = await self._session.scalar(
            select(func.count()).select_from(CustomerAccount).where(
                CustomerAccount.tenant_id == tenant_id
            )
        ) or 0
        total_sites = await self._session.scalar(
            select(func.count()).select_from(Site).where(Site.tenant_id == tenant_id)
        ) or 0

        coverage = await self._asset_coverage(tenant_id, machine_ids)
        operations = await self._operations(tenant_id, machine_ids)
        burden = await self._service_burden(tenant_id, machine_ids)

        customer_ids = list(
            (
                await self._session.scalars(
                    select(CustomerAccount.id).where(CustomerAccount.tenant_id == tenant_id)
                )
            ).all()
        )
        status_counts: dict[str, int] = {}
        for customer_id in customer_ids:
            customer_machine_ids = await self._machine_ids_for_customer(tenant_id, customer_id)
            c_coverage = await self._asset_coverage(tenant_id, customer_machine_ids)
            c_operations = await self._operations(tenant_id, customer_machine_ids)
            status, _reasons = self._classify_status(c_coverage, c_operations)
            status_counts[status.value] = status_counts.get(status.value, 0) + 1

        return FleetOverview(
            tenant_id=tenant_id,
            total_customer_accounts=total_customers,
            total_sites=total_sites,
            total_machines=len(machine_ids),
            asset_coverage=coverage,
            operations=operations,
            service_burden=burden,
            customers_by_status=status_counts,
            generated_at=datetime.now(UTC),
        )

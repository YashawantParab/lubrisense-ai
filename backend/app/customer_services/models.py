from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import CustomerOperationalStatus


@dataclass(frozen=True)
class AssetCoverageSummary:
    total_machines: int
    instrumented_machines: int
    machines_without_instrumentation: int
    machines_with_recent_telemetry: int
    machines_without_recent_telemetry: int
    machines_with_condition_assessment: int
    machines_with_ml_result: int
    machines_with_state_estimate: int
    machines_with_open_data_quality_issues: int

    @property
    def instrumentation_coverage_ratio(self) -> float | None:
        if self.total_machines == 0:
            return None
        return self.instrumented_machines / self.total_machines

    @property
    def telemetry_freshness_ratio(self) -> float | None:
        if self.total_machines == 0:
            return None
        return self.machines_with_recent_telemetry / self.total_machines

    @property
    def condition_coverage_ratio(self) -> float | None:
        if self.total_machines == 0:
            return None
        return self.machines_with_condition_assessment / self.total_machines


@dataclass(frozen=True)
class ServiceBurdenSummary:
    open_incidents: int
    incidents_per_monitored_machine: float | None
    open_maintenance_cases: int
    unresolved_maintenance_cases: int
    false_positive_feedback_count: int
    true_positive_feedback_count: int
    mean_acknowledge_time_minutes: float | None
    mean_resolution_time_minutes: float | None


@dataclass(frozen=True)
class OperationalSummary:
    active_incidents: int
    attention_required_incidents: int
    open_high_or_urgent_decisions: int
    open_maintenance_cases: int
    recent_technician_confirmed_findings: int


@dataclass(frozen=True)
class CustomerOverview:
    customer_account_id: uuid.UUID
    name: str
    status: CustomerOperationalStatus
    status_reasons: list[str]
    total_sites: int
    total_machines: int
    asset_coverage: AssetCoverageSummary
    operations: OperationalSummary
    service_burden: ServiceBurdenSummary
    generated_at: datetime


@dataclass(frozen=True)
class SiteOverview:
    site_id: uuid.UUID
    name: str
    status: CustomerOperationalStatus
    status_reasons: list[str]
    total_machines: int
    asset_coverage: AssetCoverageSummary
    operations: OperationalSummary
    generated_at: datetime


@dataclass(frozen=True)
class FleetOverview:
    tenant_id: uuid.UUID
    total_customer_accounts: int
    total_sites: int
    total_machines: int
    asset_coverage: AssetCoverageSummary
    operations: OperationalSummary
    service_burden: ServiceBurdenSummary
    customers_by_status: dict[str, int]
    generated_at: datetime

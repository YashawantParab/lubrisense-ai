from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CustomerOperationalStatus


class AssetCoverageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_machines: int
    instrumented_machines: int
    machines_without_instrumentation: int
    machines_with_recent_telemetry: int
    machines_without_recent_telemetry: int
    machines_with_condition_assessment: int
    machines_with_ml_result: int
    machines_with_state_estimate: int
    machines_with_open_data_quality_issues: int
    instrumentation_coverage_ratio: float | None
    telemetry_freshness_ratio: float | None
    condition_coverage_ratio: float | None


class ServiceBurdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    open_incidents: int
    incidents_per_monitored_machine: float | None
    open_maintenance_cases: int
    unresolved_maintenance_cases: int
    false_positive_feedback_count: int
    true_positive_feedback_count: int
    mean_acknowledge_time_minutes: float | None
    mean_resolution_time_minutes: float | None


class OperationalSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    active_incidents: int
    attention_required_incidents: int
    open_high_or_urgent_decisions: int
    open_maintenance_cases: int
    recent_technician_confirmed_findings: int


class CustomerOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_account_id: uuid.UUID
    name: str
    status: CustomerOperationalStatus
    status_reasons: list[str]
    total_sites: int
    total_machines: int
    asset_coverage: AssetCoverageResponse
    operations: OperationalSummaryResponse
    service_burden: ServiceBurdenResponse
    generated_at: datetime


class SiteOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    name: str
    status: CustomerOperationalStatus
    status_reasons: list[str]
    total_machines: int
    asset_coverage: AssetCoverageResponse
    operations: OperationalSummaryResponse
    generated_at: datetime


class FleetOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    total_customer_accounts: int
    total_sites: int
    total_machines: int
    asset_coverage: AssetCoverageResponse
    operations: OperationalSummaryResponse
    service_burden: ServiceBurdenResponse
    customers_by_status: dict[str, int]
    generated_at: datetime

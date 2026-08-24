"""Portfolio-performance API contracts (Portfolio Intelligence Pass 1 —
docs/PORTFOLIO_INTELLIGENCE.md, ADR-177). Every count/sum here traces back to real
machine-level records — see `app.portfolio.models`'s own aggregation-discipline
docstring. Mirrors `app.api.schemas.customer_services`'s own "every nested dataclass gets
its own `from_attributes=True` schema" convention."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetRefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    machine_id: uuid.UUID
    asset_code: str
    name: str
    site_id: uuid.UUID
    site_code: str
    site_name: str
    area: str
    criticality: str


class AttentionAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ref: AssetRefResponse
    priority: str
    reasons: list[str]
    condition_type: str | None
    condition_severity: str | None


class RecentOutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome_type: str
    ref: AssetRefResponse
    occurred_at: datetime
    summary: str
    provenance: str


class ReliabilitySectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monitored_assets: int
    attention_assets: int
    critical_attention_assets: int
    healthy_assets: int
    condition_distribution: dict[str, int]
    priority_distribution: dict[str, int]


class MaintenanceSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    open_actions: int
    overdue_actions: int
    sites_with_unresolved_incidents: int
    outcome_distribution: dict[str, int]


class ActionReadinessSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monitored_assets: int
    distribution: dict[str, int]


class EnergySectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monitored_assets: int
    distribution: dict[str, int]
    active_opportunities: int
    attribution_supported_opportunities: int
    qualified_recovery_count: int
    qualified_avoided_energy_kwh_total: float


class CarbonSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    qualified_recovery_count: int
    carbon_estimate_available_count: int
    carbon_outcomes_missing_factor: int
    estimated_co2e_kg_total: float


class DataTrustSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monitored_assets: int
    distribution: dict[str, int]
    critical_assets_limited: int


class PortfolioSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sites: int
    areas: int
    monitored_assets: int


class OrganizationPerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: uuid.UUID
    as_of: datetime
    portfolio: PortfolioSectionResponse
    reliability: ReliabilitySectionResponse
    maintenance: MaintenanceSectionResponse
    action_readiness: ActionReadinessSectionResponse
    energy_efficiency: EnergySectionResponse
    carbon: CarbonSectionResponse
    data_trust: DataTrustSectionResponse
    recent_outcomes: list[RecentOutcomeResponse]
    top_attention_assets: list[AttentionAssetResponse]
    provenance: str
    policy_version: str


class SitePerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    site_code: str
    site_name: str
    as_of: datetime
    asset_count: int
    condition_distribution: dict[str, int]
    attention_count: int
    critical_attention_count: int
    active_incidents: int
    open_maintenance_actions: int
    action_readiness_distribution: dict[str, int]
    data_trust_distribution: dict[str, int]
    active_energy_opportunities: int
    attribution_supported_opportunities: int
    qualified_recovery_count: int
    qualified_avoided_energy_kwh_total: float
    carbon_estimate_available_count: int
    estimated_co2e_kg_total: float
    open_maintenance_outcome_distribution: dict[str, int]
    recent_outcomes: list[RecentOutcomeResponse]
    top_attention_assets: list[AttentionAssetResponse]
    provenance: str
    policy_version: str


class AreaPerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    area: str
    as_of: datetime
    site_codes: list[str]
    asset_count: int
    condition_distribution: dict[str, int]
    attention_count: int
    critical_attention_count: int
    action_readiness_distribution: dict[str, int]
    data_trust_distribution: dict[str, int]
    active_energy_opportunities: int
    qualified_recovery_count: int
    qualified_avoided_energy_kwh_total: float
    estimated_co2e_kg_total: float
    provenance: str
    policy_version: str

"""Portfolio read-model dataclasses (Portfolio Intelligence Pass 1 — post-roadmap
capability extension, docs/PORTFOLIO_INTELLIGENCE.md, ADR-177). Plain frozen dataclasses,
never ORM/persisted — mirrors `app.customer_services.models`'s own "computed read model,
not a table" convention. Converted to Pydantic response contracts at the API boundary
(`app.api.schemas.portfolio`), never returned directly from a route.

**Aggregation discipline (design doc §"aggregation principles"), enforced by every
section below**: every count/sum here is traceable to real machine-level records; every
total that isn't a plain count carries its own denominator alongside it (never a bare
percentage with an implicit "of what"); an opportunity is never summed as if it were an
outcome; nothing here is annualized or extrapolated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import (
    ActionReadinessState,
    AttributionLevel,
    CarbonEstimateStatus,
    ConditionSeverity,
    ConditionType,
    Criticality,
    DataTrustCategory,
    EnergyAssessmentStatus,
    EnergyOutcomeStatus,
    EnergyPortfolioBucket,
    LubricationAssociationStatus,
    MachineType,
    PortfolioPriority,
)


@dataclass(frozen=True)
class AssetRef:
    """A small, stable reference to one machine — used wherever a section needs to name
    an asset without duplicating its whole snapshot."""

    machine_id: uuid.UUID
    asset_code: str
    name: str
    site_id: uuid.UUID
    site_code: str
    site_name: str
    area: str
    criticality: Criticality


@dataclass(frozen=True)
class MachineSnapshot:
    """One row per machine — everything the aggregation layer needs, assembled from a
    fixed, small number of tenant-wide queries (never one query per machine; see
    `PortfolioService` module docstring)."""

    ref: AssetRef
    machine_type: MachineType
    condition_type: ConditionType | None
    condition_severity: ConditionSeverity | None
    action_readiness: ActionReadinessState
    data_trust: DataTrustCategory
    priority: PortfolioPriority
    priority_reasons: tuple[str, ...]
    has_open_incident: bool
    has_open_maintenance: bool
    energy_status: EnergyAssessmentStatus | None
    attribution_level: AttributionLevel | None
    energy_bucket: EnergyPortfolioBucket
    latest_outcome_status: EnergyOutcomeStatus | None
    latest_outcome_avoided_kwh: float | None
    latest_outcome_lubrication_association: LubricationAssociationStatus | None
    carbon_status: CarbonEstimateStatus | None
    carbon_estimated_kg: float | None


@dataclass(frozen=True)
class AttentionAsset:
    ref: AssetRef
    priority: PortfolioPriority
    reasons: tuple[str, ...]
    condition_type: ConditionType | None
    condition_severity: ConditionSeverity | None


@dataclass(frozen=True)
class EnergyAsset:
    """One row per energy-assessable machine (`energy_status is not None` — a
    `MACHINE_POWER` sensor is commissioned and at least one `EnergyAssessment` has been
    computed) for the fleet Energy & Efficiency workspace (Enterprise Product Rebuild
    §7). Never includes a machine with no power sensor at all — that is a coverage gap,
    not an energy row; see `EnergySection.energy_assessable_assets` for the denominator."""

    ref: AssetRef
    energy_bucket: EnergyPortfolioBucket
    energy_status: EnergyAssessmentStatus | None
    attribution_level: AttributionLevel | None
    actual_power_kw: float | None
    expected_power_kw: float | None
    residual_pct: float | None
    latest_outcome_status: EnergyOutcomeStatus | None
    latest_outcome_avoided_kwh: float | None
    carbon_status: CarbonEstimateStatus | None
    carbon_estimated_kg: float | None


@dataclass(frozen=True)
class RecentOutcome:
    """One meaningful, provenance-carrying event — never mixed with a different-meaning
    event type in the same undifferentiated feed without an explicit `outcome_type`."""

    outcome_type: str
    ref: AssetRef
    occurred_at: datetime
    summary: str
    provenance: str


@dataclass(frozen=True)
class ReliabilitySection:
    monitored_assets: int
    attention_assets: int
    critical_attention_assets: int
    healthy_assets: int
    condition_distribution: dict[str, int] = field(default_factory=dict)
    priority_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MaintenanceSection:
    open_actions: int
    overdue_actions: int
    sites_with_unresolved_incidents: int
    outcome_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionReadinessSection:
    monitored_assets: int
    distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class EnergySection:
    """`energy_assessable_assets` is the real denominator behind a sparse-looking
    `active_opportunities` count (Enterprise Product Rebuild §6) — a machine with no
    commissioned machine-power sensor never gets an `EnergyAssessment` row at all
    (distinct from one that has a row but reads `INSUFFICIENT_DATA`/
    `INSUFFICIENT_BASELINE`), so "1 opportunity" only becomes trustworthy once it's read
    as "1 opportunity from N energy-assessable assets," not "1 of 24 monitored assets."
    """

    monitored_assets: int
    distribution: dict[str, int] = field(default_factory=dict)
    active_opportunities: int = 0
    attribution_supported_opportunities: int = 0
    qualified_recovery_count: int = 0
    qualified_avoided_energy_kwh_total: float = 0.0
    energy_assessable_assets: int = 0


@dataclass(frozen=True)
class CarbonSection:
    """`qualified_recovery_count` is the denominator `carbon_estimate_available_count` is
    always evaluated against — never presented as a bare percentage of the whole fleet
    (design doc §"never mix denominators")."""

    qualified_recovery_count: int
    carbon_estimate_available_count: int
    carbon_outcomes_missing_factor: int
    estimated_co2e_kg_total: float


@dataclass(frozen=True)
class DataTrustSection:
    monitored_assets: int
    distribution: dict[str, int] = field(default_factory=dict)
    critical_assets_limited: int = 0


@dataclass(frozen=True)
class PortfolioSection:
    sites: int
    areas: int
    monitored_assets: int


@dataclass(frozen=True)
class OrganizationPerformanceSummary:
    tenant_id: uuid.UUID
    organization_name: str
    as_of: datetime
    portfolio: PortfolioSection
    reliability: ReliabilitySection
    maintenance: MaintenanceSection
    action_readiness: ActionReadinessSection
    energy_efficiency: EnergySection
    carbon: CarbonSection
    data_trust: DataTrustSection
    recent_outcomes: tuple[RecentOutcome, ...]
    top_attention_assets: tuple[AttentionAsset, ...]
    provenance: str
    policy_version: str


@dataclass(frozen=True)
class SitePerformanceSummary:
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
    recent_outcomes: tuple[RecentOutcome, ...]
    top_attention_assets: tuple[AttentionAsset, ...]
    provenance: str
    policy_version: str
    energy_assessable_assets: int = 0


@dataclass(frozen=True)
class AreaPerformanceSummary:
    area: str
    as_of: datetime
    site_codes: tuple[str, ...]
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

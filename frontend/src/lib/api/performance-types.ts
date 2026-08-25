/**
 * Types mirroring the backend's Portfolio Intelligence contracts
 * (backend/app/api/schemas/portfolio.py, docs/PORTFOLIO_INTELLIGENCE.md). Every count/sum
 * here traces back to a real machine-level record on the backend — this file only
 * declares the wire shape, never recomputes or re-aggregates any of it client-side.
 */

export interface AssetRef {
  machine_id: string;
  asset_code: string;
  name: string;
  site_id: string;
  site_code: string;
  site_name: string;
  area: string;
  criticality: string;
}

export interface AttentionAsset {
  ref: AssetRef;
  priority: string;
  reasons: string[];
  condition_type: string | null;
  condition_severity: string | null;
}

export interface RecentOutcome {
  outcome_type: string;
  ref: AssetRef;
  occurred_at: string;
  summary: string;
  provenance: string;
}

export interface ReliabilitySection {
  monitored_assets: number;
  attention_assets: number;
  critical_attention_assets: number;
  healthy_assets: number;
  condition_distribution: Record<string, number>;
  priority_distribution: Record<string, number>;
}

export interface MaintenanceSection {
  open_actions: number;
  overdue_actions: number;
  sites_with_unresolved_incidents: number;
  outcome_distribution: Record<string, number>;
}

export interface ActionReadinessSection {
  monitored_assets: number;
  distribution: Record<string, number>;
}

export interface EnergySection {
  monitored_assets: number;
  distribution: Record<string, number>;
  active_opportunities: number;
  attribution_supported_opportunities: number;
  qualified_recovery_count: number;
  qualified_avoided_energy_kwh_total: number;
}

export interface CarbonSection {
  qualified_recovery_count: number;
  carbon_estimate_available_count: number;
  carbon_outcomes_missing_factor: number;
  estimated_co2e_kg_total: number;
}

export interface DataTrustSection {
  monitored_assets: number;
  distribution: Record<string, number>;
  critical_assets_limited: number;
}

export interface PortfolioSection {
  sites: number;
  areas: number;
  monitored_assets: number;
}

export interface OrganizationPerformance {
  tenant_id: string;
  organization_name: string;
  as_of: string;
  portfolio: PortfolioSection;
  reliability: ReliabilitySection;
  maintenance: MaintenanceSection;
  action_readiness: ActionReadinessSection;
  energy_efficiency: EnergySection;
  carbon: CarbonSection;
  data_trust: DataTrustSection;
  recent_outcomes: RecentOutcome[];
  top_attention_assets: AttentionAsset[];
  provenance: string;
  policy_version: string;
}

export interface SitePerformance {
  site_id: string;
  site_code: string;
  site_name: string;
  as_of: string;
  asset_count: number;
  condition_distribution: Record<string, number>;
  attention_count: number;
  critical_attention_count: number;
  active_incidents: number;
  open_maintenance_actions: number;
  action_readiness_distribution: Record<string, number>;
  data_trust_distribution: Record<string, number>;
  active_energy_opportunities: number;
  attribution_supported_opportunities: number;
  qualified_recovery_count: number;
  qualified_avoided_energy_kwh_total: number;
  carbon_estimate_available_count: number;
  estimated_co2e_kg_total: number;
  open_maintenance_outcome_distribution: Record<string, number>;
  recent_outcomes: RecentOutcome[];
  top_attention_assets: AttentionAsset[];
  provenance: string;
  policy_version: string;
}

export interface AreaPerformance {
  area: string;
  as_of: string;
  site_codes: string[];
  asset_count: number;
  condition_distribution: Record<string, number>;
  attention_count: number;
  critical_attention_count: number;
  action_readiness_distribution: Record<string, number>;
  data_trust_distribution: Record<string, number>;
  active_energy_opportunities: number;
  qualified_recovery_count: number;
  qualified_avoided_energy_kwh_total: number;
  estimated_co2e_kg_total: number;
  provenance: string;
  policy_version: string;
}

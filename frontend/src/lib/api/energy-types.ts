/**
 * Types mirroring the backend's Lubrication Efficiency Intelligence contracts
 * (backend/app/api/schemas/{energy,attribution,energy_outcome,carbon}.py, ADR-176).
 * Energy-assessment/attribution/outcome/carbon output is evidence and operational
 * estimate language — never a lubrication diagnosis or a "savings"/"verified" claim; see
 * each backend schema's own module docstring for the claim-terminology rules this
 * frontend layer must preserve when rendering these fields.
 */

export interface EnergyAssessment {
  id: string;
  tenant_id: string;
  machine_id: string;
  power_sensor_id: string;
  as_of_timestamp: string;

  actual_power_kw: number | null;
  expected_power_kw: number | null;
  expected_lower_kw: number | null;
  expected_upper_kw: number | null;
  residual_kw: number | null;
  residual_pct: number | null;

  status: string;
  data_quality_state: string;
  baseline_source: string;
  baseline_profile_id: string | null;
  operating_state: string | null;

  engine_version: string;
  created_at: string;
}

export interface Attribution {
  id: string;
  tenant_id: string;
  machine_id: string;
  energy_assessment_id: string;
  as_of_timestamp: string;

  attribution_level: string;

  energy_residual_kw: number | null;
  energy_residual_pct: number | null;

  supporting_evidence: string[];
  contradicting_evidence: string[];
  limiting_factors: string[];
  alternative_explanations: string[];

  data_quality_state: string;
  condition_assessment_id: string | null;

  policy_version: string;
  created_at: string;
}

export interface EnergyOutcomeVerification {
  id: string;
  tenant_id: string;
  machine_id: string;
  maintenance_case_id: string;
  incident_id: string | null;

  intervention_timestamp: string;
  pre_window_start: string | null;
  pre_window_end: string | null;
  post_window_start: string | null;
  post_window_end: string | null;

  pre_mean_actual_power_kw: number | null;
  pre_mean_expected_power_kw: number | null;
  pre_mean_residual_kw: number | null;
  pre_mean_residual_pct: number | null;

  post_mean_actual_power_kw: number | null;
  post_mean_expected_power_kw: number | null;
  post_mean_residual_kw: number | null;
  post_mean_residual_pct: number | null;

  residual_change_kw: number | null;
  residual_change_pct: number | null;

  comparability_status: string;
  comparison_confidence: string;

  energy_outcome_status: string;
  estimated_avoided_energy_kwh: number | null;
  energy_estimate_status: string;

  pre_attribution_id: string | null;
  pre_attribution_level: string | null;

  condition_outcome_status: string | null;

  maintenance_relevant: boolean;
  lubrication_association_status: string;

  supporting_evidence: string[];
  contradicting_evidence: string[];
  limiting_factors: string[];
  alternative_explanations: string[];

  provenance: Record<string, unknown>;

  policy_version: string;
  created_at: string;
}

export interface CarbonImpactEstimate {
  id: string;
  tenant_id: string;
  site_id: string;
  machine_id: string;
  energy_outcome_verification_id: string;
  emission_factor_id: string | null;

  observed_period_start: string | null;
  observed_period_end: string | null;

  qualified_avoided_energy_kwh: number | null;

  emission_factor_value: number | null;
  emission_factor_unit: string | null;
  method: string | null;

  estimated_co2e_kg: number | null;
  estimate_status: string;

  limitations: string[];
  provenance: Record<string, unknown>;

  policy_version: string;
  created_at: string;
}

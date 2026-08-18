/**
 * Types mirroring the backend's Phase 9 rules-engine API contract
 * (backend/app/api/schemas/rules.py). Every finding is evidence language ("consistent
 * with..."), never a confirmed diagnosis — see docs/RULES_ENGINE.md "Causal language".
 */

export type RuleCategory =
  | "HYDRAULIC"
  | "PUMP"
  | "RESERVOIR"
  | "LUBRICATION_CYCLE"
  | "BEARING_CONDITION"
  | "SENSOR_QUALITY_DEPENDENT"
  | "CROSS_SIGNAL"
  | "CONFIGURATION";

export type RuleFindingType =
  | "FLOW_BELOW_CONTEXTUAL_BASELINE"
  | "PRESSURE_ABOVE_CONTEXTUAL_BASELINE"
  | "PRESSURE_BUILD_SLOW"
  | "PUMP_CURRENT_ABOVE_BASELINE"
  | "PUMP_RUNTIME_ABOVE_BASELINE"
  | "CYCLE_DURATION_ABOVE_BASELINE"
  | "CYCLE_COMPLETION_FAILURE"
  | "RESERVOIR_LEVEL_LOW"
  | "RESERVOIR_DEPLETION_ABNORMAL"
  | "BEARING_TEMPERATURE_ABOVE_CONTEXTUAL_BASELINE"
  | "VIBRATION_ABOVE_CONTEXTUAL_BASELINE"
  | "FLOW_PRESSURE_RESTRICTION_PATTERN"
  | "FLOW_PRESSURE_LEAKAGE_PATTERN"
  | "PUMP_DEGRADATION_PATTERN"
  | "LUBRICATION_PATH_DEGRADATION_PATTERN"
  | "INDEPENDENT_BEARING_CONDITION_PATTERN"
  | "INSUFFICIENT_TRUSTED_DATA";

export type RuleFindingSeverity = "INFO" | "WARNING" | "HIGH" | "CRITICAL";
export type RuleFindingState = "CANDIDATE" | "ACTIVE" | "RECOVERING" | "RESOLVED";
export type EvidenceStrength = "LOW" | "MODERATE" | "STRONG";

export interface RuleFindingResponse {
  id: string;
  machine_id: string;
  component_id: string | null;
  component_type: string;
  finding_type: RuleFindingType;
  rule_id: string;
  rule_version: string;
  config_version: string;
  category: RuleCategory;
  severity: RuleFindingSeverity;
  state: RuleFindingState;
  evidence_strength: EvidenceStrength;
  criticality_at_detection: string | null;
  message: string;
  evidence: Record<string, unknown>;
  limitations: string[];
  quality_context: Record<string, unknown>;
  baseline_version_ids: string[];
  source_event_ids: string[];
  window_start: string | null;
  window_end: string | null;
  candidate_stable_cycles: number;
  first_detected_at: string;
  last_detected_at: string;
  activated_at: string | null;
  resolved_at: string | null;
}

export interface MachineFindingsResponse {
  machine_id: string;
  findings: RuleFindingResponse[];
}

export interface TenantFindingSummaryResponse {
  findings_by_state: Record<string, number>;
  findings_by_severity: Record<string, number>;
  total_active_findings: number;
}

export interface ConditionEvidenceSummary {
  what_is_happening: string;
  why: string[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  data_trustworthiness: string;
  unknowns: string[];
}

export interface ConditionAssessmentResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  condition_type: string;
  lifecycle_state: string;
  severity: string;
  confidence: string;
  as_of_timestamp: string;
  first_detected_at: string;
  evidence_summary: ConditionEvidenceSummary;
  rule_finding_ids: string[];
  ml_result_ids: string[];
  state_estimate_ids: string[];
  quality_context: Record<string, unknown>;
  instrumentation_coverage: Record<string, unknown>;
  limitations: string[];
  recommended_next_evidence: string | null;
  policy_version: string;
  engine_version: string;
  created_at: string;
}

export interface PrognosticAssessmentResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  state_estimate_id: string;
  state_type: "LUBRICATION_DELIVERY_STATE" | "BEARING_CONDITION_STATE";
  horizon: "ONE_HOUR" | "SIX_HOURS" | "TWENTY_FOUR_HOURS";
  status: "OK" | "NO_RELIABLE_FORECAST";
  as_of_timestamp: string;
  current_state: number;
  trend: string;
  predicted_state_at_horizon: number;
  estimated_threshold_crossing_time: string | null;
  uncertainty: string;
  data_sufficient: boolean;
  limitations: string[];
  engine_version: string;
  config_version: string;
  created_at: string;
}

export interface DecisionEvidence {
  what_should_i_do: string;
  why: string;
  when: string;
  risk_if_deferred: string;
  confidence: string;
  based_on_condition_id: string;
  missing_data: string[];
}

export interface DecisionAssessmentResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  condition_assessment_id: string;
  prognostic_assessment_id: string | null;
  priority: "MONITOR" | "PLANNED" | "HIGH" | "URGENT";
  recommended_action: string;
  recommended_window: string;
  risk_if_deferred: string;
  human_review_required: boolean;
  evidence: DecisionEvidence;
  confidence: string;
  limitations: string[];
  lifecycle_state: "ACTIVE" | "SUPERSEDED" | "EXPIRED" | "RESOLVED";
  as_of_timestamp: string;
  expires_at: string;
  policy_version: string;
  created_at: string;
}

export interface IntelligenceViewResponse {
  condition: ConditionAssessmentResponse;
  prognostics: PrognosticAssessmentResponse[];
  decision: DecisionAssessmentResponse;
}

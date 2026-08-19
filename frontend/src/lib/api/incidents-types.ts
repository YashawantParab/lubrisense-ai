export interface IncidentResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  correlation_key: string;
  incident_type: string;
  title: string;
  summary: string;
  severity: string;
  priority: string;
  state: string;
  first_detected_at: string;
  last_updated_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  condition_assessment_ids: string[];
  decision_assessment_ids: string[];
  prognostic_assessment_ids: string[];
  rule_finding_ids: string[];
  ml_result_ids: string[];
  state_estimate_ids: string[];
  evidence_refs: { why?: string[] };
  assigned_to: string | null;
  policy_version: string;
  engine_version: string;
  created_at: string;
}

export interface IncidentEventResponse {
  id: string;
  incident_id: string;
  event_type: string;
  summary: string;
  details: Record<string, unknown>;
  recorded_at: string;
}

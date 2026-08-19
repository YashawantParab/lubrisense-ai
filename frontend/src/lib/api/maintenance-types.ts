export interface ChecklistItem {
  text: string;
  completed: boolean;
}

export interface MaintenanceCaseResponse {
  id: string;
  tenant_id: string;
  incident_id: string;
  machine_id: string;
  component_id: string | null;
  condition_assessment_id: string;
  decision_assessment_id: string;
  recommended_action: string;
  recommended_window: string;
  priority: string;
  human_review_required: boolean;
  state: string;
  checklist: ChecklistItem[];
  checklist_template_id: string;
  feedback_classification: string | null;
  planned_for: string | null;
  started_at: string | null;
  completed_at: string | null;
  policy_version: string;
  created_at: string;
}

export interface TechnicianFindingResponse {
  id: string;
  maintenance_case_id: string;
  result: string;
  component: string | null;
  observed_issue: string | null;
  notes: string;
  technician_identifier: string;
  recorded_at: string;
}

export interface MaintenanceActionResponse {
  id: string;
  maintenance_case_id: string;
  action_type: string;
  notes: string;
  recorded_by: string;
  recorded_at: string;
}

export interface FeedbackRecordResponse {
  id: string;
  maintenance_case_id: string;
  incident_id: string;
  classification: string;
  confirmed_component: string | null;
  confirmed_finding: string | null;
  post_action_condition_type: string | null;
  notes: string;
  recorded_by: string;
  recorded_at: string;
}

export interface WorkOrderResponse {
  external_reference: string;
  title: string;
  description: string;
  asset_reference: string;
  priority: string;
  status: string;
  recommended_window: string;
  checklist: string[];
}

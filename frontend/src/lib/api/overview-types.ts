export interface AssetCoverageResponse {
  total_machines: number;
  instrumented_machines: number;
  machines_without_instrumentation: number;
  machines_with_recent_telemetry: number;
  machines_without_recent_telemetry: number;
  machines_with_condition_assessment: number;
  machines_with_ml_result: number;
  machines_with_state_estimate: number;
  machines_with_open_data_quality_issues: number;
  instrumentation_coverage_ratio: number | null;
  telemetry_freshness_ratio: number | null;
  condition_coverage_ratio: number | null;
}

export interface ServiceBurdenResponse {
  open_incidents: number;
  incidents_per_monitored_machine: number | null;
  open_maintenance_cases: number;
  unresolved_maintenance_cases: number;
  false_positive_feedback_count: number;
  true_positive_feedback_count: number;
  mean_acknowledge_time_minutes: number | null;
  mean_resolution_time_minutes: number | null;
}

export interface OperationalSummaryResponse {
  active_incidents: number;
  attention_required_incidents: number;
  open_high_or_urgent_decisions: number;
  open_maintenance_cases: number;
  recent_technician_confirmed_findings: number;
}

export interface FleetOverviewResponse {
  tenant_id: string;
  total_customer_accounts: number;
  total_sites: number;
  total_machines: number;
  asset_coverage: AssetCoverageResponse;
  operations: OperationalSummaryResponse;
  service_burden: ServiceBurdenResponse;
  customers_by_status: Record<string, number>;
  generated_at: string;
}

/**
 * Types mirroring the backend's Phase 7 data-quality API contract
 * (backend/app/api/schemas/data_quality.py). Deliberately only ever shows
 * TRUSTED/USABLE_WITH_CAUTION/UNUSABLE — never HEALTHY/FAILED (CLAUDE.md: this is a data
 * quality signal, not a condition/health diagnosis).
 */

export type QualityState = "TRUSTED" | "USABLE_WITH_CAUTION" | "UNUSABLE";
export type Eligibility = "ELIGIBLE" | "ELIGIBLE_WITH_CAUTION" | "INELIGIBLE";
export type IssueSeverity = "INFO" | "WARNING" | "ERROR" | "CRITICAL";
export type IssueStatus = "ACTIVE" | "RECOVERING" | "RESOLVED";
export type StalenessStatus = "FRESH" | "STALE" | "UNKNOWN";
export type ClockStatus = "NORMAL" | "OFFSET_SUSPECTED" | "DRIFT_SUSPECTED" | "UNKNOWN";

export interface SensorQualityStateResponse {
  sensor_id: string;
  machine_id: string | null;
  quality_state: QualityState;
  eligibility: Eligibility;
  last_good_reading_at: string | null;
  last_good_reading_value: number | null;
  last_observed_at: string | null;
  last_observed_value: number | null;
  last_observed_quality: string | null;
  staleness_status: StalenessStatus;
  clock_status: ClockStatus;
  active_issue_count: number;
  firmware_version: string | null;
  controller_version: string | null;
  policy_version: string | null;
  updated_at: string;
}

export interface QualityIssueResponse {
  id: string;
  sensor_id: string;
  machine_id: string | null;
  dimension: string;
  issue_type: string;
  severity: IssueSeverity;
  status: IssueStatus;
  message: string;
  evidence: Record<string, unknown>;
  first_seen: string;
  last_seen: string;
  resolved_at: string | null;
  rule_id: string;
  rule_version: string;
  policy_version: string;
}

export interface SensorQualityDetailResponse {
  sensor_id: string;
  state: SensorQualityStateResponse | null;
  active_issues: QualityIssueResponse[];
}

/** One sensor's current trust state plus its own identifying metadata and active
 * issue(s) — `GET /api/v1/data-quality/sensors`. Exists for every evaluated sensor,
 * including a fully trusted one with no active issue, which `QualityIssueResponse` alone
 * cannot represent. */
export interface SensorQualityRecordResponse {
  sensor_id: string;
  sensor_code: string;
  sensor_name: string;
  sensor_type: string;
  machine_id: string | null;
  state: SensorQualityStateResponse;
  active_issues: QualityIssueResponse[];
  expected_reporting_interval_seconds: number | null;
}

export interface MachineQualitySummaryResponse {
  machine_id: string;
  sensors: SensorQualityStateResponse[];
  active_issues: QualityIssueResponse[];
}

export interface TenantQualitySummaryResponse {
  sensors_by_quality_state: Record<string, number>;
  active_issues_by_severity: Record<string, number>;
  total_sensors_tracked: number;
  total_active_issues: number;
}

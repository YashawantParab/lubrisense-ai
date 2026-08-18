/**
 * Types mirroring the backend's Phase 8 baseline API contract
 * (backend/app/api/schemas/baselines.py). Baseline readiness is explicitly not
 * machine/asset health (docs/BASELINES.md §13/§19) — no health score is ever surfaced here.
 */

export type BaselineStrategyType =
  | "STATIC_ENGINEERING_REFERENCE"
  | "ROLLING_ASSET_BASELINE"
  | "CONTEXTUAL_ASSET_BASELINE";

export type BaselineMetricKind = "STANDARD" | "RESERVOIR_TREND" | "CYCLE_METRIC";

export type BaselineState =
  | "INSUFFICIENT_DATA"
  | "BUILDING"
  | "ACTIVE"
  | "STALE"
  | "INVALIDATED"
  | "SUPERSEDED";

export type BaselineSourceKind =
  | "EXACT_CONTEXT"
  | "OPERATING_STATE"
  | "SENSOR_LEVEL"
  | "ENGINEERING_REFERENCE"
  | "NONE";

export type DeviationClassification =
  | "WITHIN_EXPECTED_RANGE"
  | "MILD_DEVIATION"
  | "STRONG_DEVIATION"
  | "NOT_ENOUGH_DATA";

export interface BaselineProfileResponse {
  id: string;
  sensor_id: string;
  machine_id: string | null;
  measurement_type: string;
  strategy: BaselineStrategyType;
  metric_kind: BaselineMetricKind;
  context_key: string;
  context: Record<string, unknown>;
  version: number;
  state: BaselineState;
  statistics: Record<string, number> | null;
  sample_count: number;
  min_sample_required: number;
  window_start: string | null;
  window_end: string | null;
  config_version: string;
  quality_policy_version: string | null;
  activated_at: string | null;
  superseded_at: string | null;
  invalidated_at: string | null;
  invalidation_reason: string | null;
  last_evaluated_at: string | null;
  refresh_interval_seconds: number;
  stale_after_seconds: number;
}

export interface ReadinessResponse {
  label: string;
  active_count: number;
  building_count: number;
  insufficient_data_count: number;
  stale_count: number;
  invalidated_count: number;
}

export interface SensorBaselinesResponse {
  sensor_id: string;
  readiness: ReadinessResponse;
  profiles: BaselineProfileResponse[];
}

export interface MachineBaselinesResponse {
  machine_id: string;
  readiness: ReadinessResponse;
  profiles: BaselineProfileResponse[];
}

export interface DeviationResponse {
  classification: DeviationClassification;
  standardized_distance: number | null;
  quantile_position: number | null;
  method: string;
}

export interface CurrentBaselineResponse {
  sensor_id: string;
  source: BaselineSourceKind;
  profile: BaselineProfileResponse | null;
  deviation: DeviationResponse | null;
}

export interface TenantBaselineSummaryResponse {
  profiles_by_state: Record<string, number>;
  total_profiles: number;
}

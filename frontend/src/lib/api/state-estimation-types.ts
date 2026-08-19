export interface StateEstimateResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  state_type: "LUBRICATION_DELIVERY_STATE" | "BEARING_CONDITION_STATE";
  as_of_timestamp: string;
  state_value: number;
  state_rate: number;
  trend: "IMPROVING" | "STABLE" | "DETERIORATING" | "UNKNOWN";
  uncertainty: "LOW" | "MODERATE" | "HIGH";
  covariance_summary: Record<string, number>;
  estimator_id: string;
  estimator_version: string;
  config_version: string;
  feature_set: string;
  feature_set_version: string;
  feature_vector_id: string;
  dt_seconds: number;
  prediction_only: boolean;
  observations_used: string[];
  observations_missing: string[];
  quality_summary: Record<string, unknown>;
  created_at: string;
}

export type LatestStateEstimatesResponse = Record<string, StateEstimateResponse>;

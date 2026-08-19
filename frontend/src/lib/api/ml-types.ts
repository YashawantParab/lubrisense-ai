export interface MLInferenceResultResponse {
  id: string;
  tenant_id: string;
  machine_id: string;
  feature_vector_id: string;
  model_id: string;
  model_version: string;
  result_kind: "ANOMALY" | "CLASSIFICATION";
  status: "OK" | "INSUFFICIENT_FEATURES" | "UNKNOWN";
  as_of_timestamp: string;
  anomaly_score: number | null;
  anomalous: boolean | null;
  threshold: number | null;
  predicted_class: string | null;
  class_probabilities: Record<string, number>;
  confidence_category: "LOW" | "MODERATE" | "HIGH" | null;
  features_used: string[];
  missing_features: string[];
  quality_summary: Record<string, unknown>;
  explanation: Record<string, unknown>;
  created_at: string;
}

export interface ModelSummaryResponse {
  model_id: string;
  model_version: string;
  model_type: string;
  status: string;
  training_time: string;
  dataset_id: string;
  dataset_version: string;
  feature_set: string;
  feature_set_version: string;
}

export interface ModelDetailResponse extends ModelSummaryResponse {
  features: string[];
  hyperparameters: Record<string, unknown>;
  metrics: Record<string, unknown>;
  thresholds: Record<string, number>;
  seed: number;
  code_version: string;
  limitations: string[];
  minimum_required_features: string[];
}

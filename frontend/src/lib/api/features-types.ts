export interface FeatureVectorResponse {
  id: string;
  feature_set: string;
  feature_set_version: string;
  tenant_id: string;
  machine_id: string;
  component_id: string | null;
  as_of_timestamp: string;
  feature_values: Record<string, unknown>;
  missing_features: string[];
  quality_summary: Record<string, unknown>;
  source_window: Record<string, unknown>;
  baseline_versions: Record<string, unknown>;
  rule_versions: Record<string, unknown>;
  feature_definition_versions: Record<string, unknown>;
  created_at: string;
}

export interface FeatureSetResponse {
  name: string;
  version: string;
  intended_use: string;
  feature_count: number;
  feature_names: string[];
}

export interface FeatureDefinitionResponse {
  feature_name: string;
  feature_version: string;
  group: string;
  data_type: string;
  unit: string;
  entity_scope: string;
  source_measurements: string[];
  window_seconds: number | null;
  aggregation: string;
  context_requirements: string[];
  quality_requirement: string;
  null_behavior: string;
  description: string;
  owner: string;
  availability: string;
  status: string;
  feature_sets: string[];
}

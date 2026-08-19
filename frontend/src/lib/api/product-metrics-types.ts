export interface MetricResponse {
  metric_id: string;
  name: string;
  definition: string;
  window_description: string;
  value: number | null;
  unit: string;
  numerator: number | null;
  denominator: number | null;
  provenance: "MEASURED_PLATFORM_METRIC" | "DEMO_ESTIMATE" | "CONFIGURED_TARGET";
  source: string;
  scope: string;
  calculated_at: string;
  data_completeness_note: string | null;
}

export interface ProductMetricsResponse {
  north_star: MetricResponse;
  supporting: MetricResponse[];
  generated_at: string;
}

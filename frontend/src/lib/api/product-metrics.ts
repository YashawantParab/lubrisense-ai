import { tenantScopedFetch } from "@/lib/api/client";
import type { MetricResponse, ProductMetricsResponse } from "@/lib/api/product-metrics-types";

export function getProductMetrics(): Promise<ProductMetricsResponse> {
  return tenantScopedFetch<ProductMetricsResponse>("/api/v1/product-metrics");
}

export function getNorthStar(): Promise<MetricResponse> {
  return tenantScopedFetch<MetricResponse>("/api/v1/product-metrics/north-star");
}

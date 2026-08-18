import { tenantScopedFetch } from "@/lib/api/client";
import type {
  FeatureDefinitionResponse,
  FeatureSetResponse,
  FeatureVectorResponse,
} from "@/lib/api/features-types";

export function getFeatureSets(): Promise<FeatureSetResponse[]> {
  return tenantScopedFetch<FeatureSetResponse[]>("/api/v1/features/sets");
}

export function getFeatureRegistry(): Promise<FeatureDefinitionResponse[]> {
  return tenantScopedFetch<FeatureDefinitionResponse[]>("/api/v1/features/registry");
}

export function getLatestMachineFeatures(
  machineId: string,
  featureSet: string,
): Promise<FeatureVectorResponse> {
  const query = new URLSearchParams({ feature_set: featureSet });
  return tenantScopedFetch<FeatureVectorResponse>(
    `/api/v1/features/machines/${machineId}/latest?${query}`,
  );
}

export function listMachineFeatures(
  machineId: string,
  featureSet?: string,
): Promise<FeatureVectorResponse[]> {
  const query = new URLSearchParams();
  if (featureSet) query.set("feature_set", featureSet);
  return tenantScopedFetch<FeatureVectorResponse[]>(
    `/api/v1/features/machines/${machineId}${query.size ? `?${query}` : ""}`,
  );
}

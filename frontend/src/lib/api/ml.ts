import { tenantScopedFetch } from "@/lib/api/client";
import type {
  MLInferenceResultResponse,
  ModelDetailResponse,
  ModelSummaryResponse,
} from "@/lib/api/ml-types";

export function getModels(): Promise<ModelSummaryResponse[]> {
  return tenantScopedFetch<ModelSummaryResponse[]>("/api/v1/ml/models");
}

export function getModel(modelId: string): Promise<ModelDetailResponse> {
  return tenantScopedFetch<ModelDetailResponse>(`/api/v1/ml/models/${modelId}`);
}

export function getLatestMachineInference(
  machineId: string,
  modelId: string,
): Promise<MLInferenceResultResponse> {
  const query = new URLSearchParams({ model_id: modelId });
  return tenantScopedFetch<MLInferenceResultResponse>(
    `/api/v1/ml/machines/${machineId}/latest?${query}`,
  );
}

export function listMachineInferenceHistory(
  machineId: string,
  modelId?: string,
): Promise<MLInferenceResultResponse[]> {
  const query = new URLSearchParams();
  if (modelId) query.set("model_id", modelId);
  return tenantScopedFetch<MLInferenceResultResponse[]>(
    `/api/v1/ml/machines/${machineId}/history${query.size ? `?${query}` : ""}`,
  );
}

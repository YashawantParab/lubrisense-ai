import { tenantScopedFetch } from "@/lib/api/client";
import type {
  Attribution,
  CarbonImpactEstimate,
  EnergyAssessment,
  EnergyOutcomeVerification,
} from "@/lib/api/energy-types";

export function getFleetLatestEnergyAssessment(): Promise<EnergyAssessment[]> {
  return tenantScopedFetch<EnergyAssessment[]>("/api/v1/energy/fleet-latest");
}

export function getEnergyAssessmentHistory(
  machineId: string,
  limit = 200,
): Promise<EnergyAssessment[]> {
  return tenantScopedFetch<EnergyAssessment[]>(
    `/api/v1/energy/machines/${machineId}/history?limit=${limit}`,
  );
}

export function getFleetLatestAttribution(): Promise<Attribution[]> {
  return tenantScopedFetch<Attribution[]>("/api/v1/energy/attribution/fleet-latest");
}

export function getFleetLatestEnergyOutcome(): Promise<EnergyOutcomeVerification[]> {
  return tenantScopedFetch<EnergyOutcomeVerification[]>("/api/v1/energy/outcomes/fleet-latest");
}

export function getEnergyOutcomeHistory(
  machineId: string,
  limit = 50,
): Promise<EnergyOutcomeVerification[]> {
  return tenantScopedFetch<EnergyOutcomeVerification[]>(
    `/api/v1/energy/machines/${machineId}/outcomes?limit=${limit}`,
  );
}

export function getFleetLatestCarbon(): Promise<CarbonImpactEstimate[]> {
  return tenantScopedFetch<CarbonImpactEstimate[]>("/api/v1/energy/carbon/fleet-latest");
}

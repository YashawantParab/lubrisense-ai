"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  getAreaPerformance,
  getAttentionQueue,
  getEnergyQueue,
  getOrganizationPerformance,
  getRecentOutcomes,
  getSitePerformance,
  listAreaPerformance,
  listSitePerformance,
} from "@/lib/api/performance";

export function useOrganizationPerformance() {
  return useAuthenticatedQuery({
    queryKey: ["performance", "organization"],
    queryFn: () => getOrganizationPerformance(),
  });
}

export function useSitePerformances() {
  return useAuthenticatedQuery({
    queryKey: ["performance", "sites"],
    queryFn: () => listSitePerformance(),
  });
}

export function useSitePerformance(siteId: string) {
  return useAuthenticatedQuery({
    queryKey: ["performance", "sites", siteId],
    queryFn: () => getSitePerformance(siteId),
    enabled: Boolean(siteId),
  });
}

export function useAreaPerformances() {
  return useAuthenticatedQuery({
    queryKey: ["performance", "areas"],
    queryFn: () => listAreaPerformance(),
  });
}

export function useAreaPerformance(areaKey: string) {
  return useAuthenticatedQuery({
    queryKey: ["performance", "areas", areaKey],
    queryFn: () => getAreaPerformance(areaKey),
    enabled: Boolean(areaKey),
  });
}

export function useAttentionQueue(limit = 50) {
  return useAuthenticatedQuery({
    queryKey: ["performance", "attention", limit],
    queryFn: () => getAttentionQueue(limit),
  });
}

export function useRecentPortfolioOutcomes(limit = 20) {
  return useAuthenticatedQuery({
    queryKey: ["performance", "outcomes", limit],
    queryFn: () => getRecentOutcomes(limit),
  });
}

export function useEnergyQueue(limit = 200) {
  return useAuthenticatedQuery({
    queryKey: ["performance", "energy", limit],
    queryFn: () => getEnergyQueue(limit),
  });
}

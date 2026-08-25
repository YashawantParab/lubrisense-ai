"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getAreaPerformance,
  getAttentionQueue,
  getOrganizationPerformance,
  getRecentOutcomes,
  getSitePerformance,
  listAreaPerformance,
  listSitePerformance,
} from "@/lib/api/performance";

export function useOrganizationPerformance() {
  return useQuery({
    queryKey: ["performance", "organization"],
    queryFn: () => getOrganizationPerformance(),
  });
}

export function useSitePerformances() {
  return useQuery({
    queryKey: ["performance", "sites"],
    queryFn: () => listSitePerformance(),
  });
}

export function useSitePerformance(siteId: string) {
  return useQuery({
    queryKey: ["performance", "sites", siteId],
    queryFn: () => getSitePerformance(siteId),
    enabled: Boolean(siteId),
  });
}

export function useAreaPerformances() {
  return useQuery({
    queryKey: ["performance", "areas"],
    queryFn: () => listAreaPerformance(),
  });
}

export function useAreaPerformance(areaKey: string) {
  return useQuery({
    queryKey: ["performance", "areas", areaKey],
    queryFn: () => getAreaPerformance(areaKey),
    enabled: Boolean(areaKey),
  });
}

export function useAttentionQueue(limit = 50) {
  return useQuery({
    queryKey: ["performance", "attention", limit],
    queryFn: () => getAttentionQueue(limit),
  });
}

export function useRecentPortfolioOutcomes(limit = 20) {
  return useQuery({
    queryKey: ["performance", "outcomes", limit],
    queryFn: () => getRecentOutcomes(limit),
  });
}

"use client";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { getNorthStar, getProductMetrics } from "@/lib/api/product-metrics";

export function useProductMetrics() {
  return useAuthenticatedQuery({
    queryKey: ["product-metrics"],
    queryFn: () => getProductMetrics(),
  });
}

export function useNorthStar() {
  return useAuthenticatedQuery({
    queryKey: ["product-metrics", "north-star"],
    queryFn: () => getNorthStar(),
  });
}

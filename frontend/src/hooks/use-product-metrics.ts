"use client";

import { useQuery } from "@tanstack/react-query";

import { getNorthStar, getProductMetrics } from "@/lib/api/product-metrics";

export function useProductMetrics() {
  return useQuery({
    queryKey: ["product-metrics"],
    queryFn: () => getProductMetrics(),
  });
}

export function useNorthStar() {
  return useQuery({
    queryKey: ["product-metrics", "north-star"],
    queryFn: () => getNorthStar(),
  });
}

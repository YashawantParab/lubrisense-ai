"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { askKnowledge, listDocuments } from "@/lib/api/knowledge";

export function useDocuments(status?: string) {
  return useQuery({
    queryKey: ["knowledge", "documents", status],
    queryFn: () => listDocuments(status),
  });
}

export function useAskKnowledge() {
  return useMutation({
    mutationFn: (query: string) => askKnowledge(query),
  });
}

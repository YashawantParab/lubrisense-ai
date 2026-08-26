"use client";

import { useMutation } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import { askKnowledge, listDocuments } from "@/lib/api/knowledge";

export function useDocuments(status?: string) {
  return useAuthenticatedQuery({
    queryKey: ["knowledge", "documents", status],
    queryFn: () => listDocuments(status),
  });
}

export function useAskKnowledge() {
  return useMutation({
    mutationFn: (query: string) => askKnowledge(query),
  });
}

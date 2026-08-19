"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  completeCase,
  createCase,
  createCmmsDraft,
  getCase,
  getFeedback,
  listActions,
  listCases,
  listFindings,
  planCase,
  recordAction,
  recordFinding,
  startCase,
} from "@/lib/api/maintenance";

export function useMaintenanceCases(state?: string) {
  return useQuery({
    queryKey: ["maintenance", "list", state],
    queryFn: () => listCases(state),
  });
}

export function useMaintenanceCase(caseId: string) {
  return useQuery({
    queryKey: ["maintenance", "detail", caseId],
    queryFn: () => getCase(caseId),
    enabled: Boolean(caseId),
  });
}

export function useMaintenanceFindings(caseId: string) {
  return useQuery({
    queryKey: ["maintenance", "findings", caseId],
    queryFn: () => listFindings(caseId),
    enabled: Boolean(caseId),
  });
}

export function useMaintenanceActions(caseId: string) {
  return useQuery({
    queryKey: ["maintenance", "actions", caseId],
    queryFn: () => listActions(caseId),
    enabled: Boolean(caseId),
  });
}

export function useMaintenanceFeedback(caseId: string) {
  return useQuery({
    queryKey: ["maintenance", "feedback", caseId],
    queryFn: () => getFeedback(caseId),
    enabled: Boolean(caseId),
  });
}

function invalidateCase(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["maintenance"] });
  queryClient.invalidateQueries({ queryKey: ["incidents"] });
}

export function useCreateCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (incidentId: string) => createCase(incidentId),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function usePlanCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => planCase(caseId),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function useStartCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => startCase(caseId),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function useRecordFinding(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { result: string; component?: string; observed_issue?: string; notes: string }) =>
      recordFinding(caseId, body),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function useRecordAction(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { action_type: string; notes: string }) => recordAction(caseId, body),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function useCompleteCase(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      classification: string;
      confirmed_component?: string;
      confirmed_finding?: string;
      notes?: string;
    }) => completeCase(caseId, body),
    onSuccess: () => invalidateCase(queryClient),
  });
}

export function useCreateCmmsDraft(caseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => createCmmsDraft(caseId),
    onSuccess: () => invalidateCase(queryClient),
  });
}

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  acknowledgeIncident,
  closeIncident,
  evaluateMachine,
  getIncident,
  getIncidentTimeline,
  listIncidents,
  resolveIncident,
  startInvestigation,
} from "@/lib/api/incidents";

export function useIncidents(params?: { machineId?: string; state?: string }) {
  return useAuthenticatedQuery({
    queryKey: ["incidents", "list", params],
    queryFn: () => listIncidents(params),
  });
}

export function useIncident(incidentId: string) {
  return useAuthenticatedQuery({
    queryKey: ["incidents", "detail", incidentId],
    queryFn: () => getIncident(incidentId),
    enabled: Boolean(incidentId),
  });
}

export function useIncidentTimeline(incidentId: string) {
  return useAuthenticatedQuery({
    queryKey: ["incidents", "timeline", incidentId],
    queryFn: () => getIncidentTimeline(incidentId),
    enabled: Boolean(incidentId),
  });
}

function useIncidentMutation<T>(fn: (incidentId: string) => Promise<T>, incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fn(incidentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}

export function useEvaluateMachine(machineId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => evaluateMachine(machineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}

export function useAcknowledgeIncident(incidentId: string) {
  return useIncidentMutation(acknowledgeIncident, incidentId);
}

export function useStartInvestigation(incidentId: string) {
  return useIncidentMutation(startInvestigation, incidentId);
}

export function useResolveIncident(incidentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => resolveIncident(incidentId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}

export function useCloseIncident(incidentId: string) {
  return useIncidentMutation(closeIncident, incidentId);
}

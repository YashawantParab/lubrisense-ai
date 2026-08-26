"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";

import {
  addCommissioningSensor,
  assignCommissioningGateway,
  completeCommissioning,
  getCommissioningSession,
  listCommissioningSessions,
  startCommissioning,
  validateCommissioning,
} from "@/lib/api/commissioning";
import type {
  AddSensorRequest,
  AssignGatewayRequest,
  StartCommissioningRequest,
} from "@/lib/api/commissioning-types";

export function useCommissioningSessions() {
  return useAuthenticatedQuery({
    queryKey: ["commissioning", "list"],
    queryFn: () => listCommissioningSessions(),
  });
}

export function useCommissioningSession(sessionId: string) {
  return useAuthenticatedQuery({
    queryKey: ["commissioning", "detail", sessionId],
    queryFn: () => getCommissioningSession(sessionId),
    enabled: Boolean(sessionId),
  });
}

function invalidate(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["commissioning"] });
}

export function useStartCommissioning() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StartCommissioningRequest) => startCommissioning(body),
    onSuccess: () => invalidate(queryClient),
  });
}

export function useAddCommissioningSensor(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddSensorRequest) => addCommissioningSensor(sessionId, body),
    onSuccess: () => invalidate(queryClient),
  });
}

export function useAssignCommissioningGateway(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AssignGatewayRequest) => assignCommissioningGateway(sessionId, body),
    onSuccess: () => invalidate(queryClient),
  });
}

export function useValidateCommissioning(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => validateCommissioning(sessionId),
    onSuccess: () => invalidate(queryClient),
  });
}

export function useCompleteCommissioning(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => completeCommissioning(sessionId),
    onSuccess: () => invalidate(queryClient),
  });
}

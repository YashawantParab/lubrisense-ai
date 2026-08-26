"use client";

import { useQuery } from "@tanstack/react-query";
import type { DefaultError, QueryKey, UndefinedInitialDataOptions } from "@tanstack/react-query";

import { useAuth } from "@/lib/auth/context";

/**
 * Drop-in replacement for `useQuery` for every query whose `queryFn` calls
 * `tenantScopedFetch` (i.e. hits an authenticated backend endpoint) — the fix for the
 * hosted auth race where `AuthProvider`'s initial `demoLogin()` had not yet resolved
 * (so no bearer token existed) while a page's own React Query hooks had already fired,
 * producing a 401 the hosted (non-permissive) backend correctly rejects.
 *
 * ANDs the caller's own `enabled` condition (if any — e.g. `Boolean(machineId)`) with
 * `!useAuth().isLoading`, so an authenticated query never executes while auth is still
 * initializing OR while a role switch is re-issuing a token — the exact two moments a
 * request would otherwise race a missing/stale `Authorization` header. Never used for
 * `demoLogin` itself or for genuinely unauthenticated endpoints (health/readiness) —
 * gating those would either deadlock (nothing would ever set `isLoading` to false) or
 * needlessly block a check that doesn't need a token.
 */
export function useAuthenticatedQuery<
  TQueryFnData = unknown,
  TError = DefaultError,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
>(options: UndefinedInitialDataOptions<TQueryFnData, TError, TData, TQueryKey>) {
  const { isLoading: authInitializing } = useAuth();
  return useQuery({
    ...options,
    enabled: !authInitializing && (options.enabled ?? true),
  });
}

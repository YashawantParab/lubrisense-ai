"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { demoLogin } from "@/lib/api/auth";
import { setDemoAuthToken } from "@/lib/api/client";
import type { DemoRole } from "@/lib/api/auth-types";
import { type Permission, VISIBLE_DEMO_ROLES, roleHasPermission } from "@/lib/permissions";

interface AuthState {
  role: DemoRole;
  displayName: string;
  isLoading: boolean;
  /** Issues a fresh demo token for `role` and makes it the active identity for every
   * subsequent API call (`tenantScopedFetch`). See `docs/PRODUCT_EXPERIENCE.md` "Demo
   * identity switcher" — this is a demo/reference-platform convenience, not a real
   * login flow. */
  switchRole: (role: DemoRole) => void;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = "lubrisense-demo-role";
const DEFAULT_ROLE: DemoRole = "ADMIN";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<DemoRole>(DEFAULT_ROLE);
  const [displayName, setDisplayName] = useState("Admin");
  const [isLoading, setIsLoading] = useState(true);
  const queryClient = useQueryClient();

  const switchRole = useCallback(
    (nextRole: DemoRole) => {
      setIsLoading(true);
      // Every authenticated query (`useAuthenticatedQuery`) is paused for as long as
      // isLoading is true, so it's safe to drop every cached authenticated response
      // immediately — the previous role's data must never keep rendering once a switch
      // has been requested, since the new role may have different visibility into the
      // same data (Hosted Auth Race fix — role-switch requirement). `demoLogin` itself
      // never goes through `useAuthenticatedQuery`, so it is never gated by this
      // isLoading flip — no deadlock.
      queryClient.clear();
      demoLogin(nextRole)
        .then((response) => {
          setDemoAuthToken(response.access_token);
          setRole(response.role);
          setDisplayName(response.display_name);
          if (typeof window !== "undefined") {
            window.localStorage.setItem(STORAGE_KEY, response.role);
          }
        })
        .catch(() => {
          // Demo-login failure (e.g. backend briefly unreachable) — fall back to no
          // token, which the backend's permissive-mode default treats as full access
          // locally, so the product stays usable rather than hard-failing every page.
          setDemoAuthToken(null);
        })
        .finally(() => setIsLoading(false));
    },
    [queryClient],
  );

  useEffect(() => {
    const stored =
      typeof window !== "undefined"
        ? (window.localStorage.getItem(STORAGE_KEY) as DemoRole | null)
        : null;
    // A role stored from before the identity selector was trimmed to Technician/Admin
    // (Live Demo Quality Cleanup §1) — or any other non-visible role — must not silently
    // become the active identity: the selector has no option for it, which would render
    // as a blank/mismatched dropdown. Fall back to the default in that case.
    const initialRole =
      stored && (VISIBLE_DEMO_ROLES as string[]).includes(stored) ? stored : DEFAULT_ROLE;
    // Kicks off the initial demo-login request; switchRole's own setState calls all
    // land inside its .then()/.catch()/.finally() callbacks, not synchronously in this
    // effect body — the one intentional exception is `switchRole`'s own leading
    // `setIsLoading(true)`, accepted here since this is a one-time mount fetch, not a
    // render-triggered cascade.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    switchRole(initialRole);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount only
  }, []);

  const can = useCallback((permission: Permission) => roleHasPermission(role, permission), [role]);

  return (
    <AuthContext.Provider value={{ role, displayName, isLoading, switchRole, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

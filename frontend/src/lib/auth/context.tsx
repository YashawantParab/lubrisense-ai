"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { demoLogin } from "@/lib/api/auth";
import { setDemoAuthToken } from "@/lib/api/client";
import type { DemoRole } from "@/lib/api/auth-types";
import { type Permission, roleHasPermission } from "@/lib/permissions";

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
  const [displayName, setDisplayName] = useState("Demo Admin");
  const [isLoading, setIsLoading] = useState(true);

  const switchRole = useCallback((nextRole: DemoRole) => {
    setIsLoading(true);
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
  }, []);

  useEffect(() => {
    const stored =
      typeof window !== "undefined"
        ? (window.localStorage.getItem(STORAGE_KEY) as DemoRole | null)
        : null;
    // Kicks off the initial demo-login request; switchRole's own setState calls all
    // land inside its .then()/.catch()/.finally() callbacks, not synchronously in this
    // effect body — the one intentional exception is `switchRole`'s own leading
    // `setIsLoading(true)`, accepted here since this is a one-time mount fetch, not a
    // render-triggered cascade.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    switchRole(stored ?? DEFAULT_ROLE);
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

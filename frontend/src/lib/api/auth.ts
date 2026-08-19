import { tenantScopedFetch } from "@/lib/api/client";
import type { DemoLoginResponse, DemoRole } from "@/lib/api/auth-types";

export function demoLogin(role: DemoRole): Promise<DemoLoginResponse> {
  return tenantScopedFetch<DemoLoginResponse>("/api/v1/auth/demo-login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
}

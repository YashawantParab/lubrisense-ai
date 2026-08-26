import { afterEach, describe, expect, it, vi } from "vitest";

import { setDemoAuthToken, tenantScopedFetch } from "@/lib/api/client";

function mockOkFetch() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({}),
    headers: new Headers(),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * Regression coverage for the hosted auth race — `setDemoAuthToken` is the module-level
 * state `AuthProvider` writes to, and `tenantScopedFetch` is what every authenticated
 * hook's `queryFn` ultimately calls. Proves the demo-login endpoint itself works with no
 * token present (requirement: never make demo-login require authentication) and that a
 * role switch's new token is picked up immediately by the next request (no stale
 * Authorization header held over from the previous role).
 */
describe("tenantScopedFetch auth header behavior", () => {
  afterEach(() => {
    setDemoAuthToken(null);
    vi.unstubAllGlobals();
  });

  it("omits the Authorization header when no demo token has been issued yet", async () => {
    const fetchMock = mockOkFetch();

    await tenantScopedFetch("/api/v1/auth/demo-login", { method: "POST" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).not.toHaveProperty("Authorization");
  });

  it("attaches the Authorization header once a demo token has been set", async () => {
    setDemoAuthToken("token-abc");
    const fetchMock = mockOkFetch();

    await tenantScopedFetch("/api/v1/performance/organization");

    const [, init] = fetchMock.mock.calls[0] as [
      string,
      RequestInit & { headers: Record<string, string> },
    ];
    expect(init.headers.Authorization).toBe("Bearer token-abc");
  });

  it("uses the new token immediately after a role switch — no stale Authorization header", async () => {
    setDemoAuthToken("old-token");
    setDemoAuthToken("new-token");
    const fetchMock = mockOkFetch();

    await tenantScopedFetch("/api/v1/performance/organization");

    const [, init] = fetchMock.mock.calls[0] as [
      string,
      RequestInit & { headers: Record<string, string> },
    ];
    expect(init.headers.Authorization).toBe("Bearer new-token");
  });

  it("drops the Authorization header entirely after the token is cleared", async () => {
    setDemoAuthToken("token-abc");
    setDemoAuthToken(null);
    const fetchMock = mockOkFetch();

    await tenantScopedFetch("/api/v1/performance/organization");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).not.toHaveProperty("Authorization");
  });
});

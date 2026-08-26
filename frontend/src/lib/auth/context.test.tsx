import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { demoLogin } from "@/lib/api/auth";
import { AuthProvider, useAuth } from "@/lib/auth/context";
import type { DemoLoginResponse } from "@/lib/api/auth-types";

vi.mock("@/lib/api/auth", () => ({
  demoLogin: vi.fn(),
}));

function loginResponse(overrides: Partial<DemoLoginResponse> = {}): DemoLoginResponse {
  return {
    access_token: "t1",
    token_type: "bearer",
    role: "ADMIN",
    user_id: "u-1",
    display_name: "Admin",
    expires_in_seconds: 3600,
    ...overrides,
  };
}

function TestConsumer() {
  const { role, isLoading, switchRole } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="role">{role}</span>
      <button onClick={() => switchRole("TECHNICIAN")}>switch</button>
    </div>
  );
}

function renderWithClient(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

/**
 * Regression coverage for the hosted auth race, at the `AuthProvider` level: proves the
 * `isLoading` signal genuinely reflects "a demo token exists or doesn't yet" (the signal
 * `useAuthenticatedQuery` gates on), and that switching roles drops every cached
 * authenticated response immediately — the previous role's data must never keep
 * rendering once a switch has been requested, since the new role may see different data.
 */
describe("AuthProvider", () => {
  beforeEach(() => {
    vi.mocked(demoLogin).mockReset();
    window.localStorage.clear();
  });

  it("starts isLoading=true and flips to false once the initial demo-login resolves", async () => {
    vi.mocked(demoLogin).mockResolvedValue(loginResponse());
    const client = new QueryClient();

    renderWithClient(client);

    expect(screen.getByTestId("loading").textContent).toBe("true");
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(demoLogin).toHaveBeenCalledWith("ADMIN");
  });

  it("still resolves isLoading to false even if the initial demo-login rejects (no permanent auth-loading deadlock)", async () => {
    vi.mocked(demoLogin).mockRejectedValue(new Error("backend unreachable"));
    const client = new QueryClient();

    renderWithClient(client);

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
  });

  it("clears the query cache as soon as a role switch starts, before the new token arrives", async () => {
    vi.mocked(demoLogin).mockResolvedValue(loginResponse());
    const client = new QueryClient();
    client.setQueryData(["some", "authenticated", "query"], { stale: "admin-only-data" });

    renderWithClient(client);
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    let resolveSwitch!: (value: DemoLoginResponse) => void;
    vi.mocked(demoLogin).mockReturnValue(
      new Promise((resolve) => {
        resolveSwitch = resolve;
      }),
    );

    act(() => {
      screen.getByText("switch").click();
    });

    // Cleared synchronously as the switch begins — not after the new token comes back.
    expect(client.getQueryData(["some", "authenticated", "query"])).toBeUndefined();
    expect(screen.getByTestId("loading").textContent).toBe("true");

    act(() => {
      resolveSwitch(loginResponse({ role: "TECHNICIAN", display_name: "Technician" }));
    });
    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("TECHNICIAN"));
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
  });

  it("demo-login is requested with no bearer token required beforehand", async () => {
    vi.mocked(demoLogin).mockResolvedValue(loginResponse());
    const client = new QueryClient();

    renderWithClient(client);

    // The very first demoLogin call happens while no token has ever existed — proving
    // the demo-login flow itself is never gated behind having a token already.
    await waitFor(() => expect(demoLogin).toHaveBeenCalledTimes(1));
  });
});

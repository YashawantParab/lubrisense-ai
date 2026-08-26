import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthenticatedQuery } from "@/hooks/use-authenticated-query";
import { useAuth } from "@/lib/auth/context";

vi.mock("@/lib/auth/context", () => ({
  useAuth: vi.fn(),
}));

function mockAuth(isLoading: boolean) {
  vi.mocked(useAuth).mockReturnValue({
    role: "ADMIN",
    displayName: "Admin",
    isLoading,
    switchRole: vi.fn(),
    can: () => true,
  });
}

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/**
 * Regression coverage for the hosted auth race (a page's own `useQuery` hooks fired
 * `tenantScopedFetch` requests before `AuthProvider`'s initial `demoLogin()` had set a
 * bearer token, which the hosted — non-permissive — backend correctly rejected with
 * 401). `useAuthenticatedQuery` is the reusable fix every authenticated hook now goes
 * through instead of `useQuery` directly.
 */
describe("useAuthenticatedQuery", () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReset();
  });

  it("does not call queryFn while auth is still initializing", () => {
    mockAuth(true);
    const queryFn = vi.fn().mockResolvedValue("data");
    const { result } = renderHook(() => useAuthenticatedQuery({ queryKey: ["test-a"], queryFn }), {
      wrapper: createWrapper(),
    });
    expect(queryFn).not.toHaveBeenCalled();
    // pending + idle fetchStatus is exactly the state DataState renders as a loading
    // spinner (not an error, not an empty state) — see components/data-state.tsx.
    expect(result.current.isPending).toBe(true);
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("calls queryFn once auth has finished initializing", async () => {
    mockAuth(false);
    const queryFn = vi.fn().mockResolvedValue("data");
    const { result } = renderHook(() => useAuthenticatedQuery({ queryKey: ["test-b"], queryFn }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(queryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.data).toBe("data"));
  });

  it("still honors an explicit enabled:false even once auth is ready", () => {
    mockAuth(false);
    const queryFn = vi.fn().mockResolvedValue("data");
    renderHook(() => useAuthenticatedQuery({ queryKey: ["test-c"], queryFn, enabled: false }), {
      wrapper: createWrapper(),
    });
    expect(queryFn).not.toHaveBeenCalled();
  });

  it("starts firing as soon as auth flips from loading to ready, without remounting", async () => {
    mockAuth(true);
    const queryFn = vi.fn().mockResolvedValue("data");
    const { result, rerender } = renderHook(
      () => useAuthenticatedQuery({ queryKey: ["test-d"], queryFn }),
      { wrapper: createWrapper() },
    );
    expect(queryFn).not.toHaveBeenCalled();

    mockAuth(false);
    rerender();

    await waitFor(() => expect(queryFn).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(result.current.data).toBe("data"));
  });
});

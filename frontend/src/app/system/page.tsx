"use client";

import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { publicEnv } from "@/lib/env/public";
import { useBackendReadiness, useBackendSystemInfo } from "@/hooks/use-backend-status";

function BackendConnectivityCard() {
  const readiness = useBackendReadiness();

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Backend connectivity
        </h2>
        {readiness.isPending && <StatusPill tone="neutral">Checking…</StatusPill>}
        {readiness.isError && <StatusPill tone="error">Unreachable</StatusPill>}
        {readiness.isSuccess && readiness.data.status === "ready" && (
          <StatusPill tone="ok">Ready</StatusPill>
        )}
        {readiness.isSuccess && readiness.data.status !== "ready" && (
          <StatusPill tone="warn">Degraded</StatusPill>
        )}
      </div>

      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Live result of <code className="font-mono text-xs">GET /ready</code> on the backend API at{" "}
        <code className="font-mono text-xs">{publicEnv.apiBaseUrl}</code>.
      </p>

      {readiness.isError && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          Could not reach the backend service. Confirm it is running and reachable from this
          environment.
        </p>
      )}

      {readiness.isSuccess && (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {readiness.data.dependencies.map((dependency) => (
            <li key={dependency.name} className="flex items-center justify-between py-2 text-sm">
              <span className="capitalize text-zinc-700 dark:text-zinc-300">
                {dependency.name}
                {!dependency.required && (
                  <span className="ml-1.5 text-xs text-zinc-400 dark:text-zinc-600">
                    (optional)
                  </span>
                )}
              </span>
              {dependency.status === "healthy" && <StatusPill tone="ok">Healthy</StatusPill>}
              {dependency.status === "unhealthy" && <StatusPill tone="error">Unhealthy</StatusPill>}
              {dependency.status === "unavailable_optional" && (
                <StatusPill tone="neutral">Optional / not configured</StatusPill>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SystemInfoCard() {
  const systemInfo = useBackendSystemInfo();

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Backend system info
      </h2>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        From <code className="font-mono text-xs">GET /api/v1/system/info</code>.
      </p>

      {systemInfo.isPending && (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>
      )}
      {systemInfo.isError && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">Unavailable.</p>
      )}
      {systemInfo.isSuccess && (
        <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-zinc-500 dark:text-zinc-400">Application</dt>
          <dd className="font-mono text-zinc-900 dark:text-zinc-100">
            {systemInfo.data.application}
          </dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Version</dt>
          <dd className="font-mono text-zinc-900 dark:text-zinc-100">{systemInfo.data.version}</dd>
          <dt className="text-zinc-500 dark:text-zinc-400">Environment</dt>
          <dd className="font-mono text-zinc-900 dark:text-zinc-100">
            {systemInfo.data.environment}
          </dd>
        </dl>
      )}
    </section>
  );
}

function FrontendEnvironmentCard() {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Frontend</h2>
        <StatusPill tone="ok">Running</StatusPill>
      </div>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Browser-safe environment configuration (
        <code className="font-mono text-xs">NEXT_PUBLIC_*</code> only — see src/lib/env/public.ts).
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-y-2 text-sm">
        <dt className="text-zinc-500 dark:text-zinc-400">Environment</dt>
        <dd className="font-mono text-zinc-900 dark:text-zinc-100">{publicEnv.appEnv}</dd>
        <dt className="text-zinc-500 dark:text-zinc-400">API base URL</dt>
        <dd className="font-mono text-zinc-900 dark:text-zinc-100">{publicEnv.apiBaseUrl}</dd>
      </dl>
    </section>
  );
}

export default function SystemStatusPage() {
  usePageTitle("System Status");
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-12">
      <PageHeader
        title="System Status"
        description="Frontend/backend connectivity diagnostics — an operations/admin view, not the product experience. See Overview for the operational home screen."
      />

      <div className="grid gap-6">
        <FrontendEnvironmentCard />
        <BackendConnectivityCard />
        <SystemInfoCard />
      </div>
    </div>
  );
}

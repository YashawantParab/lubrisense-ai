"use client";

import Link from "next/link";

import { CapabilityLevelBadge, CommissioningStatusBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useCommissioningSessions } from "@/hooks/use-commissioning";
import { useAuth } from "@/lib/auth/context";

export default function ConfigurationPage() {
  usePageTitle("Configuration");
  const sessions = useCommissioningSessions();
  const { can } = useAuth();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Configuration"
        description="Commission new machines and review device/firmware configuration governance across your fleet."
        actions={
          can("ASSET_MANAGE") ? (
            <Link
              href="/configuration/commission"
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700"
            >
              Commission a machine
            </Link>
          ) : undefined
        }
      />

      <DataState isPending={sessions.isPending} isError={sessions.isError} error={sessions.error}>
        {(sessions.data ?? []).length === 0 ? (
          <EmptyState
            title="No commissioning sessions yet"
            description="Commission a new machine to see its onboarding progress here."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Session</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Capability</th>
                  <th className="px-4 py-2 font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {(sessions.data ?? []).map((s) => (
                  <tr key={s.id} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
                    <td className="px-4 py-2">
                      <Link
                        href={`/configuration/commission?sessionId=${s.id}`}
                        className="font-mono text-xs text-sky-600 hover:underline dark:text-sky-400"
                      >
                        {s.id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <CommissioningStatusBadge value={s.status} />
                    </td>
                    <td className="px-4 py-2">
                      <CapabilityLevelBadge value={s.capability_level} />
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                      <RelativeTime iso={s.created_at} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataState>
    </div>
  );
}

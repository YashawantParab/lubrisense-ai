"use client";

import Link from "next/link";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { FeedbackBadge, MaintenanceStateBadge, PriorityBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { humanize } from "@/lib/terminology";

export default function MaintenancePage() {
  usePageTitle("Maintenance");
  const cases = useMaintenanceCases();

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Maintenance Cases"
        description="Human-controlled workflow — every physical action is a technician-recorded observation, never an automated one."
      />

      <DataState
        isPending={cases.isPending}
        isError={cases.isError}
        error={cases.error}
        loadingLabel="Loading maintenance cases…"
      >
        {(cases.data ?? []).length === 0 ? (
          <EmptyState
            title="No maintenance cases yet"
            description="Open one from an incident under investigation."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Recommended action</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">State</th>
                  <th className="px-4 py-2 font-medium">Feedback</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {(cases.data ?? []).map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="px-4 py-2">
                      <Link
                        href={`/maintenance/${c.id}`}
                        className="text-sky-600 hover:underline dark:text-sky-400"
                      >
                        {humanize(c.recommended_action)}
                      </Link>
                    </td>
                    <td className="px-4 py-2">
                      <PriorityBadge value={c.priority} />
                    </td>
                    <td className="px-4 py-2">
                      <MaintenanceStateBadge value={c.state} />
                    </td>
                    <td className="px-4 py-2">
                      {c.feedback_classification ? (
                        <FeedbackBadge value={c.feedback_classification} />
                      ) : (
                        <span className="text-xs text-zinc-400 dark:text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                      <RelativeTime iso={c.created_at} />
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

"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import {
  EnergyOutcomeStatusBadge,
  FeedbackBadge,
  MaintenanceStateBadge,
  PriorityBadge,
} from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { useFleetLatestEnergyOutcome } from "@/hooks/use-energy";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { humanize } from "@/lib/terminology";

interface MachineRef {
  name: string;
  siteName: string;
}

type StateFilter = "all" | "open" | "completed";

const FILTER_LABEL: Record<StateFilter, string> = {
  all: "All",
  open: "Open",
  completed: "Completed",
};

// Mirrors the backend's own `_OPEN_MAINTENANCE_STATES`
// (backend/app/portfolio/services/portfolio_service.py) — the exact set Organization's
// "Open maintenance actions" KPI counts, so this filter is the one destination that
// reconciles with it (Enterprise Product Rebuild §2/§3).
const OPEN_STATES = new Set([
  "REVIEW_REQUIRED",
  "NOT_STARTED",
  "PLANNED",
  "IN_PROGRESS",
  "AWAITING_VERIFICATION",
]);

const FILTER_MATCH: Record<StateFilter, (state: string) => boolean> = {
  all: () => true,
  open: (s) => OPEN_STATES.has(s),
  completed: (s) => s === "COMPLETED",
};

export default function MaintenancePage() {
  return (
    <Suspense fallback={null}>
      <MaintenancePageContent />
    </Suspense>
  );
}

function MaintenancePageContent() {
  usePageTitle("Maintenance");
  const cases = useMaintenanceCases();
  const hierarchy = useHierarchy();
  const fleetOutcome = useFleetLatestEnergyOutcome();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filter = (searchParams.get("state") as StateFilter | null) ?? "all";
  const setFilter = (value: StateFilter) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "all") params.delete("state");
    else params.set("state", value);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const machineById = useMemo(() => {
    const map = new Map<string, MachineRef>();
    for (const customer of hierarchy.data?.customers ?? []) {
      for (const site of customer.sites) {
        for (const plant of site.plants) {
          for (const line of plant.production_lines) {
            for (const machine of line.machines) {
              map.set(machine.id, { name: machine.name, siteName: site.name });
            }
          }
        }
      }
    }
    return map;
  }, [hierarchy.data]);

  const outcomeByCase = useMemo(
    () => new Map((fleetOutcome.data ?? []).map((o) => [o.maintenance_case_id, o])),
    [fleetOutcome.data],
  );

  const allCases = useMemo(() => cases.data ?? [], [cases.data]);
  const filteredCases = useMemo(
    () => allCases.filter((c) => FILTER_MATCH[filter](c.state)),
    [allCases, filter],
  );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Maintenance Cases"
        description="Human-controlled workflow — every physical action is a technician-recorded observation, never an automated one."
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-md border border-zinc-300 p-0.5 text-xs dark:border-zinc-700">
          {(Object.keys(FILTER_LABEL) as StateFilter[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`rounded px-2.5 py-1 font-medium ${
                filter === key
                  ? "bg-sky-600 text-white"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              }`}
            >
              {FILTER_LABEL[key]}
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {filteredCases.length} of {allCases.length} cases
        </span>
      </div>

      <DataState
        isPending={cases.isPending}
        isError={cases.isError}
        error={cases.error}
        loadingLabel="Loading maintenance cases…"
      >
        {filteredCases.length === 0 ? (
          <EmptyState
            title={
              allCases.length === 0 ? "No maintenance cases yet" : "No cases match this filter"
            }
            description={
              allCases.length === 0
                ? "Open one from an incident under investigation."
                : "Try clearing the filter or switching back to all cases."
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Recommended action</th>
                  <th className="px-4 py-2 font-medium">Machine</th>
                  <th className="px-4 py-2 font-medium">Site</th>
                  <th className="px-4 py-2 font-medium">Priority</th>
                  <th className="px-4 py-2 font-medium">State</th>
                  <th className="px-4 py-2 font-medium">Feedback</th>
                  <th className="px-4 py-2 font-medium">Energy outcome</th>
                  <th className="px-4 py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((c) => {
                  const machine = machineById.get(c.machine_id);
                  const energyOutcome = outcomeByCase.get(c.id);
                  return (
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
                        <Link
                          href={`/machines/${c.machine_id}`}
                          className="text-zinc-700 hover:underline dark:text-zinc-300"
                        >
                          {machine?.name ?? "—"}
                        </Link>
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {machine?.siteName ?? "—"}
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
                      <td className="px-4 py-2">
                        {energyOutcome ? (
                          <EnergyOutcomeStatusBadge value={energyOutcome.energy_outcome_status} />
                        ) : (
                          <span className="text-xs text-zinc-400 dark:text-zinc-600">
                            Not assessed
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                        <RelativeTime iso={c.created_at} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </DataState>
    </div>
  );
}

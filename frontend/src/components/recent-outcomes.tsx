"use client";

import Link from "next/link";
import { useMemo } from "react";

import { FeedbackBadge, MaintenanceStateBadge } from "@/components/badges";
import { EmptyState } from "@/components/empty-state";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { feedbackHeadline, humanize } from "@/lib/terminology";

function flattenMachineNames(hierarchy: ReturnType<typeof useHierarchy>["data"]) {
  const map = new Map<string, string>();
  if (!hierarchy) return map;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          for (const machine of line.machines) {
            map.set(machine.id, machine.name);
          }
        }
      }
    }
  }
  return map;
}

/** CLAUDE.md §7 — real, persisted maintenance-case outcomes, most recent first. No
 * fabricated ROI/savings — just what actually happened (diagnosis confirmed, maintenance
 * completed, still recovering, monitoring continues). */
export function RecentOutcomes({ limit = 5 }: { limit?: number }) {
  const cases = useMaintenanceCases();
  const hierarchy = useHierarchy();
  const machineNames = useMemo(() => flattenMachineNames(hierarchy.data), [hierarchy.data]);

  const outcomes = useMemo(() => {
    const sorted = (cases.data ?? [])
      .filter((c) => c.state !== "PLANNED" && c.state !== "IN_PROGRESS")
      .sort((a, b) => {
        const at = a.completed_at ?? a.started_at ?? a.created_at;
        const bt = b.completed_at ?? b.started_at ?? b.created_at;
        return new Date(bt).getTime() - new Date(at).getTime();
      });
    // One outcome per machine — its most recent — so a machine that has accumulated
    // several historical cases doesn't crowd out every other asset's story.
    const seenMachines = new Set<string>();
    const deduped: typeof sorted = [];
    for (const c of sorted) {
      if (seenMachines.has(c.machine_id)) continue;
      seenMachines.add(c.machine_id);
      deduped.push(c);
    }
    return deduped.slice(0, limit);
  }, [cases.data, limit]);

  return (
    <SectionCard title="Recent outcomes">
      {outcomes.length === 0 ? (
        <EmptyState
          title="No maintenance outcomes yet"
          description="Outcomes appear here once a maintenance case is planned, worked, or completed."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
          {outcomes.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div>
                <Link
                  href={`/maintenance/${c.id}`}
                  className="text-sm font-medium text-sky-700 hover:underline dark:text-sky-400"
                >
                  {machineNames.get(c.machine_id) ?? "Machine"}
                </Link>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {c.feedback_classification
                    ? feedbackHeadline(c.feedback_classification)
                    : `${humanize(c.state)} — ${humanize(c.recommended_action)}`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <MaintenanceStateBadge value={c.state} />
                {c.feedback_classification && <FeedbackBadge value={c.feedback_classification} />}
                <RelativeTime
                  iso={c.completed_at ?? c.started_at ?? c.created_at}
                  className="text-xs text-zinc-400 dark:text-zinc-600"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

"use client";

import Link from "next/link";
import { useMemo } from "react";

import {
  FeedbackBadge,
  IncidentStateBadge,
  MaintenanceStateBadge,
  PriorityBadge,
  SeverityBadge,
} from "@/components/badges";
import { EvidenceWhyDetails, evidenceBackingLine } from "@/components/condition-evidence";
import { RelativeTime } from "@/components/relative-time";
import { useMachine } from "@/hooks/use-asset-hierarchy";
import { useIntelligenceView } from "@/hooks/use-intelligence";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { humanize } from "@/lib/terminology";
import type { IncidentResponse } from "@/lib/api/incidents-types";

const OPEN_STATES = new Set(["OPEN", "DETECTED", "ACKNOWLEDGED", "INVESTIGATING", "ACTION_PLANNED"]);

/**
 * The Overview's centerpiece: one machine's complete, real story — condition, evidence,
 * recommended action, and how it played out — sourced entirely from the incident and its
 * linked maintenance case, never a live re-evaluation. Reading the story from the
 * incident's own persisted fields (rather than "whatever the machine's condition looks
 * like right now") keeps this honest even after recovery telemetry has moved the live
 * condition back to NORMAL_OPERATION — the incident record is what actually happened.
 */
export function PriorityAssetCard({ incident }: { incident: IncidentResponse }) {
  const machine = useMachine(incident.machine_id);
  const cases = useMaintenanceCases();
  const currentIntelligence = useIntelligenceView(incident.machine_id);

  const maintenanceCase = useMemo(
    () => (cases.data ?? []).find((c) => c.incident_id === incident.id),
    [cases.data, incident.id],
  );

  const isOpen = OPEN_STATES.has(incident.state);
  const whyBullets = (incident.evidence_refs.why ?? []).slice(0, 3);

  const recovered =
    !isOpen &&
    currentIntelligence.data?.condition.condition_type === "NORMAL_OPERATION" &&
    currentIntelligence.data.condition.severity === "INFO";

  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-100 px-6 py-5 dark:border-zinc-800">
        <div>
          <p className="text-xs font-semibold tracking-wide text-sky-600 uppercase dark:text-sky-400">
            {isOpen ? "Priority asset — needs attention" : "Flagship case"}
          </p>
          <h2 className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {machine.data?.name ?? "Loading machine…"}
          </h2>
          {machine.data && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {machine.data.asset_code} · {humanize(machine.data.machine_type)}
            </p>
          )}
        </div>
        <Link
          href={`/machines/${incident.machine_id}`}
          className="shrink-0 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700"
        >
          View full machine intelligence →
        </Link>
      </div>

      <div className="grid gap-6 px-6 py-5 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          <div>
            <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
              What is happening
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <SeverityBadge value={incident.severity} />
              <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {humanize(incident.incident_type)}
              </span>
            </div>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {evidenceBackingLine(incident)}
            </p>
            <EvidenceWhyDetails why={whyBullets} />
          </div>

          <div>
            <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
              Recommended action
            </p>
            {maintenanceCase ? (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                  {humanize(maintenanceCase.recommended_action)}
                </span>
                <PriorityBadge value={maintenanceCase.priority} />
              </div>
            ) : (
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                No maintenance case opened yet.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-zinc-100 pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6 dark:border-zinc-800">
          <div>
            <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Incident</p>
            <div className="mt-1">
              <IncidentStateBadge value={incident.state} />
            </div>
            <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">
              First detected <RelativeTime iso={incident.first_detected_at} />
            </p>
          </div>

          {maintenanceCase && (
            <div>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
                Maintenance outcome
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <MaintenanceStateBadge value={maintenanceCase.state} />
                {maintenanceCase.feedback_classification && (
                  <FeedbackBadge value={maintenanceCase.feedback_classification} />
                )}
              </div>
              <Link
                href={`/maintenance/${maintenanceCase.id}`}
                className="mt-1 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
              >
                View maintenance case →
              </Link>
            </div>
          )}

          {recovered && (
            <div>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Current status</p>
              <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-400">
                Normal operation — condition confirmed recovered since this incident.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

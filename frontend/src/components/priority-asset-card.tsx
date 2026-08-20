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

interface Stage {
  label: string;
  iso: string | null;
  href?: string;
  note?: string;
}

/**
 * Detected/Diagnosed/Decision share one real timestamp here on purpose, not by mistake —
 * this platform's evaluation pipeline computes the condition assessment and the decision
 * synchronously with incident creation (one `DecisionEngine.decide_for_machine()` call), so
 * there is no separate persisted "diagnosed at" or "decided at" moment to show honestly.
 * Reusing the same real timestamp is truthful; inventing a later one would not be.
 */
function StoryProgression({
  incident,
  maintenanceCase,
}: {
  incident: IncidentResponse;
  maintenanceCase: { id: string; created_at: string; started_at: string | null; completed_at: string | null } | undefined;
}) {
  const stages: Stage[] = [
    { label: "Detected", iso: incident.first_detected_at, href: `/incidents/${incident.id}` },
    {
      label: "Diagnosed",
      iso: incident.first_detected_at,
      href: `/machines/${incident.machine_id}`,
      note: "Same evaluation as detection",
    },
    {
      label: "Decision",
      iso: incident.first_detected_at,
      href: `/incidents/${incident.id}`,
      note: "Same evaluation as detection",
    },
    {
      label: "Maintenance",
      iso: maintenanceCase?.started_at ?? maintenanceCase?.created_at ?? null,
      href: maintenanceCase ? `/maintenance/${maintenanceCase.id}` : undefined,
    },
    {
      label: "Verified",
      iso: maintenanceCase?.completed_at ?? incident.resolved_at,
      href: maintenanceCase ? `/maintenance/${maintenanceCase.id}` : `/incidents/${incident.id}`,
    },
  ];

  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Progression</p>
      <ol className="mt-1 flex flex-wrap items-start gap-x-1 gap-y-3">
        {stages.map((stage, index) => {
          const reached = Boolean(stage.iso);
          const body = (
            <div className="flex flex-col items-center gap-1 px-1 text-center">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  reached ? "bg-sky-500" : "bg-zinc-200 dark:bg-zinc-700"
                }`}
                aria-hidden
              />
              <span
                className={`text-xs font-medium ${
                  reached
                    ? "text-zinc-900 dark:text-zinc-100"
                    : "text-zinc-400 dark:text-zinc-600"
                }`}
              >
                {stage.label}
              </span>
              {reached ? (
                <RelativeTime iso={stage.iso} className="text-[11px] text-zinc-400 dark:text-zinc-600" />
              ) : (
                <span className="text-[11px] text-zinc-300 dark:text-zinc-700">Pending</span>
              )}
            </div>
          );
          return (
            <li key={stage.label} className="flex items-center">
              {index > 0 && (
                <span
                  className={`mr-1 h-px w-4 sm:w-8 ${
                    reached ? "bg-sky-300 dark:bg-sky-800" : "bg-zinc-200 dark:bg-zinc-800"
                  }`}
                  aria-hidden
                />
              )}
              {reached && stage.href ? (
                <Link href={stage.href} className="hover:opacity-75">
                  {body}
                </Link>
              ) : (
                body
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

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
            {isOpen ? "Priority asset — needs attention" : "Most significant recent case"}
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

      <div className="border-b border-zinc-100 bg-zinc-50/60 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900/40">
        <StoryProgression incident={incident} maintenanceCase={maintenanceCase} />
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

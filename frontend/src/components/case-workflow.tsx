"use client";

import { useMemo } from "react";
import Link from "next/link";

import { IncidentStateBadge, SeverityBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { StatusPill } from "@/components/status-pill";
import { useIncident } from "@/hooks/use-incidents";
import {
  useMaintenanceCases,
  useMaintenanceActions,
  useMaintenanceFeedback,
  useMaintenanceFindings,
} from "@/hooks/use-maintenance";
import { feedbackHeadline, humanize } from "@/lib/terminology";

export type WorkflowStageKey =
  | "detected"
  | "diagnosed"
  | "decision"
  | "incident"
  | "maintenance"
  | "recovery"
  | "verified";

interface Stage {
  key: WorkflowStageKey;
  label: string;
  headline: string;
  iso: string | null;
  href?: string;
}

/**
 * The one shared "what happened to this machine, in order" visualization — Overview,
 * Machine Detail, Incident Detail, and Maintenance Detail all render this same component
 * (with a different `variant`/`currentStage`) instead of four separate hand-built
 * summaries, so a reviewer navigating between them never has to re-orient. Every stage is
 * built from real persisted incident/maintenance-case/feedback records; a stage with no
 * persisted timestamp renders as "Pending", never a guessed or fabricated one.
 */
export function CaseWorkflow({
  incidentId,
  variant = "rich",
  currentStage,
}: {
  incidentId: string;
  variant?: "compact" | "rich";
  currentStage?: WorkflowStageKey;
}) {
  const incident = useIncident(incidentId);
  const cases = useMaintenanceCases();
  const machineCase = useMemo(
    () => (cases.data ?? []).find((c) => c.incident_id === incidentId),
    [cases.data, incidentId],
  );
  const findings = useMaintenanceFindings(machineCase?.id ?? "");
  const actions = useMaintenanceActions(machineCase?.id ?? "");
  const feedback = useMaintenanceFeedback(machineCase?.id ?? "");

  if (!incident.data) return null;
  const inc = incident.data;
  const latestFinding = (findings.data ?? [])[findings.data?.length ? findings.data.length - 1 : 0];
  const latestAction = (actions.data ?? [])[actions.data?.length ? actions.data.length - 1 : 0];

  const stages: Stage[] = [
    {
      key: "detected",
      label: "Detected",
      headline: "First evidence recorded",
      iso: inc.first_detected_at,
      href: `/incidents/${incidentId}`,
    },
    {
      key: "diagnosed",
      label: "Diagnosed",
      headline: humanize(inc.incident_type),
      iso: inc.first_detected_at,
      href: `/machines/${inc.machine_id}`,
    },
    {
      key: "decision",
      label: "Decision",
      headline: machineCase
        ? `${humanize(machineCase.recommended_action)} — ${humanize(machineCase.priority)}`
        : "Awaiting a maintenance decision",
      iso: machineCase ? inc.first_detected_at : null,
      href: `/machines/${inc.machine_id}`,
    },
    {
      key: "incident",
      label: "Incident",
      headline: `${humanize(inc.severity)} severity issue created`,
      iso: inc.first_detected_at,
      href: `/incidents/${incidentId}`,
    },
    {
      key: "maintenance",
      label: "Maintenance",
      headline: machineCase
        ? (latestFinding?.observed_issue ??
          (latestAction ? humanize(latestAction.action_type) : humanize(machineCase.recommended_action)))
        : "No maintenance case opened yet",
      iso: machineCase?.started_at ?? machineCase?.created_at ?? null,
      href: machineCase ? `/maintenance/${machineCase.id}` : undefined,
    },
    {
      key: "recovery",
      label: "Recovery",
      headline: "Machine returned toward normal operation",
      iso: inc.resolved_at,
      href: `/machines/${inc.machine_id}`,
    },
    {
      key: "verified",
      label: "Verified",
      headline: feedback.data
        ? feedbackHeadline(feedback.data.classification)
        : "Awaiting technician confirmation",
      iso: machineCase?.completed_at ?? null,
      href: machineCase ? `/maintenance/${machineCase.id}` : undefined,
    },
  ];

  const dense = variant === "compact";

  return (
    <ol className={`flex flex-wrap items-start ${dense ? "gap-x-0.5 gap-y-2" : "gap-x-1 gap-y-4"}`}>
      {stages.map((stage, index) => {
        const reached = Boolean(stage.iso);
        const isCurrent = stage.key === currentStage;
        const body = (
          <div
            className={`flex flex-col items-center gap-1 px-1.5 text-center ${dense ? "w-20" : "w-28"}`}
          >
            <span
              className={`rounded-full ${dense ? "h-2 w-2" : "h-2.5 w-2.5"} ${
                isCurrent
                  ? "bg-sky-500 ring-2 ring-sky-200 dark:ring-sky-900"
                  : reached
                    ? "bg-sky-500"
                    : "bg-zinc-200 dark:bg-zinc-700"
              }`}
              aria-hidden
            />
            <span
              className={`text-[11px] font-semibold tracking-wide uppercase ${
                isCurrent
                  ? "text-sky-700 dark:text-sky-400"
                  : reached
                    ? "text-zinc-500 dark:text-zinc-400"
                    : "text-zinc-300 dark:text-zinc-700"
              }`}
            >
              {stage.label}
            </span>
            {!dense && (
              <span
                className={`text-xs leading-snug ${
                  reached ? "text-zinc-700 dark:text-zinc-300" : "text-zinc-300 dark:text-zinc-700"
                }`}
              >
                {reached ? stage.headline : "Pending"}
              </span>
            )}
            {reached && (
              <RelativeTime iso={stage.iso} className="text-[10px] text-zinc-400 dark:text-zinc-600" />
            )}
          </div>
        );
        return (
          <li key={stage.key} className="flex items-start">
            {index > 0 && (
              <span
                className={`mt-[7px] h-px ${dense ? "w-3" : "w-4 sm:w-6"} ${
                  reached ? "bg-sky-300 dark:bg-sky-800" : "bg-zinc-200 dark:bg-zinc-800"
                }`}
                aria-hidden
              />
            )}
            {reached && stage.href ? (
              <Link href={stage.href} className="rounded hover:opacity-75">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}

type CaseContextSegment = "machine" | "incident" | "maintenance";

/**
 * Compact "you are here" strip for the Machine/Incident/Maintenance pages — same
 * underlying case, reused verbatim, so a reviewer always sees the same headline/severity/
 * outcome and the same Machine → Incident → Maintenance trail regardless of which page
 * they landed on. Never renders raw IDs.
 */
export function CaseContextHeader({
  incidentId,
  active,
}: {
  incidentId: string;
  active: CaseContextSegment;
}) {
  const incident = useIncident(incidentId);
  const cases = useMaintenanceCases();
  const machineCase = useMemo(
    () => (cases.data ?? []).find((c) => c.incident_id === incidentId),
    [cases.data, incidentId],
  );
  const feedback = useMaintenanceFeedback(machineCase?.id ?? "");

  if (!incident.data) return null;
  const inc = incident.data;

  const linkClass = (segment: CaseContextSegment) =>
    `hover:underline ${
      active === segment
        ? "font-semibold text-sky-700 dark:text-sky-400"
        : "text-zinc-500 dark:text-zinc-400"
    }`;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-2.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div>
        <p className="text-[10px] font-semibold tracking-wide text-zinc-400 uppercase dark:text-zinc-600">
          Recent significant case
        </p>
        <p className="font-medium text-zinc-900 dark:text-zinc-100">{humanize(inc.incident_type)}</p>
      </div>
      <SeverityBadge value={inc.severity} />
      <IncidentStateBadge value={inc.state} />
      {feedback.data && (
        <StatusPill tone="ok">{feedbackHeadline(feedback.data.classification)}</StatusPill>
      )}
      <nav aria-label="Case navigation" className="ml-auto flex items-center gap-1.5 text-xs">
        <Link href={`/machines/${inc.machine_id}`} className={linkClass("machine")}>
          Machine
        </Link>
        <span className="text-zinc-300 dark:text-zinc-700" aria-hidden>
          →
        </span>
        <Link href={`/incidents/${incidentId}`} className={linkClass("incident")}>
          Incident
        </Link>
        {machineCase && (
          <>
            <span className="text-zinc-300 dark:text-zinc-700" aria-hidden>
              →
            </span>
            <Link href={`/maintenance/${machineCase.id}`} className={linkClass("maintenance")}>
              Maintenance
            </Link>
          </>
        )}
      </nav>
    </div>
  );
}

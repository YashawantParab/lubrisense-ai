"use client";

import { use, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { CaseContextHeader, CaseWorkflow } from "@/components/case-workflow";
import { DataState } from "@/components/data-state";
import {
  FeedbackBadge,
  IncidentStateBadge,
  MaintenanceStateBadge,
  PriorityBadge,
  SeverityBadge,
} from "@/components/badges";
import { EvidenceWhyDetails, evidenceBackingLine } from "@/components/condition-evidence";
import { FindingCard } from "@/components/finding-card";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy, useMachine } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions } from "@/hooks/use-intelligence";
import {
  useAcknowledgeIncident,
  useCloseIncident,
  useIncident,
  useIncidentTimeline,
  useResolveIncident,
  useStartInvestigation,
} from "@/hooks/use-incidents";
import { useCreateCase, useMaintenanceCases } from "@/hooks/use-maintenance";
import { useFleetLatestML, useModels } from "@/hooks/use-ml";
import { useFindings } from "@/hooks/use-rules";
import { findSiteForMachine } from "@/lib/asset-context";
import { useAuth } from "@/lib/auth/context";
import { buildAssetBreadcrumb } from "@/lib/breadcrumbs";
import { stringMeta } from "@/lib/equipment";
import {
  dataTrustFusionStrength,
  FUSION_STRENGTH_LABEL,
  FUSION_STRENGTH_TONE,
  machineMlFusionStrength,
  ruleEvidenceStrength,
  stateEstimateStrength,
} from "@/lib/evidence-fusion";
import { humanize } from "@/lib/terminology";

const VALID_NEXT: Record<string, string> = {
  OPEN: "acknowledge",
  DETECTED: "acknowledge",
  ACKNOWLEDGED: "start-investigation",
};

const EVENT_DOT_CLASSES: Record<string, string> = {
  INCIDENT_CREATED: "bg-amber-500",
  SEVERITY_CHANGED: "bg-amber-500",
  PRIORITY_CHANGED: "bg-amber-500",
  EVIDENCE_ADDED: "bg-sky-500",
  ACKNOWLEDGED: "bg-sky-500",
  INVESTIGATION_STARTED: "bg-sky-500",
  ACTION_PLANNED: "bg-sky-500",
  RESOLVED: "bg-emerald-500",
  CLOSED: "bg-zinc-400 dark:bg-zinc-600",
  REOPENED: "bg-amber-500",
};

export default function IncidentDetailPage({
  params,
}: {
  params: Promise<{ incidentId: string }>;
}) {
  const { incidentId } = use(params);
  const router = useRouter();
  const { can } = useAuth();
  const incident = useIncident(incidentId);
  const timeline = useIncidentTimeline(incidentId);
  const cases = useMaintenanceCases();
  const acknowledge = useAcknowledgeIncident(incidentId);
  const startInvestigation = useStartInvestigation(incidentId);
  const resolve = useResolveIncident(incidentId);
  const close = useCloseIncident(incidentId);
  const createCase = useCreateCase();
  const fullHierarchy = useHierarchy();
  const machine = useMachine(incident.data?.machine_id ?? "");
  const siteForMachine = useMemo(
    () => findSiteForMachine(fullHierarchy.data, incident.data?.machine_id),
    [fullHierarchy.data, incident.data?.machine_id],
  );
  const machineArea = machine.data ? stringMeta(machine.data.metadata, "area") : null;

  usePageTitle(incident.data ? incident.data.title : "Incident");

  const state = incident.data?.state;
  const nextAction = state ? VALID_NEXT[state] : undefined;
  const canManage = can("INCIDENT_MANAGE");
  const whyBullets = incident.data?.evidence_refs.why ?? [];
  const linkedCase = useMemo(
    () => (cases.data ?? []).find((c) => c.incident_id === incidentId),
    [cases.data, incidentId],
  );

  // `getMachineFindings` only returns each finding's *current* state, which drops the
  // findings behind a since-resolved incident — fetch by machine with no state filter so
  // history is never silently hidden once the underlying issue recovers.
  const machineFindings = useFindings(
    { machine_id: incident.data?.machine_id, limit: 200 },
    { enabled: Boolean(incident.data?.machine_id) },
  );
  const incidentFindings = useMemo(() => {
    const ids = new Set(incident.data?.rule_finding_ids ?? []);
    return (machineFindings.data ?? []).filter((f) => ids.has(f.id));
  }, [machineFindings.data, incident.data?.rule_finding_ids]);

  // Evidence Fusion sources for the sidebar (ML productization pass, item 17) — reuses the
  // machine's *current* condition/ML state, the same real evidence the /ml page and
  // machine detail page already read, never a value invented for this page.
  const fleetML = useFleetLatestML();
  const conditions = useFleetLatestConditions();
  const models = useModels();
  const modelStatusById = useMemo(
    () => new Map((models.data ?? []).map((m) => [m.model_id, m.status])),
    [models.data],
  );
  const machineCondition = useMemo(
    () => (conditions.data ?? []).find((c) => c.machine_id === incident.data?.machine_id),
    [conditions.data, incident.data?.machine_id],
  );
  const machineMLResults = useMemo(
    () => (fleetML.data ?? []).filter((r) => r.machine_id === incident.data?.machine_id),
    [fleetML.data, incident.data?.machine_id],
  );
  const evidenceSources = useMemo(() => {
    if (!machineCondition) return null;
    return [
      { label: "Physical / rule evidence", strength: ruleEvidenceStrength(machineCondition) },
      { label: "State estimation", strength: stateEstimateStrength(machineCondition) },
      {
        label: "ML evidence",
        strength: machineMlFusionStrength(machineMLResults, machineCondition, modelStatusById),
      },
      {
        label: "Data quality",
        strength: dataTrustFusionStrength(machineCondition.evidence_summary.data_trustworthiness),
      },
    ];
  }, [machineCondition, machineMLResults, modelStatusById]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <DataState
        isPending={incident.isPending}
        isError={incident.isError}
        error={incident.error}
        loadingLabel="Loading incident…"
      >
        {incident.data && (
          <>
            <PageHeader
              breadcrumbs={buildAssetBreadcrumb({
                site: siteForMachine,
                area: machineArea,
                trailing: [
                  {
                    label: machine.data?.name ?? "Machine",
                    href: `/machines/${incident.data.machine_id}`,
                  },
                  { label: incident.data.title },
                ],
              })}
              title={incident.data.title}
              description={evidenceBackingLine(incident.data)}
              actions={
                <>
                  <IncidentStateBadge value={incident.data.state} />
                  <Link
                    href={`/assistant?machineId=${incident.data.machine_id}&incidentId=${incidentId}`}
                    className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700"
                  >
                    Ask Assistant
                  </Link>
                </>
              }
            />

            <CaseContextHeader incidentId={incidentId} active="incident" />

            <SectionCard title="Case journey">
              <CaseWorkflow incidentId={incidentId} variant="rich" currentStage="incident" />
            </SectionCard>

            <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
              <div className="flex flex-col gap-8">
                {(incidentFindings.length > 0 || whyBullets.length > 0) && (
                  <SectionCard title="What happened, and why">
                    <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                      {evidenceBackingLine(incident.data)}
                    </p>
                    {incidentFindings.length > 0 ? (
                      <div className="flex flex-col gap-2">
                        {incidentFindings.map((finding) => (
                          <FindingCard key={finding.id} finding={finding} />
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        This assessment is based on sensor-trend and model evidence rather than
                        individual rule findings — see technical evidence below.
                      </p>
                    )}
                    <EvidenceWhyDetails why={whyBullets} />
                  </SectionCard>
                )}

                <SectionCard title="Timeline">
                  <DataState
                    isPending={timeline.isPending}
                    isError={timeline.isError}
                    error={timeline.error}
                    loadingLabel="Loading timeline…"
                  >
                    <ol className="space-y-4">
                      {(timeline.data ?? []).map((event) => (
                        <li key={event.id} className="flex gap-3 text-sm">
                          <span
                            className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                              EVENT_DOT_CLASSES[event.event_type] ?? "bg-zinc-400 dark:bg-zinc-600"
                            }`}
                            aria-hidden
                          />
                          <div>
                            <p className="font-medium text-zinc-900 dark:text-zinc-100">
                              {humanize(event.event_type)}
                            </p>
                            <p className="text-xs text-zinc-500 dark:text-zinc-400">
                              {event.summary}
                            </p>
                            <p className="text-xs text-zinc-400 dark:text-zinc-500">
                              <RelativeTime iso={event.recorded_at} />
                            </p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </DataState>
                </SectionCard>
              </div>

              <div className="flex flex-col gap-6">
                <dl className="grid grid-cols-2 gap-3 text-xs text-zinc-500 dark:text-zinc-400">
                  <div>
                    <dt>Condition</dt>
                    <dd className="mt-0.5 font-medium text-zinc-900 dark:text-zinc-100">
                      {humanize(incident.data.incident_type)}
                    </dd>
                  </div>
                  <div>
                    <dt>Severity</dt>
                    <dd className="mt-0.5">
                      <SeverityBadge value={incident.data.severity} />
                    </dd>
                  </div>
                  <div>
                    <dt>Priority</dt>
                    <dd className="mt-0.5">
                      <PriorityBadge value={incident.data.priority} />
                    </dd>
                  </div>
                  <div>
                    <dt>First detected</dt>
                    <dd className="mt-0.5 text-zinc-900 dark:text-zinc-100">
                      <RelativeTime iso={incident.data.first_detected_at} />
                    </dd>
                  </div>
                  <div className="col-span-2">
                    <dt>Machine</dt>
                    <dd className="mt-0.5">
                      <a
                        href={`/machines/${incident.data.machine_id}`}
                        className="text-sky-600 hover:underline dark:text-sky-400"
                      >
                        View machine
                      </a>
                    </dd>
                  </div>
                </dl>

                {evidenceSources && (
                  <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800/70">
                    <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                      Evidence sources
                    </p>
                    {(state === "RESOLVED" || state === "CLOSED") && (
                      <p className="mb-2 text-xs text-zinc-400 italic dark:text-zinc-600">
                        Reflects this machine&rsquo;s current state, gathered after this incident
                        was resolved — not necessarily the evidence available at the time it was
                        diagnosed.
                      </p>
                    )}
                    <ul className="flex flex-col gap-1.5">
                      {evidenceSources.map((source) => (
                        <li
                          key={source.label}
                          className="flex items-center justify-between gap-2 text-sm"
                        >
                          <span className="text-zinc-600 dark:text-zinc-400">{source.label}</span>
                          <StatusPill tone={FUSION_STRENGTH_TONE[source.strength]}>
                            {FUSION_STRENGTH_LABEL[source.strength]}
                          </StatusPill>
                        </li>
                      ))}
                    </ul>
                    <Link
                      href={`/ml?machineId=${incident.data.machine_id}`}
                      className="mt-2 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
                    >
                      View full ML analysis →
                    </Link>
                  </div>
                )}

                {canManage ? (
                  <div className="flex flex-wrap gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800/70">
                    {nextAction === "acknowledge" && (
                      <button
                        type="button"
                        onClick={() => acknowledge.mutate()}
                        disabled={acknowledge.isPending}
                        className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                      >
                        {acknowledge.isPending ? "Acknowledging…" : "Acknowledge"}
                      </button>
                    )}
                    {nextAction === "start-investigation" && (
                      <button
                        type="button"
                        onClick={() => startInvestigation.mutate()}
                        disabled={startInvestigation.isPending}
                        className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                      >
                        {startInvestigation.isPending ? "Starting…" : "Start investigation"}
                      </button>
                    )}
                    {(state === "INVESTIGATING" || state === "ACTION_PLANNED") && (
                      <button
                        type="button"
                        onClick={() =>
                          createCase.mutate(incidentId, {
                            onSuccess: (createdCase) =>
                              router.push(`/maintenance/${createdCase.id}`),
                          })
                        }
                        disabled={createCase.isPending}
                        className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {createCase.isPending ? "Opening…" : "Open maintenance case"}
                      </button>
                    )}
                    {state !== "RESOLVED" && state !== "CLOSED" && (
                      <button
                        type="button"
                        onClick={() => {
                          if (
                            window.confirm(
                              "Resolve this incident? This marks the underlying problem as addressed.",
                            )
                          )
                            resolve.mutate("Resolved from the incident detail page.");
                        }}
                        disabled={resolve.isPending}
                        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      >
                        {resolve.isPending ? "Resolving…" : "Resolve"}
                      </button>
                    )}
                    {state === "RESOLVED" && (
                      <button
                        type="button"
                        onClick={() => {
                          if (
                            window.confirm(
                              "Close this incident? This is the final step in its lifecycle.",
                            )
                          )
                            close.mutate();
                        }}
                        disabled={close.isPending}
                        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      >
                        {close.isPending ? "Closing…" : "Close"}
                      </button>
                    )}
                  </div>
                ) : (
                  <p className="border-t border-zinc-100 pt-4 text-xs text-zinc-400 dark:border-zinc-800/70 dark:text-zinc-600">
                    Your current demo role cannot manage incident lifecycle transitions.
                  </p>
                )}

                <SectionCard title="Maintenance response">
                  {linkedCase ? (
                    <div className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <Link
                          href={`/maintenance/${linkedCase.id}`}
                          className="text-sm font-medium text-sky-700 hover:underline dark:text-sky-400"
                        >
                          {humanize(linkedCase.recommended_action)}
                        </Link>
                        <MaintenanceStateBadge value={linkedCase.state} />
                      </div>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        Priority: {humanize(linkedCase.priority)} · Window:{" "}
                        {humanize(linkedCase.recommended_window)}
                      </p>
                      {linkedCase.feedback_classification && (
                        <div className="flex items-center gap-2 border-t border-zinc-100 pt-2 dark:border-zinc-800">
                          <span className="text-xs text-zinc-500 dark:text-zinc-400">
                            Technician outcome:
                          </span>
                          <FeedbackBadge value={linkedCase.feedback_classification} />
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      No maintenance case has been opened for this incident yet.
                    </p>
                  )}
                </SectionCard>
              </div>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}

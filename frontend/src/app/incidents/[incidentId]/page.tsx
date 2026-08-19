"use client";

import { use } from "react";
import { useRouter } from "next/navigation";

import { DataState } from "@/components/data-state";
import { IncidentStateBadge, PriorityBadge, SeverityBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { usePageTitle } from "@/hooks/use-page-title";
import {
  useAcknowledgeIncident,
  useCloseIncident,
  useIncident,
  useIncidentTimeline,
  useResolveIncident,
  useStartInvestigation,
} from "@/hooks/use-incidents";
import { useCreateCase } from "@/hooks/use-maintenance";
import { useAuth } from "@/lib/auth/context";
import { humanize } from "@/lib/terminology";

const VALID_NEXT: Record<string, string> = {
  OPEN: "acknowledge",
  DETECTED: "acknowledge",
  ACKNOWLEDGED: "start-investigation",
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
  const acknowledge = useAcknowledgeIncident(incidentId);
  const startInvestigation = useStartInvestigation(incidentId);
  const resolve = useResolveIncident(incidentId);
  const close = useCloseIncident(incidentId);
  const createCase = useCreateCase();

  usePageTitle(incident.data ? incident.data.title : "Incident");

  const state = incident.data?.state;
  const nextAction = state ? VALID_NEXT[state] : undefined;
  const canManage = can("INCIDENT_MANAGE");

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10">
      <DataState
        isPending={incident.isPending}
        isError={incident.isError}
        error={incident.error}
        loadingLabel="Loading incident…"
      >
        {incident.data && (
          <>
            <PageHeader
              breadcrumbs={[{ label: "Incidents", href: "/incidents" }, { label: incident.data.title }]}
              title={incident.data.title}
              description={incident.data.summary}
              actions={<IncidentStateBadge value={incident.data.state} />}
            />

            <SectionCard>
              <dl className="grid grid-cols-2 gap-3 text-xs text-zinc-500 dark:text-zinc-400 sm:grid-cols-4">
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
                <div>
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

              {canManage ? (
                <div className="mt-4 flex flex-wrap gap-2">
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
                          onSuccess: (createdCase) => router.push(`/maintenance/${createdCase.id}`),
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
                        if (window.confirm("Resolve this incident? This marks the underlying problem as addressed."))
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
                        if (window.confirm("Close this incident? This is the final step in its lifecycle."))
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
                <p className="mt-4 text-xs text-zinc-400 dark:text-zinc-600">
                  Your current demo role cannot manage incident lifecycle transitions.
                </p>
              )}
            </SectionCard>

            <SectionCard title="Timeline">
              <DataState
                isPending={timeline.isPending}
                isError={timeline.isError}
                error={timeline.error}
                loadingLabel="Loading timeline…"
              >
                <ol className="space-y-2 border-l border-zinc-200 pl-4 dark:border-zinc-800">
                  {(timeline.data ?? []).map((event) => (
                    <li key={event.id} className="text-sm">
                      <p className="font-medium text-zinc-900 dark:text-zinc-100">
                        {humanize(event.event_type)}
                      </p>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">{event.summary}</p>
                      <p className="text-xs text-zinc-400 dark:text-zinc-500">
                        <RelativeTime iso={event.recorded_at} />
                      </p>
                    </li>
                  ))}
                </ol>
              </DataState>
            </SectionCard>
          </>
        )}
      </DataState>
    </div>
  );
}

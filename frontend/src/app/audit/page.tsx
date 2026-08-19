"use client";

import { useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useAuditEvents } from "@/hooks/use-audit";
import { actorTone, humanize, shortId } from "@/lib/terminology";

export default function AuditPage() {
  usePageTitle("Audit");
  const [entityType, setEntityType] = useState("");
  const events = useAuditEvents({ entityType: entityType || undefined });

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Audit Trail"
        description="Who did what, when, to which entity, and why — append-only, HUMAN/SYSTEM/AGENT actors distinguished."
        actions={
          <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
            Entity type
            <select
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
              className="min-w-44 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="">All</option>
              <option value="incident">Incident</option>
              <option value="maintenance_case">Maintenance case</option>
              <option value="knowledge_document">Knowledge document</option>
              <option value="agent_session">Agent session</option>
            </select>
          </label>
        }
      />

      <DataState isPending={events.isPending} isError={events.isError} error={events.error}>
        {events.data &&
          (events.data.items.length === 0 ? (
            <EmptyState
              title="No audit events yet"
              description="Actions like acknowledging an incident or approving a knowledge document will appear here."
            />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                  <tr>
                    <th className="px-3 py-2">Actor</th>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-3 py-2">Entity</th>
                    <th className="px-3 py-2">Occurred</th>
                    <th className="px-3 py-2">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {events.data.items.map((event) => (
                    <tr key={event.id}>
                      <td className="px-3 py-2">
                        <StatusPill tone={actorTone(event.actor_type)}>
                          {event.actor_type}
                        </StatusPill>
                        <span className="ml-2 text-zinc-600 dark:text-zinc-400">
                          {event.actor_id}
                          {event.role ? ` (${humanize(event.role)})` : ""}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-zinc-900 dark:text-zinc-100">
                        {humanize(event.action)}
                      </td>
                      <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                        {humanize(event.entity_type)}/{shortId(event.entity_id)}
                      </td>
                      <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                        <RelativeTime iso={event.occurred_at} />
                      </td>
                      <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                        {event.reason ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </DataState>
    </div>
  );
}

"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { HumanReviewBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useSendChat } from "@/hooks/use-agent";
import { useIncidents } from "@/hooks/use-incidents";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { humanize } from "@/lib/terminology";
import type { ChatResponse } from "@/lib/api/agent-types";

interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

function AssistantPageInner() {
  usePageTitle("Assistant");
  const searchParams = useSearchParams();
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState(searchParams.get("machineId") ?? "");
  const incidents = useIncidents({ machineId: machineId || undefined });
  const [incidentId, setIncidentId] = useState(searchParams.get("incidentId") ?? "");
  const [caseId, setCaseId] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [expandedToolCalls, setExpandedToolCalls] = useState<number | null>(null);
  const chat = useSendChat();
  const cases = useMaintenanceCases();
  const casesForIncident = useMemo(
    () => (cases.data ?? []).filter((c) => c.incident_id === incidentId),
    [cases.data, incidentId],
  );

  const machines = useMemo(
    () =>
      hierarchy.data?.customers.flatMap((customer) =>
        customer.sites.flatMap((site) =>
          site.plants.flatMap((plant) => plant.production_lines.flatMap((line) => line.machines)),
        ),
      ) ?? [],
    [hierarchy.data],
  );
  const contextMachine = machines.find((m) => m.id === machineId);

  const handleSend = () => {
    if (!message) return;
    const userMessage = message;
    setTurns((prev) => [...prev, { role: "user", content: userMessage }]);
    setMessage("");
    chat.mutate(
      {
        message: userMessage,
        session_id: sessionId,
        machine_id: machineId || undefined,
        incident_id: incidentId || undefined,
        maintenance_case_id: caseId || undefined,
      },
      {
        onSuccess: (response) => {
          setSessionId(response.session_id);
          setTurns((prev) => [
            ...prev,
            { role: "assistant", content: response.answer, response },
          ]);
        },
      },
    );
  };

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Assistant"
        description="Explains persisted intelligence, retrieves approved knowledge, and prepares draft artifacts — it never diagnoses independently, controls machinery, or acts without human review."
        actions={
          <Link href="/knowledge" className="text-xs text-sky-600 hover:underline dark:text-sky-400">
            Browse the knowledge base →
          </Link>
        }
      />

      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
        <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Machine context
          <select
            value={machineId}
            onChange={(e) => {
              setMachineId(e.target.value);
              setIncidentId("");
            }}
            className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">None</option>
            {machines.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name} · {m.asset_code}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Incident context
          <select
            value={incidentId}
            onChange={(e) => {
              setIncidentId(e.target.value);
              setCaseId("");
            }}
            disabled={!machineId}
            className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">None</option>
            {(incidents.data ?? []).map((i) => (
              <option key={i.id} value={i.id}>
                {i.title}
              </option>
            ))}
          </select>
        </label>
        {casesForIncident.length > 0 && (
          <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
            Maintenance case context
            <select
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="">None</option>
              {casesForIncident.map((c) => (
                <option key={c.id} value={c.id}>
                  {humanize(c.recommended_action)}
                </option>
              ))}
            </select>
          </label>
        )}
        {contextMachine && (
          <span className="ml-auto text-xs text-zinc-500 dark:text-zinc-400">
            Asking about <span className="font-medium text-zinc-700 dark:text-zinc-300">{contextMachine.name}</span>
          </span>
        )}
      </div>

      <div className="flex flex-col gap-4">
        {turns.length === 0 && (
          <p className="py-6 text-center text-sm text-zinc-400 dark:text-zinc-600">
            Select a machine (and incident, if one is open) above, then ask what is
            happening and what to do about it.
          </p>
        )}
        {turns.map((turn, index) => (
          <div
            key={index}
            className={
              turn.role === "user"
                ? "self-end rounded-lg bg-sky-600 px-4 py-2 text-sm text-white"
                : "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            }
          >
            <p className="whitespace-pre-line text-sm">{turn.content}</p>
            {turn.response && (
              <div className="mt-3 space-y-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <div className="flex flex-wrap items-center gap-2">
                  {turn.response.human_review_required && <HumanReviewBadge />}
                  {turn.response.draft_artifacts.length > 0 && (
                    <StatusPill tone="neutral">
                      {turn.response.draft_artifacts.length} draft artifact(s) — not
                      executed
                    </StatusPill>
                  )}
                </div>

                {turn.response.draft_artifacts.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2 dark:border-amber-900/50 dark:bg-amber-950/30">
                    <h3 className="text-xs font-semibold text-amber-800 dark:text-amber-400">
                      Draft artifacts (require human review before use)
                    </h3>
                    <ul className="mt-1 space-y-0.5 text-xs text-amber-700 dark:text-amber-400">
                      {turn.response.draft_artifacts.map((a, i) => (
                        <li key={i}>{humanize(a.kind)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {turn.response.citations.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                      Cited sources
                    </h3>
                    <ul className="mt-1 space-y-0.5 text-xs text-zinc-600 dark:text-zinc-400">
                      {turn.response.citations.map((c, i) => (
                        <li key={i}>
                          {c.document_title} v{c.document_version} — {c.section}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {turn.response.limitations.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">
                      Limitations
                    </h3>
                    <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-zinc-600 dark:text-zinc-400">
                      {turn.response.limitations.map((l, i) => (
                        <li key={i}>{l}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {turn.response.tool_calls.length > 0 && (
                  <div>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedToolCalls(expandedToolCalls === index ? null : index)
                      }
                      className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                    >
                      {expandedToolCalls === index ? "Hide" : "Show"}{" "}
                      {turn.response.tool_calls.length} evidence lookup(s)
                    </button>
                    {expandedToolCalls === index && (
                      <ul className="mt-1 space-y-0.5 text-xs text-zinc-600 dark:text-zinc-400">
                        {turn.response.tool_calls.map((t, i) => (
                          <li key={i}>
                            {humanize(t.tool_name)} — {humanize(t.status)}: {t.summary}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {chat.isPending && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Thinking…</p>
        )}
        {chat.isError && (
          <p className="text-sm text-red-600 dark:text-red-400">
            {chat.error instanceof Error ? chat.error.message : "The assistant is temporarily unavailable."}
          </p>
        )}
      </div>

      <div className="flex gap-2">
        <input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSend();
          }}
          placeholder="What is happening and what should I inspect?"
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          type="button"
          disabled={!message || chat.isPending}
          onClick={handleSend}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}

export default function AssistantPage() {
  return (
    <Suspense>
      <AssistantPageInner />
    </Suspense>
  );
}

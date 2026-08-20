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

/**
 * Human category for each allowlisted backend tool (`app.agent.tools.tool_functions`) —
 * the assistant never shows a raw tool/function name (e.g. `get_current_condition`) to a
 * reviewer; it shows what kind of evidence that call actually grounded the answer in.
 */
const TOOL_LABELS: Record<string, string> = {
  get_asset_context: "Machine identity",
  get_current_condition: "Condition assessment",
  get_current_decision: "Decision Intelligence",
  get_current_prognostic: "Forecast",
  get_incident: "Incident record",
  get_incident_timeline: "Incident timeline",
  get_maintenance_case: "Maintenance record",
  get_telemetry_summary: "Sensor coverage",
  search_approved_documentation: "Approved knowledge",
  search_similar_service_cases: "Maintenance history",
  generate_checklist_draft: "Inspection checklist (draft)",
  draft_work_order: "Work order (draft)",
};

function toolLabel(toolName: string): string {
  return TOOL_LABELS[toolName] ?? humanize(toolName);
}

function sourceCount(response: ChatResponse): number {
  const toolCategoryCount = new Set(
    response.tool_calls.filter((t) => t.status === "OK").map((t) => t.tool_name),
  ).size;
  return toolCategoryCount + response.citations.length;
}

type AssistantContext = "none" | "machine" | "incident" | "case";

const STARTER_PROMPTS: Record<AssistantContext, string[]> = {
  none: [],
  machine: [
    "What is this machine's current condition?",
    "What evidence supports that assessment?",
    "What should maintenance do next?",
  ],
  incident: [
    "Why was this incident created?",
    "What evidence supports this diagnosis?",
    "What is the recommended action and why?",
  ],
  case: [
    "What did the technician find?",
    "Was the diagnosis confirmed?",
    "Summarize this case for a manager",
  ],
};

function AssistantPageInner() {
  usePageTitle("Assistant");
  const searchParams = useSearchParams();
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState(searchParams.get("machineId") ?? "");
  const incidents = useIncidents({ machineId: machineId || undefined });
  const [incidentId, setIncidentId] = useState(searchParams.get("incidentId") ?? "");
  const [caseId, setCaseId] = useState(searchParams.get("caseId") ?? "");
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
  const contextIncident = (incidents.data ?? []).find((i) => i.id === incidentId);

  const assistantContext: AssistantContext = caseId
    ? "case"
    : incidentId
      ? "incident"
      : machineId
        ? "machine"
        : "none";
  const starterPrompts = STARTER_PROMPTS[assistantContext];

  const sendMessage = (text: string) => {
    if (!text) return;
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setMessage("");
    chat.mutate(
      {
        message: text,
        session_id: sessionId,
        machine_id: machineId || undefined,
        incident_id: incidentId || undefined,
        maintenance_case_id: caseId || undefined,
      },
      {
        onSuccess: (response) => {
          setSessionId(response.session_id);
          setTurns((prev) => [...prev, { role: "assistant", content: response.answer, response }]);
        },
      },
    );
  };
  const handleSend = () => sendMessage(message);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Assistant"
        description="Explains persisted intelligence, retrieves approved knowledge, and prepares draft artifacts — it never diagnoses independently, controls machinery, or acts without human review."
        actions={
          <Link
            href="/knowledge"
            className="text-xs text-sky-600 hover:underline dark:text-sky-400"
          >
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
            Asking about{" "}
            <span className="font-medium text-zinc-700 dark:text-zinc-300">
              {contextMachine.name}
            </span>
            {contextIncident && <> · {contextIncident.title}</>}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-4">
        {turns.length === 0 &&
          (assistantContext === "none" ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-zinc-300 py-10 text-center dark:border-zinc-700">
              <p className="text-base font-medium text-zinc-700 dark:text-zinc-300">
                Select a machine to get started
              </p>
              <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">
                The assistant explains one machine&rsquo;s persisted condition, decision, and
                maintenance history at a time — it doesn&rsquo;t reason across the fleet. Pick a
                machine above, or jump in from a machine, incident, or maintenance page with
                &ldquo;Ask Assistant&rdquo;.
              </p>
              <div className="mt-1 flex gap-3 text-xs">
                <Link href="/fleet" className="text-sky-600 hover:underline dark:text-sky-400">
                  Browse fleet →
                </Link>
                <Link href="/knowledge" className="text-sky-600 hover:underline dark:text-sky-400">
                  Browse knowledge base →
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-zinc-300 py-10 text-center dark:border-zinc-700">
              <p className="text-base font-medium text-zinc-700 dark:text-zinc-300">
                Ask about {contextMachine?.name ?? "this machine"}
              </p>
              <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">
                Answers are grounded in this machine&rsquo;s persisted condition, decision, and
                maintenance records — never a fresh diagnosis of its own.
              </p>
              <div className="mt-1 flex flex-wrap justify-center gap-2">
                {starterPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => sendMessage(prompt)}
                    className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 hover:bg-sky-100 dark:border-sky-900/50 dark:bg-sky-950/30 dark:text-sky-400 dark:hover:bg-sky-950/60"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ))}
        {turns.map((turn, index) => (
          <div
            key={index}
            className={
              turn.role === "user"
                ? "self-end rounded-lg bg-sky-600 px-4 py-2 text-sm text-white"
                : "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            }
          >
            {turn.role === "user" || !turn.response || turn.response.sections.length === 0 ? (
              <p className="whitespace-pre-line text-sm">{turn.content}</p>
            ) : (
              <div className="flex flex-col gap-3">
                {turn.response.sections.map((section) => (
                  <div key={section.key}>
                    <p className="text-[11px] font-semibold tracking-wide text-zinc-400 uppercase dark:text-zinc-500">
                      {section.label}
                    </p>
                    <p className="mt-0.5 text-sm leading-relaxed text-zinc-800 dark:text-zinc-200">
                      {section.text}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {turn.response && (
              <div className="mt-3 flex flex-col gap-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <div className="flex flex-wrap items-center gap-2">
                  {turn.response.human_review_required && <HumanReviewBadge />}
                  {turn.response.draft_artifacts.length > 0 && (
                    <StatusPill tone="neutral">
                      {turn.response.draft_artifacts.length} draft artifact(s) — not executed
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

                {/* Contextual navigation — the assistant is never a dead end. */}
                <div className="flex flex-wrap gap-3 text-xs">
                  {machineId && (
                    <Link
                      href={`/machines/${machineId}`}
                      className="text-sky-600 hover:underline dark:text-sky-400"
                    >
                      View machine evidence →
                    </Link>
                  )}
                  {incidentId && (
                    <Link
                      href={`/incidents/${incidentId}`}
                      className="text-sky-600 hover:underline dark:text-sky-400"
                    >
                      View incident →
                    </Link>
                  )}
                  {caseId && (
                    <Link
                      href={`/maintenance/${caseId}`}
                      className="text-sky-600 hover:underline dark:text-sky-400"
                    >
                      View maintenance outcome →
                    </Link>
                  )}
                </div>

                {(turn.response.tool_calls.length > 0 || turn.response.citations.length > 0) && (
                  <div>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedToolCalls(expandedToolCalls === index ? null : index)
                      }
                      className="text-xs font-medium text-sky-600 hover:underline dark:text-sky-400"
                    >
                      {expandedToolCalls === index ? "Hide" : "Show"} sources and evidence (
                      {sourceCount(turn.response)})
                    </button>
                    {expandedToolCalls === index && (
                      <div className="mt-2 flex flex-col gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                        {Array.from(
                          new Set(
                            turn.response.tool_calls
                              .filter((t) => t.status === "OK")
                              .map((t) => toolLabel(t.tool_name)),
                          ),
                        ).map((label) => (
                          <p key={label}>{label}</p>
                        ))}
                        {turn.response.citations.map((c, i) => (
                          <p key={i}>
                            Approved knowledge — {c.document_title} v{c.document_version} —{" "}
                            {c.section}
                          </p>
                        ))}
                        <details className="mt-1">
                          <summary className="cursor-pointer text-sky-600 select-none dark:text-sky-400">
                            Technical detail
                          </summary>
                          <ul className="mt-1 space-y-0.5">
                            {turn.response.tool_calls.map((t, i) => (
                              <li key={i}>
                                {toolLabel(t.tool_name)} — {humanize(t.status)}: {t.summary}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {chat.isPending && <p className="text-sm text-zinc-500 dark:text-zinc-400">Thinking…</p>}
        {chat.isError && (
          <p className="text-sm text-red-600 dark:text-red-400">
            {chat.error instanceof Error
              ? chat.error.message
              : "The assistant is temporarily unavailable."}
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

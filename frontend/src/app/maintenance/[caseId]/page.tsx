"use client";

import { use, useState } from "react";
import Link from "next/link";

import { DataState } from "@/components/data-state";
import { FeedbackBadge, HumanReviewBadge, MaintenanceStateBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { useMachine } from "@/hooks/use-asset-hierarchy";
import { usePageTitle } from "@/hooks/use-page-title";
import {
  useCompleteCase,
  useCreateCmmsDraft,
  useMaintenanceActions,
  useMaintenanceCase,
  useMaintenanceFeedback,
  useMaintenanceFindings,
  usePlanCase,
  useRecordAction,
  useRecordFinding,
  useStartCase,
} from "@/hooks/use-maintenance";
import { useAuth } from "@/lib/auth/context";
import { humanize, type Tone } from "@/lib/terminology";

function findingResultTone(result: string): Tone {
  if (result === "CONFIRMED") return "ok";
  if (result === "NOT_CONFIRMED") return "neutral";
  if (result === "PARTIALLY_CONFIRMED") return "warn";
  if (result === "DIFFERENT_ISSUE_FOUND") return "warn";
  return "neutral";
}

const FINDING_RESULTS = [
  "CONFIRMED",
  "NOT_CONFIRMED",
  "PARTIALLY_CONFIRMED",
  "DIFFERENT_ISSUE_FOUND",
  "UNABLE_TO_VERIFY",
];
const ACTION_TYPES = [
  "INSPECTED",
  "CLEANED",
  "REFILLED",
  "COMPONENT_REPLACED",
  "ADJUSTMENT_RECOMMENDED",
  "NO_ACTION_REQUIRED",
  "ESCALATED",
];
const FEEDBACK_CLASSIFICATIONS = [
  "TRUE_POSITIVE",
  "FALSE_POSITIVE",
  "MISSED_FAILURE",
  "INCONCLUSIVE",
];

export default function MaintenanceCaseDetailPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = use(params);
  const { can } = useAuth();
  const caseQuery = useMaintenanceCase(caseId);
  const machine = useMachine(caseQuery.data?.machine_id ?? "");
  const findings = useMaintenanceFindings(caseId);
  const actions = useMaintenanceActions(caseId);
  const feedback = useMaintenanceFeedback(caseId);

  const plan = usePlanCase(caseId);
  const start = useStartCase(caseId);
  const recordFinding = useRecordFinding(caseId);
  const recordAction = useRecordAction(caseId);
  const complete = useCompleteCase(caseId);
  const cmmsDraft = useCreateCmmsDraft(caseId);

  const [findingNotes, setFindingNotes] = useState("");
  const [findingResult, setFindingResult] = useState(FINDING_RESULTS[0]);
  const [actionNotes, setActionNotes] = useState("");
  const [actionType, setActionType] = useState(ACTION_TYPES[0]);
  const [completeNotes, setCompleteNotes] = useState("");
  const [classification, setClassification] = useState(FEEDBACK_CLASSIFICATIONS[0]);

  usePageTitle(caseQuery.data ? humanize(caseQuery.data.recommended_action) : "Maintenance case");

  const state = caseQuery.data?.state;
  const canWrite = can("MAINTENANCE_WRITE");
  const canCmms = can("CMMS_MANAGE");

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10">
      <DataState
        isPending={caseQuery.isPending}
        isError={caseQuery.isError}
        error={caseQuery.error}
        loadingLabel="Loading maintenance case…"
      >
        {caseQuery.data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Maintenance", href: "/maintenance" },
                { label: humanize(caseQuery.data.recommended_action) },
              ]}
              title={humanize(caseQuery.data.recommended_action)}
              description={`${machine.data ? `${machine.data.name} · ` : ""}Window: ${humanize(caseQuery.data.recommended_window)} · Priority: ${humanize(caseQuery.data.priority)}`}
              actions={
                <>
                  <MaintenanceStateBadge value={caseQuery.data.state} />
                  {caseQuery.data.human_review_required && <HumanReviewBadge />}
                  <Link
                    href={`/assistant?machineId=${caseQuery.data.machine_id}&incidentId=${caseQuery.data.incident_id}&caseId=${caseId}`}
                    className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700"
                  >
                    Ask Assistant
                  </Link>
                </>
              }
            />

            <p className="-mt-4 flex flex-wrap items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
              {machine.data && (
                <Link
                  href={`/machines/${caseQuery.data.machine_id}`}
                  className="text-sky-600 hover:underline dark:text-sky-400"
                >
                  View machine ({machine.data.name})
                </Link>
              )}
              <Link
                href={`/incidents/${caseQuery.data.incident_id}`}
                className="text-sky-600 hover:underline dark:text-sky-400"
              >
                View originating incident
              </Link>
            </p>

            <SectionCard>
              {canWrite ? (
                <div className="flex flex-wrap gap-2">
                  {(state === "REVIEW_REQUIRED" || state === "NOT_STARTED") && (
                    <button
                      type="button"
                      onClick={() => plan.mutate()}
                      disabled={plan.isPending}
                      className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                    >
                      {plan.isPending ? "Planning…" : "Plan"}
                    </button>
                  )}
                  {state === "PLANNED" && (
                    <button
                      type="button"
                      onClick={() => start.mutate()}
                      disabled={start.isPending}
                      className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                    >
                      {start.isPending ? "Starting…" : "Start"}
                    </button>
                  )}
                  {canCmms && (
                    <button
                      type="button"
                      onClick={() => cmmsDraft.mutate()}
                      disabled={cmmsDraft.isPending}
                      className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    >
                      {cmmsDraft.isPending ? "Creating draft…" : "Create CMMS draft"}
                    </button>
                  )}
                </div>
              ) : (
                <p className="text-xs text-zinc-400 dark:text-zinc-600">
                  Your current demo role cannot manage this maintenance case.
                </p>
              )}
              {cmmsDraft.isSuccess && (
                <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
                  Draft {cmmsDraft.data.external_reference} ({humanize(cmmsDraft.data.status)}) —
                  draft only, not submitted externally.
                </p>
              )}
              {cmmsDraft.isError && (
                <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                  CMMS draft failed — the maintenance case itself is unaffected and the draft
                  can be retried.
                </p>
              )}
            </SectionCard>

            <SectionCard title="Inspection checklist">
              <ul className="space-y-1 text-sm text-zinc-700 dark:text-zinc-300">
                {caseQuery.data.checklist.map((item) => (
                  <li key={item.text}>• {item.text}</li>
                ))}
              </ul>
            </SectionCard>

            {canWrite && (state === "IN_PROGRESS" || state === "AWAITING_VERIFICATION") && (
              <div className="grid gap-4 sm:grid-cols-2">
                <SectionCard title="Record technician finding">
                  <select
                    value={findingResult}
                    onChange={(e) => setFindingResult(e.target.value)}
                    className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  >
                    {FINDING_RESULTS.map((r) => (
                      <option key={r} value={r}>
                        {humanize(r)}
                      </option>
                    ))}
                  </select>
                  <textarea
                    value={findingNotes}
                    onChange={(e) => setFindingNotes(e.target.value)}
                    placeholder="Notes (synthetic demo finding)…"
                    className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                    rows={2}
                  />
                  <button
                    type="button"
                    disabled={recordFinding.isPending || !findingNotes}
                    onClick={() =>
                      recordFinding.mutate(
                        { result: findingResult, notes: findingNotes },
                        { onSuccess: () => setFindingNotes("") },
                      )
                    }
                    className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                  >
                    {recordFinding.isPending ? "Recording…" : "Record finding"}
                  </button>
                </SectionCard>

                <SectionCard title="Record maintenance action">
                  <select
                    value={actionType}
                    onChange={(e) => setActionType(e.target.value)}
                    className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  >
                    {ACTION_TYPES.map((a) => (
                      <option key={a} value={a}>
                        {humanize(a)}
                      </option>
                    ))}
                  </select>
                  <textarea
                    value={actionNotes}
                    onChange={(e) => setActionNotes(e.target.value)}
                    placeholder="Notes (a human performed this action)…"
                    className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                    rows={2}
                  />
                  <button
                    type="button"
                    disabled={recordAction.isPending || !actionNotes}
                    onClick={() =>
                      recordAction.mutate(
                        { action_type: actionType, notes: actionNotes },
                        { onSuccess: () => setActionNotes("") },
                      )
                    }
                    className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
                  >
                    {recordAction.isPending ? "Recording…" : "Record action"}
                  </button>
                </SectionCard>
              </div>
            )}

            {canWrite && (state === "IN_PROGRESS" || state === "AWAITING_VERIFICATION") && (
              <SectionCard title="Complete case">
                <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                  Requires an explicit feedback classification; runs a real, fresh post-action
                  condition re-check rather than closing solely because this button was
                  clicked.
                </p>
                <select
                  value={classification}
                  onChange={(e) => setClassification(e.target.value)}
                  className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                >
                  {FEEDBACK_CLASSIFICATIONS.map((c) => (
                    <option key={c} value={c}>
                      {humanize(c)}
                    </option>
                  ))}
                </select>
                <textarea
                  value={completeNotes}
                  onChange={(e) => setCompleteNotes(e.target.value)}
                  placeholder="Completion notes…"
                  className="mb-2 w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                  rows={2}
                />
                <button
                  type="button"
                  disabled={complete.isPending}
                  onClick={() => {
                    if (window.confirm("Complete this case? This records final feedback and re-checks condition."))
                      complete.mutate({ classification, notes: completeNotes });
                  }}
                  className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {complete.isPending ? "Completing…" : "Complete case"}
                </button>
              </SectionCard>
            )}

            {feedback.data && (
              <SectionCard title="Feedback">
                <div className="flex items-center gap-2">
                  <FeedbackBadge value={feedback.data.classification} />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">
                    Post-action condition: {humanize(feedback.data.post_action_condition_type)}
                  </span>
                </div>
              </SectionCard>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <SectionCard title="What the technician found">
                <ul className="space-y-3 text-sm text-zinc-700 dark:text-zinc-300">
                  {(findings.data ?? []).map((f) => (
                    <li key={f.id}>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-900 dark:text-zinc-100">
                          {f.observed_issue || humanize(f.result)}
                        </span>
                        <StatusPill tone={findingResultTone(f.result)}>{humanize(f.result)}</StatusPill>
                      </div>
                      {f.notes && (
                        <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{f.notes}</p>
                      )}
                    </li>
                  ))}
                  {(findings.data ?? []).length === 0 && (
                    <li className="text-zinc-400 dark:text-zinc-500">None yet.</li>
                  )}
                </ul>
              </SectionCard>
              <SectionCard title="Actions">
                <ul className="space-y-1 text-sm text-zinc-700 dark:text-zinc-300">
                  {(actions.data ?? []).map((a) => (
                    <li key={a.id}>
                      {humanize(a.action_type)} — {a.notes}
                    </li>
                  ))}
                  {(actions.data ?? []).length === 0 && (
                    <li className="text-zinc-400 dark:text-zinc-500">None yet.</li>
                  )}
                </ul>
              </SectionCard>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}

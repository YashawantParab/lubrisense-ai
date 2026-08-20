"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useIntelligenceView } from "@/hooks/use-intelligence";
import type {
  DecisionAssessmentResponse,
  PrognosticAssessmentResponse,
} from "@/lib/api/intelligence-types";

const STATE_LABELS: Record<string, string> = {
  LUBRICATION_DELIVERY_STATE: "Lubrication delivery",
  BEARING_CONDITION_STATE: "Bearing condition",
};

const HORIZON_LABELS: Record<string, string> = {
  ONE_HOUR: "1 hour",
  SIX_HOURS: "6 hours",
  TWENTY_FOUR_HOURS: "24 hours",
};

function confidenceTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "HIGH") return "ok";
  if (value === "MODERATE") return "warn";
  return "neutral";
}

function severityTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "INFO") return "ok";
  if (value === "WARNING") return "warn";
  if (value === "CRITICAL") return "error";
  return "warn";
}

function priorityTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "MONITOR") return "ok";
  if (value === "PLANNED") return "neutral";
  if (value === "HIGH") return "warn";
  return "error";
}

function DecisionCard({ decision }: { decision: DecisionAssessmentResponse }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Decision record</h2>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={priorityTone(decision.priority)}>{decision.priority}</StatusPill>
          {decision.human_review_required && (
            <StatusPill tone="warn">human review required</StatusPill>
          )}
        </div>
      </div>
      <p className="mt-3 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
        {decision.recommended_action.replaceAll("_", " ")}
      </p>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Window: {decision.recommended_window.replaceAll("_", " ")}
      </p>
      <div className="mt-4 grid gap-3 text-sm">
        <div>
          <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Risk if deferred</dt>
          <dd className="mt-0.5 text-zinc-700 dark:text-zinc-300">{decision.risk_if_deferred}</dd>
        </div>
        {decision.evidence.missing_data.length > 0 && (
          <div>
            <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Missing / limitations
            </dt>
            <dd className="mt-0.5 text-zinc-700 dark:text-zinc-300">
              <ul className="list-inside list-disc">
                {decision.evidence.missing_data.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        <StatusPill tone={confidenceTone(decision.confidence)}>
          confidence: {decision.confidence}
        </StatusPill>
        <span>expires {new Date(decision.expires_at).toLocaleString()}</span>
      </div>
    </div>
  );
}

function ProgCard({ forecasts }: { forecasts: PrognosticAssessmentResponse[] }) {
  if (forecasts.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        Prognostic record: no forecast is available yet — no state estimate has been computed for
        this machine.
      </div>
    );
  }

  const byStateType = forecasts.reduce<Record<string, PrognosticAssessmentResponse[]>>(
    (acc, row) => {
      (acc[row.state_type] ??= []).push(row);
      return acc;
    },
    {},
  );

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Prognostic record</h2>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        {Object.entries(byStateType).map(([stateType, rows]) => (
          <div key={stateType}>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              {STATE_LABELS[stateType] ?? stateType}
            </p>
            <ul className="mt-2 space-y-1.5 text-sm">
              {rows.map((row) => (
                <li key={row.id} className="flex items-center justify-between gap-2">
                  <span className="text-zinc-600 dark:text-zinc-400">
                    {HORIZON_LABELS[row.horizon] ?? row.horizon}
                  </span>
                  {row.status === "NO_RELIABLE_FORECAST" ? (
                    <StatusPill tone="neutral">no reliable forecast</StatusPill>
                  ) : (
                    <span className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
                      {row.predicted_state_at_horizon.toFixed(3)}
                      {row.estimated_threshold_crossing_time && (
                        <span className="ml-1 text-amber-600 dark:text-amber-400">
                          (est. crossing{" "}
                          {new Date(row.estimated_threshold_crossing_time).toLocaleString()})
                        </span>
                      )}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        Estimated trend extrapolation only — never a guarantee of future failure.
      </p>
    </div>
  );
}

export default function IntelligencePage() {
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState("");

  const machines = useMemo(
    () =>
      hierarchy.data?.customers.flatMap((customer) =>
        customer.sites.flatMap((site) =>
          site.plants.flatMap((plant) => plant.production_lines.flatMap((line) => line.machines)),
        ),
      ) ?? [],
    [hierarchy.data],
  );

  const effectiveMachineId = machineId || machines[0]?.id || "";
  const view = useIntelligenceView(effectiveMachineId);
  const selectedMachine = machines.find((machine) => machine.id === effectiveMachineId);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Technical Provenance
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500 dark:text-zinc-400">
            Detailed evidence and processing records for engineering validation and traceability —
            the three persisted assessment records (condition, prognostic, decision) exactly as
            stored. No business reviewer should need this page to understand the product: see the
            machine&rsquo;s own page, or the incident it produced, for the reviewer-facing
            explanation.
          </p>
        </div>
        <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Machine
          <select
            value={effectiveMachineId}
            onChange={(event) => setMachineId(event.target.value)}
            className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
          >
            {machines.map((machine) => (
              <option key={machine.id} value={machine.id}>
                {machine.name} · {machine.asset_code}
              </option>
            ))}
          </select>
        </label>
      </header>

      <DataState
        isPending={hierarchy.isPending || view.isPending}
        isError={hierarchy.isError || view.isError}
        error={hierarchy.error ?? view.error}
        loadingLabel="Computing condition, forecast, and decision…"
      >
        {view.data && (
          <div className="flex flex-col gap-4">
            <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  Condition record
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill tone={severityTone(view.data.condition.severity)}>
                    {view.data.condition.severity}
                  </StatusPill>
                  <StatusPill tone={confidenceTone(view.data.condition.confidence)}>
                    confidence: {view.data.condition.confidence}
                  </StatusPill>
                  <StatusPill tone="neutral">{view.data.condition.lifecycle_state}</StatusPill>
                </div>
              </div>
              <p className="mt-2 text-base font-medium text-zinc-900 dark:text-zinc-100">
                {view.data.condition.condition_type.replaceAll("_", " ")}
              </p>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {view.data.condition.evidence_summary.what_is_happening}
              </p>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Why</dt>
                  <dd className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                    <ul className="list-inside list-disc space-y-1">
                      {view.data.condition.evidence_summary.why.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                    Data trust / unknowns
                  </dt>
                  <dd className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                    <p>
                      Data trustworthiness:{" "}
                      {view.data.condition.evidence_summary.data_trustworthiness}
                    </p>
                    {view.data.condition.evidence_summary.unknowns.length > 0 && (
                      <ul className="mt-1 list-inside list-disc space-y-1">
                        {view.data.condition.evidence_summary.unknowns.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
              </div>
            </section>

            <ProgCard forecasts={view.data.prognostics} />
            <DecisionCard decision={view.data.decision} />
          </div>
        )}

        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {selectedMachine ? `${selectedMachine.name} (${selectedMachine.asset_code})` : ""}
        </p>
      </DataState>
    </div>
  );
}

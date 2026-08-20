"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useLatestStateEstimates, useStateEstimateHistory } from "@/hooks/use-state-estimation";
import { interpretState, STATE_TYPE_LABELS } from "@/lib/state-interpretation";
import { humanize } from "@/lib/terminology";
import type { StateEstimateResponse } from "@/lib/api/state-estimation-types";

function uncertaintyTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "LOW") return "ok";
  if (value === "MODERATE") return "warn";
  return "error";
}

function StateCard({ estimate }: { estimate: StateEstimateResponse }) {
  // A prediction-only tick (no recent trusted observation factored in) or a HIGH-
  // uncertainty read is not a confident reading — showing a bare "0.000"/"UNKNOWN" card
  // for it reads as a real, valid assessment when it isn't one. Route it to an honest
  // unavailable state instead of the hero number.
  const isUnavailable = estimate.prediction_only || estimate.uncertainty === "HIGH";
  const interpretation = interpretState(estimate.trend, estimate.state_value, {
    unavailable: isUnavailable,
  });

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        {STATE_TYPE_LABELS[estimate.state_type] ?? humanize(estimate.state_type)}
      </h2>

      {isUnavailable ? (
        <div className="mt-3 flex flex-col gap-1">
          <StatusPill tone="neutral">Insufficient recent observations</StatusPill>
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
            {estimate.prediction_only
              ? "No recent trusted observation has been factored in yet — this would be a projection only, not a fresh reading."
              : "Recent readings are too uncertain to report a confident estimate right now."}
          </p>
        </div>
      ) : (
        <>
          <p className="mt-3 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            {interpretation.headline}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <StatusPill tone={interpretation.tone}>{humanize(estimate.trend)} trend</StatusPill>
            <StatusPill tone={uncertaintyTone(estimate.uncertainty)}>
              {humanize(estimate.uncertainty)} confidence
            </StatusPill>
          </div>
          <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
            Condition index: <span className="font-mono">{estimate.state_value.toFixed(2)}</span>{" "}
            (0 = normal · 1 = severely degraded — a trend estimate, not a failure
            probability)
          </p>
        </>
      )}

      <details className="mt-4 border-t border-zinc-100 pt-3 dark:border-zinc-800">
        <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
          Technical detail
        </summary>
        <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <div>
            <dt>Estimator</dt>
            <dd className="text-zinc-800 dark:text-zinc-200">2-state Kalman filter</dd>
          </div>
          <div>
            <dt>As of</dt>
            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
              {new Date(estimate.as_of_timestamp).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt>Observations used</dt>
            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
              {estimate.observations_used.length ? estimate.observations_used.join(", ") : "none"}
            </dd>
          </div>
          <div>
            <dt>Observations missing</dt>
            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
              {estimate.observations_missing.length
                ? estimate.observations_missing.join(", ")
                : "none"}
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

export default function StateEstimationPage() {
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
  const latest = useLatestStateEstimates(effectiveMachineId);
  const history = useStateEstimateHistory(effectiveMachineId);
  const selectedMachine = machines.find((machine) => machine.id === effectiveMachineId);

  const states = latest.data ? Object.values(latest.data) : [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Machine Condition Estimation"
        description="Estimated machine-condition states derived from recent sensor behavior — an independent evidence source, not a diagnosis on its own. Machine and Incident pages show how this combines with rule findings and other evidence into the current assessment."
        actions={
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
        }
      />

      <DataState
        isPending={hierarchy.isPending || latest.isPending}
        isError={hierarchy.isError || latest.isError}
        error={hierarchy.error ?? latest.error}
        loadingLabel="Computing state estimate…"
      >
        <section className="grid gap-4 sm:grid-cols-2">
          {states.map((estimate) => (
            <StateCard key={estimate.state_type} estimate={estimate} />
          ))}
        </section>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {selectedMachine ? `${selectedMachine.name} (${selectedMachine.asset_code})` : ""}
        </p>
      </DataState>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Recent history
        </h2>
        <DataState
          isPending={history.isPending}
          isError={history.isError}
          error={history.error}
          loadingLabel="Loading history…"
        >
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="py-2 pr-4 font-medium">As of</th>
                  <th className="py-2 pr-4 font-medium">State</th>
                  <th className="py-2 pr-4 font-medium">Level</th>
                  <th className="py-2 pr-4 font-medium">Trend</th>
                  <th className="py-2 font-medium">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {(history.data ?? []).map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="py-2 pr-4 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                      {new Date(row.as_of_timestamp).toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-xs text-zinc-700 dark:text-zinc-300">
                      {STATE_TYPE_LABELS[row.state_type] ?? humanize(row.state_type)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs text-zinc-900 dark:text-zinc-100">
                      {row.prediction_only ? "—" : row.state_value.toFixed(2)}
                    </td>
                    <td className="py-2 pr-4 text-xs text-zinc-700 dark:text-zinc-300">
                      {humanize(row.trend)}
                    </td>
                    <td className="py-2 text-xs text-zinc-700 dark:text-zinc-300">
                      {humanize(row.uncertainty)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DataState>
      </section>
    </div>
  );
}

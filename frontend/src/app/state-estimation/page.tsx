"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useLatestStateEstimates, useStateEstimateHistory } from "@/hooks/use-state-estimation";
import type { StateEstimateResponse } from "@/lib/api/state-estimation-types";

const STATE_LABELS: Record<string, string> = {
  LUBRICATION_DELIVERY_STATE: "Lubrication delivery",
  BEARING_CONDITION_STATE: "Bearing condition",
};

function uncertaintyTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "LOW") return "ok";
  if (value === "MODERATE") return "warn";
  return "error";
}

function trendTone(value: string): "ok" | "warn" | "error" | "neutral" {
  if (value === "IMPROVING") return "ok";
  if (value === "STABLE") return "neutral";
  if (value === "DETERIORATING") return "warn";
  return "neutral";
}

function StateCard({ estimate }: { estimate: StateEstimateResponse }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {STATE_LABELS[estimate.state_type] ?? estimate.state_type}
        </h2>
        {estimate.prediction_only && <StatusPill tone="neutral">prediction-only</StatusPill>}
      </div>
      <p className="mt-3 text-3xl font-semibold text-zinc-900 dark:text-zinc-100">
        {estimate.state_value.toFixed(3)}
      </p>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        0 = nominal, 1 = severely degraded — not a failure probability
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <StatusPill tone={trendTone(estimate.trend)}>{estimate.trend}</StatusPill>
        <StatusPill tone={uncertaintyTone(estimate.uncertainty)}>
          uncertainty: {estimate.uncertainty}
        </StatusPill>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        <div>
          <dt>As of</dt>
          <dd className="font-mono text-zinc-800 dark:text-zinc-200">
            {new Date(estimate.as_of_timestamp).toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>dt (seconds)</dt>
          <dd className="font-mono text-zinc-800 dark:text-zinc-200">
            {estimate.dt_seconds.toFixed(1)}
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
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            State Estimation
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Kalman-filter condition evidence — an independent evidence source, not a
            diagnosis. See Condition Intelligence (later phase) for how this combines with
            rules and ML.
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
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
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
                  <th className="py-2 pr-4 font-medium">State type</th>
                  <th className="py-2 pr-4 font-medium">Value</th>
                  <th className="py-2 pr-4 font-medium">Trend</th>
                  <th className="py-2 font-medium">Uncertainty</th>
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
                      {STATE_LABELS[row.state_type] ?? row.state_type}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs text-zinc-900 dark:text-zinc-100">
                      {row.state_value.toFixed(3)}
                    </td>
                    <td className="py-2 pr-4 text-xs text-zinc-700 dark:text-zinc-300">
                      {row.trend}
                    </td>
                    <td className="py-2 text-xs text-zinc-700 dark:text-zinc-300">
                      {row.uncertainty}
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

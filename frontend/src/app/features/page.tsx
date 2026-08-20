"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFeatureSets, useLatestMachineFeatures } from "@/hooks/use-features";
import { humanize } from "@/lib/terminology";

function displayValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export default function FeaturesPage() {
  const hierarchy = useHierarchy();
  const featureSets = useFeatureSets();
  const [machineId, setMachineId] = useState("");
  const [featureSet, setFeatureSet] = useState("LUBRICATION_ANOMALY_V1");
  const [showDetail, setShowDetail] = useState(false);

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
  const vector = useLatestMachineFeatures(effectiveMachineId, featureSet);
  const selectedMachine = machines.find((machine) => machine.id === effectiveMachineId);
  const values = vector.data
    ? Object.entries(vector.data.feature_values).sort(([a], [b]) => a.localeCompare(b))
    : [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="Feature Vectors"
        description="The exact engineered inputs an ML model computed a result from — dot-notation names are ML feature-engineering identifiers, one row per input, purely for tracing an ML result back to its source data."
        actions={
          <div className="flex flex-wrap gap-3">
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
            <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
              Feature set
              <select
                value={featureSet}
                onChange={(event) => setFeatureSet(event.target.value)}
                className="min-w-60 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              >
                {(featureSets.data ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        }
      />

      <DataState
        isPending={hierarchy.isPending || featureSets.isPending || vector.isPending}
        isError={hierarchy.isError || featureSets.isError || vector.isError}
        error={hierarchy.error ?? featureSets.error ?? vector.error}
        loadingLabel="Computing feature vector…"
      >
        {vector.data && (
          <>
            <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {[
                ["Machine", selectedMachine?.name ?? effectiveMachineId.slice(0, 8)],
                ["Feature set", vector.data.feature_set],
                ["As of", new Date(vector.data.as_of_timestamp).toLocaleString()],
                ["Features", String(values.length)],
                ["Missing", String(vector.data.missing_features.length)],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
                >
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
                  <p className="mt-1 break-words text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                    {value}
                  </p>
                </div>
              ))}
            </section>

            <section className="flex items-center justify-between border-y border-zinc-200 py-3 dark:border-zinc-800">
              <div className="flex items-center gap-3 text-sm text-zinc-700 dark:text-zinc-300">
                <span>Quality state</span>
                <StatusPill tone={vector.data.quality_summary.state === "TRUSTED" ? "ok" : "warn"}>
                  {humanize(String(vector.data.quality_summary.state ?? "UNKNOWN"))}
                </StatusPill>
              </div>
              <button
                type="button"
                onClick={() => setShowDetail((visible) => !visible)}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
              >
                {showDetail ? "Hide provenance" : "Show provenance"}
              </button>
            </section>

            <section className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                    <th className="py-2 pr-4 font-medium">Feature</th>
                    <th className="py-2 font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {values.map(([name, value]) => (
                    <tr
                      key={name}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="py-2 pr-4 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                        {name}
                      </td>
                      <td className="py-2 font-mono text-xs text-zinc-900 dark:text-zinc-100">
                        {displayValue(value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {showDetail && (
              <section className="grid gap-4 lg:grid-cols-2">
                {[
                  ["Missing features", vector.data.missing_features],
                  ["Quality summary", vector.data.quality_summary],
                  ["Source window", vector.data.source_window],
                  ["Baseline versions", vector.data.baseline_versions],
                  ["Rule versions", vector.data.rule_versions],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      {String(label)}
                    </h2>
                    <pre className="max-h-72 overflow-auto rounded-md bg-zinc-900 p-3 text-xs text-zinc-100 dark:bg-black">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
      </DataState>
    </div>
  );
}

"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useLatestMachineInference } from "@/hooks/use-ml";

const MODEL_IDS = ["LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1"] as const;

function statusTone(status: string): "ok" | "warn" | "error" | "neutral" {
  if (status === "OK") return "ok";
  if (status === "UNKNOWN") return "warn";
  if (status === "INSUFFICIENT_FEATURES") return "neutral";
  return "neutral";
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function MLPage() {
  const hierarchy = useHierarchy();
  const [machineId, setMachineId] = useState("");
  const [modelId, setModelId] = useState<(typeof MODEL_IDS)[number]>("LUBRICATION_ANOMALY_V1");
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
  const inference = useLatestMachineInference(effectiveMachineId, modelId);
  const selectedMachine = machines.find((machine) => machine.id === effectiveMachineId);

  const probabilities = inference.data
    ? Object.entries(inference.data.class_probabilities).sort(([, a], [, b]) => b - a)
    : [];

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            ML Model Evidence
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Evidence only — not a diagnosis or maintenance decision. See Condition Intelligence
            (later phase) for how this combines with rules.
          </p>
        </div>
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
            Model
            <select
              value={modelId}
              onChange={(event) => setModelId(event.target.value as (typeof MODEL_IDS)[number])}
              className="min-w-60 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              {MODEL_IDS.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <DataState
        isPending={hierarchy.isPending || inference.isPending}
        isError={hierarchy.isError || inference.isError}
        error={hierarchy.error ?? inference.error}
        loadingLabel="Running inference…"
      >
        {inference.data && (
          <>
            <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Machine", selectedMachine?.name ?? effectiveMachineId.slice(0, 8)],
                ["Model version", inference.data.model_version],
                ["As of", new Date(inference.data.as_of_timestamp).toLocaleString()],
                ["Missing features", String(inference.data.missing_features.length)],
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

            <section className="flex flex-wrap items-center justify-between gap-3 border-y border-zinc-200 py-3 dark:border-zinc-800">
              <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-700 dark:text-zinc-300">
                <span>Status</span>
                <StatusPill tone={statusTone(inference.data.status)}>
                  {inference.data.status}
                </StatusPill>

                {inference.data.result_kind === "ANOMALY" && inference.data.status === "OK" && (
                  <>
                    <span>Anomaly score</span>
                    <StatusPill tone={inference.data.anomalous ? "warn" : "ok"}>
                      {inference.data.anomaly_score?.toFixed(4)}{" "}
                      {inference.data.anomalous ? "(anomalous)" : "(within threshold)"}
                    </StatusPill>
                  </>
                )}

                {inference.data.result_kind === "CLASSIFICATION" && (
                  <>
                    <span>Predicted class</span>
                    <StatusPill tone={inference.data.predicted_class === "NORMAL" ? "ok" : "warn"}>
                      {inference.data.predicted_class ?? "—"}
                    </StatusPill>
                    {inference.data.confidence_category && (
                      <StatusPill
                        tone={inference.data.confidence_category === "HIGH" ? "ok" : "neutral"}
                      >
                        confidence: {inference.data.confidence_category}
                      </StatusPill>
                    )}
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={() => setShowDetail((visible) => !visible)}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
              >
                {showDetail ? "Hide detail" : "Show detail"}
              </button>
            </section>

            {inference.data.result_kind === "CLASSIFICATION" && probabilities.length > 0 && (
              <section className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                      <th className="py-2 pr-4 font-medium">Class</th>
                      <th className="py-2 font-medium">Probability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {probabilities.map(([label, value]) => (
                      <tr
                        key={label}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                      >
                        <td className="py-2 pr-4 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                          {label}
                        </td>
                        <td className="py-2 font-mono text-xs text-zinc-900 dark:text-zinc-100">
                          {formatPercent(value)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {showDetail && (
              <section className="grid gap-4 lg:grid-cols-2">
                {[
                  ["Features used", inference.data.features_used],
                  ["Missing features", inference.data.missing_features],
                  ["Quality summary", inference.data.quality_summary],
                  ["Explanation", inference.data.explanation],
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

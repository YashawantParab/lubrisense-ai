"use client";

import { useState } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useSensors } from "@/hooks/use-asset-hierarchy";
import { useCurrentBaseline, useSensorBaselines, useBaselineSummary } from "@/hooks/use-baselines";
import { humanize } from "@/lib/terminology";
import type { BaselineState, DeviationClassification } from "@/lib/api/baselines-types";

const STAT_LABELS: Record<string, string> = {
  median: "Median",
  mad: "Median abs. deviation",
  mean: "Mean",
  p05: "5th percentile",
  p75: "75th percentile",
  p95: "95th percentile",
};

const READINESS_ORDER = ["ACTIVE", "BUILDING", "INSUFFICIENT_DATA", "STALE", "INVALIDATED"];

function toneForState(state: BaselineState): "ok" | "warn" | "error" | "neutral" {
  if (state === "ACTIVE") return "ok";
  if (state === "BUILDING" || state === "STALE") return "warn";
  if (state === "INVALIDATED") return "error";
  return "neutral";
}

function toneForDeviation(
  classification: DeviationClassification,
): "ok" | "warn" | "error" | "neutral" {
  if (classification === "WITHIN_EXPECTED_RANGE") return "ok";
  if (classification === "MILD_DEVIATION") return "warn";
  if (classification === "STRONG_DEVIATION") return "error";
  return "neutral";
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

export default function BaselinesPage() {
  const summary = useBaselineSummary();
  const sensors = useSensors({ limit: 200 });
  const [selectedSensorId, setSelectedSensorId] = useState("");
  const [operatingState, setOperatingState] = useState("");
  const [cycleValue, setCycleValue] = useState("");

  const sensorId = selectedSensorId || sensors.data?.items[0]?.id || "";
  const sensorBaselines = useSensorBaselines(sensorId);
  const current = useCurrentBaseline(sensorId, {
    operating_state: operatingState || undefined,
    value: cycleValue !== "" ? Number(cycleValue) : undefined,
  });

  const selectedSensor = sensors.data?.items.find((s) => s.id === sensorId);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
      <PageHeader
        title="Baselines"
        description="What normal looks like for each sensor, under its own operating context — the statistical reference rules and other evidence sources compare against. A baseline profile is not itself a fault diagnosis or health score."
      />

      <DataState
        isPending={summary.isPending}
        isError={summary.isError}
        error={summary.error}
        loadingLabel="Loading summary…"
      >
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <SummaryCard
              label="Total profiles"
              value={summary.data.total_profiles}
              tone="text-zinc-900 dark:text-zinc-100"
            />
            {READINESS_ORDER.map((state) => (
              <SummaryCard
                key={state}
                label={humanize(state)}
                value={summary.data.profiles_by_state[state] ?? 0}
                tone={
                  toneForState(state as BaselineState) === "ok"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : toneForState(state as BaselineState) === "warn"
                      ? "text-amber-600 dark:text-amber-400"
                      : toneForState(state as BaselineState) === "error"
                        ? "text-red-600 dark:text-red-400"
                        : "text-zinc-500 dark:text-zinc-400"
                }
              />
            ))}
          </div>
        )}
      </DataState>

      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Sensor baseline profiles
          </h2>
          <DataState
            isPending={sensors.isPending}
            isError={sensors.isError}
            error={sensors.error}
            loadingLabel="Loading sensors…"
          >
            <select
              value={sensorId}
              onChange={(e) => setSelectedSensorId(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              {sensors.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.sensor_code} — {humanize(s.sensor_type)}
                </option>
              ))}
            </select>
          </DataState>
        </div>

        <DataState
          isPending={sensorBaselines.isPending}
          isError={sensorBaselines.isError}
          error={sensorBaselines.error}
          loadingLabel="Loading baselines…"
        >
          {sensorBaselines.data && (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <span>Readiness:</span>
                <StatusPill
                  tone={
                    sensorBaselines.data.readiness.label === "READY"
                      ? "ok"
                      : sensorBaselines.data.readiness.label === "PARTIAL"
                        ? "warn"
                        : "neutral"
                  }
                >
                  {humanize(sensorBaselines.data.readiness.label)}
                </StatusPill>
                <span>
                  ({sensorBaselines.data.readiness.active_count} active,{" "}
                  {sensorBaselines.data.readiness.building_count} building,{" "}
                  {sensorBaselines.data.readiness.insufficient_data_count} insufficient data)
                </span>
              </div>

              {sensorBaselines.data.profiles.length === 0 ? (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  No baseline profiles yet for this sensor — baselines refresh on a regular cadence,
                  so a brand-new sensor may not have been evaluated yet.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                        <th className="py-2 pr-4 font-medium">Strategy</th>
                        <th className="py-2 pr-4 font-medium">Context</th>
                        <th className="py-2 pr-4 font-medium">State</th>
                        <th className="py-2 pr-4 font-medium">Version</th>
                        <th className="py-2 pr-4 font-medium">Samples</th>
                        <th className="py-2 pr-4 font-medium">Machine</th>
                        <th className="py-2 pr-4 font-medium">Last evaluated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sensorBaselines.data.profiles.map((p) => (
                        <tr
                          key={p.id}
                          className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                        >
                          <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">
                            {humanize(p.strategy)}
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-zinc-600 dark:text-zinc-400">
                            {p.context_key || "—"}
                          </td>
                          <td className="py-2 pr-4">
                            <StatusPill tone={toneForState(p.state)}>
                              {humanize(p.state)}
                            </StatusPill>
                          </td>
                          <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                            v{p.version}
                          </td>
                          <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                            {p.sample_count}
                            {p.min_sample_required > 0 ? ` / ${p.min_sample_required}` : ""}
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-zinc-500">
                            {p.machine_id ? `${p.machine_id.slice(0, 8)}…` : "—"}
                          </td>
                          <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                            {p.last_evaluated_at
                              ? new Date(p.last_evaluated_at).toLocaleString()
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </DataState>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Resolved baseline &amp; deviation
          {selectedSensor ? ` — ${selectedSensor.sensor_code}` : ""}
        </h2>
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          Resolves the best-available reference for the chosen context (an exact match, falling back
          to a coarser one when needed), and — if a reading is entered below — computes an
          explainable deviation. This is a statistical distance, not a fault diagnosis, and the
          input below is an engineering verification tool, not a live reading.
        </p>

        <div className="mb-3 flex flex-wrap gap-3">
          <select
            value={operatingState}
            onChange={(e) => setOperatingState(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          >
            <option value="">Any operating state</option>
            <option value="STOPPED">{humanize("STOPPED")}</option>
            <option value="RUNNING_LOW_LOAD">{humanize("RUNNING_LOW_LOAD")}</option>
            <option value="RUNNING_NORMAL_LOAD">{humanize("RUNNING_NORMAL_LOAD")}</option>
            <option value="RUNNING_HIGH_LOAD">{humanize("RUNNING_HIGH_LOAD")}</option>
          </select>
          <input
            type="number"
            placeholder="Reading to evaluate (optional)"
            value={cycleValue}
            onChange={(e) => setCycleValue(e.target.value)}
            className="w-56 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
          />
        </div>

        <DataState
          isPending={current.isPending}
          isError={current.isError}
          error={current.error}
          loadingLabel="Resolving baseline…"
        >
          {current.data && (
            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <span>Resolved via:</span>
                <StatusPill tone={current.data.source === "NONE" ? "neutral" : "ok"}>
                  {humanize(current.data.source)}
                </StatusPill>
              </div>

              {current.data.profile?.statistics ? (
                <div className="grid grid-cols-3 gap-3 text-sm sm:grid-cols-6">
                  {(["median", "mad", "mean", "p05", "p75", "p95"] as const).map((key) => (
                    <div key={key}>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">{STAT_LABELS[key]}</p>
                      <p className="font-mono text-zinc-800 dark:text-zinc-200">
                        {current.data!.profile!.statistics![key] !== undefined
                          ? current.data!.profile!.statistics![key].toFixed(2)
                          : "—"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  No resolved baseline statistics yet for this sensor/context.
                </p>
              )}

              {current.data.deviation && (
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-zinc-100 pt-3 text-sm dark:border-zinc-800">
                  <StatusPill tone={toneForDeviation(current.data.deviation.classification)}>
                    {humanize(current.data.deviation.classification)}
                  </StatusPill>
                  {current.data.deviation.standardized_distance !== null && (
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      standardized distance{" "}
                      {current.data.deviation.standardized_distance.toFixed(2)} (
                      {current.data.deviation.method})
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </DataState>
      </section>
    </div>
  );
}

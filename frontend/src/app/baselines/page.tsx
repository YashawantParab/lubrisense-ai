"use client";

import { useState } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useSensors } from "@/hooks/use-asset-hierarchy";
import { useCurrentBaseline, useSensorBaselines, useBaselineSummary } from "@/hooks/use-baselines";
import { expectedRangeLabel, humanizedBaselineName } from "@/lib/baseline-naming";
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
                <div className="flex flex-col gap-3">
                  {sensorBaselines.data.profiles.map((p) => (
                    <div
                      key={p.id}
                      className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                            {humanizedBaselineName(p)}
                          </h3>
                          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                            {selectedSensor?.unit ? `Measured in ${selectedSensor.unit} · ` : ""}
                            {p.sample_count} sample{p.sample_count === 1 ? "" : "s"}
                            {p.min_sample_required > 0
                              ? ` of ${p.min_sample_required} required`
                              : ""}
                          </p>
                        </div>
                        <StatusPill tone={toneForState(p.state)}>{humanize(p.state)}</StatusPill>
                      </div>

                      <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                        <div>
                          <dt className="text-zinc-500 dark:text-zinc-400">Expected range</dt>
                          <dd className="mt-0.5 font-mono text-zinc-800 dark:text-zinc-200">
                            {expectedRangeLabel(p.statistics, selectedSensor?.unit ?? null)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-zinc-500 dark:text-zinc-400">Last updated</dt>
                          <dd className="mt-0.5 text-zinc-800 dark:text-zinc-200">
                            {p.last_evaluated_at
                              ? new Date(p.last_evaluated_at).toLocaleString()
                              : "Never evaluated"}
                          </dd>
                        </div>
                      </dl>

                      <details className="mt-3 border-t border-zinc-100 pt-2 dark:border-zinc-800">
                        <summary className="cursor-pointer text-xs font-medium text-sky-600 select-none dark:text-sky-400">
                          Technical detail
                        </summary>
                        <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-zinc-500 dark:text-zinc-400 sm:grid-cols-4">
                          <div>
                            <dt>Strategy</dt>
                            <dd className="text-zinc-800 dark:text-zinc-200">
                              {humanize(p.strategy)}
                            </dd>
                          </div>
                          <div>
                            <dt>Context key</dt>
                            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
                              {p.context_key || "—"}
                            </dd>
                          </div>
                          <div>
                            <dt>Baseline ID / version</dt>
                            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
                              {p.id.slice(0, 8)}… · v{p.version}
                            </dd>
                          </div>
                          <div>
                            <dt>Config / quality policy</dt>
                            <dd className="font-mono text-zinc-800 dark:text-zinc-200">
                              {p.config_version} / {p.quality_policy_version ?? "—"}
                            </dd>
                          </div>
                        </dl>
                      </details>
                    </div>
                  ))}
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

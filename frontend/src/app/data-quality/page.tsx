"use client";

import { useState } from "react";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useQualityIssues, useQualitySummary } from "@/hooks/use-data-quality";
import { humanize } from "@/lib/terminology";
import type { IssueSeverity, QualityState } from "@/lib/api/data-quality-types";

const SEVERITIES: IssueSeverity[] = ["CRITICAL", "ERROR", "WARNING", "INFO"];
const QUALITY_STATES: QualityState[] = ["TRUSTED", "USABLE_WITH_CAUTION", "UNUSABLE"];

function toneForQualityState(state: QualityState): "ok" | "warn" | "error" {
  if (state === "TRUSTED") return "ok";
  if (state === "USABLE_WITH_CAUTION") return "warn";
  return "error";
}

function toneForSeverity(severity: IssueSeverity): "ok" | "warn" | "error" {
  if (severity === "INFO") return "ok";
  if (severity === "WARNING") return "warn";
  return "error";
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

export default function DataQualityPage() {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("ACTIVE");

  const summary = useQualitySummary();
  const issues = useQualityIssues({
    severity: severity || undefined,
    status: status || undefined,
    limit: 100,
  });

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
      <PageHeader
        title="Data Quality"
        description="Whether telemetry can be trusted before it feeds any downstream evidence — baselines, rules, or ML. This is a signal about data trustworthiness, not a machine-condition diagnosis: no health score, no failure prediction here."
      />

      <DataState
        isPending={summary.isPending}
        isError={summary.isError}
        error={summary.error}
        loadingLabel="Loading summary…"
      >
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryCard
              label="Sensors tracked"
              value={summary.data.total_sensors_tracked}
              tone="text-zinc-900 dark:text-zinc-100"
            />
            {QUALITY_STATES.map((state) => (
              <SummaryCard
                key={state}
                label={humanize(state)}
                value={summary.data.sensors_by_quality_state[state] ?? 0}
                tone={
                  toneForQualityState(state) === "ok"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : toneForQualityState(state) === "warn"
                      ? "text-amber-600 dark:text-amber-400"
                      : "text-red-600 dark:text-red-400"
                }
              />
            ))}
          </div>
        )}
      </DataState>

      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Quality Issues
          </h2>
          <div className="flex flex-wrap gap-3">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              <option value="ACTIVE">Active</option>
              <option value="RECOVERING">Recovering</option>
              <option value="RESOLVED">Resolved</option>
              <option value="">All statuses</option>
            </select>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              <option value="">All severities</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <DataState
          isPending={issues.isPending}
          isError={issues.isError}
          error={issues.error}
          loadingLabel="Loading issues…"
        >
          {issues.data && issues.data.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No quality issues match this filter — either the fleet is clean, or telemetry
              for it hasn&apos;t been evaluated yet.
            </p>
          ) : (
            issues.data && (
              <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                      <th className="py-2 pr-4 font-medium">Sensor</th>
                      <th className="py-2 pr-4 font-medium">Dimension</th>
                      <th className="py-2 pr-4 font-medium">Issue</th>
                      <th className="py-2 pr-4 font-medium">Severity</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 pr-4 font-medium">Message</th>
                      <th className="py-2 pr-4 font-medium">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.data.map((issue) => (
                      <tr
                        key={issue.id}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                      >
                        <td className="py-2 pr-4 font-mono text-xs text-zinc-500">
                          {issue.sensor_id.slice(0, 8)}…
                        </td>
                        <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                          {humanize(issue.dimension)}
                        </td>
                        <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">
                          {humanize(issue.issue_type)}
                        </td>
                        <td className="py-2 pr-4">
                          <StatusPill tone={toneForSeverity(issue.severity)}>
                            {humanize(issue.severity)}
                          </StatusPill>
                        </td>
                        <td className="py-2 pr-4">
                          <StatusPill tone={issue.status === "ACTIVE" ? "warn" : "neutral"}>
                            {humanize(issue.status)}
                          </StatusPill>
                        </td>
                        <td className="max-w-md py-2 pr-4 text-xs text-zinc-600 dark:text-zinc-400">
                          {issue.message}
                        </td>
                        <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                          {new Date(issue.last_seen).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </DataState>
      </section>
    </div>
  );
}

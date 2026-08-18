"use client";

import { useState } from "react";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useFindings, useFindingsSummary } from "@/hooks/use-rules";
import type {
  EvidenceStrength,
  RuleFindingSeverity,
  RuleFindingState,
} from "@/lib/api/rules-types";

const SEVERITIES: RuleFindingSeverity[] = ["CRITICAL", "HIGH", "WARNING", "INFO"];
const STATES: RuleFindingState[] = ["CANDIDATE", "ACTIVE", "RECOVERING", "RESOLVED"];

function toneForSeverity(severity: RuleFindingSeverity): "ok" | "warn" | "error" | "neutral" {
  if (severity === "INFO") return "ok";
  if (severity === "WARNING") return "warn";
  return "error";
}

function toneForState(state: RuleFindingState): "ok" | "warn" | "error" | "neutral" {
  if (state === "ACTIVE") return "error";
  if (state === "CANDIDATE" || state === "RECOVERING") return "warn";
  return "neutral";
}

function toneForEvidenceStrength(strength: EvidenceStrength): "ok" | "warn" | "error" {
  if (strength === "LOW") return "ok";
  if (strength === "MODERATE") return "warn";
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

export default function RulesPage() {
  const [severity, setSeverity] = useState("");
  const [state, setState] = useState("ACTIVE");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const summary = useFindingsSummary();
  const findings = useFindings({
    severity: severity || undefined,
    state: state || undefined,
    limit: 200,
  });

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
      <header>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
          Rule Findings
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Deterministic evidence patterns from telemetry, data quality, and baselines
          (Phase 9) — evidence language only (&ldquo;consistent with...&rdquo;), never a
          confirmed diagnosis. Feeds a future Condition Intelligence phase; not itself a
          health score. Sourced live from{" "}
          <code className="font-mono text-xs">GET /api/v1/rules/*</code>.
        </p>
      </header>

      <DataState
        isPending={summary.isPending}
        isError={summary.isError}
        error={summary.error}
        loadingLabel="Loading summary…"
      >
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryCard
              label="Active findings"
              value={summary.data.total_active_findings}
              tone="text-zinc-900 dark:text-zinc-100"
            />
            {(["ACTIVE", "CANDIDATE", "RECOVERING"] as const).map((s) => (
              <SummaryCard
                key={s}
                label={s}
                value={summary.data!.findings_by_state[s] ?? 0}
                tone={
                  toneForState(s) === "error"
                    ? "text-red-600 dark:text-red-400"
                    : "text-amber-600 dark:text-amber-400"
                }
              />
            ))}
          </div>
        )}
      </DataState>

      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Findings</h2>
          <div className="flex flex-wrap gap-3">
            <select
              value={state}
              onChange={(e) => setState(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              {STATES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
              <option value="">All states</option>
            </select>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              <option value="">All severities</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <DataState
          isPending={findings.isPending}
          isError={findings.isError}
          error={findings.error}
          loadingLabel="Loading findings…"
        >
          {findings.data && findings.data.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No findings match this filter — either the fleet shows no evidence patterns
              right now, or the rules worker hasn&apos;t evaluated any machines yet.
            </p>
          ) : (
            findings.data && (
              <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                      <th className="py-2 pr-4 font-medium">Finding</th>
                      <th className="py-2 pr-4 font-medium">Component</th>
                      <th className="py-2 pr-4 font-medium">Severity</th>
                      <th className="py-2 pr-4 font-medium">State</th>
                      <th className="py-2 pr-4 font-medium">Evidence</th>
                      <th className="py-2 pr-4 font-medium">First detected</th>
                      <th className="py-2 pr-4 font-medium">Last detected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.data.map((f) => (
                      <>
                        <tr
                          key={f.id}
                          onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}
                          className="cursor-pointer border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                        >
                          <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">
                            {f.finding_type.replace(/_/g, " ")}
                          </td>
                          <td className="py-2 pr-4 font-mono text-xs text-zinc-500">
                            {f.component_type}
                            {f.component_id ? ` ${f.component_id.slice(0, 8)}…` : ""}
                          </td>
                          <td className="py-2 pr-4">
                            <StatusPill tone={toneForSeverity(f.severity)}>
                              {f.severity}
                            </StatusPill>
                          </td>
                          <td className="py-2 pr-4">
                            <StatusPill tone={toneForState(f.state)}>{f.state}</StatusPill>
                          </td>
                          <td className="py-2 pr-4">
                            <StatusPill tone={toneForEvidenceStrength(f.evidence_strength)}>
                              {f.evidence_strength}
                            </StatusPill>
                          </td>
                          <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                            {new Date(f.first_detected_at).toLocaleString()}
                          </td>
                          <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                            {new Date(f.last_detected_at).toLocaleString()}
                          </td>
                        </tr>
                        {expandedId === f.id && (
                          <tr className="border-b border-zinc-100 bg-zinc-50 last:border-0 dark:border-zinc-800 dark:bg-zinc-800/30">
                            <td colSpan={7} className="px-2 py-4">
                              <div className="grid gap-4 sm:grid-cols-2">
                                <div>
                                  <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                    Message
                                  </p>
                                  <p className="text-sm text-zinc-800 dark:text-zinc-200">
                                    {f.message}
                                  </p>
                                  <p className="mt-3 mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                    Limitations — what this does NOT prove
                                  </p>
                                  <ul className="list-disc space-y-1 pl-4 text-xs text-zinc-600 dark:text-zinc-400">
                                    {f.limitations.map((l) => (
                                      <li key={l}>{l}</li>
                                    ))}
                                  </ul>
                                  <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                                    rule <span className="font-mono">{f.rule_id}</span> v
                                    {f.rule_version} · policy {f.config_version} · category{" "}
                                    {f.category} · candidate cycles{" "}
                                    {f.candidate_stable_cycles}
                                  </p>
                                </div>
                                <div>
                                  <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                    Structured evidence
                                  </p>
                                  <pre className="max-h-64 overflow-auto rounded-md bg-zinc-900 p-3 text-xs text-zinc-100 dark:bg-black">
                                    {JSON.stringify(f.evidence, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
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

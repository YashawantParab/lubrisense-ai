"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import { ConfidenceBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetSensorQuality, useQualitySummary } from "@/hooks/use-data-quality";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { readinessModeFor, type ReadinessMode } from "@/lib/action-readiness";
import type { SensorQualityRecordResponse } from "@/lib/api/data-quality-types";
import {
  DECISION_IMPACT_LABEL,
  ISSUE_CATEGORY_LABEL,
  ISSUE_CATEGORY_MEANING,
  TRUST_FILTER_LABEL,
  TRUST_LABEL,
  decisionImpactFor,
  issueCategoryFor,
  machineBlockLevel,
  matchesImpactFilter,
  matchesTrustFilter,
  primaryIssueFor,
  recommendedActionFor,
  sortSensorRecords,
  trustTone,
  type DecisionImpactLevel,
  type IssueCategory,
  type MachineBlockLevel,
  type TrustFilter,
} from "@/lib/data-quality";
import { humanize } from "@/lib/terminology";

const TRUST_FILTERS: TrustFilter[] = ["ALL", "TRUSTED", "NEEDS_ATTENTION", "UNTRUSTED"];
const ISSUE_FILTERS: IssueCategory[] = [
  "STALE",
  "DROPOUT",
  "DRIFT",
  "OUTLIER",
  "COMMUNICATION_LOSS",
];
const IMPACT_FILTERS: DecisionImpactLevel[] = [
  "ASSESSMENT_BLOCKED",
  "ACTION_BLOCKED",
  "CONFIDENCE_REDUCED",
];

interface MachineRef {
  id: string;
  name: string;
  asset_code: string;
  status: string;
}

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]): MachineRef[] {
  const out: MachineRef[] = [];
  if (!hierarchy) return out;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          for (const machine of line.machines) {
            out.push({
              id: machine.id,
              name: machine.name,
              asset_code: machine.asset_code,
              status: machine.status,
            });
          }
        }
      }
    }
  }
  return out;
}

function relativeTime(iso: string | null): string {
  if (!iso) return "not yet recorded";
  const ms = Date.now() - new Date(iso).getTime();
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function emptyStateFor(filters: {
  trust: TrustFilter;
  issue: IssueCategory | "";
  impact: DecisionImpactLevel | "";
  machineName: string | null;
}): { title: string; description: string } {
  const scope = filters.machineName ? ` on ${filters.machineName}` : "";
  if (filters.issue) {
    return {
      title: `No active ${ISSUE_CATEGORY_LABEL[filters.issue].toLowerCase()} issue`,
      description: `No active ${ISSUE_CATEGORY_LABEL[filters.issue].toLowerCase()} condition is present${scope}.`,
    };
  }
  if (filters.impact === "ASSESSMENT_BLOCKED") {
    return {
      title: "No condition assessment is currently blocked",
      description: `No current machine assessment is blocked by data quality${scope}.`,
    };
  }
  if (filters.impact === "ACTION_BLOCKED") {
    return {
      title: "No action is currently blocked",
      description: `No action is currently blocked by insufficient data-quality evidence${scope}.`,
    };
  }
  if (filters.impact === "CONFIDENCE_REDUCED") {
    return {
      title: "No sensor is currently reducing confidence",
      description: `No sensor is currently degrading condition confidence without fully blocking it${scope}.`,
    };
  }
  if (filters.trust === "TRUSTED") {
    return {
      title: "No trusted sensors match this filter",
      description: `No sensor evaluated as trusted matches the selected machine${scope || " filter"}.`,
    };
  }
  if (filters.trust === "UNTRUSTED") {
    return {
      title: "No sensor is currently untrusted",
      description: `No sensor is currently in a not-trustworthy state${scope}.`,
    };
  }
  if (filters.trust === "NEEDS_ATTENTION") {
    return {
      title: "No sensor currently needs attention",
      description: `Every evaluated sensor${scope} is fully trusted right now.`,
    };
  }
  return {
    title: "No sensors match the selected filters",
    description:
      "Assessment completed — no active sensor-quality limitation detected for this filter.",
  };
}

export default function DataQualityPage() {
  return (
    <Suspense fallback={null}>
      <DataQualityPageContent />
    </Suspense>
  );
}

function DataQualityPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const [trustFilter, setTrustFilterState] = useState<TrustFilter>(
    (searchParams.get("state") as TrustFilter) || "ALL",
  );
  const [issueFilter, setIssueFilterState] = useState<IssueCategory | "">(
    (searchParams.get("issue") as IssueCategory) || "",
  );
  const [impactFilter, setImpactFilterState] = useState<DecisionImpactLevel | "">(
    (searchParams.get("impact") as DecisionImpactLevel) || "",
  );
  const [machineFilter, setMachineFilterState] = useState<string>(
    searchParams.get("machine") || "",
  );
  const [expandedSensorId, setExpandedSensorId] = useState<string | null>(null);

  const pushQuery = useCallback(
    (next: Record<string, string>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(next)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const setTrustFilter = (value: TrustFilter) => {
    setTrustFilterState(value);
    pushQuery({ state: value === "ALL" ? "" : value });
  };
  const setIssueFilter = (value: IssueCategory | "") => {
    setIssueFilterState(value);
    pushQuery({ issue: value });
  };
  const setImpactFilter = (value: DecisionImpactLevel | "") => {
    setImpactFilterState(value);
    pushQuery({ impact: value });
  };
  const setMachineFilter = (value: string) => {
    setMachineFilterState(value);
    pushQuery({ machine: value });
  };

  const summary = useQualitySummary();
  const sensors = useFleetSensorQuality();
  const hierarchy = useHierarchy();
  const conditions = useFleetLatestConditions();
  const decisions = useFleetLatestDecisions();

  const machines = useMemo(() => flattenMachines(hierarchy.data), [hierarchy.data]);
  const machineById = useMemo(() => new Map(machines.map((m) => [m.id, m])), [machines]);
  const conditionByMachine = useMemo(
    () => new Map((conditions.data ?? []).map((c) => [c.machine_id, c])),
    [conditions.data],
  );
  const decisionByMachine = useMemo(
    () => new Map((decisions.data ?? []).map((d) => [d.machine_id, d])),
    [decisions.data],
  );
  const actionModeByMachine = useMemo(() => {
    const map = new Map<string, ReadinessMode>();
    for (const machine of machines) {
      const condition = conditionByMachine.get(machine.id);
      if (!condition) continue;
      map.set(
        machine.id,
        readinessModeFor(condition, decisionByMachine.get(machine.id) ?? null, machine.status),
      );
    }
    return map;
  }, [machines, conditionByMachine, decisionByMachine]);
  const blockByMachine = useMemo(() => {
    const map = new Map<string, MachineBlockLevel>();
    for (const machine of machines) {
      map.set(
        machine.id,
        machineBlockLevel(conditionByMachine.get(machine.id), actionModeByMachine.get(machine.id)),
      );
    }
    return map;
  }, [machines, conditionByMachine, actionModeByMachine]);

  const allSensors = useMemo(() => sensors.data ?? [], [sensors.data]);

  const machinesAffected = useMemo(() => {
    const byMachine = new Map<string, { trusted: number; caution: number; unusable: number }>();
    for (const record of allSensors) {
      if (!record.machine_id) continue;
      const bucket = byMachine.get(record.machine_id) ?? { trusted: 0, caution: 0, unusable: 0 };
      if (record.state.quality_state === "TRUSTED") bucket.trusted += 1;
      else if (record.state.quality_state === "USABLE_WITH_CAUTION") bucket.caution += 1;
      else bucket.unusable += 1;
      byMachine.set(record.machine_id, bucket);
    }
    return Array.from(byMachine.entries())
      .filter(([, counts]) => counts.caution + counts.unusable > 0)
      .map(([machineId, counts]) => ({
        machineId,
        machine: machineById.get(machineId) ?? null,
        counts,
        condition: conditionByMachine.get(machineId),
        block: blockByMachine.get(machineId) ?? "NONE",
      }))
      .sort((a, b) => {
        const rank = { ACTION_BLOCKED: 0, ASSESSMENT_BLOCKED: 1, NONE: 2 } as const;
        return rank[a.block] - rank[b.block] || b.counts.unusable - a.counts.unusable;
      });
  }, [allSensors, machineById, conditionByMachine, blockByMachine]);

  const trackedMachineOptions = useMemo(() => {
    const ids = new Set(
      allSensors.map((r) => r.machine_id).filter((id): id is string => Boolean(id)),
    );
    return Array.from(ids)
      .map((id) => machineById.get(id))
      .filter((m): m is MachineRef => Boolean(m))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [allSensors, machineById]);

  const enriched = useMemo(
    () =>
      allSensors.map((record) => {
        const primaryIssue = primaryIssueFor(record.active_issues);
        const impact = decisionImpactFor(
          record.state.quality_state,
          record.machine_id ? conditionByMachine.get(record.machine_id) : undefined,
          record.machine_id ? actionModeByMachine.get(record.machine_id) : undefined,
        );
        return { record, primaryIssue, impact };
      }),
    [allSensors, conditionByMachine, actionModeByMachine],
  );

  const filtered = useMemo(() => {
    return enriched.filter(({ record, primaryIssue, impact }) => {
      if (!matchesTrustFilter(record.state.quality_state, trustFilter)) return false;
      if (issueFilter) {
        if (!primaryIssue || issueCategoryFor(primaryIssue.issue_type) !== issueFilter)
          return false;
      }
      if (!matchesImpactFilter(impact.level, impactFilter)) return false;
      if (machineFilter && record.machine_id !== machineFilter) return false;
      return true;
    });
  }, [enriched, trustFilter, issueFilter, impactFilter, machineFilter]);

  const sortedRecords = useMemo(
    () =>
      sortSensorRecords(
        filtered.map((f) => f.record),
        blockByMachine,
      ),
    [filtered, blockByMachine],
  );
  const impactById = useMemo(() => {
    const map = new Map<string, ReturnType<typeof decisionImpactFor>>();
    for (const { record, impact } of enriched) map.set(record.sensor_id, impact);
    return map;
  }, [enriched]);
  const primaryIssueById = useMemo(() => {
    const map = new Map<string, SensorQualityRecordResponse["active_issues"][number] | null>();
    for (const { record, primaryIssue } of enriched) map.set(record.sensor_id, primaryIssue);
    return map;
  }, [enriched]);

  const trustedCount = summary.data?.sensors_by_quality_state?.TRUSTED ?? 0;
  const attentionCount =
    (summary.data?.sensors_by_quality_state?.USABLE_WITH_CAUTION ?? 0) +
    (summary.data?.sensors_by_quality_state?.UNUSABLE ?? 0);
  const untrustedCount = summary.data?.sensors_by_quality_state?.UNUSABLE ?? 0;
  const totalTracked = summary.data?.total_sensors_tracked ?? 0;
  const assessmentsBlockedCount = Array.from(blockByMachine.values()).filter(
    (b) => b !== "NONE",
  ).length;
  const actionsBlockedCount = Array.from(blockByMachine.values()).filter(
    (b) => b === "ACTION_BLOCKED",
  ).length;
  const mostRecentEvaluation = allSensors.reduce<string | null>((latest, r) => {
    if (!latest) return r.state.updated_at;
    return new Date(r.state.updated_at) > new Date(latest) ? r.state.updated_at : latest;
  }, null);

  const machineName = machineFilter ? (machineById.get(machineFilter)?.name ?? null) : null;
  const emptyState = emptyStateFor({
    trust: trustFilter,
    issue: issueFilter,
    impact: impactFilter,
    machineName,
  });

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-12">
      <PageHeader
        title="Data Quality"
        description="Understand whether sensor evidence is reliable enough to support machine-condition decisions. This is a trust signal for the sensors feeding the platform — not a machine-condition diagnosis."
      />

      <DataState
        isPending={summary.isPending}
        isError={summary.isError}
        error={summary.error}
        loadingLabel="Loading fleet trust summary…"
      >
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <button
              type="button"
              onClick={() => {
                setTrustFilter("TRUSTED");
                setImpactFilter("");
                setIssueFilter("");
              }}
              className={`rounded-lg border p-4 text-left transition ${trustFilter === "TRUSTED" ? "border-emerald-400 ring-1 ring-emerald-300 dark:border-emerald-600" : "border-zinc-200 dark:border-zinc-800"} bg-white dark:bg-zinc-900`}
            >
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Trusted sensors</p>
              <p className="mt-1 text-2xl font-semibold text-emerald-600 dark:text-emerald-400">
                {trustedCount}
              </p>
            </button>
            <button
              type="button"
              onClick={() => {
                setTrustFilter("NEEDS_ATTENTION");
                setImpactFilter("");
                setIssueFilter("");
              }}
              className={`rounded-lg border p-4 text-left transition ${trustFilter === "NEEDS_ATTENTION" ? "border-amber-400 ring-1 ring-amber-300 dark:border-amber-600" : "border-zinc-200 dark:border-zinc-800"} bg-white dark:bg-zinc-900`}
            >
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Needs attention</p>
              <p className="mt-1 text-2xl font-semibold text-amber-600 dark:text-amber-400">
                {attentionCount}
              </p>
            </button>
            <button
              type="button"
              onClick={() => {
                setImpactFilter("ASSESSMENT_BLOCKED");
                setTrustFilter("ALL");
                setIssueFilter("");
              }}
              className={`rounded-lg border p-4 text-left transition ${impactFilter === "ASSESSMENT_BLOCKED" ? "border-red-400 ring-1 ring-red-300 dark:border-red-600" : "border-zinc-200 dark:border-zinc-800"} bg-white dark:bg-zinc-900`}
            >
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Assessments blocked</p>
              <p className="mt-1 text-2xl font-semibold text-red-600 dark:text-red-400">
                {assessmentsBlockedCount}
              </p>
            </button>
            <button
              type="button"
              onClick={() => {
                setImpactFilter("ACTION_BLOCKED");
                setTrustFilter("ALL");
                setIssueFilter("");
              }}
              className={`rounded-lg border p-4 text-left transition ${impactFilter === "ACTION_BLOCKED" ? "border-red-400 ring-1 ring-red-300 dark:border-red-600" : "border-zinc-200 dark:border-zinc-800"} bg-white dark:bg-zinc-900`}
            >
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Action blocked</p>
              <p className="mt-1 text-2xl font-semibold text-red-600 dark:text-red-400">
                {actionsBlockedCount}
              </p>
            </button>
          </div>

          {totalTracked > 0 && (
            <div>
              <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className="h-full bg-emerald-500"
                  style={{ width: `${(trustedCount / totalTracked) * 100}%` }}
                />
                <div
                  className="h-full bg-amber-500"
                  style={{
                    width: `${((summary.data?.sensors_by_quality_state?.USABLE_WITH_CAUTION ?? 0) / totalTracked) * 100}%`,
                  }}
                />
                <div
                  className="h-full bg-red-500"
                  style={{ width: `${(untrustedCount / totalTracked) * 100}%` }}
                />
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                <span>{totalTracked} sensors evaluated</span>
                <span>·</span>
                <span>
                  {machinesAffected.length} machines affected by a data-quality limitation
                </span>
                {mostRecentEvaluation && (
                  <>
                    <span>·</span>
                    <span>Most recent evaluation {relativeTime(mostRecentEvaluation)}</span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </DataState>

      {machinesAffected.length > 0 && (
        <SectionCard title="Machines affected by data-quality limitations" tier="band">
          <ul className="flex flex-col divide-y divide-zinc-200/70 dark:divide-zinc-800">
            {machinesAffected.map(({ machineId, machine, counts, condition, block }) => (
              <li key={machineId} className="flex flex-wrap items-center gap-3 py-2.5">
                <button
                  type="button"
                  onClick={() => setMachineFilter(machineId)}
                  className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                >
                  {machine?.name ?? "Machine"}
                </button>
                <span className="text-xs text-zinc-400 dark:text-zinc-600">
                  {counts.unusable} not trustworthy · {counts.caution} use with caution
                </span>
                {condition && (
                  <span className="text-sm text-zinc-600 dark:text-zinc-400">
                    Condition confidence <ConfidenceBadge value={condition.confidence} />
                  </span>
                )}
                <span className="ml-auto flex items-center gap-2">
                  {block !== "NONE" && (
                    <StatusPill tone="error">{DECISION_IMPACT_LABEL[block]}</StatusPill>
                  )}
                  <Link
                    href={`/machines/${machineId}`}
                    className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                  >
                    Machine detail
                  </Link>
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <SectionCard
        title="Sensor-quality issues"
        actions={
          <div className="flex flex-wrap gap-2">
            <label className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
              Machine
              <select
                value={machineFilter}
                onChange={(e) => setMachineFilter(e.target.value)}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
              >
                <option value="">All machines</option>
                {trackedMachineOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <select
              value={issueFilter}
              onChange={(e) => setIssueFilter(e.target.value as IssueCategory | "")}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <option value="">All issue types</option>
              {ISSUE_FILTERS.map((cat) => (
                <option key={cat} value={cat}>
                  {ISSUE_CATEGORY_LABEL[cat]}
                </option>
              ))}
            </select>
            <select
              value={impactFilter}
              onChange={(e) => setImpactFilter(e.target.value as DecisionImpactLevel | "")}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <option value="">Any decision impact</option>
              {IMPACT_FILTERS.map((level) => (
                <option key={level} value={level}>
                  {DECISION_IMPACT_LABEL[level]}
                </option>
              ))}
            </select>
          </div>
        }
      >
        <div className="mb-3 flex flex-wrap gap-1.5">
          {TRUST_FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setTrustFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
                trustFilter === f
                  ? "bg-zinc-900 text-white ring-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 dark:ring-zinc-100"
                  : "bg-transparent text-zinc-600 ring-zinc-300 hover:bg-zinc-50 dark:text-zinc-400 dark:ring-zinc-700 dark:hover:bg-zinc-800/50"
              }`}
            >
              {TRUST_FILTER_LABEL[f]}
            </button>
          ))}
          {machineFilter && (
            <button
              type="button"
              onClick={() => setMachineFilter("")}
              className="rounded-full px-3 py-1 text-xs font-medium text-sky-600 ring-1 ring-sky-300 hover:bg-sky-50 dark:text-sky-400 dark:ring-sky-800 dark:hover:bg-sky-950/40"
            >
              {machineName} ✕
            </button>
          )}
        </div>

        <DataState
          isPending={sensors.isPending}
          isError={sensors.isError}
          error={sensors.error}
          loadingLabel="Loading sensor-quality records…"
        >
          {sortedRecords.length === 0 ? (
            <EmptyState title={emptyState.title} description={emptyState.description} />
          ) : (
            <ul className="flex flex-col divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
              {sortedRecords.map((record) => {
                const primaryIssue = primaryIssueById.get(record.sensor_id) ?? null;
                const impact = impactById.get(record.sensor_id)!;
                const machine = record.machine_id ? machineById.get(record.machine_id) : null;
                const expanded = expandedSensorId === record.sensor_id;
                return (
                  <li key={record.sensor_id} className="flex flex-col gap-2 p-4">
                    <button
                      type="button"
                      onClick={() => setExpandedSensorId(expanded ? null : record.sensor_id)}
                      className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-left"
                    >
                      <span className="min-w-[9rem]">
                        {machine ? (
                          <Link
                            href={`/machines/${machine.id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                          >
                            {machine.name}
                          </Link>
                        ) : (
                          <span className="text-zinc-400 dark:text-zinc-600">Unknown machine</span>
                        )}
                      </span>
                      <span className="text-sm text-zinc-700 dark:text-zinc-300">
                        {record.sensor_name}
                        <span className="ml-1 text-xs text-zinc-400 dark:text-zinc-600">
                          ({humanize(record.sensor_type)})
                        </span>
                      </span>
                      <StatusPill tone={trustTone(record.state.quality_state)}>
                        {TRUST_LABEL[record.state.quality_state]}
                      </StatusPill>
                      <span className="text-xs text-zinc-600 dark:text-zinc-400">
                        {primaryIssue ? humanize(primaryIssue.issue_type) : "No active issue"}
                      </span>
                      <span className="text-xs text-zinc-400 dark:text-zinc-600">
                        Last valid: {relativeTime(record.state.last_good_reading_at)}
                      </span>
                      <span className="ml-auto flex items-center gap-2">
                        {impact.level !== "NO_IMPACT" && (
                          <StatusPill
                            tone={impact.level === "CONFIDENCE_REDUCED" ? "warn" : "error"}
                          >
                            {DECISION_IMPACT_LABEL[impact.level]}
                          </StatusPill>
                        )}
                        <span className="text-xs text-sky-600 dark:text-sky-400">
                          {expanded ? "Hide detail" : "View detail"}
                        </span>
                      </span>
                    </button>

                    {expanded && (
                      <div className="mt-1 grid gap-x-6 gap-y-3 rounded-md bg-zinc-50/70 p-4 text-xs sm:grid-cols-2 dark:bg-zinc-900/40">
                        <div>
                          <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                            Trust decision
                          </p>
                          <p className="mt-0.5 text-zinc-800 dark:text-zinc-200">
                            {TRUST_LABEL[record.state.quality_state]} ·{" "}
                            {humanize(record.state.eligibility)}
                          </p>
                        </div>
                        <div>
                          <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                            Expected reporting
                          </p>
                          <p className="mt-0.5 text-zinc-800 dark:text-zinc-200">
                            {record.expected_reporting_interval_seconds
                              ? `Every ~${record.expected_reporting_interval_seconds}s`
                              : "Not configured for this signal type"}
                          </p>
                        </div>
                        <div>
                          <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                            Last trusted observation
                          </p>
                          <p className="mt-0.5 text-zinc-800 dark:text-zinc-200">
                            {record.state.last_good_reading_at
                              ? new Date(record.state.last_good_reading_at).toLocaleString()
                              : "None recorded yet"}
                          </p>
                        </div>
                        <div>
                          <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                            Recommended next step
                          </p>
                          <p className="mt-0.5 text-zinc-800 dark:text-zinc-200">
                            {primaryIssue
                              ? recommendedActionFor(primaryIssue.issue_type)
                              : "No action needed — evidence is currently trusted."}
                          </p>
                        </div>
                        <div className="sm:col-span-2">
                          <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                            Impact on downstream intelligence
                          </p>
                          <dl className="mt-1 grid grid-cols-3 gap-3">
                            <div>
                              <dt className="text-zinc-400 dark:text-zinc-600">Condition</dt>
                              <dd className="text-zinc-800 dark:text-zinc-200">
                                {impact.conditionImpact}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-zinc-400 dark:text-zinc-600">ML</dt>
                              <dd className="text-zinc-800 dark:text-zinc-200">
                                {impact.mlImpact}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-zinc-400 dark:text-zinc-600">Action readiness</dt>
                              <dd className="text-zinc-800 dark:text-zinc-200">
                                {impact.actionImpact}
                              </dd>
                            </div>
                          </dl>
                        </div>
                        {record.active_issues.length > 0 && (
                          <div className="sm:col-span-2">
                            <p className="font-semibold text-zinc-500 dark:text-zinc-400">
                              Quality evidence
                            </p>
                            <ul className="mt-1 flex flex-col gap-1.5">
                              {record.active_issues.map((issue) => (
                                <li
                                  key={issue.id}
                                  className="rounded border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-950"
                                >
                                  <p className="text-zinc-700 dark:text-zinc-300">
                                    {issue.message}
                                  </p>
                                  <p className="mt-1 text-[11px] text-zinc-400 dark:text-zinc-600">
                                    {humanize(issue.dimension)} · {humanize(issue.severity)} ·{" "}
                                    {humanize(issue.status)} · detected{" "}
                                    {new Date(issue.first_seen).toLocaleString()}
                                  </p>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <details className="sm:col-span-2">
                          <summary className="cursor-pointer font-semibold text-zinc-500 select-none dark:text-zinc-400">
                            Technical provenance
                          </summary>
                          <dl className="mt-1.5 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-600 dark:text-zinc-400">
                            <dt>sensor_id</dt>
                            <dd>{record.sensor_id}</dd>
                            <dt>sensor_code</dt>
                            <dd>{record.sensor_code}</dd>
                            <dt>quality_state</dt>
                            <dd>{record.state.quality_state}</dd>
                            <dt>eligibility</dt>
                            <dd>{record.state.eligibility}</dd>
                            <dt>staleness_status</dt>
                            <dd>{record.state.staleness_status}</dd>
                            <dt>clock_status</dt>
                            <dd>{record.state.clock_status}</dd>
                            <dt>policy_version</dt>
                            <dd>{record.state.policy_version ?? "—"}</dd>
                            {primaryIssue && (
                              <>
                                <dt>rule_id</dt>
                                <dd>{primaryIssue.rule_id}</dd>
                                <dt>rule_version</dt>
                                <dd>{primaryIssue.rule_version}</dd>
                                <dt>dimension</dt>
                                <dd>{primaryIssue.dimension}</dd>
                              </>
                            )}
                          </dl>
                        </details>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </DataState>
      </SectionCard>

      <SectionCard title="Issue-type reference">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ISSUE_FILTERS.map((cat) => (
            <div key={cat} className="flex flex-col gap-0.5">
              <dt className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                {ISSUE_CATEGORY_LABEL[cat]}
              </dt>
              <dd className="text-xs text-zinc-500 dark:text-zinc-400">
                {ISSUE_CATEGORY_MEANING[cat]}
              </dd>
            </div>
          ))}
        </dl>
      </SectionCard>
    </div>
  );
}

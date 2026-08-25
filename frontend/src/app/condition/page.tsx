"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import { ConfidenceBadge, SeverityBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { useMaintenanceCases } from "@/hooks/use-maintenance";
import { usePriorityIncident } from "@/hooks/use-priority-incident";
import {
  READINESS_MODE_LABEL,
  READINESS_MODE_TONE,
  readinessModeFor,
} from "@/lib/action-readiness";
import { componentFromName, equipmentTypeFor } from "@/lib/equipment";
import { humanize } from "@/lib/terminology";
import type { HierarchyMachine } from "@/lib/api/asset-hierarchy-types";
import type { ConditionAssessmentResponse } from "@/lib/api/intelligence-types";

const OPEN_MAINTENANCE_STATES = new Set([
  "REVIEW_REQUIRED",
  "NOT_STARTED",
  "PLANNED",
  "IN_PROGRESS",
  "AWAITING_VERIFICATION",
]);

interface ConditionRow {
  machine: HierarchyMachine;
  siteName: string;
  area: string;
  condition: ConditionAssessmentResponse | null;
}

export default function ConditionIntelligencePage() {
  return (
    <Suspense fallback={null}>
      <ConditionIntelligencePageContent />
    </Suspense>
  );
}

function ConditionIntelligencePageContent() {
  usePageTitle("Condition Intelligence");
  const hierarchy = useHierarchy();
  const conditions = useFleetLatestConditions();
  const decisions = useFleetLatestDecisions();
  const { data: incidents } = usePriorityIncident();
  const maintenance = useMaintenanceCases();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState("");

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

  const siteFilter = searchParams.get("site") ?? "";
  const areaFilter = searchParams.get("area") ?? "";
  const conditionFilter = searchParams.get("condition") ?? "";
  const confidenceFilter = searchParams.get("confidence") ?? "";
  const readinessFilter = searchParams.get("readiness") ?? "";

  const rows: ConditionRow[] = useMemo(() => {
    if (!hierarchy.data) return [];
    const conditionByMachine = new Map(
      (conditions.data ?? []).map((c) => [c.machine_id, c] as const),
    );
    const out: ConditionRow[] = [];
    for (const customer of hierarchy.data.customers) {
      for (const site of customer.sites) {
        for (const plant of site.plants) {
          for (const line of plant.production_lines) {
            for (const machine of line.machines) {
              out.push({
                machine,
                siteName: site.name,
                area: machine.area ?? "Unspecified area",
                condition: conditionByMachine.get(machine.id) ?? null,
              });
            }
          }
        }
      }
    }
    return out;
  }, [hierarchy.data, conditions.data]);

  const decisionByMachine = useMemo(
    () => new Map((decisions.data ?? []).map((d) => [d.machine_id, d])),
    [decisions.data],
  );

  const openIncidentByMachine = useMemo(() => {
    const set = new Set<string>();
    for (const incident of incidents ?? []) {
      if (incident.state !== "RESOLVED" && incident.state !== "CLOSED") {
        set.add(incident.machine_id);
      }
    }
    return set;
  }, [incidents]);

  const maintenanceStateByMachine = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of maintenance.data ?? []) {
      if (OPEN_MAINTENANCE_STATES.has(c.state)) {
        map.set(c.machine_id, c.state);
      } else if (!map.has(c.machine_id)) {
        map.set(c.machine_id, c.state);
      }
    }
    return map;
  }, [maintenance.data]);

  const areaOptions = useMemo(() => {
    const set = new Set<string>();
    for (const row of rows) set.add(row.area);
    return Array.from(set).sort();
  }, [rows]);
  const siteOptions = useMemo(() => {
    const set = new Set<string>();
    for (const row of rows) set.add(row.siteName);
    return Array.from(set).sort();
  }, [rows]);
  const conditionOptions = useMemo(() => {
    const set = new Set<string>();
    for (const row of rows) if (row.condition) set.add(row.condition.condition_type);
    return Array.from(set).sort();
  }, [rows]);

  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase();
    return rows.filter((row) => {
      if (term) {
        const haystack = `${row.machine.name} ${row.machine.asset_code}`.toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      if (siteFilter && row.siteName !== siteFilter) return false;
      if (areaFilter && row.area !== areaFilter) return false;
      if (conditionFilter && row.condition?.condition_type !== conditionFilter) return false;
      if (confidenceFilter && row.condition?.confidence !== confidenceFilter) return false;
      if (readinessFilter) {
        if (!row.condition) return false;
        const mode = readinessModeFor(
          row.condition,
          decisionByMachine.get(row.machine.id) ?? null,
          row.machine.status,
        );
        if (mode !== readinessFilter) return false;
      }
      return true;
    });
  }, [
    rows,
    search,
    siteFilter,
    areaFilter,
    conditionFilter,
    confidenceFilter,
    readinessFilter,
    decisionByMachine,
  ]);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-6 py-10 lg:px-10">
      <PageHeader
        title="Condition Intelligence"
        description="Every monitored asset's current fused condition — rules, ML, state estimation, and data quality combined into one assessment — filterable by site, area, condition, confidence, and action readiness."
      />

      <DataState
        isPending={hierarchy.isPending || conditions.isPending}
        isError={hierarchy.isError || conditions.isError}
        error={hierarchy.error ?? conditions.error}
        loadingLabel="Loading condition intelligence…"
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search machine name or asset code…"
            className="w-56 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            aria-label="Search machines"
          />
          <select
            value={siteFilter}
            onChange={(e) => pushQuery({ site: e.target.value })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            aria-label="Filter by site"
          >
            <option value="">All sites</option>
            {siteOptions.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={areaFilter}
            onChange={(e) => pushQuery({ area: e.target.value })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            aria-label="Filter by area"
          >
            <option value="">All areas</option>
            {areaOptions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <select
            value={conditionFilter}
            onChange={(e) => pushQuery({ condition: e.target.value })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            aria-label="Filter by condition"
          >
            <option value="">All conditions</option>
            {conditionOptions.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
          <select
            value={confidenceFilter}
            onChange={(e) => pushQuery({ confidence: e.target.value })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            aria-label="Filter by confidence"
          >
            <option value="">All confidence levels</option>
            {["HIGH", "MODERATE", "LOW"].map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
          <select
            value={readinessFilter}
            onChange={(e) => pushQuery({ readiness: e.target.value })}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            aria-label="Filter by action readiness"
          >
            <option value="">All action readiness</option>
            {Object.entries(READINESS_MODE_LABEL).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {filteredRows.length} of {rows.length} assets
          </span>
        </div>

        {filteredRows.length === 0 ? (
          <EmptyState
            title={rows.length === 0 ? "No machines registered yet" : "No assets match this filter"}
            description={
              rows.length === 0 ? "Commission a machine to see it here." : "Try clearing a filter."
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <th className="px-4 py-2 font-medium">Asset</th>
                  <th className="px-4 py-2 font-medium">Site / Area</th>
                  <th className="px-4 py-2 font-medium">Current condition</th>
                  <th className="px-4 py-2 font-medium">Confidence</th>
                  <th className="px-4 py-2 font-medium">Lifecycle</th>
                  <th className="px-4 py-2 font-medium">Primary evidence</th>
                  <th className="px-4 py-2 font-medium">Action readiness</th>
                  <th className="px-4 py-2 font-medium">Maintenance state</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const { machine, condition } = row;
                  // Equipment identity leads — asset/equipment name and code first,
                  // internal machine-type category never shown here (Enterprise Product
                  // Rebuild Pass 2 §10; see Technical Provenance for the raw category).
                  const equipmentType = equipmentTypeFor(
                    machine.machine_type,
                    machine.equipment_class,
                  );
                  const component = componentFromName(machine.name);
                  const readiness = condition
                    ? readinessModeFor(
                        condition,
                        decisionByMachine.get(machine.id) ?? null,
                        machine.status,
                      )
                    : null;
                  const maintState = maintenanceStateByMachine.get(machine.id);
                  return (
                    <tr
                      key={machine.id}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-2">
                        <Link
                          href={`/machines/${machine.id}`}
                          className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                        >
                          {component ? `${equipmentType} — ${component}` : machine.name}
                        </Link>
                        <div className="text-xs text-zinc-400 dark:text-zinc-600">
                          {machine.asset_code}
                          {openIncidentByMachine.has(machine.id) && (
                            <span className="ml-2 text-amber-600 dark:text-amber-400">
                              open incident
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {row.siteName} · {row.area}
                      </td>
                      <td className="px-4 py-2">
                        {condition ? (
                          <div className="flex items-center gap-1.5">
                            <SeverityBadge value={condition.severity} />
                            <span className="text-zinc-700 dark:text-zinc-300">
                              {humanize(condition.condition_type)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-zinc-400 dark:text-zinc-600">
                            Not yet assessed
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        {condition ? (
                          <ConfidenceBadge value={condition.confidence} />
                        ) : (
                          <span className="text-xs text-zinc-400 dark:text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {condition ? humanize(condition.lifecycle_state) : "—"}
                      </td>
                      <td className="max-w-xs px-4 py-2 text-xs text-zinc-600 dark:text-zinc-400">
                        {condition?.evidence_summary.why[0] ??
                          condition?.evidence_summary.what_is_happening ??
                          "—"}
                      </td>
                      <td className="px-4 py-2">
                        {readiness ? (
                          <StatusPill tone={READINESS_MODE_TONE[readiness]}>
                            {READINESS_MODE_LABEL[readiness]}
                          </StatusPill>
                        ) : (
                          <span className="text-xs text-zinc-400 dark:text-zinc-600">
                            Not assessed
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                        {maintState ? humanize(maintState) : "No open maintenance"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </DataState>
    </div>
  );
}

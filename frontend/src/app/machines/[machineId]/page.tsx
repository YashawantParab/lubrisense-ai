"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";

import { CaseContextHeader, CaseWorkflow } from "@/components/case-workflow";
import { EvidenceWhyDetails, evidenceBackingLine } from "@/components/condition-evidence";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { TelemetryChart } from "@/components/telemetry-chart";
import {
  CompatibilityBadge,
  ConfidenceBadge,
  FeedbackBadge,
  HumanReviewBadge,
  IncidentStateBadge,
  MaintenanceStateBadge,
  PriorityBadge,
  SeverityBadge,
} from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";
import { usePageTitle } from "@/hooks/use-page-title";
import { useMachineHierarchy } from "@/hooks/use-asset-hierarchy";
import { useMachineBaselines } from "@/hooks/use-baselines";
import { useMachineConfigurationChanges, useMachineDevices } from "@/hooks/use-device-management";
import { useIncidents } from "@/hooks/use-incidents";
import { useDecisionHistory, useIntelligenceView } from "@/hooks/use-intelligence";
import {
  useMaintenanceActions,
  useMaintenanceCases,
  useMaintenanceFeedback,
  useMaintenanceFindings,
} from "@/hooks/use-maintenance";
import { useMachineFindings } from "@/hooks/use-rules";
import { useLatestStateEstimates } from "@/hooks/use-state-estimation";
import { useMachineTelemetry } from "@/hooks/use-telemetry";
import {
  READINESS_MODE_LABEL,
  READINESS_MODE_TONE,
  readinessEvidenceFor,
  readinessModeFor,
} from "@/lib/action-readiness";
import { interpretState, STATE_TYPE_LABELS } from "@/lib/state-interpretation";
import { humanize, toneForStatus } from "@/lib/terminology";
import type {
  BearingResponse,
  LubricationSystemResponse,
  SensorResponse,
} from "@/lib/api/asset-hierarchy-types";
import type { DecisionAssessmentResponse } from "@/lib/api/intelligence-types";

// Pressure/flow/vibration/bearing temperature carry the story for the failure modes this
// platform models — leading with them (rather than an arbitrary/alphabetical order) means a
// reviewer sees the signals that actually explain a diagnosis first.
const SIGNAL_PRIORITY = ["PRESSURE", "FLOW", "VIBRATION_RMS", "BEARING_TEMPERATURE"];

const HORIZON_LABELS: Record<string, string> = {
  ONE_HOUR: "1 hour",
  SIX_HOURS: "6 hours",
  TWENTY_FOUR_HOURS: "24 hours",
};

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-sm text-zinc-900 dark:text-zinc-100">{value ?? "—"}</dd>
    </div>
  );
}

function BearingCard({ bearing }: { bearing: BearingResponse }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{bearing.name}</span>
        <StatusPill tone={toneForStatus(bearing.status)}>{bearing.status}</StatusPill>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span>Position: {bearing.position}</span>
        <span>Criticality: {bearing.criticality}</span>
        <span>Type: {bearing.bearing_type ?? "—"}</span>
        <span>
          {bearing.manufacturer ?? "—"} {bearing.model ?? ""}
        </span>
      </dl>
    </div>
  );
}

function LubricationSystemCard({ system }: { system: LubricationSystemResponse }) {
  return (
    <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{system.name}</span>
        <div className="flex gap-2">
          <StatusPill tone="neutral">{system.system_type}</StatusPill>
          <StatusPill tone={toneForStatus(system.status)}>{system.status}</StatusPill>
        </div>
      </div>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Commissioning: {system.commissioning_state}
      </p>
      <div className="mt-3 grid gap-2 text-xs text-zinc-600 dark:text-zinc-400 sm:grid-cols-2">
        {system.reservoirs.map((r) => (
          <div key={r.id} className="rounded border border-zinc-100 p-2 dark:border-zinc-800/60">
            Reservoir — {r.name}
            {r.capacity_demo != null && (
              <>
                {" "}
                ({r.capacity_demo} {r.capacity_unit})
              </>
            )}
          </div>
        ))}
        {system.pumps.map((p) => (
          <div key={p.id} className="rounded border border-zinc-100 p-2 dark:border-zinc-800/60">
            Pump — {p.name} {p.pump_type ? `(${p.pump_type})` : ""}
          </div>
        ))}
        {system.controllers.map((c) => (
          <div key={c.id} className="rounded border border-zinc-100 p-2 dark:border-zinc-800/60">
            Controller — {c.name}
          </div>
        ))}
        {system.distributors.map((d) => (
          <div key={d.id} className="rounded border border-zinc-100 p-2 dark:border-zinc-800/60">
            Distributor — {d.name}
          </div>
        ))}
      </div>
      {system.circuits.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Circuits</p>
          <ul className="mt-1 space-y-1">
            {system.circuits.map((circuit) => (
              <li key={circuit.id} className="text-xs text-zinc-600 dark:text-zinc-400">
                {circuit.name} ({circuit.code}) — {circuit.lubrication_points.length} lubrication
                point(s)
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SensorRow({ sensor }: { sensor: SensorResponse }) {
  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
      <td className="py-2 pr-4 font-mono text-xs text-zinc-500">{sensor.sensor_code}</td>
      <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">{sensor.name}</td>
      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{sensor.sensor_type}</td>
      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{sensor.attached_entity_type}</td>
      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{sensor.unit ?? "—"}</td>
      <td className="py-2 pr-4">
        <StatusPill tone={toneForStatus(sensor.status)}>{sensor.status}</StatusPill>
      </td>
    </tr>
  );
}

export default function MachineDetailPage({ params }: { params: Promise<{ machineId: string }> }) {
  const { machineId } = use(params);
  const hierarchy = useMachineHierarchy(machineId);
  // 2000 is the API's max (`limit: le=2000`) and is applied across *all* measurement
  // types combined for this machine, not per-type — a low limit here silently truncates
  // to only the most recent minutes of a multi-hour story once several sensors share the
  // budget, hiding the calm "healthy" baseline period a reviewer needs to see for
  // contrast (a real defect found during Phase 36's industrial visualization review).
  const telemetry = useMachineTelemetry(machineId, { limit: 2000 });
  const intelligence = useIntelligenceView(machineId);
  const incidents = useIncidents({ machineId });
  const cases = useMaintenanceCases();
  const findings = useMachineFindings(machineId);
  const stateEstimates = useLatestStateEstimates(machineId);
  const baselines = useMachineBaselines(machineId);
  const devices = useMachineDevices(machineId);
  const configChanges = useMachineConfigurationChanges(machineId);
  const [assetDetailsOpen, setAssetDetailsOpen] = useState(false);
  const [changeHistoryOpen, setChangeHistoryOpen] = useState(false);

  usePageTitle(hierarchy.data ? hierarchy.data.machine.name : "Machine");

  const activeIncident = useMemo(
    () => (incidents.data ?? []).find((i) => i.state !== "RESOLVED" && i.state !== "CLOSED"),
    [incidents.data],
  );
  // The incident Workflow Intelligence tells its story from — the open one if there is
  // one, otherwise the most recently detected one. Gating this on `activeIncident` alone
  // meant the whole panel (including the maintenance outcome and technician feedback)
  // silently disappeared the moment an incident resolved — exactly the "outcome" part of
  // the story a reviewer most needs to see.
  const relevantIncident = useMemo(() => {
    if (activeIncident) return activeIncident;
    const rows = incidents.data ?? [];
    if (rows.length === 0) return undefined;
    return [...rows].sort(
      (a, b) => new Date(b.first_detected_at).getTime() - new Date(a.first_detected_at).getTime(),
    )[0];
  }, [activeIncident, incidents.data]);
  // Prefer the case linked to the currently-open incident; otherwise the machine's most
  // recently created case — a plain "first match" silently picked a stale case once a
  // machine had accumulated more than one over its history.
  const machineCase = useMemo(() => {
    const matches = (cases.data ?? []).filter((c) => c.machine_id === machineId);
    if (matches.length === 0) return undefined;
    const linkedToActive = activeIncident
      ? matches.find((c) => c.incident_id === activeIncident.id)
      : undefined;
    if (linkedToActive) return linkedToActive;
    return [...matches].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
  }, [cases.data, machineId, activeIncident]);
  const caseFindings = useMaintenanceFindings(machineCase?.id ?? "");
  const caseActions = useMaintenanceActions(machineCase?.id ?? "");

  const readiness = useMemo(() => {
    if (!intelligence.data || !hierarchy.data) return null;
    const mode = readinessModeFor(
      intelligence.data.condition,
      intelligence.data.decision,
      hierarchy.data.machine.status,
    );
    return {
      mode,
      evidence: readinessEvidenceFor(
        intelligence.data.condition,
        intelligence.data.decision,
        hierarchy.data.machine.status,
        mode,
      ),
    };
  }, [intelligence.data, hierarchy.data]);
  const caseFeedback = useMaintenanceFeedback(machineCase?.id ?? "");

  const decisionHistory = useDecisionHistory(machineId);
  // The decision persisted closest to the incident's own detection time — i.e. "what was
  // recommended while this was actually happening", read from real history rather than
  // re-deriving it from the (now different) live condition.
  const duringIncidentDecision = useMemo(() => {
    if (!relevantIncident) return undefined;
    const target = new Date(relevantIncident.first_detected_at).getTime();
    let best: DecisionAssessmentResponse | undefined;
    let bestDiff = Infinity;
    for (const d of decisionHistory.data ?? []) {
      const diff = Math.abs(new Date(d.as_of_timestamp).getTime() - target);
      if (diff < bestDiff) {
        bestDiff = diff;
        best = d;
      }
    }
    return best;
  }, [decisionHistory.data, relevantIncident]);
  const showDecisionComparison = Boolean(
    !activeIncident &&
    relevantIncident &&
    duringIncidentDecision &&
    intelligence.data &&
    duringIncidentDecision.id !== intelligence.data.decision.id &&
    (duringIncidentDecision.recommended_action !== intelligence.data.decision.recommended_action ||
      duringIncidentDecision.priority !== intelligence.data.decision.priority),
  );

  const measurementTypes = useMemo(() => {
    const types = new Set<string>();
    for (const reading of telemetry.data ?? []) types.add(reading.measurement_type);
    return Array.from(types).sort((a, b) => {
      const ai = SIGNAL_PRIORITY.indexOf(a);
      const bi = SIGNAL_PRIORITY.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [telemetry.data]);

  const telemetryStoryMarkers = useMemo(() => {
    const markers: { label: string; iso: string; tone: "warn" | "info" | "ok" }[] = [];
    if (relevantIncident) {
      markers.push({ label: "Detected", iso: relevantIncident.first_detected_at, tone: "warn" });
    }
    if (machineCase?.started_at) {
      markers.push({ label: "Inspection started", iso: machineCase.started_at, tone: "info" });
    }
    if (machineCase?.completed_at) {
      markers.push({ label: "Maintenance complete", iso: machineCase.completed_at, tone: "info" });
    }
    if (relevantIncident?.resolved_at) {
      markers.push({ label: "Recovered", iso: relevantIncident.resolved_at, tone: "ok" });
    }
    return markers;
  }, [relevantIncident, machineCase]);

  const baselineRangeFor = (measurementType: string): [number, number] | null => {
    const profile = (baselines.data?.profiles ?? []).find(
      (p) => p.measurement_type === measurementType && p.state === "ACTIVE",
    );
    const mean = profile?.statistics?.mean;
    const std = profile?.statistics?.std;
    if (typeof mean !== "number" || typeof std !== "number") return null;
    return [mean - std, mean + std];
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-7 px-6 py-10 lg:px-10">
      <DataState
        isPending={hierarchy.isPending}
        isError={hierarchy.isError}
        error={hierarchy.error}
        loadingLabel="Loading machine…"
      >
        {hierarchy.data && (
          <>
            <PageHeader
              breadcrumbs={[
                { label: "Fleet", href: "/fleet" },
                { label: hierarchy.data.machine.name },
              ]}
              title={hierarchy.data.machine.name}
              description={`${hierarchy.data.machine.asset_code} · ${humanize(hierarchy.data.machine.machine_type)}`}
              actions={
                <>
                  <StatusPill tone={toneForStatus(hierarchy.data.machine.criticality)}>
                    {hierarchy.data.machine.criticality}
                  </StatusPill>
                  <StatusPill tone={toneForStatus(hierarchy.data.machine.status)}>
                    {hierarchy.data.machine.status}
                  </StatusPill>
                  <Link
                    href={`/assistant?machineId=${machineId}${relevantIncident ? `&incidentId=${relevantIncident.id}` : ""}`}
                    className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700"
                  >
                    Ask Assistant
                  </Link>
                </>
              }
            />

            {/* Wide current-state header — explicitly labeled "current" so it can never
                read as contradicting a past, now-resolved incident shown elsewhere on the
                page. Open band, not a bordered box: this is the page's lead statement. */}
            <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl bg-zinc-50/70 px-6 py-5 dark:bg-zinc-900/40">
              <div>
                <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
                  Current condition
                </p>
                {intelligence.data ? (
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <SeverityBadge value={intelligence.data.condition.severity} />
                    <span className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                      {humanize(intelligence.data.condition.condition_type)}
                    </span>
                    <ConfidenceBadge value={intelligence.data.condition.confidence} />
                  </div>
                ) : (
                  <p className="mt-1 text-lg text-zinc-500 dark:text-zinc-400">
                    {intelligence.isPending ? "Computing…" : "Unavailable"}
                  </p>
                )}
              </div>
              {intelligence.data && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Data trust</p>
                  <p className="mt-1 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                    {humanize(intelligence.data.condition.evidence_summary.data_trustworthiness)}
                  </p>
                </div>
              )}
              {readiness && (
                <div>
                  <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
                    Can the system take action?
                  </p>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusPill tone={READINESS_MODE_TONE[readiness.mode]}>
                      {READINESS_MODE_LABEL[readiness.mode]}
                    </StatusPill>
                  </div>
                </div>
              )}
              {activeIncident ? (
                <Link
                  href={`/incidents/${activeIncident.id}`}
                  className="ml-auto flex items-center gap-1.5 text-sm text-sky-700 hover:underline dark:text-sky-400"
                >
                  Active incident <IncidentStateBadge value={activeIncident.state} />
                </Link>
              ) : (
                relevantIncident && (
                  <Link
                    href={`/incidents/${relevantIncident.id}`}
                    className="ml-auto flex items-center gap-1.5 text-sm text-zinc-500 hover:underline dark:text-zinc-400"
                  >
                    Recent event: {relevantIncident.title}{" "}
                    <IncidentStateBadge value={relevantIncident.state} />
                  </Link>
                )
              )}
            </div>

            {/* An active incident's `incident_type` only updates when `IncidentService`
                re-correlates it against a new condition — this platform's condition
                re-assessment (above) and that correlation aren't wired to run in lockstep,
                so the two can legitimately disagree for a period while the incident is
                still open. Silently juxtaposing "Current condition: Normal Operation" next
                to an open "Pump Performance Degradation" incident would misrepresent the
                machine — this note is real, computed from the same two persisted fields
                displayed above, not a guess. */}
            {activeIncident &&
              intelligence.data &&
              activeIncident.incident_type !== intelligence.data.condition.condition_type && (
                <p className="-mt-4 text-xs text-amber-600 dark:text-amber-400">
                  This incident was opened for {humanize(activeIncident.incident_type)}; the
                  machine&rsquo;s condition has since re-assessed as{" "}
                  {humanize(intelligence.data.condition.condition_type)}. The incident stays open
                  until a technician reviews and resolves it.
                </p>
              )}

            {relevantIncident && (
              <CaseContextHeader incidentId={relevantIncident.id} active="machine" />
            )}

            {relevantIncident && (
              <SectionCard title="Case journey">
                <CaseWorkflow
                  incidentId={relevantIncident.id}
                  variant="rich"
                  currentStage={activeIncident ? "incident" : "verified"}
                />
              </SectionCard>
            )}

            {/* Telemetry — moved ahead of the intelligence panels: the evidence itself,
                not just the system's read of it. Pressure leads, full width; the rest
                supports it in a compact grid (SIGNAL_PRIORITY already orders pressure
                first). */}
            <SectionCard title="Telemetry">
              <DataState
                isPending={telemetry.isPending}
                isError={telemetry.isError}
                error={telemetry.error}
                loadingLabel="Loading telemetry…"
              >
                {measurementTypes.length === 0 ? (
                  <EmptyState
                    title="No telemetry received yet"
                    description="Start the edge/simulator and telemetry pipeline to see readings here."
                  />
                ) : (
                  <div className="flex flex-col gap-4">
                    <TelemetryChart
                      measurementType={measurementTypes[0]}
                      readings={telemetry.data ?? []}
                      baselineRange={baselineRangeFor(measurementTypes[0])}
                      storyMarkers={telemetryStoryMarkers}
                      tall
                    />
                    {measurementTypes.length > 1 && (
                      <div className="grid gap-4 sm:grid-cols-2">
                        {measurementTypes.slice(1).map((type) => (
                          <TelemetryChart
                            key={type}
                            measurementType={type}
                            readings={telemetry.data ?? []}
                            baselineRange={baselineRangeFor(type)}
                            storyMarkers={telemetryStoryMarkers}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </DataState>
            </SectionCard>

            {/* Three intelligence layers */}
            <div className="grid gap-4 lg:grid-cols-3">
              <SectionCard
                title="Machine Intelligence"
                className="border-l-2 border-l-sky-200 pl-4 dark:border-l-sky-900/60"
              >
                <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                  What the machine&rsquo;s raw evidence sources report.
                </p>
                {Object.keys(stateEstimates.data ?? {}).length > 0 && (
                  <div className="mb-3 flex flex-col gap-3 border-b border-zinc-100 pb-3 dark:border-zinc-800">
                    {Object.entries(stateEstimates.data ?? {}).map(([stateType, estimate]) => {
                      const unavailable =
                        estimate.prediction_only || estimate.uncertainty === "HIGH";
                      const interpretation = interpretState(estimate.trend, estimate.state_value, {
                        unavailable,
                      });
                      return (
                        <div key={stateType} className="text-sm">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-zinc-600 dark:text-zinc-400">
                              {STATE_TYPE_LABELS[stateType] ?? humanize(stateType)}
                            </span>
                            <StatusPill tone={interpretation.tone}>
                              {interpretation.headline}
                            </StatusPill>
                          </div>
                          <p className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-600">
                            {unavailable
                              ? "Insufficient recent observations"
                              : `Supporting: condition index ${estimate.state_value.toFixed(2)} (0 = normal · 1 = severely degraded)`}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
                <dl className="grid gap-2 text-sm">
                  <div className="flex items-center justify-between">
                    <dt className="text-zinc-500 dark:text-zinc-400">Rule findings</dt>
                    <dd>{findings.data?.findings.length ?? 0} active</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-zinc-500 dark:text-zinc-400">ML evidence</dt>
                    <dd>{intelligence.data?.condition.ml_result_ids.length ?? 0} result(s)</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-zinc-500 dark:text-zinc-400">Baseline readiness</dt>
                    <dd>{baselines.data?.readiness.label ?? "—"}</dd>
                  </div>
                </dl>
                {(findings.data?.findings.length ?? 0) > 0 && (
                  <ul className="mt-3 space-y-1 border-t border-zinc-100 pt-2 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                    {findings.data!.findings.slice(0, 3).map((f) => (
                      <li key={f.id} className="flex items-center justify-between gap-2">
                        <span>{humanize(f.finding_type)}</span>
                        <SeverityBadge value={f.severity} />
                      </li>
                    ))}
                  </ul>
                )}
              </SectionCard>

              <SectionCard title="Decision Intelligence" tier="band">
                <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {activeIncident
                    ? "The synthesized diagnosis, its confidence, and the recommended response for the active issue below."
                    : "The current recommendation, based on the machine's condition right now."}
                </p>
                {intelligence.data ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 pb-2 dark:border-zinc-800">
                      <SeverityBadge value={intelligence.data.condition.severity} />
                      <ConfidenceBadge value={intelligence.data.condition.confidence} />
                    </div>
                    {showDecisionComparison && duringIncidentDecision && (
                      <div className="flex flex-col gap-0.5 border-b border-zinc-100 pb-2 text-sm dark:border-zinc-800">
                        <span className="text-zinc-500 dark:text-zinc-400">
                          During incident:{" "}
                          <span className="text-zinc-700 dark:text-zinc-300">
                            {humanize(duringIncidentDecision.recommended_action)}
                          </span>{" "}
                          — {humanize(duringIncidentDecision.priority)}
                        </span>
                      </div>
                    )}
                    <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                      {showDecisionComparison ? "Current: " : ""}
                      {humanize(intelligence.data.decision.recommended_action)}
                    </p>
                    {!activeIncident && relevantIncident && !showDecisionComparison && (
                      <p className="text-xs text-zinc-400 dark:text-zinc-600">
                        This reflects the machine&rsquo;s condition now — see Workflow Intelligence
                        below for what was recommended during the recent incident.
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-2">
                      <PriorityBadge value={intelligence.data.decision.priority} />
                      {intelligence.data.decision.human_review_required && <HumanReviewBadge />}
                    </div>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      Window: {humanize(intelligence.data.decision.recommended_window)}
                    </p>
                    <p className="text-sm text-zinc-700 dark:text-zinc-300">
                      Risk if deferred: {intelligence.data.decision.risk_if_deferred}
                    </p>
                    {readiness && (
                      <details className="border-t border-zinc-100 pt-2 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                        <summary className="cursor-pointer font-medium text-sky-600 select-none dark:text-sky-400">
                          Why: {READINESS_MODE_LABEL[readiness.mode]}
                        </summary>
                        <dl className="mt-1.5 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
                          {readiness.evidence.map((item) => (
                            <div key={item.label} className="contents">
                              <dt className="text-zinc-400 dark:text-zinc-600">{item.label}:</dt>
                              <dd className="text-zinc-700 dark:text-zinc-300">{item.value}</dd>
                            </div>
                          ))}
                        </dl>
                        <Link
                          href="/action-readiness"
                          className="mt-1.5 inline-block text-sky-600 hover:underline dark:text-sky-400"
                        >
                          View fleet action readiness →
                        </Link>
                      </details>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    {intelligence.isPending ? "Computing…" : "No decision available yet."}
                  </p>
                )}
              </SectionCard>

              <SectionCard
                title="Workflow Intelligence"
                className="border-l-2 border-l-emerald-200 pl-4 dark:border-l-emerald-900/60"
              >
                <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                  Incident and maintenance response — human-controlled, end to end.
                </p>
                {relevantIncident ? (
                  <div className="flex flex-col gap-2 text-sm">
                    <p className="text-xs font-medium text-zinc-400 dark:text-zinc-600">
                      {activeIncident ? "Active incident" : "Most recent incident"}
                    </p>
                    <div className="flex items-center justify-between gap-2">
                      <Link
                        href={`/incidents/${relevantIncident.id}`}
                        className="text-sky-700 hover:underline dark:text-sky-400"
                      >
                        {relevantIncident.title}
                      </Link>
                      <IncidentStateBadge value={relevantIncident.state} />
                    </div>
                    {machineCase ? (
                      <div className="flex flex-col gap-2 border-t border-zinc-100 pt-2 dark:border-zinc-800">
                        <div className="flex items-center justify-between gap-2">
                          <Link
                            href={`/maintenance/${machineCase.id}`}
                            className="text-sky-700 hover:underline dark:text-sky-400"
                          >
                            {humanize(machineCase.recommended_action)}
                          </Link>
                          <MaintenanceStateBadge value={machineCase.state} />
                        </div>
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">
                          {caseFindings.data?.length ?? 0} technician finding(s) ·{" "}
                          {caseActions.data?.length ?? 0} action(s) recorded
                        </p>
                        {caseFeedback.data && (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-zinc-500 dark:text-zinc-400">
                              Outcome:
                            </span>
                            <FeedbackBadge value={caseFeedback.data.classification} />
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="border-t border-zinc-100 pt-2 text-xs text-zinc-400 dark:border-zinc-800 dark:text-zinc-600">
                        No maintenance case opened yet.
                      </p>
                    )}
                  </div>
                ) : (
                  <EmptyState
                    title="No incidents on record"
                    description="This machine has no incident history yet."
                  />
                )}
              </SectionCard>
            </div>

            {/* Forecast */}
            {intelligence.data && (
              <SectionCard title="What may happen next?">
                {intelligence.data.prognostics.length === 0 ? (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    No forecast is available yet — no state estimate has been computed for this
                    machine.
                  </p>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2">
                    {Object.entries(
                      intelligence.data.prognostics.reduce<
                        Record<string, typeof intelligence.data.prognostics>
                      >((acc, row) => {
                        (acc[row.state_type] ??= []).push(row);
                        return acc;
                      }, {}),
                    ).map(([stateType, rows]) => (
                      <div key={stateType}>
                        <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                          {humanize(stateType)}
                        </p>
                        <ul className="mt-2 space-y-1.5 text-sm">
                          {rows.map((row) => (
                            <li key={row.id} className="flex items-center justify-between gap-2">
                              <span className="text-zinc-600 dark:text-zinc-400">
                                {HORIZON_LABELS[row.horizon] ?? row.horizon}
                              </span>
                              {row.status === "NO_RELIABLE_FORECAST" ? (
                                <StatusPill tone="neutral">No reliable forecast</StatusPill>
                              ) : (
                                <span className="font-mono text-xs text-zinc-800 dark:text-zinc-200">
                                  {row.predicted_state_at_horizon.toFixed(3)}
                                  {row.estimated_threshold_crossing_time && (
                                    <span className="ml-1 text-amber-600 dark:text-amber-400">
                                      (est. crossing{" "}
                                      {new Date(
                                        row.estimated_threshold_crossing_time,
                                      ).toLocaleString()}
                                      )
                                    </span>
                                  )}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  Estimated trend extrapolation only — never a guarantee of future failure.
                </p>
              </SectionCard>
            )}

            {/* Evidence panel */}
            {intelligence.data && (
              <SectionCard title="Evidence">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">
                  {evidenceBackingLine(intelligence.data.condition)}
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                      Data trust
                    </dt>
                    <dd className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                      {humanize(intelligence.data.condition.evidence_summary.data_trustworthiness)}
                    </dd>
                  </div>
                  {intelligence.data.condition.evidence_summary.unknowns.length > 0 && (
                    <div>
                      <dt className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Unknowns
                      </dt>
                      <dd className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                        <ul className="list-inside list-disc space-y-1">
                          {intelligence.data.condition.evidence_summary.unknowns.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </dd>
                    </div>
                  )}
                </div>
                <EvidenceWhyDetails why={intelligence.data.condition.evidence_summary.why}>
                  <p className="text-zinc-700 dark:text-zinc-300">
                    {intelligence.data.condition.evidence_summary.what_is_happening}
                  </p>
                  {intelligence.data.condition.evidence_summary.supporting_evidence.length > 0 && (
                    <div>
                      <p className="font-medium text-zinc-700 dark:text-zinc-300">
                        Supporting evidence
                      </p>
                      <ul className="mt-1 list-inside list-disc">
                        {intelligence.data.condition.evidence_summary.supporting_evidence.map(
                          (e) => (
                            <li key={e}>{e}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}
                  {intelligence.data.condition.evidence_summary.contradicting_evidence.length >
                    0 && (
                    <div>
                      <p className="font-medium text-zinc-700 dark:text-zinc-300">
                        Contradicting evidence
                      </p>
                      <ul className="mt-1 list-inside list-disc">
                        {intelligence.data.condition.evidence_summary.contradicting_evidence.map(
                          (e) => (
                            <li key={e}>{e}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}
                  {intelligence.data.condition.limitations.length > 0 && (
                    <div>
                      <p className="font-medium text-zinc-700 dark:text-zinc-300">Limitations</p>
                      <ul className="mt-1 list-inside list-disc">
                        {intelligence.data.condition.limitations.map((l) => (
                          <li key={l}>{l}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p>Policy version: {intelligence.data.condition.policy_version}</p>
                  <p>Engine version: {intelligence.data.condition.engine_version}</p>
                  <p>Condition id: {intelligence.data.condition.id}</p>
                </EvidenceWhyDetails>
              </SectionCard>
            )}

            {/* Telemetry */}
            {/* Device / configuration governance — Phase 31: visibility only, no OTA */}
            <SectionCard
              title="Device / Configuration"
              actions={
                (configChanges.data ?? []).length > 0 && (
                  <button
                    type="button"
                    onClick={() => setChangeHistoryOpen((v) => !v)}
                    className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                  >
                    {changeHistoryOpen ? "Hide" : "Show"} change history
                  </button>
                )
              }
            >
              <DataState
                isPending={devices.isPending}
                isError={devices.isError}
                error={devices.error}
                loadingLabel="Loading device configuration…"
              >
                {(devices.data ?? []).length === 0 ? (
                  <EmptyState
                    title="No device configuration recorded yet"
                    description="Device/firmware provenance is captured when a gateway or sensor is registered during commissioning."
                  />
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                          <th className="py-2 pr-4 font-medium">Device</th>
                          <th className="py-2 pr-4 font-medium">Firmware</th>
                          <th className="py-2 pr-4 font-medium">Compatibility</th>
                          <th className="py-2 pr-4 font-medium">Captured</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(devices.data ?? []).map((d) => (
                          <tr
                            key={d.id}
                            className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                          >
                            <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">
                              {humanize(d.device_type)}
                            </td>
                            <td className="py-2 pr-4 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                              {d.firmware_version ?? "—"}
                            </td>
                            <td className="py-2 pr-4">
                              <CompatibilityBadge value={d.compatibility_status} />
                            </td>
                            <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                              <RelativeTime iso={d.captured_at} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </DataState>

              {changeHistoryOpen && (
                <ul className="mt-4 space-y-2 border-t border-zinc-100 pt-3 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                  {(configChanges.data ?? []).map((c) => (
                    <li key={c.id} className="flex items-start justify-between gap-2">
                      <span>
                        {humanize(c.device_type)} configuration changed by {c.changed_by}
                        {c.reason ? ` — ${c.reason}` : ""}
                        {c.baseline_review_required && (
                          <span className="ml-2 text-amber-600 dark:text-amber-400">
                            (baseline review recommended)
                          </span>
                        )}
                      </span>
                      <RelativeTime iso={c.occurred_at} />
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>

            {/* Asset details, collapsible */}
            <SectionCard
              title="Asset details"
              actions={
                <button
                  type="button"
                  onClick={() => setAssetDetailsOpen((v) => !v)}
                  className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                >
                  {assetDetailsOpen ? "Hide" : "Show"}
                </button>
              }
            >
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Field label="Manufacturer" value={hierarchy.data.machine.manufacturer} />
                <Field label="Model" value={hierarchy.data.machine.model} />
                <Field label="Serial (demo)" value={hierarchy.data.machine.serial_number_demo} />
                <Field label="Installed" value={hierarchy.data.machine.installation_date} />
              </dl>

              {assetDetailsOpen && (
                <div className="mt-4 flex flex-col gap-6">
                  <div>
                    <h3 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      Bearings ({hierarchy.data.bearings.length})
                    </h3>
                    {hierarchy.data.bearings.length === 0 ? (
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        No bearings recorded for this machine yet.
                      </p>
                    ) : (
                      <div className="grid gap-2 sm:grid-cols-2">
                        {hierarchy.data.bearings.map((bearing) => (
                          <BearingCard key={bearing.id} bearing={bearing} />
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      Lubrication system
                    </h3>
                    {hierarchy.data.lubrication_systems.length === 0 ? (
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        No lubrication system commissioned for this machine yet.
                      </p>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {hierarchy.data.lubrication_systems.map((system) => (
                          <LubricationSystemCard key={system.id} system={system} />
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      Sensor inventory ({hierarchy.data.sensors.length})
                    </h3>
                    {hierarchy.data.sensors.length === 0 ? (
                      <p className="text-sm text-zinc-500 dark:text-zinc-400">
                        No sensors attached anywhere on this machine yet.
                      </p>
                    ) : (
                      <div className="overflow-x-auto rounded-lg border border-zinc-200 px-4 dark:border-zinc-800">
                        <table className="w-full text-left text-sm">
                          <thead>
                            <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                              <th className="py-2 pr-4 font-medium">Code</th>
                              <th className="py-2 pr-4 font-medium">Name</th>
                              <th className="py-2 pr-4 font-medium">Type</th>
                              <th className="py-2 pr-4 font-medium">Attached to</th>
                              <th className="py-2 pr-4 font-medium">Unit</th>
                              <th className="py-2 pr-4 font-medium">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {hierarchy.data.sensors.map((sensor) => (
                              <SensorRow key={sensor.id} sensor={sensor} />
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </SectionCard>

            <p className="text-xs text-zinc-400 dark:text-zinc-600">
              Last computed{" "}
              <RelativeTime iso={intelligence.data?.condition.as_of_timestamp ?? null} />
            </p>
          </>
        )}
      </DataState>
    </div>
  );
}

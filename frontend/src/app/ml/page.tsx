"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { ConfidenceBadge, ModelStatusBadge, SeverityBadge } from "@/components/badges";
import { ConfusionMatrix, PerClassPerformance } from "@/components/ml/confusion-matrix";
import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { EvidenceFusionDiagram, type FusionSource } from "@/components/evidence-fusion-diagram";
import { FeatureEvidence } from "@/components/ml/feature-evidence";
import { PageHeader } from "@/components/page-header";
import { ProbabilityBars } from "@/components/ml/probability-bars";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useFleetLatestConditions, useFleetLatestDecisions } from "@/hooks/use-intelligence";
import { useFleetLatestML, useModel, useModels } from "@/hooks/use-ml";
import {
  dataTrustFusionStrength,
  machineMlFusionStrength,
  ruleEvidenceStrength,
  stateEstimateStrength,
} from "@/lib/evidence-fusion";
import {
  classificationConditionHint,
  failureLabelName,
  humanizeFeatureName,
  ML_ROLE_LABEL,
  mlRoleFor,
  modelDisplayName,
} from "@/lib/ml-terminology";
import { humanize, SERVABLE_MODEL_STATUSES } from "@/lib/terminology";
import type { HierarchyMachine } from "@/lib/api/asset-hierarchy-types";
import type {
  ClassificationReport,
  FeatureContribution,
  MLInferenceResultResponse,
} from "@/lib/api/ml-types";

function flattenMachines(hierarchy: ReturnType<typeof useHierarchy>["data"]): HierarchyMachine[] {
  if (!hierarchy) return [];
  const out: HierarchyMachine[] = [];
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          out.push(...line.machines);
        }
      }
    }
  }
  return out;
}

function contributionsFrom(explanation: Record<string, unknown>): FeatureContribution[] {
  const raw = explanation["top_contributing_features"];
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (c): c is FeatureContribution =>
      typeof c === "object" && c !== null && "feature" in c && "magnitude" in c,
  );
}

/** Extracts just the ML-sourced bullets from a condition's real evidence "why" array
 * (`ConditionEngine._evidence_from_ml_result`'s own `description` text, e.g. "ML
 * classifier FAILURE_CLASSIFICATION_V1@1.0.0 (EXPERIMENT): predicted_class=...") — never
 * a separate invented summary of what ML contributed. */
function mlWhyLines(why: string[]): string[] {
  return why.filter((line) => line.startsWith("ML classifier") || line.startsWith("ML anomaly"));
}

const PIPELINE_STAGES = [
  { label: "Signals", detail: "Pressure, flow, pump current, reservoir, vibration, bearing temp" },
  { label: "Features", detail: "Trend, deviation, context-relative behavior" },
  { label: "ML", detail: "Anomaly detection + failure-pattern classification" },
  { label: "Condition", detail: "Fused with rules, state estimation, data trust" },
  { label: "Decision", detail: "A recommended action, gated by confidence" },
  { label: "Action", detail: "Readiness mode — human-approved, never automatic" },
];

function MLPageInner() {
  const searchParams = useSearchParams();
  const hierarchy = useHierarchy();
  const models = useModels();
  const fleetML = useFleetLatestML();
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
  const resultsByMachine = useMemo(() => {
    const map = new Map<string, MLInferenceResultResponse[]>();
    for (const r of fleetML.data ?? []) {
      const list = map.get(r.machine_id) ?? [];
      list.push(r);
      map.set(r.machine_id, list);
    }
    return map;
  }, [fleetML.data]);

  const machinesWithEvidence = useMemo(
    () => machines.filter((m) => (resultsByMachine.get(m.id)?.length ?? 0) > 0),
    [machines, resultsByMachine],
  );

  const [machineId, setMachineId] = useState(searchParams.get("machineId") ?? "");
  const effectiveMachineId = machineId || machinesWithEvidence[0]?.id || machines[0]?.id || "";
  const selectedMachine = machineById.get(effectiveMachineId);
  const selectedResults = useMemo(
    () => resultsByMachine.get(effectiveMachineId) ?? [],
    [resultsByMachine, effectiveMachineId],
  );
  const selectedCondition = conditionByMachine.get(effectiveMachineId);
  const selectedDecision = decisionByMachine.get(effectiveMachineId);

  const anomalyResult = selectedResults.find((r) => r.result_kind === "ANOMALY") ?? null;
  const classificationResults = selectedResults.filter((r) => r.result_kind === "CLASSIFICATION");
  const [selectedClassifierId, setSelectedClassifierId] = useState("");
  const effectiveClassifier =
    classificationResults.find((r) => r.model_id === selectedClassifierId) ??
    classificationResults.find((r) => r.model_id === "FAILURE_CLASSIFICATION_BASELINE_V1") ??
    classificationResults[0] ??
    null;

  const modelStatusById = useMemo(
    () => new Map((models.data ?? []).map((m) => [m.model_id, m.status])),
    [models.data],
  );

  const fusionSources: FusionSource[] | null = useMemo(() => {
    if (!selectedCondition) return null;
    return [
      { label: "Physical / rule evidence", strength: ruleEvidenceStrength(selectedCondition) },
      { label: "State estimation", strength: stateEstimateStrength(selectedCondition) },
      {
        label: "ML evidence",
        strength: machineMlFusionStrength(selectedResults, selectedCondition, modelStatusById),
      },
      {
        label: "Data trust",
        strength: dataTrustFusionStrength(selectedCondition.evidence_summary.data_trustworthiness),
      },
    ];
  }, [selectedCondition, selectedResults, modelStatusById]);

  const sortedModels = useMemo(
    () => [...(models.data ?? [])].sort((a, b) => a.model_id.localeCompare(b.model_id)),
    [models.data],
  );
  const [selectedModelId, setSelectedModelId] = useState("");
  const effectiveModelId = selectedModelId || sortedModels[0]?.model_id || "";
  const detail = useModel(effectiveModelId);
  const classifierReport =
    detail.data && "test_report" in detail.data.metrics
      ? (detail.data.metrics.test_report as ClassificationReport)
      : null;

  // Fleet-wide "what ML is detecting now" — every count traces to a persisted
  // MLInferenceResult, never a frontend-invented number.
  const summary = useMemo(() => {
    const allResults = fleetML.data ?? [];
    // Raw record counts (not distinct machines) — the same grain as "24 scored, 3
    // insufficient-features" reported from the persisted MLInferenceResult table.
    const scored = allResults.filter((r) => r.status === "OK").length;
    const insufficientFeatures = allResults.filter(
      (r) => r.status === "INSUFFICIENT_FEATURES",
    ).length;
    const machinesScored = new Set(
      allResults.filter((r) => r.status === "OK").map((r) => r.machine_id),
    ).size;
    const machinesBlocked = new Set(
      allResults.filter((r) => r.status === "INSUFFICIENT_FEATURES").map((r) => r.machine_id),
    ).size;
    const anomalous = allResults.filter((r) => r.result_kind === "ANOMALY" && r.anomalous).length;
    const classified = allResults.filter(
      (r) => r.result_kind === "CLASSIFICATION" && r.status === "OK",
    ).length;
    const highConfidence = allResults.filter((r) => r.confidence_category === "HIGH").length;
    const supportingCondition = (conditions.data ?? []).filter(
      (c) => c.ml_result_ids.length > 0,
    ).length;
    return {
      scored,
      insufficientFeatures,
      machinesScored,
      machinesBlocked,
      anomalous,
      classified,
      highConfidence,
      supportingCondition,
    };
  }, [fleetML.data, conditions.data]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10 lg:px-10">
      <PageHeader
        title="Machine Learning Intelligence"
        description="ML detects multivariable lubrication and machine-condition patterns that may not be visible from individual sensor thresholds. Predictions become evidence for Condition Intelligence and are gated by data quality, model maturity, and other trusted evidence — never a maintenance decision on their own."
      />

      <div className="flex flex-col gap-1 text-sm text-zinc-700 sm:flex-row sm:items-stretch sm:gap-0 dark:text-zinc-300">
        {PIPELINE_STAGES.map((stage, index, arr) => (
          <div key={stage.label} className="flex flex-1 items-stretch">
            <div
              className={`flex-1 rounded-md p-3 ${
                stage.label === "ML"
                  ? "bg-sky-50 ring-1 ring-sky-200 dark:bg-sky-500/10 dark:ring-sky-800"
                  : "bg-zinc-50/70 dark:bg-zinc-900/40"
              }`}
            >
              <p
                className={`text-xs font-semibold tracking-wide uppercase ${
                  stage.label === "ML"
                    ? "text-sky-700 dark:text-sky-400"
                    : "text-zinc-500 dark:text-zinc-400"
                }`}
              >
                {stage.label}
              </p>
              <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{stage.detail}</p>
            </div>
            {index < arr.length - 1 && (
              <div className="flex w-5 shrink-0 items-center justify-center text-zinc-300 dark:text-zinc-700">
                →
              </div>
            )}
          </div>
        ))}
      </div>

      {/* A. What ML is doing now */}
      <DataState isPending={fleetML.isPending} isError={fleetML.isError} error={fleetML.error}>
        <div className="flex flex-wrap items-baseline gap-x-10 gap-y-3 border-y border-zinc-100 py-4 dark:border-zinc-800/70">
          {[
            ["Scored ML assessments", summary.scored],
            ["Insufficient-feature assessments", summary.insufficientFeatures],
            ["Machines with active ML evidence", summary.machinesScored],
            ["Machines where ML was blocked", summary.machinesBlocked],
            ["Elevated anomaly evidence", summary.anomalous],
            ["Classified with a pattern", summary.classified],
            ["High-confidence results", summary.highConfidence],
            ["Currently supporting a condition", summary.supportingCondition],
          ].map(([label, value]) => (
            <div key={label as string} className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                {value}
              </span>
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
            </div>
          ))}
        </div>
      </DataState>

      {/* B. Machine ML Analysis */}
      <SectionCard
        title="Machine ML analysis"
        actions={
          <label className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            Machine
            <select
              value={effectiveMachineId}
              onChange={(event) => {
                setMachineId(event.target.value);
                setSelectedClassifierId("");
              }}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              {machines.map((machine) => (
                <option key={machine.id} value={machine.id}>
                  {machine.name}
                  {(resultsByMachine.get(machine.id)?.length ?? 0) === 0 ? " (no ML evidence)" : ""}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {!selectedMachine ? (
          <EmptyState title="No machine selected" description="Choose a machine above." />
        ) : (
          <div className="flex flex-col gap-6">
            <div className="grid grid-cols-2 gap-4 border-b border-zinc-100 pb-4 sm:grid-cols-4 dark:border-zinc-800">
              <div>
                <p className="text-xs text-zinc-400 dark:text-zinc-600">Current condition</p>
                <p className="mt-0.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {selectedCondition
                    ? humanize(selectedCondition.condition_type)
                    : "Not yet assessed"}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-400 dark:text-zinc-600">Data trust</p>
                <p className="mt-0.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {selectedCondition
                    ? humanize(selectedCondition.evidence_summary.data_trustworthiness)
                    : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-400 dark:text-zinc-600">Current recommendation</p>
                <p className="mt-0.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {selectedDecision
                    ? humanize(selectedDecision.recommended_action)
                    : "Not yet decided"}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-400 dark:text-zinc-600">ML evidence status</p>
                <p className="mt-0.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {selectedResults.length === 0
                    ? "None"
                    : selectedResults.some((r) => r.status === "INSUFFICIENT_FEATURES")
                      ? "Blocked (some models)"
                      : "Available"}
                </p>
              </div>
            </div>

            {selectedResults.length === 0 ? (
              <EmptyState
                title="No ML evidence for this machine"
                description="No model has produced a persisted inference result for this machine yet. This is expected for machines outside the curated fleet, or before the ML pipeline has run."
              />
            ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                {/* Classification card */}
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                      Failure pattern classification
                    </h3>
                    {classificationResults.length > 1 && (
                      <select
                        value={effectiveClassifier?.model_id ?? ""}
                        onChange={(e) => setSelectedClassifierId(e.target.value)}
                        className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                      >
                        {classificationResults.map((r) => (
                          <option key={r.model_id} value={r.model_id}>
                            {modelDisplayName(r.model_id)}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  {!effectiveClassifier ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      No classifier result for this machine.
                    </p>
                  ) : (
                    <ClassificationCard
                      result={effectiveClassifier}
                      machineId={effectiveMachineId}
                      modelServable={
                        modelStatusById.has(effectiveClassifier.model_id)
                          ? SERVABLE_MODEL_STATUSES.has(
                              modelStatusById.get(effectiveClassifier.model_id) as string,
                            )
                          : false
                      }
                      conditionType={selectedCondition?.condition_type ?? null}
                      includedInCondition={
                        selectedCondition?.ml_result_ids.includes(effectiveClassifier.id) ?? false
                      }
                    />
                  )}
                </div>

                {/* Anomaly card */}
                <div className="flex flex-col gap-3">
                  <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                    Anomaly detection
                  </h3>
                  {!anomalyResult ? (
                    <p className="text-sm text-zinc-500 dark:text-zinc-400">
                      No anomaly-model result for this machine.
                    </p>
                  ) : (
                    <AnomalyCard
                      result={anomalyResult}
                      machineId={effectiveMachineId}
                      modelServable={
                        modelStatusById.has(anomalyResult.model_id)
                          ? SERVABLE_MODEL_STATUSES.has(
                              modelStatusById.get(anomalyResult.model_id) as string,
                            )
                          : false
                      }
                      includedInCondition={
                        selectedCondition?.ml_result_ids.includes(anomalyResult.id) ?? false
                      }
                    />
                  )}
                </div>
              </div>
            )}

            {/* C. Evidence fusion */}
            {selectedCondition && (
              <div className="border-t border-zinc-100 pt-5 dark:border-zinc-800">
                <h3 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  Evidence fusion — how ML affects the condition
                </h3>
                {fusionSources && (
                  <div className="mb-4">
                    <EvidenceFusionDiagram
                      sources={fusionSources}
                      conditionLabel={humanize(selectedCondition.condition_type)}
                      decisionLabel={
                        selectedDecision ? humanize(selectedDecision.recommended_action) : null
                      }
                      actionReadinessLabel={
                        selectedDecision
                          ? selectedDecision.human_review_required
                            ? "Human approval required"
                            : "No human review flagged"
                          : null
                      }
                    />
                  </div>
                )}
                {mlWhyLines(selectedCondition.evidence_summary.why).length > 0 ? (
                  <ul className="flex flex-col gap-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                    {mlWhyLines(selectedCondition.evidence_summary.why).map((line) => (
                      <li key={line} className="flex gap-2">
                        <span
                          className="mt-1.5 h-1 w-1 flex-none rounded-full bg-sky-500"
                          aria-hidden
                        />
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    ML evidence exists for this machine but did not factor into its current
                    condition assessment — the assessment ran before this inference, or other
                    evidence sources were sufficient on their own.
                  </p>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-xs text-zinc-400 dark:text-zinc-600">Final condition:</span>
                  {selectedCondition && <SeverityBadge value={selectedCondition.severity} />}
                  <span className="font-medium text-zinc-800 dark:text-zinc-200">
                    {humanize(selectedCondition.condition_type)}
                  </span>
                  {selectedCondition && <ConfidenceBadge value={selectedCondition.confidence} />}
                  <span className="text-zinc-300 dark:text-zinc-700">→</span>
                  <span className="text-zinc-700 dark:text-zinc-300">
                    {selectedDecision
                      ? humanize(selectedDecision.recommended_action)
                      : "No decision yet"}
                  </span>
                  <Link
                    href={`/machines/${effectiveMachineId}`}
                    className="ml-auto text-xs text-sky-600 hover:underline dark:text-sky-400"
                  >
                    Open machine →
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}
      </SectionCard>

      {/* D. Fleet ML view */}
      <SectionCard title="Fleet ML evidence">
        <DataState isPending={fleetML.isPending} isError={fleetML.isError} error={fleetML.error}>
          {machinesWithEvidence.length === 0 ? (
            <EmptyState
              title="No ML evidence anywhere in the fleet"
              description="No model has produced a persisted inference result yet."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                    <th className="py-1.5 pr-4 font-medium">Machine</th>
                    <th className="py-1.5 pr-4 font-medium">Condition</th>
                    <th className="py-1.5 pr-4 font-medium">Anomaly evidence</th>
                    <th className="py-1.5 pr-4 font-medium">Classification evidence</th>
                    <th className="py-1.5 pr-4 font-medium">Data trust</th>
                    <th className="py-1.5 pr-4 font-medium">Last inference</th>
                  </tr>
                </thead>
                <tbody>
                  {machinesWithEvidence.map((machine) => {
                    const results = resultsByMachine.get(machine.id) ?? [];
                    const anomaly = results.find((r) => r.result_kind === "ANOMALY");
                    const classification =
                      results.find((r) => r.model_id === "FAILURE_CLASSIFICATION_BASELINE_V1") ??
                      results.find((r) => r.result_kind === "CLASSIFICATION");
                    const condition = conditionByMachine.get(machine.id);
                    const latest = results
                      .map((r) => r.as_of_timestamp)
                      .sort()
                      .at(-1);
                    return (
                      <tr
                        key={machine.id}
                        className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                      >
                        <td className="py-2 pr-4">
                          <Link
                            href={`/machines/${machine.id}`}
                            className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                          >
                            {machine.name}
                          </Link>
                        </td>
                        <td className="py-2 pr-4 text-zinc-700 dark:text-zinc-300">
                          {condition ? humanize(condition.condition_type) : "—"}
                        </td>
                        <td className="py-2 pr-4">
                          {anomaly && anomaly.status === "OK" ? (
                            <StatusPill tone={anomaly.anomalous ? "warn" : "ok"}>
                              {anomaly.anomaly_score?.toFixed(2)}{" "}
                              {anomaly.anomalous ? "elevated" : "normal"}
                            </StatusPill>
                          ) : (
                            <span className="text-xs text-zinc-400 dark:text-zinc-600">
                              {anomaly ? "Blocked" : "—"}
                            </span>
                          )}
                        </td>
                        <td className="py-2 pr-4">
                          {classification && classification.status === "OK" ? (
                            <span className="text-zinc-700 dark:text-zinc-300">
                              {failureLabelName(classification.predicted_class ?? "")}
                            </span>
                          ) : (
                            <span className="text-xs text-zinc-400 dark:text-zinc-600">
                              {classification ? "Blocked" : "—"}
                            </span>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-zinc-700 dark:text-zinc-300">
                          {condition
                            ? humanize(condition.evidence_summary.data_trustworthiness)
                            : "—"}
                        </td>
                        <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
                          {latest ? <RelativeTime iso={latest} /> : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </SectionCard>

      {/* E/F. Model portfolio */}
      <DataState isPending={models.isPending} isError={models.isError} error={models.error}>
        {sortedModels.length === 0 ? (
          <EmptyState
            title="No models registered"
            description="The ML model registry is empty in this environment — nothing has been trained or registered yet."
          />
        ) : (
          <div className="flex flex-col gap-6">
            <SectionCard title="Models supporting the platform">
              <div className="grid gap-3 sm:grid-cols-3">
                {sortedModels.map((model) => (
                  <button
                    key={`${model.model_id}@${model.model_version}`}
                    type="button"
                    onClick={() => setSelectedModelId(model.model_id)}
                    className={`rounded-lg border p-3 text-left transition-colors ${
                      effectiveModelId === model.model_id
                        ? "border-sky-400 bg-sky-50 dark:border-sky-600 dark:bg-sky-500/10"
                        : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {modelDisplayName(model.model_id)}
                      </span>
                      <ModelStatusBadge value={model.status} />
                    </div>
                    <p className="mt-1 font-mono text-xs text-zinc-400 dark:text-zinc-600">
                      {model.model_id}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {humanize(model.model_type)} · v{model.model_version} · trained{" "}
                      <RelativeTime iso={model.training_time} />
                    </p>
                  </button>
                ))}
              </div>
            </SectionCard>

            {/* G. Selected model evaluation */}
            {detail.data && (
              <SectionCard
                title={`${modelDisplayName(detail.data.model_id)} — evaluation`}
                actions={<ModelStatusBadge value={detail.data.status} />}
              >
                <div className="flex flex-col gap-5">
                  <LifecycleExplainer status={detail.data.status} />

                  <p className="text-xs text-zinc-500 italic dark:text-zinc-400">
                    Current model evidence is evaluated on synthetic industrial scenarios. Field
                    validation against real machine histories and maintenance outcomes is required
                    before production promotion.
                  </p>

                  <div>
                    <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                      Training data
                    </p>
                    <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
                      Synthetic lubrication-condition scenarios — {detail.data.features.length}{" "}
                      engineered features, dataset {detail.data.dataset_id}@
                      {detail.data.dataset_version}.
                    </p>
                  </div>

                  {classifierReport && (
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div>
                        <p className="text-xs text-zinc-400 dark:text-zinc-600">Macro F1</p>
                        <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                          {(classifierReport.macro_f1 * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-zinc-400 dark:text-zinc-600">Weighted F1</p>
                        <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                          {(classifierReport.weighted_f1 * 100).toFixed(0)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-zinc-400 dark:text-zinc-600">
                          Evaluation samples
                        </p>
                        <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                          {String(detail.data.metrics.sample_count ?? "—")}
                        </p>
                      </div>
                    </div>
                  )}

                  {classifierReport && (
                    <div className="grid gap-6 lg:grid-cols-2">
                      <div>
                        <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                          Per-class performance
                        </p>
                        <PerClassPerformance report={classifierReport} />
                      </div>
                      <div>
                        <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                          Confusion matrix
                        </p>
                        <ConfusionMatrix report={classifierReport} />
                      </div>
                    </div>
                  )}

                  {!classifierReport && "healthy_false_positive_rate" in detail.data.metrics && (
                    <AnomalyEvaluation metrics={detail.data.metrics} />
                  )}

                  {detail.data.promotion_history.length > 0 && (
                    <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
                      <p className="mb-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Lifecycle decisions
                      </p>
                      <ul className="flex flex-col gap-2">
                        {detail.data.promotion_history.map((p) => (
                          <li
                            key={`${p.decided_at}-${p.to_status}`}
                            className="rounded-md bg-zinc-50/70 p-2.5 text-sm dark:bg-zinc-900/40"
                          >
                            <p className="text-zinc-800 dark:text-zinc-200">
                              {humanize(p.from_status)} → {humanize(p.to_status)}
                              <span className="ml-2 text-xs text-zinc-400 dark:text-zinc-600">
                                <RelativeTime iso={p.decided_at} /> · {p.actor}
                              </span>
                            </p>
                            <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                              {p.reason}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {detail.data.limitations.length > 0 && (
                    <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
                      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Documented limitations
                      </p>
                      <ul className="mt-1 list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
                        {detail.data.limitations.map((limitation) => (
                          <li key={limitation}>{limitation}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </SectionCard>
            )}
          </div>
        )}
      </DataState>

      <SectionCard title="ML, condition intelligence, and GenAI — where each stops">
        <div className="grid gap-4 text-sm sm:grid-cols-4">
          <div>
            <p className="font-medium text-zinc-800 dark:text-zinc-200">Machine learning</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Analyzes numerical sensor/features to detect patterns.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-800 dark:text-zinc-200">Condition intelligence</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Combines ML with physics, rules, state estimation, and data quality.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-800 dark:text-zinc-200">GenAI / Assistant</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Explains trusted results and retrieves approved maintenance knowledge.
            </p>
          </div>
          <div>
            <p className="font-medium text-zinc-800 dark:text-zinc-200">Action readiness</p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              Determines whether the recommended action may proceed. No component here directly
              controls machinery.
            </p>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

/** The insufficient-features case is real product evidence, not an error to hide (ML
 * productization pass, item 6): shows exactly which required features this model's
 * minimum input set was missing for this machine, at this inference, and links straight
 * to the Data Quality page for the sensor(s) behind that gap — never a generic "blocked"
 * message with no way to act on it. */
function InsufficientFeaturesCard({
  result,
  machineId,
}: {
  result: MLInferenceResultResponse;
  machineId: string;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-zinc-50/70 p-4 dark:bg-zinc-900/40">
      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        ML inference unavailable
      </p>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Reason: required feature evidence was incomplete for {modelDisplayName(result.model_id)}.
      </p>
      {result.missing_features.length > 0 && (
        <div>
          <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Missing features</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {result.missing_features.map((feature) => (
              <li
                key={feature}
                className="rounded-full bg-zinc-100 px-2 py-0.5 font-mono text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {humanizeFeatureName(feature)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Insufficient features means condition confidence for this machine is reduced, and any
        recommended action stays gated on human review until trusted evidence is available.
      </p>
      <Link
        href={`/data-quality?machine=${machineId}`}
        className="text-xs text-sky-600 hover:underline dark:text-sky-400"
      >
        Review data quality →
      </Link>
    </div>
  );
}

function ClassificationCard({
  result,
  machineId,
  modelServable,
  conditionType,
  includedInCondition,
}: {
  result: MLInferenceResultResponse;
  machineId: string;
  modelServable: boolean;
  conditionType: string | null;
  includedInCondition: boolean;
}) {
  if (result.status === "INSUFFICIENT_FEATURES") {
    return <InsufficientFeaturesCard result={result} machineId={machineId} />;
  }
  const agrees =
    conditionType != null &&
    classificationConditionHint(result.predicted_class ?? "") === conditionType;
  const role = mlRoleFor({
    status: result.status,
    modelServable,
    confidenceCategory: result.confidence_category,
    agreesWithCondition: conditionType == null ? null : agrees,
  });
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-zinc-50/70 p-4 dark:bg-zinc-900/40">
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
          {result.status === "UNKNOWN"
            ? "No confident pattern"
            : failureLabelName(result.predicted_class ?? "")}
        </span>
        {result.confidence_category && (
          <StatusPill
            tone={
              result.confidence_category === "HIGH"
                ? "ok"
                : result.confidence_category === "MODERATE"
                  ? "warn"
                  : "neutral"
            }
          >
            {humanize(result.confidence_category)} confidence
          </StatusPill>
        )}
      </div>
      <ProbabilityBars
        probabilities={result.class_probabilities}
        predictedClass={result.predicted_class}
      />
      <FeatureEvidence
        contributions={contributionsFrom(result.explanation)}
        resultKind="CLASSIFICATION"
      />
      <div className="border-t border-zinc-200 pt-2 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        {includedInCondition ? (
          <>
            ML role in this assessment: <span className="font-medium">{ML_ROLE_LABEL[role]}</span>
          </>
        ) : (
          "Not yet reflected in this machine's current condition assessment — see Evidence fusion below."
        )}
      </div>
      <p className="text-xs text-zinc-400 dark:text-zinc-600">
        Inference as of <RelativeTime iso={result.as_of_timestamp} /> · model version{" "}
        {result.model_version}
      </p>
    </div>
  );
}

function AnomalyCard({
  result,
  machineId,
  modelServable,
  includedInCondition,
}: {
  result: MLInferenceResultResponse;
  machineId: string;
  modelServable: boolean;
  includedInCondition: boolean;
}) {
  if (result.status === "INSUFFICIENT_FEATURES") {
    return <InsufficientFeaturesCard result={result} machineId={machineId} />;
  }
  const role = mlRoleFor({
    status: result.status,
    modelServable,
    confidenceCategory: null,
    agreesWithCondition: null,
  });
  const interpretation =
    result.anomaly_score == null
      ? "No score available."
      : result.anomaly_score >= (result.threshold ?? 1)
        ? "Strong anomaly — behavior deviates materially from what this model learned as healthy."
        : result.anomaly_score >= (result.threshold ?? 1) * 0.7
          ? "Elevated deviation — approaching, but not yet past, the anomaly threshold."
          : "Within normal behavior for this model.";
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-zinc-50/70 p-4 dark:bg-zinc-900/40">
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
          {result.anomaly_score?.toFixed(3) ?? "—"}
        </span>
        <StatusPill tone={result.anomalous ? "warn" : "ok"}>
          {result.anomalous ? "Anomalous" : "Within threshold"}
        </StatusPill>
      </div>
      <p className="text-sm text-zinc-700 dark:text-zinc-300">{interpretation}</p>
      {result.threshold != null && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Anomaly threshold for this model: {result.threshold.toFixed(3)}. The score itself is an
          Isolation Forest decision-function value, not a percentage or probability.
        </p>
      )}
      <FeatureEvidence contributions={contributionsFrom(result.explanation)} resultKind="ANOMALY" />
      <div className="border-t border-zinc-200 pt-2 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        {includedInCondition || role === "EXPERIMENTAL_EVIDENCE" ? (
          <>
            ML role in this assessment: <span className="font-medium">{ML_ROLE_LABEL[role]}</span>
          </>
        ) : (
          "Not yet reflected in this machine's current condition assessment — see Evidence fusion below."
        )}
      </div>
      <p className="text-xs text-zinc-400 dark:text-zinc-600">
        Inference as of <RelativeTime iso={result.as_of_timestamp} /> · model version{" "}
        {result.model_version}
      </p>
    </div>
  );
}

function LifecycleExplainer({ status }: { status: string }) {
  const copy: Record<string, string> = {
    EXPERIMENT:
      "Model under technical evaluation — real inference runs and is recorded as shadow evidence, but it does not influence an operational decision.",
    VALIDATED: "Model passed defined validation gates for its documented scope.",
    STAGING:
      "Candidate allowed to provide governed supporting evidence in the reference environment.",
    PRODUCTION: "Promoted for standing use in this reference environment.",
    RETIRED: "No longer used — kept for audit history only.",
  };
  return (
    <div className="flex items-start gap-2 rounded-md bg-zinc-50/70 p-3 text-sm dark:bg-zinc-900/40">
      <ModelStatusBadge value={status} />
      <p className="text-zinc-600 dark:text-zinc-400">
        {copy[status] ?? "Lifecycle stage not recognized."}
      </p>
    </div>
  );
}

function AnomalyEvaluation({ metrics }: { metrics: Record<string, unknown> }) {
  const fpr = metrics["healthy_false_positive_rate"] as number | undefined;
  const recall = metrics["binary_recall"] as number | undefined;
  const precision = metrics["binary_precision"] as number | undefined;
  const prAuc = metrics["pr_auc"] as number | undefined;
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-4">
        {[
          ["Precision", precision],
          ["Recall", recall],
          ["Healthy false-positive rate", fpr],
          ["PR-AUC", prAuc],
        ].map(([label, value]) => (
          <div key={label as string}>
            <p className="text-xs text-zinc-400 dark:text-zinc-600">{label}</p>
            <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "—"}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        Ground truth for anomaly detection is inherently weaker than for classification —
        &ldquo;anomalous&rdquo; is evaluated against known synthetic failure windows, not a labeled
        fault type. A high false-positive rate or low recall here means the model should not be
        trusted to gate a decision on its own, which is exactly why its evidence stays experimental
        until further validated.
      </p>
    </div>
  );
}

export default function MLPage() {
  return (
    <Suspense>
      <MLPageInner />
    </Suspense>
  );
}

"use client";

import { useMemo, useState } from "react";

import { DataState } from "@/components/data-state";
import { EmptyState } from "@/components/empty-state";
import { ModelStatusBadge } from "@/components/badges";
import { PageHeader } from "@/components/page-header";
import { RelativeTime } from "@/components/relative-time";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useLatestMachineInference, useModel, useModels } from "@/hooks/use-ml";
import { humanize, SERVABLE_MODEL_STATUSES } from "@/lib/terminology";

// Only these two model ids are wired into the live per-machine inference endpoint
// (backend/app/api/v1/ml.py `_KNOWN_MODEL_IDS`) — the registry can hold other models
// (e.g. a STAGING baseline classifier) that this page still lists above, just without a
// "try live inference" panel, since the API itself would reject an unknown model_id.
const LIVE_INFERENCE_MODEL_IDS = ["LUBRICATION_ANOMALY_V1", "FAILURE_CLASSIFICATION_V1"] as const;

function isPlainValue(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function formatMetricValue(value: number | string | boolean): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  return String(value);
}

function ModelMetricsGrid({ metrics }: { metrics: Record<string, unknown> }) {
  const scalarEntries = Object.entries(metrics).filter(([, value]) => isPlainValue(value));
  if (scalarEntries.length === 0) return null;
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {scalarEntries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs text-zinc-500 dark:text-zinc-400">{humanize(key)}</dt>
          <dd className="mt-0.5 font-mono text-sm text-zinc-900 dark:text-zinc-100">
            {formatMetricValue(value as string | number | boolean)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function LiveInferencePanel({ machineId, modelId }: { machineId: string; modelId: string }) {
  const inference = useLatestMachineInference(machineId, modelId);

  return (
    <DataState
      isPending={inference.isPending}
      isError={false}
      error={undefined}
      loadingLabel="Running inference…"
    >
      {inference.isError ? (
        <EmptyState
          title="Not used for live scoring yet"
          description="This model version has not been promoted to VALIDATED (or later), so it does not independently score machines yet — the registry entry above is real, evaluated evidence, just not currently servable."
        />
      ) : inference.data ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-700 dark:text-zinc-300">
            <span>Status</span>
            <StatusPill tone={inference.data.status === "OK" ? "ok" : "neutral"}>
              {humanize(inference.data.status)}
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
              </>
            )}
          </div>
          <p className="text-xs text-zinc-400 dark:text-zinc-600">
            As of <RelativeTime iso={inference.data.as_of_timestamp} /> · model{" "}
            {inference.data.model_version}
          </p>
        </div>
      ) : null}
    </DataState>
  );
}

export default function MLPage() {
  const hierarchy = useHierarchy();
  const models = useModels();
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [machineId, setMachineId] = useState("");
  const [showRawDetail, setShowRawDetail] = useState(false);

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

  const sortedModels = useMemo(
    () => [...(models.data ?? [])].sort((a, b) => a.model_id.localeCompare(b.model_id)),
    [models.data],
  );
  const effectiveModelId = selectedModelId || sortedModels[0]?.model_id || "";

  const detail = useModel(effectiveModelId);
  const canTryLiveInference = (LIVE_INFERENCE_MODEL_IDS as readonly string[]).includes(
    effectiveModelId,
  );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        title="ML Model Evidence"
        description="Model output is one evidence source among several (rules, state estimation, technician history) that feed Condition Intelligence — it never independently makes a maintenance decision. A model only scores live machines once promoted from EXPERIMENT to VALIDATED or later."
      />

      <SectionCard title="How AI fits into this product" tier="band">
        <div className="flex flex-col gap-1 text-sm text-zinc-700 sm:flex-row sm:items-stretch sm:gap-0 dark:text-zinc-300">
          {[
            {
              label: "Condition intelligence",
              detail: "Physics/deterministic rules + state estimation + ML evidence → a condition assessment",
            },
            {
              label: "Decision intelligence",
              detail: "Condition + asset context + criticality → a maintenance recommendation",
            },
            {
              label: "Workflow intelligence",
              detail: "Recommendation → incident, maintenance case, and a real outcome",
            },
            {
              label: "GenAI / knowledge",
              detail: "Approved documentation → explanation and workflow assistance, never a diagnosis",
            },
          ].map((step, index, arr) => (
            <div key={step.label} className="flex flex-1 items-stretch">
              <div className="flex-1 rounded-md bg-white/60 p-3 dark:bg-zinc-950/30">
                <p className="text-xs font-semibold tracking-wide text-zinc-500 uppercase dark:text-zinc-400">
                  {step.label}
                </p>
                <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{step.detail}</p>
              </div>
              {index < arr.length - 1 && (
                <div className="flex w-6 shrink-0 items-center justify-center text-zinc-300 dark:text-zinc-700">
                  →
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          ML models never become physical truth on their own — a model result is one input
          the Condition Engine weighs alongside rule findings and state estimates, and every
          resulting maintenance recommendation still requires human review.
        </p>
      </SectionCard>

      <DataState
        isPending={models.isPending}
        isError={models.isError}
        error={models.error}
        loadingLabel="Loading model registry…"
      >
        {sortedModels.length === 0 ? (
          <EmptyState
            title="No models registered"
            description="The ML model registry is empty in this environment — nothing has been trained or registered yet."
          />
        ) : (
          <div className="flex flex-col gap-6">
            <SectionCard title="Registered models">
              <div className="grid gap-3 sm:grid-cols-2">
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
                      <span className="font-mono text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {model.model_id}
                      </span>
                      <ModelStatusBadge value={model.status} />
                    </div>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {humanize(model.model_type)} · v{model.model_version}
                    </p>
                    <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">
                      Trained <RelativeTime iso={model.training_time} />
                    </p>
                  </button>
                ))}
              </div>
            </SectionCard>

            {detail.data && (
              <SectionCard
                title={`${detail.data.model_id} — evaluation`}
                actions={
                  <div className="flex items-center gap-2">
                    <ModelStatusBadge value={detail.data.status} />
                    {!SERVABLE_MODEL_STATUSES.has(detail.data.status) && (
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">
                        Evidence only — not yet used for maintenance decisions.
                      </span>
                    )}
                  </div>
                }
              >
                <ModelMetricsGrid metrics={detail.data.metrics} />

                {detail.data.limitations.length > 0 && (
                  <div className="mt-4 border-t border-zinc-100 pt-3 dark:border-zinc-800">
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

                <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                  <span>{detail.data.features.length} feature(s)</span>
                  <span>
                    Dataset: {detail.data.dataset_id}@{detail.data.dataset_version}
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowRawDetail((v) => !v)}
                    className="ml-auto text-sky-600 hover:underline dark:text-sky-400"
                  >
                    {showRawDetail ? "Hide" : "Show"} full evaluation detail
                  </button>
                </div>

                {showRawDetail && (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {[
                      ["Metrics", detail.data.metrics],
                      ["Thresholds", detail.data.thresholds],
                      ["Hyperparameters", detail.data.hyperparameters],
                      ["Features used", detail.data.features],
                    ].map(([label, value]) => (
                      <div key={String(label)}>
                        <p className="mb-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                          {String(label)}
                        </p>
                        <pre className="max-h-64 overflow-auto rounded-md bg-zinc-900 p-3 text-xs text-zinc-100 dark:bg-black">
                          {JSON.stringify(value, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </SectionCard>
            )}

            {effectiveModelId && canTryLiveInference && (
              <SectionCard
                title="Try live inference"
                actions={
                  <label className="flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                    Machine
                    <select
                      value={effectiveMachineId}
                      onChange={(event) => setMachineId(event.target.value)}
                      className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                    >
                      {machines.map((machine) => (
                        <option key={machine.id} value={machine.id}>
                          {machine.name}
                        </option>
                      ))}
                    </select>
                  </label>
                }
              >
                {effectiveMachineId && (
                  <LiveInferencePanel machineId={effectiveMachineId} modelId={effectiveModelId} />
                )}
              </SectionCard>
            )}
          </div>
        )}
      </DataState>
    </div>
  );
}

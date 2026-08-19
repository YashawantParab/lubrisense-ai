"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { CapabilityLevelBadge, CommissioningStatusBadge } from "@/components/badges";
import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";
import { StatusPill } from "@/components/status-pill";
import { usePageTitle } from "@/hooks/use-page-title";
import { useHierarchy } from "@/hooks/use-asset-hierarchy";
import { useGateways } from "@/hooks/use-gateways";
import {
  useAddCommissioningSensor,
  useAssignCommissioningGateway,
  useCommissioningSession,
  useCompleteCommissioning,
  useStartCommissioning,
  useValidateCommissioning,
} from "@/hooks/use-commissioning";
import { humanize } from "@/lib/terminology";

const MACHINE_TYPES = ["CONVEYOR", "MOTOR", "FAN", "PUMP", "COMPRESSOR", "CRUSHER"];
const SENSOR_TYPES = [
  "PRESSURE",
  "FLOW",
  "RESERVOIR_LEVEL",
  "PUMP_CURRENT",
  "PUMP_RUNTIME",
  "CYCLE_COMPLETION",
  "PISTON_MOVEMENT",
  "LUBRICANT_TEMPERATURE",
  "VIBRATION_RMS",
  "VIBRATION_PEAK",
  "BEARING_TEMPERATURE",
  "RPM",
  "LOAD",
];

function StepIndicator({ current }: { current: number }) {
  const steps = ["Machine", "Sensors", "Gateway", "Validate", "Complete"];
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
      {steps.map((label, i) => (
        <li key={label} className="flex items-center gap-2">
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-medium ${
              i + 1 === current
                ? "bg-sky-600 text-white"
                : i + 1 < current
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400"
                  : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
            }`}
          >
            {i + 1}
          </span>
          <span className={i + 1 === current ? "font-medium text-zinc-900 dark:text-zinc-100" : ""}>
            {label}
          </span>
          {i < steps.length - 1 && <span className="text-zinc-300 dark:text-zinc-700">→</span>}
        </li>
      ))}
    </ol>
  );
}

function CommissioningWizardInner() {
  usePageTitle("Commission a Machine");
  const searchParams = useSearchParams();
  const hierarchy = useHierarchy();

  const [sessionId, setSessionId] = useState(searchParams.get("sessionId") ?? "");
  const sessionQuery = useCommissioningSession(sessionId);

  const [productionLineId, setProductionLineId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [name, setName] = useState("");
  const [assetCode, setAssetCode] = useState("");
  const [machineType, setMachineType] = useState(MACHINE_TYPES[1]);

  const [sensorType, setSensorType] = useState(SENSOR_TYPES[0]);
  const [sensorCode, setSensorCode] = useState("");
  const [sensorName, setSensorName] = useState("");
  const [sensorUnit, setSensorUnit] = useState("");

  const [gatewayId, setGatewayId] = useState("");

  const startMutation = useStartCommissioning();
  const addSensorMutation = useAddCommissioningSensor(sessionId);
  const assignGatewayMutation = useAssignCommissioningGateway(sessionId);
  const validateMutation = useValidateCommissioning(sessionId);
  const completeMutation = useCompleteCommissioning(sessionId);
  const gateways = useGateways(siteId || undefined);

  const productionLines = useMemo(
    () =>
      hierarchy.data?.customers.flatMap((customer) =>
        customer.sites.flatMap((site) =>
          site.plants.flatMap((plant) =>
            plant.production_lines.map((line) => ({ site, plant, line })),
          ),
        ),
      ) ?? [],
    [hierarchy.data],
  );

  const session = sessionQuery.data;
  const step = !session
    ? 1
    : session.status === "CONFIGURING" && session.steps_completed.length <= 1
      ? 2
      : session.status === "CONFIGURING"
        ? 3
        : session.status === "VALIDATING" || session.status === "READY" || session.status === "FAILED"
          ? 4
          : 5;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-10">
      <PageHeader
        breadcrumbs={[{ label: "Configuration", href: "/configuration" }, { label: "Commission" }]}
        title="Commission a Machine"
        description="A guided demo onboarding workflow — real records are created at every step, but no physical device is ever contacted."
      />

      <StepIndicator current={step} />

      {!session && (
        <SectionCard title="1. Machine">
          <DataState isPending={hierarchy.isPending} isError={hierarchy.isError} error={hierarchy.error}>
            <div className="flex flex-col gap-3">
              <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                Production line
                <select
                  value={productionLineId}
                  onChange={(e) => {
                    setProductionLineId(e.target.value);
                    const match = productionLines.find((p) => p.line.id === e.target.value);
                    setSiteId(match?.site.id ?? "");
                  }}
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                >
                  <option value="">Select…</option>
                  {productionLines.map(({ site, plant, line }) => (
                    <option key={line.id} value={line.id}>
                      {site.name} / {plant.name} / {line.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                Machine name
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Conveyor 027"
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
              </label>
              <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                Asset code
                <input
                  value={assetCode}
                  onChange={(e) => setAssetCode(e.target.value)}
                  placeholder="e.g. L3-92C1-M027"
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
              </label>
              <label className="grid gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                Machine type
                <select
                  value={machineType}
                  onChange={(e) => setMachineType(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                >
                  {MACHINE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {humanize(t)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={!productionLineId || !name || !assetCode || startMutation.isPending}
                onClick={() =>
                  startMutation.mutate(
                    {
                      production_line_id: productionLineId,
                      name,
                      asset_code: assetCode,
                      machine_type: machineType,
                    },
                    { onSuccess: (created) => setSessionId(created.id) },
                  )
                }
                className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
              >
                {startMutation.isPending ? "Starting…" : "Start commissioning"}
              </button>
              {startMutation.isError && (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {startMutation.error instanceof Error
                    ? startMutation.error.message
                    : "Could not start commissioning."}
                </p>
              )}
            </div>
          </DataState>
        </SectionCard>
      )}

      {session && (session.status === "CONFIGURING" || session.status === "FAILED") && (
        <>
          <SectionCard title="2. Sensors">
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-2 gap-2">
                <select
                  value={sensorType}
                  onChange={(e) => setSensorType(e.target.value)}
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                >
                  {SENSOR_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {humanize(t)}
                    </option>
                  ))}
                </select>
                <input
                  value={sensorUnit}
                  onChange={(e) => setSensorUnit(e.target.value)}
                  placeholder="Unit (e.g. bar)"
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
                <input
                  value={sensorCode}
                  onChange={(e) => setSensorCode(e.target.value)}
                  placeholder="Sensor code"
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
                <input
                  value={sensorName}
                  onChange={(e) => setSensorName(e.target.value)}
                  placeholder="Sensor name"
                  className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
              </div>
              <button
                type="button"
                disabled={!sensorCode || !sensorName || addSensorMutation.isPending}
                onClick={() =>
                  addSensorMutation.mutate(
                    { sensor_type: sensorType, sensor_code: sensorCode, name: sensorName, unit: sensorUnit || undefined },
                    {
                      onSuccess: () => {
                        setSensorCode("");
                        setSensorName("");
                        setSensorUnit("");
                      },
                    },
                  )
                }
                className="w-fit rounded-md border border-sky-300 px-3 py-1.5 text-sm font-medium text-sky-700 hover:bg-sky-50 disabled:opacity-50 dark:border-sky-800 dark:text-sky-400 dark:hover:bg-sky-950/40"
              >
                {addSensorMutation.isPending ? "Adding…" : "Add sensor"}
              </button>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {session.steps_completed.filter((s) => s.startsWith("sensor_mapped")).length} sensor(s) mapped so far.
              </p>
            </div>
          </SectionCard>

          <SectionCard title="3. Gateway (optional)">
            <div className="flex flex-wrap items-end gap-2">
              <select
                value={gatewayId}
                onChange={(e) => setGatewayId(e.target.value)}
                className="min-w-52 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              >
                <option value="">None</option>
                {(gateways.data ?? []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name} ({g.gateway_code})
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!gatewayId || assignGatewayMutation.isPending}
                onClick={() => assignGatewayMutation.mutate({ gateway_id: gatewayId })}
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                {assignGatewayMutation.isPending ? "Assigning…" : "Assign gateway"}
              </button>
              {session.gateway_id && (
                <StatusPill tone="ok">Gateway assigned</StatusPill>
              )}
            </div>
          </SectionCard>

          <button
            type="button"
            disabled={validateMutation.isPending}
            onClick={() => validateMutation.mutate()}
            className="w-fit rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {validateMutation.isPending ? "Validating…" : "4. Validate"}
          </button>
        </>
      )}

      {session && (session.status === "VALIDATING" || session.status === "READY" || session.status === "FAILED") && (
        <SectionCard title="4. Validation result">
          <div className="flex flex-wrap items-center gap-2">
            <CommissioningStatusBadge value={session.status} />
            <CapabilityLevelBadge value={session.capability_level} />
          </div>
          {session.validation_issues.length > 0 && (
            <ul className="mt-3 space-y-1.5 text-sm">
              {session.validation_issues.map((issue) => (
                <li key={issue.code} className="flex items-start gap-2">
                  <StatusPill tone={issue.blocking ? "error" : "warn"}>
                    {issue.blocking ? "Blocking" : "Warning"}
                  </StatusPill>
                  <span className="text-zinc-700 dark:text-zinc-300">{issue.message}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex gap-2">
            {session.status === "READY" && (
              <button
                type="button"
                disabled={completeMutation.isPending}
                onClick={() => completeMutation.mutate()}
                className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {completeMutation.isPending ? "Completing…" : "5. Complete commissioning"}
              </button>
            )}
            {session.status === "FAILED" && (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Add the missing instrumentation above, then validate again.
              </p>
            )}
          </div>
        </SectionCard>
      )}

      {session && session.status === "COMPLETED" && (
        <SectionCard title="5. Complete">
          <div className="flex flex-col items-start gap-3">
            <StatusPill tone="ok">Commissioning complete</StatusPill>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Capability level: <CapabilityLevelBadge value={session.capability_level} />
            </p>
            <Link
              href={`/machines/${session.machine_id}`}
              className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700"
            >
              View machine
            </Link>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

export default function CommissioningWizardPage() {
  return (
    <Suspense>
      <CommissioningWizardInner />
    </Suspense>
  );
}

"use client";

import { use } from "react";
import Link from "next/link";

import { DataState } from "@/components/data-state";
import { StatusPill } from "@/components/status-pill";
import { useMachineHierarchy } from "@/hooks/use-asset-hierarchy";
import { useMachineTelemetry } from "@/hooks/use-telemetry";
import { toneForStatus } from "@/lib/status-tone";
import type {
  BearingResponse,
  LubricationSystemResponse,
  SensorResponse,
} from "@/lib/api/asset-hierarchy-types";
import type { TelemetryReadingResponse } from "@/lib/api/telemetry-types";

const QUALITY_ERROR_VALUES = new Set(["BAD", "INVALID", "MISSING", "UNAVAILABLE"]);
const QUALITY_WARN_VALUES = new Set(["UNCERTAIN", "SUSPECT", "COMMUNICATION_LOSS"]);

function toneForQuality(value: string): "ok" | "warn" | "error" | "neutral" {
  if (QUALITY_ERROR_VALUES.has(value)) return "error";
  if (QUALITY_WARN_VALUES.has(value)) return "warn";
  return "ok";
}

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

function TelemetryRow({ reading }: { reading: TelemetryReadingResponse }) {
  return (
    <tr className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
      <td className="py-2 pr-4 font-mono text-xs text-zinc-500">
        {reading.sensor_id.slice(0, 8)}…
      </td>
      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{reading.measurement_type}</td>
      <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">
        {reading.value ?? "—"} {reading.value !== null ? reading.unit : ""}
      </td>
      <td className="py-2 pr-4">
        <StatusPill tone={toneForQuality(reading.quality)}>{reading.quality}</StatusPill>
      </td>
      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{reading.operating_state}</td>
      <td className="py-2 pr-4 text-xs text-zinc-500 dark:text-zinc-400">
        {new Date(reading.source_timestamp).toLocaleString()}
      </td>
    </tr>
  );
}

export default function MachineDetailPage({ params }: { params: Promise<{ machineId: string }> }) {
  const { machineId } = use(params);
  const hierarchy = useMachineHierarchy(machineId);
  const telemetry = useMachineTelemetry(machineId, { limit: 25 });

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-12">
      <Link href="/hierarchy" className="text-sm text-sky-600 hover:underline dark:text-sky-400">
        ← Back to Asset Hierarchy
      </Link>

      <DataState
        isPending={hierarchy.isPending}
        isError={hierarchy.isError}
        error={hierarchy.error}
        loadingLabel="Loading machine…"
      >
        {hierarchy.data && (
          <>
            <header className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
              <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                  {hierarchy.data.machine.name}
                </h1>
                <div className="flex gap-2">
                  <StatusPill tone={toneForStatus(hierarchy.data.machine.criticality)}>
                    {hierarchy.data.machine.criticality}
                  </StatusPill>
                  <StatusPill tone={toneForStatus(hierarchy.data.machine.status)}>
                    {hierarchy.data.machine.status}
                  </StatusPill>
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Field label="Asset code" value={hierarchy.data.machine.asset_code} />
                <Field label="Type" value={hierarchy.data.machine.machine_type} />
                <Field label="Manufacturer" value={hierarchy.data.machine.manufacturer} />
                <Field label="Model" value={hierarchy.data.machine.model} />
                <Field label="Serial (demo)" value={hierarchy.data.machine.serial_number_demo} />
                <Field label="Installed" value={hierarchy.data.machine.installation_date} />
              </dl>
            </header>

            <section>
              <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Bearings ({hierarchy.data.bearings.length})
              </h2>
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
            </section>

            <section>
              <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Lubrication System
              </h2>
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
            </section>

            <section>
              <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Sensor Inventory ({hierarchy.data.sensors.length})
              </h2>
              {hierarchy.data.sensors.length === 0 ? (
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  No sensors attached anywhere on this machine yet.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
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
            </section>

            <section>
              <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                Recent Telemetry
              </h2>
              <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                Live readings from the central telemetry pipeline (Simulator → Edge → MQTT →
                Kafka → TimescaleDB) — a developer/product validation view, not the final
                Sensor Intelligence experience. No condition, health score, or diagnosis is
                computed here.
              </p>
              <DataState
                isPending={telemetry.isPending}
                isError={telemetry.isError}
                error={telemetry.error}
                loadingLabel="Loading telemetry…"
              >
                {telemetry.data && telemetry.data.length === 0 ? (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    No telemetry received for this machine yet. Start the edge/simulator and the
                    telemetry pipeline (`docker compose --profile edge up -d`) to see readings
                    here.
                  </p>
                ) : (
                  telemetry.data && (
                    <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                            <th className="py-2 pr-4 font-medium">Sensor</th>
                            <th className="py-2 pr-4 font-medium">Measurement</th>
                            <th className="py-2 pr-4 font-medium">Value</th>
                            <th className="py-2 pr-4 font-medium">Quality</th>
                            <th className="py-2 pr-4 font-medium">Operating state</th>
                            <th className="py-2 pr-4 font-medium">Source time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {telemetry.data.map((reading) => (
                            <TelemetryRow key={reading.event_id} reading={reading} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}
              </DataState>
            </section>
          </>
        )}
      </DataState>
    </div>
  );
}

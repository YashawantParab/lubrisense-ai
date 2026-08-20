"use client";

import { useState } from "react";
import Link from "next/link";

import { DataState } from "@/components/data-state";
import { PageHeader } from "@/components/page-header";
import { StatusPill } from "@/components/status-pill";
import { useSensors } from "@/hooks/use-asset-hierarchy";
import { humanize, toneForStatus } from "@/lib/terminology";

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

const SENSOR_STATUSES = ["ACTIVE", "INACTIVE", "FAULTY", "DECOMMISSIONED"];

const PAGE_SIZE = 25;

export default function SensorInventoryPage() {
  const [sensorType, setSensorType] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  const sensors = useSensors({
    sensor_type: sensorType || undefined,
    status: status || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-6 py-12">
      <PageHeader
        title="Sensor Inventory"
        description="Every sensor commissioned across your fleet, its attachment point, and its configuration status — the registry telemetry, baselines, and rules are all built on top of. Live telemetry readings are on each machine's own page."
      />

      <div className="flex flex-wrap gap-3">
        <select
          value={sensorType}
          onChange={(e) => {
            setSensorType(e.target.value);
            setOffset(0);
          }}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          <option value="">All sensor types</option>
          {SENSOR_TYPES.map((type) => (
            <option key={type} value={type}>
              {humanize(type)}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          <option value="">All statuses</option>
          {SENSOR_STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </select>
      </div>

      <DataState
        isPending={sensors.isPending}
        isError={sensors.isError}
        error={sensors.error}
        loadingLabel="Loading sensors…"
      >
        {sensors.data && (
          <>
            <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                    <th className="py-2 pr-4 font-medium">Code</th>
                    <th className="py-2 pr-4 font-medium">Name</th>
                    <th className="py-2 pr-4 font-medium">Type</th>
                    <th className="py-2 pr-4 font-medium">Attached to</th>
                    <th className="py-2 pr-4 font-medium">Unit</th>
                    <th className="py-2 pr-4 font-medium">Firmware</th>
                    <th className="py-2 pr-4 font-medium">Calibrated</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sensors.data.items.map((sensor) => (
                    <tr
                      key={sensor.id}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="py-2 pr-4 font-mono text-xs text-zinc-500">
                        {sensor.sensor_code}
                      </td>
                      <td className="py-2 pr-4 text-zinc-800 dark:text-zinc-200">{sensor.name}</td>
                      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                        {humanize(sensor.sensor_type)}
                      </td>
                      <td className="py-2 pr-4">
                        <Link
                          href={
                            sensor.attached_entity_type === "machine"
                              ? `/machines/${sensor.attached_entity_id}`
                              : "/hierarchy"
                          }
                          className="text-sky-600 hover:underline dark:text-sky-400"
                        >
                          {humanize(sensor.attached_entity_type)}
                        </Link>
                      </td>
                      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                        {sensor.unit ?? "—"}
                      </td>
                      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                        {sensor.firmware_version ?? "—"}
                      </td>
                      <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                        {sensor.calibration_date ?? "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <StatusPill tone={toneForStatus(sensor.status)}>
                          {humanize(sensor.status)}
                        </StatusPill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
              <span>
                Showing {sensors.data.items.length === 0 ? 0 : offset + 1}–
                {offset + sensors.data.items.length} of {sensors.data.meta.total}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="rounded-md border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={!sensors.data.meta.has_more}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="rounded-md border border-zinc-300 px-3 py-1 disabled:opacity-40 dark:border-zinc-700"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </DataState>
    </div>
  );
}

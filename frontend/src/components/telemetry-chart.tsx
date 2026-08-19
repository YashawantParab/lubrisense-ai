"use client";

import { Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { humanize } from "@/lib/terminology";
import type { TelemetryReadingResponse } from "@/lib/api/telemetry-types";

/** A restrained, single-series time chart for one measurement type on one machine
 * (Phase 28 brief §28.9). Deliberately not interactive/zoomable — this reference
 * platform's telemetry volumes don't need it, and CLAUDE.md's visual language calls for
 * "restrained charts," not a full analytics-grade charting surface (ADR-159). */
export function TelemetryChart({
  measurementType,
  readings,
  baselineRange,
}: {
  measurementType: string;
  readings: TelemetryReadingResponse[];
  /** optional [low, high] expected-range band, when a baseline exists for this sensor */
  baselineRange?: [number, number] | null;
}) {
  const points = readings
    .filter((r) => r.measurement_type === measurementType && r.value !== null)
    .map((r) => ({
      t: new Date(r.source_timestamp).getTime(),
      value: r.value as number,
      quality: r.quality,
    }))
    .sort((a, b) => a.t - b.t);

  const unit = readings.find((r) => r.measurement_type === measurementType)?.unit ?? "";
  const hasBadQuality = points.some((p) => p.quality !== "GOOD");

  if (points.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        No {humanize(measurementType).toLowerCase()} readings yet.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {humanize(measurementType)}
        </span>
        <span>{unit}</span>
      </div>
      <div className="h-40 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t: number) => new Date(t).toLocaleTimeString()}
              tick={{ fontSize: 10 }}
              stroke="currentColor"
              className="text-zinc-400"
            />
            <YAxis
              tick={{ fontSize: 10 }}
              width={40}
              stroke="currentColor"
              className="text-zinc-400"
              domain={["auto", "auto"]}
            />
            <Tooltip
              labelFormatter={(t) => (typeof t === "number" ? new Date(t).toLocaleString() : t)}
              formatter={(value) => [`${value} ${unit}`, humanize(measurementType)]}
              contentStyle={{ fontSize: 12 }}
            />
            {baselineRange && (
              <ReferenceArea
                y1={baselineRange[0]}
                y2={baselineRange[1]}
                fill="#0ea5e9"
                fillOpacity={0.08}
                stroke="none"
              />
            )}
            <Line
              type="monotone"
              dataKey="value"
              stroke="#0ea5e9"
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {hasBadQuality && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          Includes readings flagged with a data-quality limitation — see Evidence for detail.
        </p>
      )}
    </div>
  );
}

"use client";

import {
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { humanize } from "@/lib/terminology";
import type { TelemetryReadingResponse } from "@/lib/api/telemetry-types";

export interface TelemetryStoryMarker {
  label: string;
  iso: string;
  tone: "warn" | "info" | "ok";
}

const MARKER_COLOR: Record<TelemetryStoryMarker["tone"], string> = {
  warn: "#d97706",
  info: "#0284c7",
  ok: "#059669",
};

/** A one-line read of the latest point against this signal's own baseline range — real
 * computed comparison, never a fabricated diagnosis. When no baseline exists yet, says so
 * rather than guessing. */
function interpretSignal(
  latest: number,
  baselineRange: [number, number] | null | undefined,
): string {
  if (!baselineRange) {
    return "Not enough baseline history yet to characterize this signal's expected range.";
  }
  const [low, high] = baselineRange;
  if (latest > high) return "Currently above this asset's expected operating range.";
  if (latest < low) return "Currently below this asset's expected operating range.";
  return "Currently within this asset's expected operating range.";
}

/** A restrained, single-series time chart for one measurement type on one machine
 * (Phase 28 brief §28.9). Deliberately not interactive/zoomable — this reference
 * platform's telemetry volumes don't need it, and CLAUDE.md's visual language calls for
 * "restrained charts," not a full analytics-grade charting surface (ADR-159).
 *
 * `storyMarkers` overlays real, persisted incident/maintenance timestamps (detected,
 * intervention, recovered) so the calm-baseline / developing-issue / response / recovery
 * shape of a real event is visible directly on the chart — never a fabricated annotation,
 * only timestamps the platform actually recorded, and only drawn when they fall inside
 * this series' own data window. */
export function TelemetryChart({
  measurementType,
  readings,
  baselineRange,
  storyMarkers,
  tall = false,
}: {
  measurementType: string;
  readings: TelemetryReadingResponse[];
  /** optional [low, high] expected-range band, when a baseline exists for this sensor */
  baselineRange?: [number, number] | null;
  storyMarkers?: TelemetryStoryMarker[];
  /** the visually-dominant lead chart (e.g. pressure) — taller, larger type. */
  tall?: boolean;
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
  const visibleMarkers = (storyMarkers ?? []).filter((m) => {
    const t = new Date(m.iso).getTime();
    return points.length > 0 && t >= points[0].t && t <= points[points.length - 1].t;
  });

  if (points.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        No {humanize(measurementType).toLowerCase()} readings yet.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-zinc-500 dark:text-zinc-400">
        <span
          className={`font-medium text-zinc-700 dark:text-zinc-300 ${tall ? "text-sm" : "text-xs"}`}
        >
          {humanize(measurementType)}
        </span>
        <span className="text-xs">{unit}</span>
      </div>
      <div className={`w-full ${tall ? "h-56" : "h-40"}`}>
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
            {visibleMarkers.map((marker) => (
              <ReferenceLine
                key={`${marker.label}-${marker.iso}`}
                x={new Date(marker.iso).getTime()}
                stroke={MARKER_COLOR[marker.tone]}
                strokeDasharray="3 3"
                strokeWidth={1.25}
                label={{
                  value: marker.label,
                  position: "insideTopLeft",
                  fontSize: 9,
                  fill: MARKER_COLOR[marker.tone],
                }}
              />
            ))}
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
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        {interpretSignal(points[points.length - 1].value, baselineRange)}
      </p>
      {hasBadQuality && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          Includes readings flagged with a data-quality limitation — see Evidence for detail.
        </p>
      )}
      {visibleMarkers.length > 0 && (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">
          Dashed lines mark this machine&rsquo;s recorded incident/maintenance timestamps.
        </p>
      )}
    </div>
  );
}

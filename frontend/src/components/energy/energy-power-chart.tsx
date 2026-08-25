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

import type { TelemetryStoryMarker } from "@/components/telemetry-chart";
import type { EnergyAssessment } from "@/lib/api/energy-types";

const MARKER_COLOR: Record<TelemetryStoryMarker["tone"], string> = {
  warn: "#d97706",
  info: "#0284c7",
  ok: "#059669",
};

/**
 * Actual vs. expected contextual power over time (task §7) — mirrors
 * `TelemetryChart`'s restrained, non-interactive charting language exactly (same story-
 * marker overlay convention) rather than inventing a second charting idiom. Only ever
 * plots backend-returned `EnergyAssessment` history rows — no interpolation, no
 * reconstructed points for gaps the backend didn't compute.
 */
export function EnergyPowerChart({
  history,
  storyMarkers,
}: {
  history: EnergyAssessment[];
  storyMarkers?: TelemetryStoryMarker[];
}) {
  const points = history
    .filter((a) => a.actual_power_kw !== null)
    .map((a) => ({
      t: new Date(a.as_of_timestamp).getTime(),
      actual: a.actual_power_kw as number,
      expected: a.expected_power_kw,
      lower: a.expected_lower_kw,
      upper: a.expected_upper_kw,
    }))
    .sort((a, b) => a.t - b.t);

  const hasBand = points.some((p) => p.lower !== null && p.upper !== null);
  const visibleMarkers = (storyMarkers ?? []).filter((m) => {
    const t = new Date(m.iso).getTime();
    return points.length > 0 && t >= points[0].t && t <= points[points.length - 1].t;
  });

  if (points.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        No energy-assessment history recorded yet.
      </div>
    );
  }

  // A per-point band (ReferenceArea only supports one fixed y1/y2) — use the widest
  // observed band across the window as a visual guide rather than a per-point shape,
  // consistent with `TelemetryChart`'s own baseline-range treatment.
  const bandLow = hasBand
    ? Math.min(...points.filter((p) => p.lower !== null).map((p) => p.lower as number))
    : null;
  const bandHigh = hasBand
    ? Math.max(...points.filter((p) => p.upper !== null).map((p) => p.upper as number))
    : null;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-zinc-500 dark:text-zinc-400">
        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Actual vs. expected power
        </span>
        <span className="text-xs">kW</span>
      </div>
      <div className="h-56 w-full">
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
              formatter={(value, name) => [
                `${value} kW`,
                name === "actual" ? "Actual power" : "Expected (contextual)",
              ]}
              contentStyle={{ fontSize: 12 }}
            />
            {bandLow !== null && bandHigh !== null && (
              <ReferenceArea
                y1={bandLow}
                y2={bandHigh}
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
              dataKey="expected"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="actual"
              stroke="#0ea5e9"
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Solid line: actual power. Dashed line: expected power under comparable operating conditions.
        Shaded band: the widest expected range observed in this window.
      </p>
      {visibleMarkers.length > 0 && (
        <p className="mt-1 text-xs text-zinc-400 dark:text-zinc-600">
          Dashed vertical lines mark this machine&rsquo;s recorded incident/maintenance timestamps.
        </p>
      )}
    </div>
  );
}

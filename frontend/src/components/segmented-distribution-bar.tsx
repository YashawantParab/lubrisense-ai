interface Segment {
  key: string;
  label: string;
  count: number;
  colorClass: string;
}

/** Shared stacked-bar-plus-legend primitive (mirrors the pre-existing bespoke pattern in
 * `fleet-condition-distribution.tsx`/`action-readiness-distribution.tsx`) — used across
 * the Organization Command Center's reliability/action-readiness/data-trust/energy
 * sections so every portfolio distribution reads the same way. Status is never carried by
 * color alone: each legend row repeats the count and label as text. */
export function SegmentedDistributionBar({
  segments,
  emptyLabel = "No data recorded yet.",
}: {
  segments: Segment[];
  emptyLabel?: string;
}) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);

  if (total === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">{emptyLabel}</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
        role="img"
        aria-label={segments.map((s) => `${s.label}: ${s.count}`).join(", ")}
      >
        {segments.map((s) => (
          <div
            key={s.key}
            className={s.colorClass}
            style={{ width: `${(s.count / total) * 100}%` }}
            title={`${s.label}: ${s.count}`}
          />
        ))}
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {segments.map((s) => (
          <div key={s.key} className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${s.colorClass}`} aria-hidden />
            <dt className="text-zinc-500 dark:text-zinc-400">{s.label}</dt>
            <dd className="ml-auto font-medium text-zinc-900 dark:text-zinc-100">{s.count}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

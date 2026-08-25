import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { StatusPill } from "@/components/status-pill";
import type { AreaPerformance } from "@/lib/api/performance-types";

/**
 * Areas are organization-wide rollups (an area's real seeded metadata can span more than
 * one site — `site_codes`), never site-scoped aggregates the backend doesn't compute
 * (task's design-doc "no client-side recomputation of backend business semantics"). When
 * this table is shown inside a Site Detail page, every row's figures are still the area's
 * full organization-wide total — `site_codes` makes that explicit rather than implying a
 * site-scoped number that doesn't exist.
 */
export function AreaPerformanceTable({
  areas,
  currentSiteCode,
}: {
  areas: AreaPerformance[];
  /** When set, rows for an area active at more than this one site show which other sites
   * also report into it — read this table's own figures as organization-wide, not
   * filtered to `currentSiteCode` alone. */
  currentSiteCode?: string;
}) {
  if (areas.length === 0) {
    return (
      <EmptyState
        title="No areas yet"
        description="Areas appear here once machines carry process-area metadata."
      />
    );
  }

  const ordered = [...areas].sort(
    (a, b) =>
      b.critical_attention_count - a.critical_attention_count ||
      b.attention_count - a.attention_count,
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            <th className="px-4 py-2 font-medium">Area</th>
            <th className="px-4 py-2 font-medium">Assets</th>
            <th className="px-4 py-2 font-medium">Attention</th>
            <th className="px-4 py-2 font-medium">Critical</th>
            <th className="px-4 py-2 font-medium">Energy opportunities</th>
            <th className="px-4 py-2 font-medium">Qualified recoveries</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((area) => {
            const otherSites = area.site_codes.filter((code) => code !== currentSiteCode);
            return (
              <tr
                key={area.area}
                className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <td className="px-4 py-2.5">
                  <Link
                    href={`/performance/areas/${encodeURIComponent(area.area)}`}
                    className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                  >
                    {area.area}
                  </Link>
                  {currentSiteCode && otherSites.length > 0 && (
                    <div className="text-xs text-zinc-400 dark:text-zinc-600">
                      Also active at {otherSites.join(", ")}
                    </div>
                  )}
                </td>
                <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">{area.asset_count}</td>
                <td className="px-4 py-2.5">
                  {area.attention_count > 0 ? (
                    <StatusPill tone="warn">{area.attention_count}</StatusPill>
                  ) : (
                    <span className="text-zinc-400 dark:text-zinc-600">0</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  {area.critical_attention_count > 0 ? (
                    <StatusPill tone="error">{area.critical_attention_count}</StatusPill>
                  ) : (
                    <span className="text-zinc-400 dark:text-zinc-600">0</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                  {area.active_energy_opportunities > 0 ? area.active_energy_opportunities : "—"}
                </td>
                <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                  {area.qualified_recovery_count > 0 ? area.qualified_recovery_count : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

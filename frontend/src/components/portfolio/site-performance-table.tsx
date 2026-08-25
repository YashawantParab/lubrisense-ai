import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { StatusPill } from "@/components/status-pill";
import { bySeverityThenAttention } from "@/lib/portfolio";
import type { SitePerformance } from "@/lib/api/performance-types";

function dataLimitedCount(site: SitePerformance): number {
  return (
    (site.data_trust_distribution["ASSESSMENT_BLOCKED"] ?? 0) +
    (site.data_trust_distribution["ACTION_BLOCKED"] ?? 0)
  );
}

/**
 * Compact comparative rows, not one giant card per site (task §5) — real backend counts
 * only, ordered by critical-attention-first (`bySeverityThenAttention`), never a
 * fabricated per-site score. Every row is a click-through to Site Detail.
 */
export function SitePerformanceTable({ sites }: { sites: SitePerformance[] }) {
  if (sites.length === 0) {
    return (
      <EmptyState
        title="No sites yet"
        description="Sites appear here once machines are commissioned under them."
      />
    );
  }

  const ordered = bySeverityThenAttention(sites);

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
            <th className="px-4 py-2 font-medium">Site</th>
            <th className="px-4 py-2 font-medium">Assets</th>
            <th className="px-4 py-2 font-medium">Attention</th>
            <th className="px-4 py-2 font-medium">Critical</th>
            <th className="px-4 py-2 font-medium">Open maintenance</th>
            <th className="px-4 py-2 font-medium">Data limited</th>
            <th className="px-4 py-2 font-medium">Energy opportunities</th>
            <th className="px-4 py-2 font-medium">Qualified recoveries</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((site) => (
            <tr
              key={site.site_id}
              className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
            >
              <td className="px-4 py-2.5">
                <Link
                  href={`/performance/sites/${site.site_id}`}
                  className="font-medium text-sky-700 hover:underline dark:text-sky-400"
                >
                  {site.site_name}
                </Link>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">{site.site_code}</div>
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">{site.asset_count}</td>
              <td className="px-4 py-2.5">
                {site.attention_count > 0 ? (
                  <StatusPill tone="warn">{site.attention_count}</StatusPill>
                ) : (
                  <span className="text-zinc-400 dark:text-zinc-600">0</span>
                )}
              </td>
              <td className="px-4 py-2.5">
                {site.critical_attention_count > 0 ? (
                  <StatusPill tone="error">{site.critical_attention_count}</StatusPill>
                ) : (
                  <span className="text-zinc-400 dark:text-zinc-600">0</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                {site.open_maintenance_actions}
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                {dataLimitedCount(site) > 0 ? dataLimitedCount(site) : "—"}
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                {site.active_energy_opportunities > 0 ? site.active_energy_opportunities : "—"}
              </td>
              <td className="px-4 py-2.5 text-zinc-700 dark:text-zinc-300">
                {site.qualified_recovery_count > 0 ? site.qualified_recovery_count : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

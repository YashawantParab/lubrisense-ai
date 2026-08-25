import Link from "next/link";

import { PortfolioPriorityBadge, SeverityBadge } from "@/components/badges";
import { EmptyState } from "@/components/empty-state";
import { SectionCard } from "@/components/section-card";
import { humanize } from "@/lib/terminology";
import type { AttentionAsset } from "@/lib/api/performance-types";

/**
 * The Organization Command Center's/Site Detail's "Priority Attention" queue — sourced
 * directly from `GET /performance/{organization,sites/{id}}`'s own `top_attention_assets`
 * (backend-derived `PortfolioPriority` + evidence-language reasons). No score, no
 * client-side re-ranking: reliability/safety reasons appear first in `reasons` because the
 * backend's own `derive_priority` policy puts them first — this only renders that order.
 */
export function PortfolioAttentionQueue({
  assets,
  showSite = true,
  actions,
}: {
  assets: AttentionAsset[];
  /** Hide the site badge when already inside a single site's detail page. */
  showSite?: boolean;
  actions?: React.ReactNode;
}) {
  return (
    <SectionCard title="Priority attention" actions={actions}>
      {assets.length === 0 ? (
        <EmptyState
          title="Nothing needs attention right now"
          description="Every monitored asset currently reads healthy or is limited only by pending assessment — see the sections below."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
          {assets.map((asset) => (
            <li key={asset.ref.machine_id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Link
                    href={`/machines/${asset.ref.machine_id}`}
                    className="text-base font-semibold text-sky-700 hover:underline dark:text-sky-400"
                  >
                    {asset.ref.name}
                  </Link>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {asset.ref.asset_code}
                    {showSite && ` · ${asset.ref.site_name}`} · {asset.ref.area}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <PortfolioPriorityBadge value={asset.priority} />
                  {asset.condition_severity && <SeverityBadge value={asset.condition_severity} />}
                </div>
              </div>

              {asset.condition_type && (
                <p className="mt-2 text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {humanize(asset.condition_type)}
                </p>
              )}

              {asset.reasons.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-0.5">
                  {asset.reasons.map((reason, index) => (
                    <li
                      key={index}
                      className="text-xs text-zinc-500 before:mr-1.5 before:content-['—'] dark:text-zinc-400"
                    >
                      {reason}
                    </li>
                  ))}
                </ul>
              )}

              {(asset.priority === "DATA_LIMITED" || asset.condition_type === null) && (
                <Link
                  href={`/data-quality?machine=${asset.ref.machine_id}`}
                  className="mt-1.5 inline-block text-xs text-sky-600 hover:underline dark:text-sky-400"
                >
                  See why — Data Quality for this asset →
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

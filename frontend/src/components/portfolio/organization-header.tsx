import { ProvenanceBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";

/**
 * Task §3A — organization name, as-of timestamp, monitored sites/assets, and evidence
 * provenance. Deliberately no marketing copy: every value here is a real backend field
 * (`OrganizationPerformance`), not a headline written for this page.
 */
export function OrganizationHeader({
  organizationName,
  asOf,
  sites,
  monitoredAssets,
  provenance,
}: {
  organizationName: string;
  asOf: string;
  sites: number;
  monitoredAssets: number;
  provenance: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-xs font-semibold tracking-wide text-sky-600 uppercase dark:text-sky-400">
          Organization command center
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          {organizationName}
        </h1>
        <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
          {sites} monitored site{sites === 1 ? "" : "s"} · {monitoredAssets} monitored asset
          {monitoredAssets === 1 ? "" : "s"} · as of <RelativeTime iso={asOf} />
        </p>
      </div>
      <div className="flex flex-col items-end gap-1">
        <ProvenanceBadge value={provenance} />
        <p className="text-[11px] text-zinc-400 dark:text-zinc-600">
          Synthetic industrial scenarios — demonstrates product behavior, not field validation.
        </p>
      </div>
    </header>
  );
}

import { ProvenanceBadge } from "@/components/badges";
import { RelativeTime } from "@/components/relative-time";

/**
 * Task §3A — organization name, as-of timestamp, monitored sites/assets, and evidence
 * provenance. Deliberately no marketing copy: every number here is a real backend field
 * (`OrganizationPerformance`), never a headline written for this page. The one static
 * line (Live Demo Quality Cleanup §2/§16) is scope description, not a performance claim —
 * it names the domains this view covers, not a result — and replaces the earlier
 * "Organization command center" eyebrow/"Demo Tenant" framing this pass removed.
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
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          {organizationName}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Multi-site reliability, lubrication and efficiency performance
        </p>
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

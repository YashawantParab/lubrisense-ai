import type { HierarchySite } from "@/lib/api/asset-hierarchy-types";

export interface Crumb {
  label: string;
  href?: string;
}

/**
 * The one shared Organization / Site / Area / Asset / <capability> breadcrumb builder
 * (Enterprise Experience Pass B §3) — Machine Detail, Incident Detail, and Maintenance
 * Detail all call this instead of each hand-rolling its own crumb array, so the product's
 * context hierarchy reads identically everywhere. Falls back to "Fleet" only when a
 * machine's site genuinely cannot be resolved yet (hierarchy still loading, or a machine
 * with no site — should not happen in practice, but never crashes on it).
 */
export function buildAssetBreadcrumb({
  site,
  area,
  trailing,
}: {
  site: HierarchySite | null;
  area?: string | null;
  /** Zero or more crumbs after the asset itself — e.g. an incident/maintenance-case
   * title, or a sub-capability like "Energy & Efficiency". The last entry is never
   * given an href (it's the current page). */
  trailing: Crumb[];
}): Crumb[] {
  const crumbs: Crumb[] = [{ label: "Organization", href: "/performance/organization" }];
  crumbs.push(
    site
      ? { label: site.name, href: `/performance/sites/${site.id}` }
      : { label: "Fleet", href: "/fleet" },
  );
  if (area) {
    crumbs.push({ label: area, href: `/performance/areas/${encodeURIComponent(area)}` });
  }
  crumbs.push(...trailing);
  return crumbs;
}

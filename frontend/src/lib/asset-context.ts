import type { HierarchyResponse, HierarchySite } from "@/lib/api/asset-hierarchy-types";

/** Resolves the `HierarchySite` that contains a given machine, from the full tenant tree.
 * Shared by every page that needs an Organization/Site context for one machine (Machine
 * Detail, Incident Detail, Maintenance Detail) — extracted so each page stops
 * re-implementing its own flatten-and-search (Enterprise Experience Pass B §3). */
export function findSiteForMachine(
  hierarchy: HierarchyResponse | undefined,
  machineId: string | undefined,
): HierarchySite | null {
  if (!hierarchy || !machineId) return null;
  for (const customer of hierarchy.customers) {
    for (const site of customer.sites) {
      for (const plant of site.plants) {
        for (const line of plant.production_lines) {
          if (line.machines.some((m) => m.id === machineId)) return site;
        }
      }
    }
  }
  return null;
}

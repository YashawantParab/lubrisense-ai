import { describe, expect, it } from "vitest";

import { buildAssetBreadcrumb } from "@/lib/breadcrumbs";
import type { HierarchySite } from "@/lib/api/asset-hierarchy-types";

const site: HierarchySite = {
  id: "site-1",
  name: "Harborview Site",
  code: "HARBOR",
  status: "ACTIVE",
  plants: [],
};

describe("buildAssetBreadcrumb", () => {
  it("builds the full Organization / Site / Area / Asset chain when everything resolves", () => {
    const crumbs = buildAssetBreadcrumb({
      site,
      area: "Pyroprocessing",
      trailing: [{ label: "Kiln ID Fan IDF-01" }],
    });
    expect(crumbs.map((c) => c.label)).toEqual([
      "Organization",
      "Harborview Site",
      "Pyroprocessing",
      "Kiln ID Fan IDF-01",
    ]);
    expect(crumbs[1].href).toBe("/performance/sites/site-1");
    expect(crumbs[2].href).toBe("/performance/areas/Pyroprocessing");
  });

  it("falls back to Fleet when the site cannot be resolved yet", () => {
    const crumbs = buildAssetBreadcrumb({ site: null, trailing: [{ label: "Machine" }] });
    expect(crumbs[1]).toEqual({ label: "Fleet", href: "/fleet" });
  });

  it("omits the area segment when there is no area", () => {
    const crumbs = buildAssetBreadcrumb({ site, area: null, trailing: [{ label: "Machine" }] });
    expect(crumbs.map((c) => c.label)).toEqual(["Organization", "Harborview Site", "Machine"]);
  });

  it("supports multiple trailing crumbs (e.g. machine then incident)", () => {
    const crumbs = buildAssetBreadcrumb({
      site,
      trailing: [{ label: "BE-201", href: "/machines/be-201" }, { label: "Incident title" }],
    });
    expect(crumbs.map((c) => c.label)).toEqual([
      "Organization",
      "Harborview Site",
      "BE-201",
      "Incident title",
    ]);
  });
});

import { describe, expect, it } from "vitest";

import { findSiteForMachine } from "@/lib/asset-context";
import type { HierarchyResponse } from "@/lib/api/asset-hierarchy-types";

function hierarchy(): HierarchyResponse {
  return {
    generated_at: new Date().toISOString(),
    customers: [
      {
        id: "cust-1",
        name: "Customer",
        code: "C1",
        service_tier: "STANDARD",
        commercial_status: "ACTIVE",
        sites: [
          {
            id: "site-a",
            name: "Site A",
            code: "SITE_A",
            status: "ACTIVE",
            plants: [
              {
                id: "plant-1",
                name: "Plant",
                code: "P1",
                status: "ACTIVE",
                production_lines: [
                  {
                    id: "line-1",
                    name: "Line",
                    code: "L1",
                    criticality: "MEDIUM",
                    status: "ACTIVE",
                    machines: [
                      {
                        id: "machine-1",
                        name: "Machine One",
                        asset_code: "M1",
                        machine_type: "PUMP",
                        criticality: "MEDIUM",
                        status: "MONITORED",
                        equipment_class: null,
                        area: null,
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  };
}

describe("findSiteForMachine", () => {
  it("finds the site containing a given machine", () => {
    const site = findSiteForMachine(hierarchy(), "machine-1");
    expect(site?.name).toBe("Site A");
  });

  it("returns null for an unknown machine id", () => {
    expect(findSiteForMachine(hierarchy(), "unknown")).toBeNull();
  });

  it("returns null when hierarchy or machineId is not yet available", () => {
    expect(findSiteForMachine(undefined, "machine-1")).toBeNull();
    expect(findSiteForMachine(hierarchy(), undefined)).toBeNull();
  });
});

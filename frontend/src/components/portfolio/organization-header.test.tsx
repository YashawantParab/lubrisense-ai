import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OrganizationHeader } from "@/components/portfolio/organization-header";

describe("OrganizationHeader", () => {
  it("renders the real organization name and counts, no marketing copy", () => {
    render(
      <OrganizationHeader
        organizationName="LubriSense Demo Tenant"
        asOf={new Date().toISOString()}
        sites={5}
        monitoredAssets={24}
        provenance="MEASURED_PLATFORM_METRIC"
      />,
    );
    expect(screen.getByText("LubriSense Demo Tenant")).toBeInTheDocument();
    expect(screen.getByText(/5 monitored sites/)).toBeInTheDocument();
    expect(screen.getByText(/24 monitored assets/)).toBeInTheDocument();
  });

  it("uses singular wording for exactly one site/asset", () => {
    render(
      <OrganizationHeader
        organizationName="Solo Tenant"
        asOf={new Date().toISOString()}
        sites={1}
        monitoredAssets={1}
        provenance="MEASURED_PLATFORM_METRIC"
      />,
    );
    expect(screen.getByText(/1 monitored site ·/)).toBeInTheDocument();
    expect(screen.getByText(/1 monitored asset ·/)).toBeInTheDocument();
  });
});

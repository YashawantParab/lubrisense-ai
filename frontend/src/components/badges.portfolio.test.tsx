import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ActionReadinessStateBadge,
  DataTrustCategoryBadge,
  EnergyBucketBadge,
  MaintenanceOutcomeBadge,
  PortfolioOutcomeBadge,
  PortfolioPriorityBadge,
} from "@/components/badges";

describe("Portfolio Intelligence badges", () => {
  it("humanizes every portfolio enum value it renders — never raw snake_case", () => {
    render(
      <>
        <PortfolioPriorityBadge value="CRITICAL_ATTENTION" />
        <ActionReadinessStateBadge value="HUMAN_ACTION_REQUIRED" />
        <EnergyBucketBadge value="ATTRIBUTION_SUPPORTED_OPPORTUNITY" />
        <MaintenanceOutcomeBadge value="COMPLETED_QUALIFIED_RECOVERY" />
        <DataTrustCategoryBadge value="DECISION_EVIDENCE_TRUSTED" />
        <PortfolioOutcomeBadge value="QUALIFIED_ENERGY_RECOVERY" />
      </>,
    );
    expect(screen.getByText("Critical Attention")).toBeInTheDocument();
    expect(screen.getByText("Human Action Required")).toBeInTheDocument();
    expect(screen.getByText("Attribution Supported Opportunity")).toBeInTheDocument();
    expect(screen.getByText("Completed Qualified Recovery")).toBeInTheDocument();
    expect(screen.getByText("Decision Evidence Trusted")).toBeInTheDocument();
    expect(screen.getByText("Qualified Energy Recovery")).toBeInTheDocument();
    expect(screen.queryByText(/_/)).not.toBeInTheDocument();
  });
});

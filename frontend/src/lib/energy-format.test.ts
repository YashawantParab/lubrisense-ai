import { describe, expect, it } from "vitest";

import { formatKw, formatPct } from "@/lib/energy-format";

describe("formatPct", () => {
  it("does not multiply by 100 — the backend already returns a percentage value", () => {
    // Regression: IDF-01's real seeded residual_pct is 13.72016591812358, meaning
    // +13.7%, not +1372.0%. A first draft of this formatter multiplied by 100 again.
    expect(formatPct(13.72016591812358)).toBe("+13.7%");
    expect(formatPct(-1.607375798677596)).toBe("-1.6%");
  });

  it("renders an em dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });

  it("always signs a non-negative value with a leading +", () => {
    expect(formatPct(0)).toBe("+0.0%");
  });
});

describe("formatKw", () => {
  it("formats to two decimal places with a unit", () => {
    expect(formatKw(29.58640170371888)).toBe("29.59 kW");
  });

  it("renders an em dash for null", () => {
    expect(formatKw(null)).toBe("—");
  });
});

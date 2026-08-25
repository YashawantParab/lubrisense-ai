import { describe, expect, it } from "vitest";

import {
  bySeverityThenAttention,
  toDynamicSegments,
  toSegments,
  PRIORITY_BAR_CLASS,
  PRIORITY_ORDER,
} from "@/lib/portfolio";

describe("toSegments", () => {
  it("orders segments by the fixed category order, not by count", () => {
    const segments = toSegments(
      { CRITICAL_ATTENTION: 1, MONITOR: 5 },
      PRIORITY_ORDER,
      PRIORITY_BAR_CLASS,
      (v) => v,
    );
    expect(segments.map((s) => s.key)).toEqual(["MONITOR", "CRITICAL_ATTENTION"]);
  });

  it("drops zero-count categories", () => {
    const segments = toSegments({ MONITOR: 3 }, PRIORITY_ORDER, PRIORITY_BAR_CLASS, (v) => v);
    expect(segments).toHaveLength(1);
    expect(segments[0].key).toBe("MONITOR");
  });

  it("returns an empty list for an empty distribution", () => {
    const segments = toSegments({}, PRIORITY_ORDER, PRIORITY_BAR_CLASS, (v) => v);
    expect(segments).toEqual([]);
  });
});

describe("toDynamicSegments", () => {
  it("sorts by count descending, not alphabetically", () => {
    const segments = toDynamicSegments(
      { NORMAL_OPERATION: 1, DEVELOPING_RESTRICTION_PATTERN: 5, POSSIBLE_LEAKAGE_PATTERN: 3 },
      (v) => v,
    );
    expect(segments.map((s) => s.key)).toEqual([
      "DEVELOPING_RESTRICTION_PATTERN",
      "POSSIBLE_LEAKAGE_PATTERN",
      "NORMAL_OPERATION",
    ]);
  });

  it("drops zero-count entries", () => {
    const segments = toDynamicSegments({ A: 0, B: 2 }, (v) => v);
    expect(segments).toHaveLength(1);
  });

  it("assigns every segment a color class", () => {
    const segments = toDynamicSegments({ A: 1, B: 1 }, (v) => v);
    expect(segments.every((s) => Boolean(s.colorClass))).toBe(true);
  });
});

describe("bySeverityThenAttention", () => {
  it("ranks critical attention above plain attention, using real backend counts only", () => {
    const sites = [
      { id: "low", critical_attention_count: 0, attention_count: 5 },
      { id: "high", critical_attention_count: 2, attention_count: 1 },
      { id: "mid", critical_attention_count: 0, attention_count: 1 },
    ];
    expect(bySeverityThenAttention(sites).map((s) => s.id)).toEqual(["high", "low", "mid"]);
  });

  it("does not mutate the input array", () => {
    const sites = [
      { id: "a", critical_attention_count: 0, attention_count: 1 },
      { id: "b", critical_attention_count: 1, attention_count: 0 },
    ];
    const original = [...sites];
    bySeverityThenAttention(sites);
    expect(sites).toEqual(original);
  });
});

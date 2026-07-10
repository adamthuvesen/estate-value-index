import {
  DEFAULT_ESTIMATE_RANGE_FACTORS,
  estimateRange,
  estimateRangeFactorsFromArtifact,
  formatEstimateRange,
  type EstimateRangeFactors,
} from "../estimate-range";
import { formatNumber } from "../format";

describe("estimateRange", () => {
  // Frozen against the 2026-07-09 evaluation (baked factors); these are the
  // exact windows the eval script's worked examples produce.
  it("produces the evaluated window for a 7M estimate (6-8M bucket)", () => {
    expect(estimateRange(7_000_000)).toEqual({
      center: 7_000_000,
      min: 6_900_000,
      max: 7_600_000,
    });
  });

  it("produces the evaluated window for a 4.5M estimate (4-5M bucket)", () => {
    expect(estimateRange(4_500_000)).toEqual({
      center: 4_500_000,
      min: 4_300_000,
      max: 4_700_000,
    });
  });

  it("produces the evaluated window for a 12M estimate (10-13M bucket)", () => {
    expect(estimateRange(12_000_000)).toEqual({
      center: 12_000_000,
      min: 11_900_000,
      max: 13_000_000,
    });
  });

  it("keeps the bands asymmetric — no symmetric ±window", () => {
    const range = estimateRange(7_000_000);
    const lowerGap = range.center - range.min; // 100k
    const upperGap = range.max - range.center; // 600k
    expect(lowerGap).not.toBe(upperGap);
  });

  it("clamps predictions below 3M to the first bucket", () => {
    expect(estimateRange(2_500_000)).toEqual({
      center: 2_500_000,
      min: 2_300_000,
      max: 2_500_000,
    });
  });

  it("clamps predictions at or above 13M to the last bucket", () => {
    expect(estimateRange(14_000_000)).toEqual({
      center: 14_000_000,
      min: 13_500_000,
      max: 14_900_000,
    });
  });

  it("rounds the low edge down and the high edge up to whole 100k", () => {
    const range = estimateRange(3_449_000);
    expect(range.min % 100_000).toBe(0);
    expect(range.max % 100_000).toBe(0);
    expect(range.min).toBeLessThanOrEqual(range.center);
    expect(range.max).toBeGreaterThanOrEqual(range.center);
  });

  it("rounds the center to the nearest 100k", () => {
    expect(estimateRange(11_930_000).center).toBe(11_900_000);
    expect(estimateRange(11_981_389).center).toBe(12_000_000);
  });

  it("picks the upper bucket exactly at a bucket edge", () => {
    // 6M falls in the 6-8M bucket (q65 = 1.0792); just below stays in 5-6M.
    expect(estimateRange(6_000_000).max).toBe(6_500_000);
    expect(estimateRange(5_999_999).max).toBe(6_300_000);
  });

  it("uses supplied factors over the baked default", () => {
    const factors: EstimateRangeFactors = {
      edges: [3_000_000],
      buckets: [{ lower: 0.5, upper: 2.0 }],
    };
    expect(estimateRange(4_000_000, factors)).toEqual({
      center: 4_000_000,
      min: 2_000_000,
      max: 8_000_000,
    });
  });

  it("formats the displayed range without exposing the point estimate", () => {
    expect(formatEstimateRange(estimateRange(7_000_000))).toBe(
      `${formatNumber(6_900_000)} – ${formatNumber(7_600_000)} kr`
    );
  });
});

describe("estimateRangeFactorsFromArtifact", () => {
  it("parses a well-formed metrics block into the lookup shape", () => {
    const parsed = estimateRangeFactorsFromArtifact({
      buckets: [
        { lower_edge: 3_000_000, upper_edge: 4_000_000, lower: 0.94, upper: 0.99 },
        { lower_edge: 4_000_000, upper_edge: null, lower: 0.96, upper: 1.05 },
      ],
    });
    expect(parsed).toEqual({
      edges: [3_000_000, 4_000_000],
      buckets: [
        { lower: 0.94, upper: 0.99 },
        { lower: 0.96, upper: 1.05 },
      ],
    });
  });

  it("returns null for malformed or empty input so callers use the baked default", () => {
    expect(estimateRangeFactorsFromArtifact(null)).toBeNull();
    expect(estimateRangeFactorsFromArtifact({ buckets: [] })).toBeNull();
    expect(
      estimateRangeFactorsFromArtifact({ buckets: [{ lower_edge: 3_000_000, lower: "x", upper: 1 }] })
    ).toBeNull();
    // Non-ascending edges are rejected.
    expect(
      estimateRangeFactorsFromArtifact({
        buckets: [
          { lower_edge: 4_000_000, lower: 0.9, upper: 1.1 },
          { lower_edge: 3_000_000, lower: 0.9, upper: 1.1 },
        ],
      })
    ).toBeNull();
  });

  it("keeps the baked default in sync with the frozen eval edges", () => {
    expect(DEFAULT_ESTIMATE_RANGE_FACTORS.edges).toHaveLength(
      DEFAULT_ESTIMATE_RANGE_FACTORS.buckets.length
    );
  });
});

import { buildMonthlySeries, computeTrailingChange } from "../price-trend";
import type { MonthlySeriesSource } from "../price-trend";

// Fixed reference date so month labels are deterministic.
const NOW = new Date("2026-06-15T00:00:00Z");

function source(partial: Partial<MonthlySeriesSource> = {}): MonthlySeriesSource {
  return {
    median_price_3m: null,
    median_price_6m: null,
    median_price_12m: null,
    ...partial,
  };
}

// Realistic entry shaped like data/derived/area_statistics.json (bromma_mariehall:
// 4 real months of 12, medians present, avg living area ~61 m²).
const realisticSource = source({
  monthly_prices: {
    month_6: 4_800_000,
    month_9: 3_800_000,
    month_10: 3_450_000,
    month_11: 2_425_000,
  },
  median_price_3m: 3_750_000,
  median_price_6m: 3_750_000,
  median_price_12m: 3_850_000,
});

describe("buildMonthlySeries", () => {
  it("preserves gaps — no forward/back fill of missing months", () => {
    const series = buildMonthlySeries(
      source({ monthly_prices: { month_3: 3_000_000, month_1: 3_300_000 } }),
      { now: NOW },
    );

    expect(series.points).toHaveLength(12);
    expect(series.realCount).toBe(2);

    const byAgo = Object.fromEntries(series.points.map((p) => [p.monthsAgo, p]));
    expect(byAgo[3].value).toBe(3_000_000);
    expect(byAgo[3].isReal).toBe(true);
    expect(byAgo[1].value).toBe(3_300_000);
    // Everything else stays null — the old code would have filled these.
    expect(byAgo[2].value).toBeNull();
    expect(byAgo[2].isReal).toBe(false);
    expect(byAgo[12].value).toBeNull();
    expect(series.points.filter((p) => p.value === null)).toHaveLength(10);
  });

  it("uses medians mode with fewer than 3 real points but medians present", () => {
    const series = buildMonthlySeries(
      source({ monthly_prices: { month_8: 2_350_000 }, median_price_12m: 3_000_000 }),
      { now: NOW },
    );
    expect(series.realCount).toBe(1);
    expect(series.mode).toBe("medians");
    expect(series.medians.find((m) => m.key === "12m")?.value).toBe(3_000_000);
  });

  it("uses line mode with 3 or more real points", () => {
    const series = buildMonthlySeries(realisticSource, { now: NOW });
    expect(series.realCount).toBe(4);
    expect(series.mode).toBe("line");
  });

  it("returns empty mode when everything is null", () => {
    const series = buildMonthlySeries(source(), { now: NOW });
    expect(series.realCount).toBe(0);
    expect(series.mode).toBe("empty");
    expect(series.points.every((p) => p.value === null)).toBe(true);
  });

  it("converts to price per m² when a living area is given", () => {
    const series = buildMonthlySeries(realisticSource, {
      now: NOW,
      unit: "per_sqm",
      avgLivingArea: 61,
    });
    expect(series.unit).toBe("per_sqm");
    const byAgo = Object.fromEntries(series.points.map((p) => [p.monthsAgo, p]));
    expect(byAgo[6].value).toBe(Math.round(4_800_000 / 61)); // 78689
    expect(series.medians.find((m) => m.key === "12m")?.value).toBe(Math.round(3_850_000 / 61));
  });

  it("falls back to total unit when per-m² is requested without a valid living area", () => {
    const series = buildMonthlySeries(realisticSource, { now: NOW, unit: "per_sqm", avgLivingArea: 0 });
    expect(series.unit).toBe("total");
    const byAgo = Object.fromEntries(series.points.map((p) => [p.monthsAgo, p]));
    expect(byAgo[6].value).toBe(4_800_000);
  });
});

describe("computeTrailingChange", () => {
  it("computes % change from first to last real point, ignoring nulls between", () => {
    const { points } = buildMonthlySeries(
      source({ monthly_prices: { month_3: 3_000_000, month_1: 3_300_000 } }),
      { now: NOW },
    );
    // month_3 (earlier) → month_1 (later): +10%
    expect(computeTrailingChange(points)).toBeCloseTo(10, 5);
  });

  it("uses the earliest and latest real points across the realistic fixture", () => {
    const { points } = buildMonthlySeries(realisticSource, { now: NOW });
    // month_11 (2_425_000) → month_6 (4_800_000)
    expect(computeTrailingChange(points)).toBeCloseTo(((4_800_000 - 2_425_000) / 2_425_000) * 100, 5);
  });

  it("returns null with fewer than 2 real points", () => {
    const { points } = buildMonthlySeries(
      source({ monthly_prices: { month_8: 2_350_000 } }),
      { now: NOW },
    );
    expect(computeTrailingChange(points)).toBeNull();
  });

  it("returns null when there are no real points", () => {
    const { points } = buildMonthlySeries(source(), { now: NOW });
    expect(computeTrailingChange(points)).toBeNull();
  });
});

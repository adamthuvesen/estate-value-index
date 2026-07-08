import { selectSimilarAreas } from "../similar-areas";
import type { AreaOverview } from "../area-types";

function overview(partial: Partial<AreaOverview> & Pick<AreaOverview, "area_name">): AreaOverview {
  return {
    display_name: partial.area_name,
    price_tier: "medium",
    avg_sold_price: 5_000_000,
    avg_price_per_sqm: 90_000,
    listing_count: 10,
    inventory: 5,
    median_price_3m: 5_000_000,
    days_on_market_median: 20,
    price_change_mean: 0,
    volatility: 0,
    undervalued_pct: 10,
    has_limited_data: false,
    sample_size: 30,
    ...partial,
  };
}

const current = overview({ area_name: "home", price_tier: "medium", avg_sold_price: 5_000_000 });

describe("selectSimilarAreas", () => {
  it("scores a tier match (+3) above a close-price different-tier area (+2)", () => {
    const tierMatchFarPrice = overview({
      area_name: "tier-match",
      price_tier: "medium",
      avg_sold_price: 9_000_000, // 80% away → no proximity points, only +3 tier
    });
    const priceCloseOtherTier = overview({
      area_name: "price-close",
      price_tier: "premium",
      avg_sold_price: 5_200_000, // within 10% → +2, but no tier match
    });

    const result = selectSimilarAreas(current, [priceCloseOtherTier, tierMatchFarPrice]);

    expect(result.map((a) => a.area_name)).toEqual(["tier-match", "price-close"]);
    expect(result[0].similarityScore).toBe(3);
    expect(result[1].similarityScore).toBe(2);
  });

  it("adds tier + proximity for a within-10% same-tier area", () => {
    const best = overview({ area_name: "best", price_tier: "medium", avg_sold_price: 5_400_000 });
    const [top] = selectSimilarAreas(current, [best]);
    expect(top.similarityScore).toBe(5); // +3 tier, +2 within 10%
  });

  it("gives +1 for within 20% but not within 10%", () => {
    const near = overview({ area_name: "near", price_tier: "premium", avg_sold_price: 5_800_000 }); // 16% away
    const [top] = selectSimilarAreas(current, [near]);
    expect(top.similarityScore).toBe(1);
  });

  it("excludes the current area itself", () => {
    const self = overview({ area_name: "home" });
    const other = overview({ area_name: "other" });
    const result = selectSimilarAreas(current, [self, other]);
    expect(result.map((a) => a.area_name)).toEqual(["other"]);
  });

  it("handles empty input", () => {
    expect(selectSimilarAreas(current, [])).toEqual([]);
  });

  it("returns at most n", () => {
    const many = Array.from({ length: 10 }, (_, i) => overview({ area_name: `a${i}` }));
    expect(selectSimilarAreas(current, many, 3)).toHaveLength(3);
    expect(selectSimilarAreas(current, many, 5)).toHaveLength(5);
  });
});

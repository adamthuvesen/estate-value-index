import type { AreaOverview } from "@/lib/area-types";

export interface ScoredArea extends AreaOverview {
  similarityScore: number;
}

/** The current-area fields the scoring compares against. */
type CurrentArea = Pick<AreaOverview, "area_name" | "price_tier" | "avg_sold_price">;

/**
 * Rank areas most similar to `current`, excluding `current` itself.
 *
 * Score (verbatim from the old `SimilarAreas` component):
 * +3 same price tier · +2 avg sold price within 10% · +1 within 20%.
 * Ties keep input order (stable sort); returns at most `n`.
 */
export function selectSimilarAreas(
  current: CurrentArea,
  all: AreaOverview[],
  n = 3,
): ScoredArea[] {
  return all
    .filter((area) => area.area_name !== current.area_name)
    .map((area) => {
      let score = 0;
      if (area.price_tier === current.price_tier) {
        score += 3;
      }
      const priceDiff = Math.abs(area.avg_sold_price - current.avg_sold_price) / current.avg_sold_price;
      if (priceDiff < 0.1) {
        score += 2;
      } else if (priceDiff < 0.2) {
        score += 1;
      }
      return { ...area, similarityScore: score };
    })
    .sort((a, b) => b.similarityScore - a.similarityScore)
    .slice(0, n);
}

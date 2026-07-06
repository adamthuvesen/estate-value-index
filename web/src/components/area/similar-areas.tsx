"use client";

import Link from "next/link";
import type { AreaOverview } from "@/lib/area-types";
import { formatNumber, formatNumberOrDash, formatSek } from "@/lib/format";

interface SimilarAreasProps {
  currentArea: string;
  currentPriceTier: string;
  avgSoldPrice: number;
  allAreas: AreaOverview[];
}

export function SimilarAreas({ currentArea, currentPriceTier, avgSoldPrice, allAreas }: SimilarAreasProps) {
  // Score similarity by price tier match (+3) and price proximity (+1 within 20%, +2 within 10%)
  const similarAreas = allAreas
    .filter((area) => area.area_name !== currentArea)
    .map((area) => {
      let score = 0;
      if (area.price_tier === currentPriceTier) {
        score += 3;
      }
      const priceDiff = Math.abs(area.avg_sold_price - avgSoldPrice) / avgSoldPrice;
      if (priceDiff < 0.1) {
        score += 2;
      } else if (priceDiff < 0.2) {
        score += 1;
      }
      return { ...area, similarityScore: score };
    })
    .sort((a, b) => b.similarityScore - a.similarityScore)
    .slice(0, 3);

  if (similarAreas.length === 0) {
    return null;
  }

  const tierLabel: Record<string, string> = {
    premium: "Premium",
    upper: "Upper",
    medium: "Medium",
    budget: "Budget",
  };

  return (
    <div>
      <div className="mb-6">
        <h3 className="text-[17px] font-semibold tracking-tight text-tactical-text">Similar areas</h3>
        <p className="text-[13px] text-tactical-muted">Comparable neighbourhoods based on price tier and market characteristics</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {similarAreas.map((area) => (
          <Link
            key={area.area_name}
            href={`/area/${area.area_name}`}
            className="tactical-focus-ring group block overflow-hidden rounded-xl border border-tactical-border bg-tactical-surface shadow-elev-1 transition-all hover:-translate-y-0.5 hover:border-tactical-border-emphasis hover:shadow-elev-2"
          >
            <div className="p-5">
              <div className="mb-3 flex items-start justify-between gap-2">
                <h4 className="text-[17px] font-semibold text-tactical-text transition-colors group-hover:text-tactical-accent">
                  {area.display_name}
                </h4>
                <span className="inline-flex shrink-0 rounded-pill border border-tactical-border bg-tactical-elevated px-2.5 py-0.5 text-[12px] font-medium text-tactical-muted">
                  {tierLabel[area.price_tier] ?? area.price_tier}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-tactical-muted">Avg price</span>
                  <span className="num font-medium text-tactical-text">{formatSek(area.avg_sold_price)}</span>
                </div>
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-tactical-muted">Properties</span>
                  <span className="num font-medium text-tactical-text">{formatNumber(area.listing_count)}</span>
                </div>
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-tactical-muted">Undervalued</span>
                  <span className="num font-medium text-val-exc">{formatNumberOrDash(area.undervalued_pct, 1)}%</span>
                </div>
              </div>

              <div className="mt-4 flex items-center text-[13px] font-medium text-tactical-accent transition-colors">
                <span>View area details</span>
                <svg
                  className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

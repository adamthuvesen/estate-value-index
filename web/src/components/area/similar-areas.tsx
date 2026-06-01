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

  const getPriceTierBadgeClass = (tier: string) => {
    switch (tier) {
      case "premium":
        return "bg-tactical-accent/10 text-tactical-accent border-tactical-accent/30";
      case "upper":
        return "bg-tactical-accent-hover/10 text-tactical-accent-hover border-tactical-accent-hover/30";
      case "medium":
        return "bg-tactical-success/10 text-tactical-success border-tactical-success/30";
      case "budget":
        return "bg-tactical-elevated text-tactical-muted border-tactical-border";
      default:
        return "bg-tactical-elevated text-tactical-muted border-tactical-border";
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h3 className="text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Similar Areas</h3>
        <p className="text-xs text-tactical-muted font-mono tracking-tactical">COMPARABLE NEIGHBORHOODS BASED ON PRICE TIER AND MARKET CHARACTERISTICS</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {similarAreas.map((area) => (
          <Link
            key={area.area_name}
            href={`/area/${area.area_name}`}
            className="group block overflow-hidden rounded-tactical border border-tactical-border bg-tactical-elevated transition-all duration-tactical hover:border-tactical-accent"
          >
            <div className="p-5">
              <div className="mb-3 flex items-start justify-between">
                <h4 className="text-lg font-bold text-tactical-text font-mono transition-colors duration-tactical group-hover:text-tactical-accent">
                  {area.display_name}
                </h4>
                <span
                  className={`inline-flex rounded-tactical border px-2.5 py-0.5 text-xs font-mono font-semibold uppercase ${getPriceTierBadgeClass(
                    area.price_tier
                  )}`}
                >
                  {area.price_tier}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-tactical-muted uppercase">Avg Price</span>
                  <span className="font-semibold text-tactical-text">{formatSek(area.avg_sold_price)}</span>
                </div>
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-tactical-muted uppercase">Properties</span>
                  <span className="font-semibold text-tactical-text">{formatNumber(area.listing_count)}</span>
                </div>
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-tactical-muted uppercase">Undervalued</span>
                  <span className="font-semibold text-tactical-success">{formatNumberOrDash(area.undervalued_pct, 1)}%</span>
                </div>
              </div>

              <div className="mt-4 flex items-center text-xs font-mono font-medium text-tactical-accent group-hover:text-tactical-accent-hover transition-colors duration-tactical uppercase">
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

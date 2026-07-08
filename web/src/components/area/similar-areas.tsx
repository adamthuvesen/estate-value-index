import Link from "next/link";
import type { ScoredArea } from "@/lib/similar-areas";
import { PRICE_TIER_LABEL } from "@/lib/tiers";
import { formatNumber, formatNumberOrDash, formatSek } from "@/lib/format";

interface SimilarAreasProps {
  /** Pre-scored on the server via `selectSimilarAreas` — render-only here. */
  areas: ScoredArea[];
}

export function SimilarAreas({ areas }: SimilarAreasProps) {
  if (areas.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="mb-6">
        <h3 className="text-[17px] font-semibold tracking-tight text-ledger-text">
          Similar areas
        </h3>
        <p className="text-[13px] text-ledger-muted">
          Comparable neighbourhoods based on price tier and market characteristics
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {areas.map((area) => (
          <Link
            key={area.area_name}
            href={`/area/${area.area_name}`}
            className="focus-ring group block overflow-hidden rounded-xl border border-ledger-border bg-ledger-surface shadow-elev-1 transition-all hover:-translate-y-0.5 hover:border-ledger-border-emphasis hover:shadow-elev-2"
          >
            <div className="p-5">
              <div className="mb-3 flex items-start justify-between gap-2">
                <h4 className="text-[17px] font-semibold text-ledger-text transition-colors group-hover:text-ledger-accent">
                  {area.display_name}
                </h4>
                <span className="inline-flex shrink-0 rounded-pill border border-ledger-border bg-ledger-elevated px-2.5 py-0.5 text-[12px] font-medium text-ledger-muted">
                  {PRICE_TIER_LABEL[area.price_tier] ?? area.price_tier}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-ledger-muted">Avg price</span>
                  <span className="num font-medium text-ledger-text">
                    {formatSek(area.avg_sold_price)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-ledger-muted">Properties</span>
                  <span className="num font-medium text-ledger-text">
                    {formatNumber(area.listing_count)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-ledger-muted">Undervalued</span>
                  <span className="num font-medium text-val-exc">
                    {formatNumberOrDash(area.undervalued_pct, 1)}%
                  </span>
                </div>
              </div>

              <div className="mt-4 flex items-center text-[13px] font-medium text-ledger-accent transition-colors">
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

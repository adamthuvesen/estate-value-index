"use client";

import type { AreaMarketDynamics, AreaOverviewStats } from "@/lib/area-types";
import { formatNumber, formatSek } from "@/lib/format";
import { useRoomFilter } from "@/components/area/room-filter-provider";

interface OverviewSectionProps {
  overview: AreaOverviewStats;
  marketDynamics: AreaMarketDynamics;
}

/** Headline KPI row — room-filter aware. Phase 7 folds this into the hero. */
export function OverviewSection({ overview, marketDynamics }: OverviewSectionProps) {
  const { stats } = useRoomFilter();

  const avgPricePerSqm = stats?.overview.avg_price_per_sqm ?? overview.avg_price_per_sqm;
  const avgSoldPrice = stats?.overview.avg_sold_price ?? overview.avg_sold_price;
  const listingCount = stats?.overview.listing_count ?? overview.listing_count;
  const daysOnMarket =
    stats?.market_dynamics.days_on_market_median ?? marketDynamics.days_on_market_median;

  return (
    <div id="overview" className="mx-auto mb-6 max-w-3xl">
      <dl className="grid grid-cols-1 divide-y divide-ledger-border overflow-hidden rounded-2xl border border-ledger-border bg-ledger-surface shadow-elev-1 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div className="px-5 py-4">
          <dt className="eyebrow">Average price per m²</dt>
          <dd className="num mt-1 text-2xl font-semibold text-ledger-text">
            {avgPricePerSqm ? formatNumber(avgPricePerSqm) : "—"}
          </dd>
          <p className="mt-0.5 text-[12px] text-ledger-muted">
            Sold: <span className="num">{formatSek(avgSoldPrice)}</span>
          </p>
        </div>
        <div className="px-5 py-4">
          <dt className="eyebrow">Market activity</dt>
          <dd className="num mt-1 text-2xl font-semibold text-ledger-text">
            {formatNumber(listingCount)}
          </dd>
          <p className="mt-0.5 text-[12px] text-ledger-muted">Total properties</p>
        </div>
        <div className="px-5 py-4">
          <dt className="eyebrow">Days on market</dt>
          <dd className="num mt-1 text-2xl font-semibold text-ledger-text">
            {formatNumber(daysOnMarket)}
          </dd>
          <p className="mt-0.5 text-[12px] text-ledger-muted">Median listing duration</p>
        </div>
      </dl>
    </div>
  );
}

"use client";

import type { AreaMarketDynamics, AreaOverviewStats } from "@/lib/area-types";
import { formatNumber, formatNumberOrDash, formatSek } from "@/lib/format";
import { PriceTrendChart } from "@/components/area/price-trend-chart";
import { useRoomFilter } from "@/components/area/room-filter-provider";

interface MarketSectionProps {
  /** All-rooms overview — the monthly price series only exists at this level. */
  overview: AreaOverviewStats;
  marketDynamics: AreaMarketDynamics;
  avgLivingArea: number | null;
}

export function MarketSection({ overview, marketDynamics, avgLivingArea }: MarketSectionProps) {
  const { stats } = useRoomFilter();
  const dynamics = stats?.market_dynamics ?? marketDynamics;

  return (
    <div id="market" className="ledger-card mb-6 p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold tracking-tight text-ledger-text">
        Market dynamics
      </h2>

      <div className="mb-5">
        <PriceTrendChart
          median_price_3m={overview.median_price_3m}
          median_price_6m={overview.median_price_6m}
          median_price_12m={overview.median_price_12m}
          monthly_prices={overview.monthly_prices}
          avgLivingArea={avgLivingArea}
        />
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="eyebrow">Price change (mean)</p>
          <p
            className={`num mt-2 text-2xl font-semibold ${
              dynamics.price_change_mean > 0 ? "text-val-exc" : "text-val-high"
            }`}
          >
            {dynamics.price_change_mean > 0 ? "+" : ""}
            {formatSek(dynamics.price_change_mean)}
          </p>
        </div>
        <div>
          <p className="eyebrow">Volatility</p>
          <p className="num mt-2 text-2xl font-semibold text-ledger-text">
            {formatSek(dynamics.volatility)}
          </p>
        </div>
        <div>
          <p className="eyebrow">Sales volume (3M)</p>
          <p className="num mt-2 text-2xl font-semibold text-ledger-text">
            {formatNumber(marketDynamics.sales_volume_3m)}
          </p>
          <p className="num mt-1 text-[12px] text-ledger-muted">
            6M: {formatNumber(marketDynamics.sales_volume_6m)} · 12M:{" "}
            {formatNumber(marketDynamics.sales_volume_12m)}
          </p>
        </div>
        <div>
          <p className="eyebrow">Liquidity score</p>
          <p className="num mt-2 text-2xl font-semibold text-ledger-text">
            {formatNumberOrDash(dynamics.liquidity, 2)}
          </p>
        </div>
      </div>
    </div>
  );
}

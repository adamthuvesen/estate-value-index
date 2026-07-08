"use client";

import { useState } from "react";
import type { AreaMarketDynamics, AreaOverviewStats } from "@/lib/area-types";
import { formatNumber, formatNumberOrDash, formatSek } from "@/lib/format";
import { buildMonthlySeries, computeTrailingChange, type PriceUnit } from "@/lib/price-trend";
import { FigureFrame } from "@/components/ui/figure-frame";
import { PriceTrendChart } from "@/components/area/charts/price-trend-chart";
import { Segmented } from "@/components/area/charts/segmented";
import { useRoomFilter } from "@/components/area/room-filter-provider";
import { figureMeta, roomScopeNote } from "@/lib/area-report";

interface MarketSectionProps {
  /** All-rooms overview — the monthly price series only exists at this level. */
  overview: AreaOverviewStats;
  marketDynamics: AreaMarketDynamics;
  avgLivingArea: number | null;
  updatedAt: string;
  stale: boolean;
}

export function MarketSection({
  overview,
  marketDynamics,
  avgLivingArea,
  updatedAt,
  stale,
}: MarketSectionProps) {
  const { filter, stats } = useRoomFilter();
  const dynamics = stats?.market_dynamics ?? marketDynamics;

  const canPerSqm = Boolean(avgLivingArea && avgLivingArea > 0);
  const [unit, setUnit] = useState<PriceUnit>(canPerSqm ? "per_sqm" : "total");
  const series = buildMonthlySeries(overview, { unit, avgLivingArea });
  const change = computeTrailingChange(series.points);

  const note = roomScopeNote(filter, stats?.property_count);

  return (
    <FigureFrame
      kind="figure"
      index={1}
      id="market"
      title="Market dynamics"
      meta={figureMeta(updatedAt, note)}
      stale={stale}
      actions={
        canPerSqm ? (
          <Segmented
            ariaLabel="Price unit"
            value={unit}
            onChange={setUnit}
            options={[
              { value: "per_sqm", label: "Price/m²" },
              { value: "total", label: "Total" },
            ]}
          />
        ) : undefined
      }
    >
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <p className="text-caption text-ledger-dimmed">
          Median {unit === "per_sqm" ? "price / m²" : "sold price"} over the last 12 months
        </p>
        {change !== null && (
          <p className="text-right">
            <span className="eyebrow text-ledger-dimmed">12-mo change</span>{" "}
            <span
              className={`num text-body-sm font-semibold ${change >= 0 ? "text-val-exc" : "text-val-high"}`}
            >
              {change >= 0 ? "+" : ""}
              {change.toFixed(1)}%
            </span>
          </p>
        )}
      </div>

      <PriceTrendChart series={series} unit={series.unit} />

      <dl className="mt-6 grid gap-5 border-t border-ledger-border pt-5 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="eyebrow">Price change (mean)</dt>
          <dd
            className={`num mt-1.5 text-title font-semibold ${
              dynamics.price_change_mean > 0 ? "text-val-exc" : "text-val-high"
            }`}
          >
            {dynamics.price_change_mean > 0 ? "+" : ""}
            {formatSek(dynamics.price_change_mean)}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Volatility</dt>
          <dd className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatSek(dynamics.volatility)}
          </dd>
        </div>
        <div>
          {/* Sales volume isn't computed per room bucket, so it stays all-rooms; label it
              honestly when a room filter is active rather than implying it's scoped. */}
          <dt className="eyebrow">
            {filter === "all" ? "Sales volume (3M)" : "Sales volume (3M, all rooms)"}
          </dt>
          <dd className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatNumber(marketDynamics.sales_volume_3m)}
          </dd>
          <p className="num mt-1 text-caption text-ledger-muted">
            6M: {formatNumber(marketDynamics.sales_volume_6m)} · 12M:{" "}
            {formatNumber(marketDynamics.sales_volume_12m)}
          </p>
        </div>
        <div>
          <dt className="eyebrow">Liquidity score</dt>
          <dd className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatNumberOrDash(dynamics.liquidity, 2)}
          </dd>
        </div>
      </dl>
    </FigureFrame>
  );
}

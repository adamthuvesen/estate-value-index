import type { AreaStatistics } from "@/lib/area-types";
import { PRICE_TIER_LABEL } from "@/lib/tiers";
import { StatBar, Stat } from "@/components/ui/stat-bar";
import { buildMonthlySeries, computeTrailingChange } from "@/lib/price-trend";
import { formatDateSv, formatNumber, formatNumberOrDash } from "@/lib/format";
import { cn } from "@/lib/cn";

interface AreaHeroProps {
  area: AreaStatistics;
  updatedAt: string;
  stale: boolean;
}

/** Opening spread — pinned to all-rooms figures (matches the OG description).
 *  Room-filtered KPIs live on in the sections below. */
export function AreaHero({ area, updatedAt, stale }: AreaHeroProps) {
  const tierLabel = PRICE_TIER_LABEL[area.price_tier] ?? area.price_tier;
  const perSqm = area.overview.avg_price_per_sqm;

  const series = buildMonthlySeries(area.overview, {
    unit: "per_sqm",
    avgLivingArea: area.size_analysis.size_distribution.living_area.mean,
  });
  const change = computeTrailingChange(series.points);
  const undervalued = area.value_insights.undervalued_pct;

  return (
    <header className="border-t border-ledger-border pt-5">
      <p className="eyebrow text-ledger-accent">
        Area report · <span className="text-ledger-muted">{tierLabel}</span>
      </p>
      <h1 className="mt-3 font-display text-display text-ledger-text text-balance">
        {area.display_name}
      </h1>

      <StatBar className="mt-7">
        <Stat
          value={perSqm ? formatNumber(perSqm) : "—"}
          label="Avg price / m²"
        />
        <Stat
          value={
            change === null ? (
              "—"
            ) : (
              <span className={change >= 0 ? "text-val-exc" : "text-val-high"}>
                {change >= 0 ? "+" : ""}
                {change.toFixed(1)}%
              </span>
            )
          }
          label="12-mo change"
        />
        <Stat
          value={formatNumber(area.market_dynamics.days_on_market_median)}
          label="Days on market"
        />
        <Stat
          value={
            <span className={undervalued ? "text-val-exc" : undefined}>
              {formatNumberOrDash(undervalued, 1)}%
            </span>
          }
          label="Undervalued share"
        />
      </StatBar>

      <p
        className={cn(
          "mt-6 text-body-sm",
          stale ? "text-val-over" : "text-ledger-muted",
        )}
      >
        Based on <span className="num">{formatNumber(area.overview.listing_count)}</span> sold
        listings · Updated {formatDateSv(updatedAt)}
        {stale ? " — data may be out of date" : ""}
      </p>

      {area.has_limited_data && (
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-pill border border-val-over-line bg-val-over-tint px-3 py-1 text-caption text-val-over">
          Small sample (n=<span className="num">{area.sample_size}</span>) — figures are
          indicative
        </p>
      )}
    </header>
  );
}

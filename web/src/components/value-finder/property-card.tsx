import Link from "next/link";
import { formatCurrency } from "@/lib/format";
import type { ValueProperty } from "@/lib/value-finder-types";

interface PropertyCardProps {
  property: ValueProperty;
}

function getValueBadgeColor(score: number): string {
  if (score >= 80) return "bg-tactical-success/10 text-tactical-success border-tactical-success/30";
  if (score >= 65) return "bg-tactical-success/10 text-tactical-success border-tactical-success/30";
  if (score >= 55) return "bg-tactical-elevated text-tactical-text border-tactical-border-emphasis";
  if (score >= 45) return "bg-tactical-elevated text-tactical-muted border-tactical-border";
  if (score >= 30) return "bg-tactical-accent-hover/10 text-tactical-accent-hover border-tactical-accent-hover/30";
  return "bg-tactical-accent/10 text-tactical-accent border-tactical-accent/30";
}


function getDeltaColor(deltaPercentage: number): string {
  if (deltaPercentage >= 20) return "text-tactical-success bg-tactical-success/10 border border-tactical-success/30";
  if (deltaPercentage >= 10) return "text-tactical-success bg-tactical-success/10 border border-tactical-success/30";
  if (deltaPercentage >= 5) return "text-tactical-success bg-tactical-success/5 border border-tactical-success/20";
  if (deltaPercentage >= 0) return "text-tactical-muted bg-tactical-elevated border border-tactical-border";
  if (deltaPercentage >= -5) return "text-tactical-muted bg-tactical-elevated border border-tactical-border";
  if (deltaPercentage >= -10) return "text-tactical-accent-hover bg-tactical-accent-hover/5 border border-tactical-accent-hover/20";
  if (deltaPercentage >= -20) return "text-tactical-accent-hover bg-tactical-accent-hover/10 border border-tactical-accent-hover/30";
  return "text-tactical-accent bg-tactical-accent/10 border border-tactical-accent/30";
}

export function PropertyCard({ property }: PropertyCardProps) {
  // Backend reports prediction_delta = predicted - sold; flip sign so positive = sold above prediction.
  const displayDelta = -property.prediction_delta_absolute;
  const displayPercentage = -property.prediction_delta_percentage;
  const soldAbovePrediction = displayDelta > 0;
  const deltaIcon = soldAbovePrediction ? "↑" : "↓";

  return (
    <div className="tactical-card tactical-card-hover group relative flex flex-col overflow-hidden p-5 transition-all duration-tactical ease-tactical hover:border-tactical-border-emphasis">
      <div className="absolute right-3 top-3 z-10">
        <div className={`inline-flex items-center gap-1.5 rounded-tactical border px-3 py-1.5 text-xs font-mono font-semibold ${getValueBadgeColor(property.value_score)}`}>
          <span>{property.value_score.toFixed(0)}</span>
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="mb-3 pr-16">
          <h3 className="truncate text-lg font-semibold text-tactical-text group-hover:text-tactical-accent transition-colors font-mono tracking-tactical" title={property.address}>
            {property.address}
          </h3>
          <p className="text-xs text-tactical-muted font-mono tracking-tactical">
            {property.area.toUpperCase()}, {property.municipality.toUpperCase()}
          </p>
        </div>

        <div className="mb-4">
          <span className={`inline-flex items-center rounded-tactical px-3 py-1 text-xs font-mono font-semibold uppercase tracking-tactical ${getValueBadgeColor(property.value_score)}`}>
            {property.value_tier}
          </span>
        </div>

        <div className="mb-4 space-y-2.5 rounded-tactical border border-tactical-border bg-tactical-elevated p-4">
          {property.listing_price && (
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[10px] font-mono tracking-tactical text-tactical-muted whitespace-nowrap uppercase">Listed Price:</span>
              <span className="text-sm font-mono font-semibold text-tactical-text text-right">{formatCurrency(property.listing_price)}</span>
            </div>
          )}
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-mono tracking-tactical text-tactical-muted whitespace-nowrap uppercase">Sold Price:</span>
            <span className="text-sm font-mono font-semibold text-tactical-text text-right">{formatCurrency(property.sold_price)}</span>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[10px] font-mono tracking-tactical text-tactical-muted whitespace-nowrap uppercase">Predicted:</span>
            <span className="text-sm font-mono font-semibold text-tactical-text text-right">{formatCurrency(property.predicted_price)}</span>
          </div>
          <div className={`mt-2 flex items-center justify-between gap-2 rounded-tactical px-3 py-2 ${getDeltaColor(-displayPercentage)}`}>
            <span className="text-[10px] font-mono tracking-tactical whitespace-nowrap uppercase">Difference:</span>
            <div className="flex flex-col items-end">
              <span className="text-sm font-mono font-bold whitespace-nowrap">
                {deltaIcon} {formatCurrency(Math.abs(displayDelta))}
              </span>
              <span className="text-xs font-mono font-medium">
                ({displayPercentage >= 0 ? '+' : ''}{displayPercentage.toFixed(1)}%)
              </span>
            </div>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-tactical-muted flex-shrink-0">📐</span>
            <span className="text-tactical-text truncate font-mono text-xs">{property.living_area} M²</span>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-tactical-muted flex-shrink-0">🚪</span>
            <span className="text-tactical-text truncate font-mono text-xs">{property.rooms} {property.rooms === 1 ? 'ROOM' : 'ROOMS'}</span>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-tactical-muted flex-shrink-0">🏗️</span>
            <span className="text-tactical-text truncate font-mono text-xs">{property.construction_year || "N/A"}</span>
          </div>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-tactical-muted flex-shrink-0">💰</span>
            <span className="text-tactical-text truncate font-mono text-xs">{formatCurrency(property.monthly_fee)}/MO</span>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-2 text-xs">
          {property.floor !== null && (
            <span className="rounded-tactical border border-tactical-border bg-tactical-elevated px-2.5 py-1 text-tactical-text font-mono whitespace-nowrap">
              FLOOR {property.floor}
            </span>
          )}
          {property.elevator !== null && (
            <span className={`rounded-tactical border px-2.5 py-1 font-mono whitespace-nowrap ${property.elevator ? "bg-tactical-success/10 text-tactical-success border-tactical-success/30" : "bg-tactical-elevated text-tactical-muted border-tactical-border"}`}>
              {property.elevator ? "✓ ELEVATOR" : "NO ELEVATOR"}
            </span>
          )}
          {property.balcony !== null && (
            <span className={`rounded-tactical border px-2.5 py-1 font-mono whitespace-nowrap ${property.balcony ? "bg-tactical-success/10 text-tactical-success border-tactical-success/30" : "bg-tactical-elevated text-tactical-muted border-tactical-border"}`}>
              {property.balcony ? "✓ BALCONY" : "NO BALCONY"}
            </span>
          )}
        </div>

        <div className="mb-4 border-t border-tactical-border pt-3 text-xs text-tactical-muted font-mono">
          <div className="flex flex-col gap-1 sm:flex-row sm:justify-between sm:gap-2">
            <span className="whitespace-nowrap">SOLD: {new Date(property.sold_date).toLocaleDateString("en-US", { year: 'numeric', month: 'short', day: 'numeric' }).toUpperCase()}</span>
            {property.days_on_market !== null && (
              <span className="whitespace-nowrap">{property.days_on_market} {property.days_on_market === 1 ? 'DAY' : 'DAYS'} ON MARKET</span>
            )}
          </div>
        </div>

        {property.url && (
          <Link
            href={property.url}
            target="_blank"
            rel="noopener noreferrer"
            className="tactical-btn-primary tactical-focus-ring mt-auto inline-flex items-center justify-center px-4 py-2.5 text-xs font-mono font-medium uppercase"
          >
            View on Booli
            <svg
              className="ml-2 h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
              />
            </svg>
          </Link>
        )}
      </div>
    </div>
  );
}

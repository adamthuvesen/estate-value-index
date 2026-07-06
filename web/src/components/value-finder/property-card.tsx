import Link from "next/link";
import { formatCurrency } from "@/lib/format";
import type { ValueProperty, ValueTier } from "@/lib/value-finder-types";

interface PropertyCardProps {
  property: ValueProperty;
}

type TierStyle = {
  label: string;
  dot: string;
  text: string;
  chip: string;
  gauge: string;
};

const TIER_STYLES: Record<ValueTier, TierStyle> = {
  "Excellent Value": {
    label: "Excellent value",
    dot: "bg-val-exc",
    text: "text-val-exc",
    chip: "bg-val-exc-tint text-val-exc border-val-exc-line",
    gauge: "bg-val-exc",
  },
  "Great Value": {
    label: "Great value",
    dot: "bg-val-great",
    text: "text-val-great",
    chip: "bg-val-exc-tint text-val-great border-val-exc-line",
    gauge: "bg-val-great",
  },
  "Good Value": {
    label: "Good value",
    dot: "bg-val-good",
    text: "text-val-good",
    chip: "bg-val-fair-tint text-val-good border-tactical-border",
    gauge: "bg-val-good",
  },
  "Fair Value": {
    label: "Fair value",
    dot: "bg-val-fair",
    text: "text-val-fair",
    chip: "bg-val-fair-tint text-val-fair border-tactical-border",
    gauge: "bg-val-fair",
  },
  Overvalued: {
    label: "Overvalued",
    dot: "bg-val-over",
    text: "text-val-over",
    chip: "bg-val-over-tint text-val-over border-val-over-line",
    gauge: "bg-val-over",
  },
  "Highly Overvalued": {
    label: "Highly overvalued",
    dot: "bg-val-high",
    text: "text-val-high",
    chip: "bg-val-high-tint text-val-high border-val-high-line",
    gauge: "bg-val-high",
  },
};

const FALLBACK_TIER: TierStyle = TIER_STYLES["Fair Value"];

function titleCaseArea(value: string): string {
  return value
    .toLowerCase()
    .split(/([\s-])/)
    .map((part) => (part.length > 1 ? part[0].toUpperCase() + part.slice(1) : part))
    .join("");
}

export function PropertyCard({ property }: PropertyCardProps) {
  const tier = TIER_STYLES[property.value_tier as ValueTier] ?? FALLBACK_TIER;

  // Backend reports prediction_delta = predicted - sold; flip so positive = sold above prediction.
  const displayDelta = -property.prediction_delta_absolute;
  const displayPercentage = -property.prediction_delta_percentage;
  const belowPrediction = displayDelta < 0; // sold under model estimate = undervalued

  // Gauge: symmetric ±40% band around the model estimate (center).
  const BAND = 40;
  const clamped = Math.max(-BAND, Math.min(BAND, displayPercentage));
  const half = (Math.abs(clamped) / BAND) * 50; // width from center, in %
  const fillLeft = belowPrediction ? 50 - half : 50;

  return (
    <article className="tactical-card tactical-card-hover group flex flex-col p-5">
      {/* Header: address + score */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className="truncate text-[17px] font-semibold leading-tight text-tactical-text"
            title={property.address}
          >
            {property.address}
          </h3>
          <p className="mt-0.5 truncate text-[13px] text-tactical-muted">
            {titleCaseArea(property.area)} · {titleCaseArea(property.municipality)}
          </p>
        </div>
        <div
          className={`flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-xl border ${tier.chip}`}
          title="Value score"
        >
          <span className="num text-[15px] font-semibold leading-none">
            {property.value_score.toFixed(0)}
          </span>
        </div>
      </div>

      {/* Tier */}
      <div className="mt-2.5 flex items-center gap-1.5">
        <span className={`h-2 w-2 rounded-full ${tier.dot}`} aria-hidden />
        <span className={`text-[13px] font-medium ${tier.text}`}>{tier.label}</span>
      </div>

      {/* Fair-value block */}
      <div className="mt-4 rounded-xl border border-tactical-border bg-tactical-elevated/60 p-4">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] text-tactical-muted">Sold</span>
          <span className="num text-[15px] font-semibold text-tactical-text">
            {formatCurrency(property.sold_price)}
          </span>
        </div>
        <div className="mt-1.5 flex items-baseline justify-between gap-2">
          <span className="text-[12px] text-tactical-muted">Model estimate</span>
          <span className="num text-[15px] font-medium text-tactical-muted">
            {formatCurrency(property.predicted_price)}
          </span>
        </div>

        {/* Gauge */}
        <div className="mt-3.5">
          <div className="value-gauge">
            {/* center reference (model estimate) */}
            <span
              className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-tactical-border-emphasis"
              aria-hidden
            />
            <span
              className={`value-gauge-fill ${tier.gauge}`}
              style={{ left: `${fillLeft}%`, width: `${half}%` }}
              aria-hidden
            />
          </div>
          <div className="mt-2 flex items-baseline justify-between gap-2">
            <span className={`num text-[15px] font-semibold ${tier.text}`}>
              {belowPrediction ? "−" : "+"}
              {formatCurrency(Math.abs(displayDelta))}
            </span>
            <span className={`text-[12px] font-medium ${tier.text}`}>
              {Math.abs(displayPercentage).toFixed(1)}% {belowPrediction ? "under estimate" : "over estimate"}
            </span>
          </div>
        </div>
      </div>

      {/* Facts */}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
        <Fact label="Size" value={`${property.living_area} m²`} />
        <Fact label="Rooms" value={`${property.rooms}`} />
        <Fact label="Built" value={property.construction_year ? `${property.construction_year}` : "—"} />
        <Fact label="Fee" value={`${formatCurrency(property.monthly_fee)}/mo`} />
      </dl>

      {/* Amenity chips */}
      <div className="mt-3.5 flex flex-wrap gap-1.5">
        {property.floor !== null && <Chip>Floor {property.floor}</Chip>}
        {property.elevator && <Chip icon>Elevator</Chip>}
        {property.balcony && <Chip icon>Balcony</Chip>}
      </div>

      {/* Meta */}
      <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-tactical-border pt-3 text-[12px] text-tactical-dimmed">
        <span>
          Sold{" "}
          {new Date(property.sold_date).toLocaleDateString("en-GB", {
            year: "numeric",
            month: "short",
            day: "numeric",
          })}
        </span>
        {property.days_on_market !== null && (
          <>
            <span aria-hidden>·</span>
            <span>
              {property.days_on_market} {property.days_on_market === 1 ? "day" : "days"} on market
            </span>
          </>
        )}
      </div>

      {property.url && (
        <Link
          href={property.url}
          target="_blank"
          rel="noopener noreferrer"
          className="tactical-btn tactical-focus-ring mt-4 w-full text-[13px]"
        >
          View on Booli
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
        </Link>
      )}
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-[11px] uppercase tracking-tactical-wide text-tactical-dimmed">{label}</dt>
      <dd className="num text-[13px] font-medium text-tactical-text">{value}</dd>
    </div>
  );
}

function Chip({ children, icon = false }: { children: React.ReactNode; icon?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-pill border border-tactical-border bg-tactical-surface px-2.5 py-1 text-[12px] font-medium text-tactical-muted">
      {icon && (
        <svg className="h-3 w-3 text-val-exc" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
        </svg>
      )}
      {children}
    </span>
  );
}

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { estimateRange, formatEstimateRange } from "@/lib/estimate-range";
import { formatSek, titleCaseArea } from "@/lib/format";
import { FALLBACK_TIER, VALUE_TIER_STYLES } from "@/lib/tiers";
import type { ValueProperty, ValueTier } from "@/lib/value-finder-types";

interface PropertyCardProps {
  property: ValueProperty;
}

// Human labels for the core fields a value score depends on. Missing any of
// these suppresses the row from ranking (see value_analysis.py CORE_RANK_FIELDS).
const CORE_FIELD_LABELS: Record<string, string> = {
  living_area: "size",
  price_per_sqm: "price per m²",
};

export function PropertyCard({ property }: PropertyCardProps) {
  if (!property.is_rankable) {
    return <InsufficientDataCard property={property} />;
  }

  const tier = VALUE_TIER_STYLES[property.value_tier as ValueTier] ?? FALLBACK_TIER;
  const displayedEstimateRange = estimateRange(property.predicted_price);

  // Match the Predictor page: visible gaps use the rounded estimate center, not
  // the raw point estimate from the model.
  const displayDelta = property.sold_price - displayedEstimateRange.center;
  const displayPercentage = (displayDelta / displayedEstimateRange.center) * 100;
  const belowPrediction = displayDelta < 0; // sold under model estimate = undervalued

  // Gauge: symmetric ±40% band around the model estimate (center).
  const BAND = 40;
  const clamped = Math.max(-BAND, Math.min(BAND, displayPercentage));
  const half = (Math.abs(clamped) / BAND) * 50; // width from center, in %
  const fillLeft = belowPrediction ? 50 - half : 50;

  const soldDate = new Date(property.sold_date).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <article className="ledger-card ledger-card-hover group flex flex-col p-4">
      {/* Header: address + location + tier, score badge */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className="truncate font-display text-[15px] font-semibold leading-tight text-ledger-text"
            title={property.address}
          >
            {property.address}
          </h3>
          <p className="mt-1 flex items-center gap-1.5 truncate text-[12px]">
            <span className="truncate text-ledger-muted">
              <Link
                href={`/area/${property.area}`}
                className="focus-ring font-medium text-ledger-muted underline-offset-2 transition-colors hover:text-ledger-accent hover:underline hover:decoration-ledger-accent/50"
              >
                {titleCaseArea(property.area)}
              </Link>{" "}
              · {titleCaseArea(property.municipality)}
            </span>
            <span aria-hidden className="text-ledger-border-emphasis">·</span>
            <span className={`inline-flex shrink-0 items-center gap-1 font-medium ${tier.text}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${tier.dot}`} aria-hidden />
              {tier.label}
            </span>
          </p>
        </div>
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${tier.chip}`}
          title="Value score (1–100)"
        >
          <span className="num text-[14px] font-semibold leading-none">
            {property.value_score?.toFixed(0) ?? "—"}
          </span>
        </div>
      </div>

      {/* Fair-value block */}
      <div className="mt-3 rounded-lg border border-ledger-border bg-ledger-elevated/60 px-3 py-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] text-ledger-muted">Sold</span>
          <span className="num text-[14px] font-semibold text-ledger-text">
            {formatSek(property.sold_price)}
          </span>
        </div>
        <div className="mt-1 flex items-baseline justify-between gap-2">
          <span className="text-[12px] text-ledger-muted">Estimate range</span>
          <span className="num text-right text-[13px] font-medium text-ledger-muted">
            {formatEstimateRange(displayedEstimateRange)}
          </span>
        </div>

        {/* Gauge */}
        <div className="mt-2.5">
          <div className="value-gauge">
            {/* center reference (model estimate) */}
            <span
              className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ledger-border-emphasis"
              aria-hidden
            />
            <span
              className={`value-gauge-fill ${tier.gauge}`}
              style={{ left: `${fillLeft}%`, width: `${half}%` }}
              aria-hidden
            />
          </div>
          <div className="mt-1.5 flex items-baseline justify-between gap-2">
            <span className={`num text-[14px] font-semibold ${tier.text}`}>
              {belowPrediction ? "−" : "+"}
              {formatSek(Math.abs(displayDelta))}
            </span>
            <span className={`text-[12px] font-medium ${tier.text}`}>
              {Math.abs(displayPercentage).toFixed(1)}% {belowPrediction ? "under estimate" : "over estimate"}
            </span>
          </div>
        </div>
      </div>

      {/* Facts */}
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
        <Fact label="Size" value={`${property.living_area} m²`} />
        <Fact label="Rooms" value={`${property.rooms}`} />
        <Fact label="Built" value={property.construction_year ? `${property.construction_year}` : "—"} />
        <Fact label="Fee" value={`${formatSek(property.monthly_fee)}/mo`} />
      </dl>

      {/* Footer: amenities + link, then meta */}
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-ledger-border pt-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {property.floor !== null && <Chip>Floor {property.floor}</Chip>}
          {property.elevator && <Chip icon>Elevator</Chip>}
          {property.balcony && <Chip icon>Balcony</Chip>}
        </div>
        {property.url && (
          <Link
            href={property.url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring inline-flex shrink-0 items-center gap-1 text-[12px] font-medium text-ledger-muted transition-colors hover:text-ledger-accent"
          >
            Booli
            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
      <p className="mt-2 text-[11px] text-ledger-dimmed">
        Sold {soldDate}
        {property.days_on_market !== null &&
          ` · ${property.days_on_market} ${property.days_on_market === 1 ? "day" : "days"} on market`}
      </p>
    </article>
  );
}

function InsufficientDataCard({ property }: PropertyCardProps) {
  const missing = property.missing_core_fields
    .map((field) => CORE_FIELD_LABELS[field] ?? field)
    .join(", ");
  const reason = missing ? `Missing ${missing}` : "Insufficient data";
  const sizeLabel = property.living_area ? `${property.living_area} m²` : "—";

  const soldDate = new Date(property.sold_date).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <article className="flex flex-col rounded-ledger border border-dashed border-ledger-border-emphasis bg-ledger-elevated/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3
            className="truncate font-display text-[15px] font-semibold leading-tight text-ledger-text"
            title={property.address}
          >
            {property.address}
          </h3>
          <p className="mt-1 truncate text-[12px] text-ledger-muted">
            <Link
              href={`/area/${property.area}`}
              className="focus-ring font-medium text-ledger-muted underline-offset-2 transition-colors hover:text-ledger-accent hover:underline hover:decoration-ledger-accent/50"
            >
              {titleCaseArea(property.area)}
            </Link>{" "}
            · {titleCaseArea(property.municipality)}
          </p>
        </div>
        <Badge variant="neutral" className="shrink-0">
          Not ranked
        </Badge>
      </div>

      <p className="mt-3 rounded-lg border border-ledger-border bg-ledger-surface px-3 py-2.5 text-[12px] text-ledger-muted">
        {reason} — not ranked. Sold for{" "}
        <span className="num font-medium text-ledger-text">
          {formatSek(property.sold_price)}
        </span>
        .
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
        <Fact label="Size" value={sizeLabel} />
        <Fact label="Rooms" value={property.rooms ? `${property.rooms}` : "—"} />
        <Fact label="Built" value={property.construction_year ? `${property.construction_year}` : "—"} />
        <Fact label="Fee" value={property.monthly_fee ? `${formatSek(property.monthly_fee)}/mo` : "—"} />
      </dl>

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-ledger-border pt-2.5">
        <p className="text-[11px] text-ledger-dimmed">Sold {soldDate}</p>
        {property.url && (
          <Link
            href={property.url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring inline-flex shrink-0 items-center gap-1 text-[12px] font-medium text-ledger-muted transition-colors hover:text-ledger-accent"
          >
            Booli
            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-[10px] uppercase tracking-eyebrow text-ledger-dimmed">{label}</dt>
      <dd className="num mt-0.5 whitespace-nowrap text-[13px] font-medium text-ledger-text">{value}</dd>
    </div>
  );
}

function Chip({ children, icon = false }: { children: React.ReactNode; icon?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-pill border border-ledger-border bg-ledger-surface px-2 py-0.5 text-[11px] font-medium text-ledger-muted">
      {icon && (
        <svg className="h-2.5 w-2.5 text-val-exc" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
        </svg>
      )}
      {children}
    </span>
  );
}

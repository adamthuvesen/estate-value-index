"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import type { PredictionResult } from "@/lib/prediction-types";

type PredictionResultsProps = {
  prediction: PredictionResult | null;
  modelLabel: string;
  currencyFormatter: Intl.NumberFormat;
  priceDifference: number | null;
  differencePercent: number | null;
  isAboveAsking: boolean | null;
};

const TIP_FOOTNOTE =
  "Small changes to rooms, area, or build year can move the estimate by 100k+ kr — adjust and re-run to compare scenarios.";

export function PredictionResults({
  prediction,
  modelLabel,
  currencyFormatter,
  priceDifference,
  differencePercent,
  isAboveAsking,
}: PredictionResultsProps) {
  return (
    <div className="lg:col-span-1">
      <FigureFrame
        kind="figure"
        index={2}
        title="Estimated value"
        meta={prediction ? `Model · ${modelLabel}` : "Awaiting inputs"}
        footnote={prediction ? TIP_FOOTNOTE : undefined}
        className="lg:sticky lg:top-20"
      >
        {prediction ? (
          <div className="space-y-6">
            <div>
              <p className="num font-display text-display leading-none text-ledger-text">
                {formatDisplayPrice(currencyFormatter, prediction.rounded_predicted_price)}
              </p>
              <IntervalBar
                min={prediction.price_range_min}
                estimate={prediction.rounded_predicted_price}
                max={prediction.price_range_max}
                formatter={currencyFormatter}
              />
            </div>

            {priceDifference !== null && (
              <div
                className={`rounded-ledger border p-4 ${
                  isAboveAsking
                    ? "border-val-exc-line bg-val-exc-tint"
                    : "border-val-high-line bg-val-high-tint"
                }`}
              >
                <p
                  className={`text-caption font-medium ${isAboveAsking ? "text-val-exc" : "text-val-high"}`}
                >
                  {isAboveAsking ? "Above listing price" : "Below listing price"}
                </p>
                <p
                  className={`num mt-1 text-2xl font-semibold ${isAboveAsking ? "text-val-exc" : "text-val-high"}`}
                >
                  {priceDifference > 0 ? "+" : "−"}
                  {currencyFormatter.format(Math.abs(priceDifference))}
                  {differencePercent !== null && (
                    <span className="ml-1.5 text-body font-medium">
                      ({differencePercent > 0 ? "+" : ""}
                      {differencePercent.toFixed(1)}%)
                    </span>
                  )}
                </p>
              </div>
            )}

            <dl className="space-y-0 text-body-sm">
              {prediction.input_data.listing_price != null && (
                <Row label="Listing price">
                  <span className="num font-semibold text-ledger-text">
                    {currencyFormatter.format(prediction.input_data.listing_price)}
                  </span>
                </Row>
              )}
              <Row label="Model">
                <span className="font-medium text-ledger-text">{modelLabel}</span>
              </Row>
              <Row label="Listing ID">
                <span className="num text-ledger-text">{prediction.listing_id}</span>
              </Row>
              <Row label="Estimated" last>
                <span className="text-ledger-muted">
                  {new Date(prediction.timestamp).toLocaleString("en-GB")}
                </span>
              </Row>
            </dl>
          </div>
        ) : (
          <div className="rounded-ledger border border-dashed border-ledger-border-emphasis px-5 py-12 text-center">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-ledger-elevated">
              <svg
                className="h-5 w-5 text-ledger-dimmed"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.75}
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                />
              </svg>
            </div>
            <p className="mt-3 text-body-sm leading-relaxed text-ledger-muted">
              Fill in the details and estimate to see a valuation here.
            </p>
          </div>
        )}
      </FigureFrame>
    </div>
  );
}

/** Horizontal interval bar: ink ticks at min/max with a marker at the estimate on an elevated track. */
function IntervalBar({
  min,
  estimate,
  max,
  formatter,
}: {
  min: number;
  estimate: number;
  max: number;
  formatter: Intl.NumberFormat;
}) {
  const range = max - min;
  const pct = range > 0 ? Math.min(100, Math.max(0, ((estimate - min) / range) * 100)) : 50;

  return (
    <div className="mt-5">
      <span className="eyebrow text-ledger-dimmed">Estimated range</span>
      <div className="relative mt-2.5 h-2 rounded-pill bg-ledger-elevated">
        <span
          className="absolute inset-y-0 left-0 rounded-pill bg-ledger-accent/15"
          style={{ width: `${pct}%` }}
        />
        <span className="absolute left-0 top-1/2 h-3.5 w-0.5 -translate-y-1/2 bg-ledger-text" />
        <span className="absolute right-0 top-1/2 h-3.5 w-0.5 -translate-y-1/2 bg-ledger-text" />
        <span
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ledger-surface bg-ledger-text"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="num mt-2 flex justify-between text-caption text-ledger-dimmed">
        <span>{formatDisplayPrice(formatter, min)}</span>
        <span>{formatDisplayPrice(formatter, max)}</span>
      </div>
    </div>
  );
}

function formatDisplayPrice(formatter: Intl.NumberFormat, value: number): string {
  return formatter.format(value).replace(/\u00a0/g, " ");
}

function Row({
  label,
  children,
  last = false,
}: {
  label: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-baseline justify-between py-2.5 ${last ? "" : "border-b border-ledger-border"}`}
    >
      <dt className="text-ledger-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

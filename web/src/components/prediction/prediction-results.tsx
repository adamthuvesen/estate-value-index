"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import type { PredictionResult } from "@/lib/prediction-types";
import type { EstimateRange } from "@/lib/estimate-range";
import { formatNumber } from "@/lib/format";

type PredictionResultsProps = {
  prediction: PredictionResult | null;
  modelLabel: string;
  currencyFormatter: Intl.NumberFormat;
  /** The displayed value window — the raw point estimate is never shown. */
  estimateRange: EstimateRange | null;
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
  estimateRange,
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
        {prediction && estimateRange ? (
          <div className="space-y-6">
            <div>
              <p className="num font-display text-headline leading-tight text-ledger-text">
                <span className="block">{formatNumber(estimateRange.min)} –</span>
                <span className="block">
                  {formatNumber(estimateRange.max)}{" "}
                  <span className="text-title text-ledger-muted">kr</span>
                </span>
              </p>
              <p className="mt-2 text-caption text-ledger-dimmed">Estimated range</p>
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

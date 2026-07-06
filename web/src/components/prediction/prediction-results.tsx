"use client";

import type { PredictionResult } from "@/lib/prediction-types";

type PredictionResultsProps = {
  prediction: PredictionResult | null;
  modelLabel: string;
  currencyFormatter: Intl.NumberFormat;
  priceDifference: number | null;
  differencePercent: number | null;
  isAboveAsking: boolean | null;
};

export function PredictionResults({
  prediction,
  modelLabel,
  currencyFormatter,
  priceDifference,
  differencePercent,
  isAboveAsking,
}: PredictionResultsProps) {
  return (
    <aside className="space-y-4 lg:col-span-1">
      <div className="tactical-card p-6 lg:sticky lg:top-20">
        <h3 className="text-[15px] font-semibold text-tactical-text">Estimated value</h3>

        {prediction ? (
          <div className="mt-4 space-y-5">
            <div>
              <p className="num text-[34px] font-semibold leading-none tracking-tight text-tactical-text">
                {formatDisplayPrice(currencyFormatter, prediction.rounded_predicted_price)}
              </p>
              <p className="mt-2 text-[13px] text-tactical-muted">Estimated range around rounded model estimate</p>
              <p className="num mt-1 text-[13px] font-medium text-tactical-text">
                {formatDisplayPrice(currencyFormatter, prediction.price_range_min)} -{" "}
                {formatDisplayPrice(currencyFormatter, prediction.price_range_max)}
              </p>
            </div>

            {priceDifference !== null && (
              <div
                className={`rounded-xl border p-4 ${
                  isAboveAsking
                    ? "border-val-exc-line bg-val-exc-tint"
                    : "border-val-high-line bg-val-high-tint"
                }`}
              >
                <p className={`text-[12px] font-medium ${isAboveAsking ? "text-val-exc" : "text-val-high"}`}>
                  {isAboveAsking ? "Above listing price" : "Below listing price"}
                </p>
                <p className={`num mt-1 text-2xl font-semibold ${isAboveAsking ? "text-val-exc" : "text-val-high"}`}>
                  {priceDifference > 0 ? "+" : "−"}
                  {currencyFormatter.format(Math.abs(priceDifference))}
                  {differencePercent !== null && (
                    <span className="ml-1.5 text-[15px] font-medium">
                      ({differencePercent > 0 ? "+" : ""}
                      {differencePercent.toFixed(1)}%)
                    </span>
                  )}
                </p>
              </div>
            )}

            <dl className="space-y-0 text-[13px]">
              {prediction.input_data.listing_price != null && (
                <Row label="Listing price">
                  <span className="num font-semibold text-tactical-text">
                    {currencyFormatter.format(prediction.input_data.listing_price)}
                  </span>
                </Row>
              )}
              <Row label="Model">
                <span className="font-medium text-tactical-text">{modelLabel}</span>
              </Row>
              <Row label="Confidence">
                <span className="text-tactical-muted">{prediction.confidence}</span>
              </Row>
              <Row label="Listing ID">
                <span className="num text-tactical-text">{prediction.listing_id}</span>
              </Row>
              <Row label="Estimated" last>
                <span className="text-tactical-muted">
                  {new Date(prediction.timestamp).toLocaleString("en-GB")}
                </span>
              </Row>
            </dl>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-tactical-border-emphasis px-5 py-10 text-center">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-tactical-elevated">
              <svg className="h-5 w-5 text-tactical-dimmed" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            </div>
            <p className="mt-3 text-[13px] leading-relaxed text-tactical-muted">
              Fill in the details and estimate to see a valuation here.
            </p>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-tactical-border bg-tactical-elevated/50 p-5">
        <p className="text-[13px] leading-relaxed text-tactical-muted">
          <span className="font-medium text-tactical-text">Tip.</span> Small changes to rooms, area, or
          build year can move the estimate by 100k+ kr — adjust and re-run to compare scenarios.
        </p>
      </div>
    </aside>
  );
}

function formatDisplayPrice(formatter: Intl.NumberFormat, value: number): string {
  return formatter.format(value).replace(/\u00a0/g, " ");
}

function Row({ label, children, last = false }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between py-2.5 ${last ? "" : "border-b border-tactical-border"}`}>
      <dt className="text-tactical-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

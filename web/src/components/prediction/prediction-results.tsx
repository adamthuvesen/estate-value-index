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
    <aside className="tactical-section-gap lg:col-span-1">
      <div className="tactical-card p-6 tactical-corners">
        <header className="mb-4 space-y-1">
          <p className="tactical-label">PREDICTION OUTPUT</p>
          <h3 className="text-2xl font-bold text-tactical-text tracking-tactical">RESULT</h3>
        </header>

        {prediction ? (
          <div className="space-y-5">
            <div className="border border-tactical-border-emphasis bg-tactical-elevated p-4">
              <p className="tactical-label mb-2">PREDICTED SELLING PRICE</p>
              <p className="text-3xl font-bold text-tactical-text font-mono tracking-tactical">
                {currencyFormatter.format(prediction.predicted_price)}
              </p>
            </div>

            {priceDifference !== null && (
              <div
                className={`border p-4 ${
                  isAboveAsking
                    ? "border-tactical-success bg-tactical-elevated"
                    : "border-tactical-accent bg-tactical-elevated"
                }`}
              >
                <div className="flex items-center gap-2 tactical-label mb-2">
                  {isAboveAsking ? "▲ ABOVE ASKING" : "▼ BELOW ASKING"}
                </div>
                <div
                  className={`text-2xl font-bold font-mono tracking-tactical ${
                    isAboveAsking ? "text-tactical-success" : "text-tactical-accent"
                  }`}
                >
                  {priceDifference > 0 ? "+" : ""}
                  {currencyFormatter.format(priceDifference).replace("kr", "kr")}
                  {differencePercent !== null && (
                    <span className="ml-2 text-sm">
                      ({priceDifference > 0 ? "+" : ""}
                      {differencePercent.toFixed(1)}%)
                    </span>
                  )}
                </div>
              </div>
            )}

            <dl className="space-y-3 text-xs font-mono">
              <div className="flex items-baseline justify-between border-b border-tactical-border pb-2">
                <dt className="tactical-label">LISTING PRICE</dt>
                <dd className="text-sm font-bold text-tactical-text">
                  {currencyFormatter.format(prediction.input_data.listing_price)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between border-b border-tactical-border pb-2">
                <dt className="tactical-label">MODEL</dt>
                <dd className="tactical-badge border-tactical-border-emphasis text-tactical-text">
                  {modelLabel.toUpperCase()}
                </dd>
              </div>
              <div className="flex items-baseline justify-between border-b border-tactical-border pb-2">
                <dt className="tactical-label">CONFIDENCE</dt>
                <dd className="text-tactical-muted">{prediction.confidence}</dd>
              </div>
              <div className="flex items-baseline justify-between border-b border-tactical-border pb-2">
                <dt className="tactical-label">LISTING ID</dt>
                <dd className="text-tactical-text font-semibold">{prediction.listing_id}</dd>
              </div>
              <div className="flex items-baseline justify-between">
                <dt className="tactical-label">TIMESTAMP</dt>
                <dd className="text-tactical-muted text-[10px]">
                  {new Date(prediction.timestamp).toLocaleString()}
                </dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="tactical-border-dashed p-6 text-center">
            <p className="text-xs font-mono text-tactical-muted tracking-tactical leading-relaxed">
              AWAITING INPUT // EXECUTE PREDICTION TO GENERATE RESULTS
            </p>
          </div>
        )}
      </div>

      <div className="tactical-card p-5 border-tactical-success">
        <p className="tactical-label mb-2 text-tactical-success">TACTICAL BRIEFING</p>
        <p className="text-xs font-mono text-tactical-muted leading-relaxed tracking-tactical">
          ADJUST PARAMETERS (ROOMS / AREA / CONSTRUCTION YEAR) TO RUN COMPARATIVE SCENARIOS //
          MINOR VARIATIONS CAN SHIFT VALUATION BY 100K+ SEK
        </p>
      </div>
    </aside>
  );
}

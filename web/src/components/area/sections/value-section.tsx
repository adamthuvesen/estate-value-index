"use client";

import type { AreaValueInsights } from "@/lib/area-types";
import { formatNumber, formatNumberOrDash, formatPercent, formatSek } from "@/lib/format";
import { ValueDistributionChart } from "@/components/area/value-distribution-chart";
import { useRoomFilter } from "@/components/area/room-filter-provider";

interface ValueSectionProps {
  valueInsights: AreaValueInsights;
}

export function ValueSection({ valueInsights }: ValueSectionProps) {
  const { stats } = useRoomFilter();
  const insights = stats?.value_insights ?? valueInsights;

  return (
    <div id="value" className="ledger-card mb-6 p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold tracking-tight text-ledger-text">
        Value insights
      </h2>
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-val-exc-line bg-val-exc-tint p-4">
          <p className="text-[11px] font-semibold uppercase tracking-eyebrow text-val-exc">
            Undervalued properties
          </p>
          <p className="num mt-1.5 text-2xl font-semibold text-val-exc">
            {formatPercent(insights.undervalued_pct)}
          </p>
          <p className="mt-1 text-[12px] text-val-exc">
            <span className="num">{formatNumber(insights.undervalued_count)}</span> properties
          </p>
        </div>
        <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
          <p className="eyebrow">Avg value score</p>
          <p className="num mt-1.5 text-2xl font-semibold text-ledger-text">
            {formatNumberOrDash(insights.avg_value_score, 1)}
          </p>
          <p className="mt-1 text-[12px] text-ledger-muted">
            Median:{" "}
            <span className="num">{formatNumberOrDash(insights.median_value_score, 1)}</span>
          </p>
        </div>
        <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
          <p className="eyebrow">Avg prediction delta</p>
          <p
            className={`num mt-2 text-2xl font-semibold ${
              insights.avg_prediction_delta > 0 ? "text-val-exc" : "text-val-high"
            }`}
          >
            {insights.avg_prediction_delta > 0 ? "+" : ""}
            {formatSek(insights.avg_prediction_delta)}
          </p>
        </div>
      </div>

      <ValueDistributionChart value_tier_distribution={insights.value_tier_distribution} />
    </div>
  );
}

"use client";

import type { AreaValueInsights } from "@/lib/area-types";
import { formatNumber, formatNumberOrDash, formatPercent, formatSek } from "@/lib/format";
import { FigureFrame } from "@/components/ui/figure-frame";
import { ValueDistributionChart } from "@/components/area/charts/value-distribution-chart";
import { useRoomFilter } from "@/components/area/room-filter-provider";
import { figureMeta, roomScopeNote } from "@/lib/area-report";

interface ValueSectionProps {
  valueInsights: AreaValueInsights;
  updatedAt: string;
  stale: boolean;
}

export function ValueSection({ valueInsights, updatedAt, stale }: ValueSectionProps) {
  const { filter, stats } = useRoomFilter();
  const insights = stats?.value_insights ?? valueInsights;
  const note = roomScopeNote(filter, stats?.property_count);

  return (
    <FigureFrame
      kind="figure"
      index={2}
      id="value"
      title="Value"
      meta={figureMeta(updatedAt, note)}
      stale={stale}
    >
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <div className="rounded-sm border border-val-exc-line bg-val-exc-tint p-4">
          <p className="eyebrow text-val-exc">Undervalued properties</p>
          <p className="num mt-1.5 text-title font-semibold text-val-exc">
            {formatPercent(insights.undervalued_pct)}
          </p>
          <p className="mt-1 text-caption text-val-exc">
            <span className="num">{formatNumber(insights.undervalued_count)}</span> properties
          </p>
        </div>
        <div className="rounded-sm border border-ledger-border bg-ledger-elevated p-4">
          <p className="eyebrow">Avg value score</p>
          <p className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatNumberOrDash(insights.avg_value_score, 1)}
          </p>
          <p className="mt-1 text-caption text-ledger-muted">
            Median: <span className="num">{formatNumberOrDash(insights.median_value_score, 1)}</span>
          </p>
        </div>
        <div className="rounded-sm border border-ledger-border bg-ledger-elevated p-4">
          <p className="eyebrow">Avg prediction delta</p>
          <p
            className={`num mt-1.5 text-title font-semibold ${
              insights.avg_prediction_delta > 0 ? "text-val-exc" : "text-val-high"
            }`}
          >
            {insights.avg_prediction_delta > 0 ? "+" : ""}
            {formatSek(insights.avg_prediction_delta)}
          </p>
        </div>
      </div>

      <p className="mb-3 eyebrow text-ledger-dimmed">Properties per value tier</p>
      <ValueDistributionChart value_tier_distribution={insights.value_tier_distribution} />
    </FigureFrame>
  );
}

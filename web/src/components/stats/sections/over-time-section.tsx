"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { TrendLineChart, type TrendPoint } from "@/components/stats/charts/trend-line-chart";
import { SimpleBarChart, type SimpleBar } from "@/components/stats/charts/simple-bar-chart";
import type { OverallOverTime } from "@/lib/overall-statistics-types";
import {
  formatMonthOfYear,
  formatMonthShort,
  formatNumber,
  formatShortThousands,
} from "@/lib/format";

export function OverTimeSection({
  overTime,
  updatedMeta,
}: {
  overTime: OverallOverTime;
  updatedMeta: string;
}) {
  const monthly = overTime.monthly;
  const complete = monthly.filter((m) => !m.is_partial);
  const first = complete[0];
  const last = complete[complete.length - 1];
  const changePct =
    first && last
      ? ((last.median_price_per_sqm - first.median_price_per_sqm) /
          first.median_price_per_sqm) *
        100
      : null;

  const priceLine: TrendPoint[] = monthly.map((m) => ({
    label: formatMonthShort(m.month),
    value: m.median_price_per_sqm,
    partial: m.is_partial,
  }));

  const volumeBars: SimpleBar[] = monthly.map((m) => ({
    label: formatMonthShort(m.month),
    value: m.sales_count,
    muted: m.is_partial,
    note: m.is_partial ? "partial month" : undefined,
  }));

  const seasonBars: SimpleBar[] = overTime.seasonality.map((s) => ({
    label: formatMonthOfYear(s.month_of_year),
    value: Math.round(s.avg_sales_count),
    note: `${formatNumber(s.median_price_per_sqm)} kr/m²`,
  }));

  const busiest = [...overTime.seasonality].sort((a, b) => b.avg_sales_count - a.avg_sales_count)[0];

  return (
    <section id="over-time" className="scroll-mt-24">
      <SectionIntro
        chapter="02"
        title="Over time"
        lead={
          <>
            {changePct !== null && (
              <>
                Across the full window the median price per m² moved{" "}
                {changePct >= 0 ? "up" : "down"} {Math.abs(changePct).toFixed(1)}%.{" "}
              </>
            )}
            Volume is seasonal — {formatMonthOfYear(busiest.month_of_year)} is the busiest
            selling month. The current month is incomplete and drawn hollow.
          </>
        }
      />

      <div className="mt-8">
        <FigureFrame
          kind="figure"
          index={3}
          title="Median price per m², month by month"
          meta={updatedMeta}
          footnote="The final point is the current, incomplete month — shown hollow with a dashed bridge so it doesn't read as a real move."
        >
          <TrendLineChart
            data={priceLine}
            valueFormat={(v) => `${formatNumber(v)} kr/m²`}
            axisFormat={formatShortThousands}
            valueLabel="Median / m²"
            height={280}
          />
        </FigureFrame>
      </div>

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={4}
          title="Sales volume by month"
          meta={updatedMeta}
          footnote="Count of recorded sales per calendar month."
        >
          <SimpleBarChart
            data={volumeBars}
            valueFormat={formatNumber}
            valueLabel="sales"
            showLabels={false}
            maxLabels={8}
            height={240}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={5}
          title="Seasonality by calendar month"
          meta={updatedMeta}
          footnote="Average sales per occurrence of each calendar month across the window."
        >
          <SimpleBarChart
            data={seasonBars}
            valueFormat={formatNumber}
            valueLabel="avg sales"
            height={240}
          />
        </FigureFrame>
      </div>
    </section>
  );
}
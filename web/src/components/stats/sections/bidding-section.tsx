"use client";

import Link from "next/link";
import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { HistogramBarChart } from "@/components/stats/charts/histogram-bar-chart";
import { TrendLineChart, type TrendPoint } from "@/components/stats/charts/trend-line-chart";
import type { AreaPremium, OverallBidding } from "@/lib/overall-statistics-types";
import { formatMonthShort, formatNumber, formatSignedPct } from "@/lib/format";

function pctAxis(value: number): string {
  const rounded = Math.round(value);
  return `${rounded > 0 ? "+" : ""}${rounded}%`;
}

function PremiumRanking({ areas }: { areas: AreaPremium[] }) {
  const scale = Math.max(1, ...areas.map((a) => Math.abs(a.avg_premium_pct)));
  return (
    <ul className="space-y-3">
      {areas.map((area) => {
        const positive = area.avg_premium_pct >= 0;
        const width = (Math.abs(area.avg_premium_pct) / scale) * 100;
        return (
          <li key={area.area_name} className="flex items-center gap-3">
            <Link
              href={`/area/${area.area_name}`}
              className="focus-ring w-32 shrink-0 truncate text-body-sm font-medium text-ledger-text transition-colors hover:text-ledger-accent"
            >
              {area.display_name}
            </Link>
            <span className="relative h-2.5 flex-1 rounded-pill bg-ledger-elevated">
              <span
                className="absolute inset-y-0 left-0 rounded-pill"
                style={{
                  width: `${width}%`,
                  backgroundColor: positive
                    ? "var(--color-val-over)"
                    : "var(--color-ledger-neutral)",
                }}
                aria-hidden
              />
            </span>
            <span
              className={`num w-16 shrink-0 text-right text-body-sm font-semibold ${
                positive ? "text-val-over" : "text-ledger-muted"
              }`}
            >
              {formatSignedPct(area.avg_premium_pct)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function BiddingSection({
  bidding,
  updatedMeta,
}: {
  bidding: OverallBidding;
  updatedMeta: string;
}) {
  const listedFootnote = `Covers the ${formatNumber(
    bidding.sample_size,
  )} sales that carried a listing price. Premium is (sold − asking) ÷ asking.`;

  const shareLine: TrendPoint[] = bidding.monthly_over_under.map((m) => ({
    label: formatMonthShort(m.month),
    value: m.share_over_ask * 100,
    partial: m.is_partial,
  }));

  const hist = bidding.premium_pct_histogram;

  return (
    <section id="bidding" className="scroll-mt-24">
      <SectionIntro
        chapter="03"
        title="Bidding"
        lead={
          <>
            The median sale closed {formatSignedPct(hist.p50)} against its asking price. Most homes
            clear above ask, but the tail runs both ways — the quietest listings still sell under
            their guide.
          </>
        }
      />

      <div className="mt-8">
        <FigureFrame
          kind="figure"
          index={6}
          title="How far sales land from the asking price"
          meta={updatedMeta}
          footnote={listedFootnote}
        >
          <HistogramBarChart
            hist={hist}
            xFormat={pctAxis}
            countLabel="sales"
            diverging={{ threshold: 0 }}
            reference={{ value: hist.p50, label: "median" }}
            height={260}
          />
          <p className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-ledger-border pt-3 text-caption text-ledger-muted">
            <span>
              <span className="inline-block h-2 w-2 rounded-[2px] bg-val-over align-middle" /> above
              ask
            </span>
            <span>
              <span className="inline-block h-2 w-2 rounded-[2px] bg-ledger-neutral align-middle" />{" "}
              at or below ask
            </span>
          </p>
        </FigureFrame>
      </div>

      <div className="mt-8">
        <FigureFrame
          kind="figure"
          index={7}
          title="Share of sales over asking, by month"
          meta={updatedMeta}
          footnote="Fraction of listed sales that closed above their asking price each month."
        >
          <TrendLineChart
            data={shareLine}
            valueFormat={(v) => `${v.toFixed(0)}%`}
            axisFormat={(v) => `${Math.round(v)}%`}
            valueLabel="Over ask"
            reference={{ value: 50, label: "half" }}
            height={240}
          />
        </FigureFrame>
      </div>

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={8}
          title="Hottest areas for over-bidding"
          meta={updatedMeta}
          footnote="Top 5 areas by average premium. Areas with at least 30 listed sales."
        >
          <PremiumRanking areas={bidding.top_premium_areas} />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={9}
          title="Coolest areas for over-bidding"
          meta={updatedMeta}
          footnote="Bottom 5 areas by average premium. Areas with at least 30 listed sales."
        >
          <PremiumRanking areas={bidding.bottom_premium_areas} />
        </FigureFrame>
      </div>
    </section>
  );
}
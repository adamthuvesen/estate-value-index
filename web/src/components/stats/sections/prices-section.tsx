"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { HistogramBarChart } from "@/components/stats/charts/histogram-bar-chart";
import type { OverallPrices } from "@/lib/overall-statistics-types";
import {
  formatNumber,
  formatSek,
  formatShortSek,
  formatShortThousands,
} from "@/lib/format";

function Quartiles({
  p25,
  p50,
  p75,
  format,
}: {
  p25: number;
  p50: number;
  p75: number;
  format: (v: number) => string;
}) {
  const cells: Array<[string, number, boolean]> = [
    ["25th pct", p25, false],
    ["Median", p50, true],
    ["75th pct", p75, false],
  ];
  return (
    <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-ledger-border pt-4">
      {cells.map(([label, value, strong]) => (
        <div key={label} className={strong ? "rounded-sm bg-ledger-accent-tint px-3 py-2" : "px-3 py-2"}>
          <dt className="eyebrow text-ledger-dimmed">{label}</dt>
          <dd
            className={`num mt-1 text-heading font-semibold ${
              strong ? "text-ledger-accent" : "text-ledger-text"
            }`}
          >
            {format(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function PricesSection({
  prices,
  updatedMeta,
}: {
  prices: OverallPrices;
  updatedMeta: string;
}) {
  const sold = prices.sold_price_histogram;
  const perSqm = prices.price_per_sqm_histogram;

  return (
    <section id="prices" className="scroll-mt-24">
      <SectionIntro
        chapter="01"
        title="Prices"
        lead={
          <>
            The middle apartment sold for {formatSek(sold.p50)} — but the spread is wide: the
            central half of the market cleared between {formatShortSek(sold.p25)} and{" "}
            {formatShortSek(sold.p75)}. Measured per square metre, the median sale fetched{" "}
            {formatNumber(perSqm.p50)} kr/m².
          </>
        }
      />

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={1}
          title="Where the money lands"
          meta={updatedMeta}
          footnote={`Sold price across ${formatNumber(sold.sample_size)} sales. Bars clipped to the 1st–99th percentile.`}
        >
          <HistogramBarChart
            hist={sold}
            xFormat={formatShortSek}
            reference={{ value: sold.p50, label: "median" }}
          />
          <Quartiles p25={sold.p25} p50={sold.p50} p75={sold.p75} format={formatShortSek} />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={2}
          title="Price per square metre"
          meta={updatedMeta}
          footnote={`kr/m² across ${formatNumber(perSqm.sample_size)} sales. Bars clipped to the 1st–99th percentile.`}
        >
          <HistogramBarChart
            hist={perSqm}
            xFormat={(v) => `${formatShortThousands(v)}`}
            countLabel="sales"
            reference={{ value: perSqm.p50, label: "median" }}
          />
          <Quartiles
            p25={perSqm.p25}
            p50={perSqm.p50}
            p75={perSqm.p75}
            format={(v) => `${formatNumber(v)}`}
          />
        </FigureFrame>
      </div>
    </section>
  );
}
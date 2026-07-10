"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { SimpleBarChart, type SimpleBar } from "@/components/stats/charts/simple-bar-chart";
import { HistogramBarChart } from "@/components/stats/charts/histogram-bar-chart";
import type { AmenityEffect, OverallBuilding } from "@/lib/overall-statistics-types";
import { formatNumber, formatSharePct, formatShortSek } from "@/lib/format";

function AmenityRow({
  name,
  effect,
  total,
}: {
  name: string;
  effect: AmenityEffect;
  total: number;
}) {
  const share = effect.known_count / total;
  return (
    <div className="border-t border-ledger-border py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-body font-medium text-ledger-text">{name}</span>
        <span className="num text-body-sm text-ledger-muted">
          {formatNumber(effect.known_count)} of {formatNumber(total)} confirmed
          <span className="text-ledger-dimmed"> · {formatSharePct(share)}</span>
        </span>
      </div>
      <div className="mt-2.5 h-3 w-full overflow-hidden rounded-pill bg-ledger-elevated">
        <div
          className="h-full rounded-pill bg-ledger-accent"
          style={{ width: `${share * 100}%` }}
          aria-hidden
        />
      </div>
      <p className="num mt-2 text-caption text-ledger-muted">
        Median where present: {formatNumber(effect.median_ppsqm_with)} kr/m²
      </p>
    </div>
  );
}

export function BuildingSection({
  building,
  totalProperties,
  updatedMeta,
}: {
  building: OverallBuilding;
  totalProperties: number;
  updatedMeta: string;
}) {
  const eraCount: SimpleBar[] = building.construction_era.map((e) => ({
    label: e.era,
    value: e.count,
    note: formatSharePct(e.share),
  }));
  const eraPrice: SimpleBar[] = building.construction_era.map((e) => ({
    label: e.era,
    value: e.median_price_per_sqm,
  }));

  const floorBars: SimpleBar[] = building.by_floor.map((f) => ({
    label: f.floor_bucket === "6+" ? "6+" : `Fl ${f.floor_bucket}`,
    value: f.median_price_per_sqm,
    muted: f.sample_size < 30,
    note: `n=${formatNumber(f.sample_size)}`,
  }));

  const feeBucketBars: SimpleBar[] = building.monthly_fee.median_price_by_fee_bucket.map((b) => ({
    label: b.fee_bucket,
    value: b.median_sold_price,
    muted: b.sample_size < 30,
    note: `n=${formatNumber(b.sample_size)}`,
  }));

  const dominantEra = [...building.construction_era].sort((a, b) => b.count - a.count)[0];

  return (
    <section id="building" className="scroll-mt-24">
      <SectionIntro
        chapter="06"
        title="Building & amenities"
        lead={
          <>
            Most of the stock is old: {dominantEra.era} buildings alone account for{" "}
            {formatSharePct(dominantEra.share)} of sales. Ground and low floors carry a slight
            premium, and the monthly fee tracks inversely with price per m².
          </>
        }
      />

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={15}
          title="Construction era"
          meta={updatedMeta}
          footnote="Share of sales by building era, chronological."
        >
          <SimpleBarChart
            data={eraCount}
            layout="vertical"
            categoryWidth={92}
            valueFormat={formatNumber}
            valueLabel="sales"
            height={210}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={16}
          title="Price per m², by era"
          meta={updatedMeta}
          footnote="Median kr/m² within each construction era."
        >
          <SimpleBarChart
            data={eraPrice}
            layout="vertical"
            categoryWidth={92}
            valueFormat={formatNumber}
            valueLabel="Median / m²"
            height={210}
          />
        </FigureFrame>
      </div>

      <div className="mt-8">
        <FigureFrame
          kind="panel"
          title="Balcony & elevator: what the register actually records"
          meta={updatedMeta}
          footnote="The source only records these flags when the amenity is present, so absence is unknown, not confirmed false. A with-vs-without price comparison isn't possible; only prevalence and the median where present are shown."
        >
          <AmenityRow name="Balcony" effect={building.amenities.balcony} total={totalProperties} />
          <AmenityRow name="Elevator" effect={building.amenities.elevator} total={totalProperties} />
        </FigureFrame>
      </div>

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={17}
          title="Price per m², by floor"
          meta={updatedMeta}
          footnote="Median kr/m² by floor. Ground floor is 0; the top bucket is 6th floor and above. Unknown floor excluded."
        >
          <SimpleBarChart
            data={floorBars}
            valueFormat={formatNumber}
            valueLabel="Median / m²"
            height={220}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={18}
          title="The monthly fee"
          meta={updatedMeta}
          footnote={`Monthly fee per m² across ${formatNumber(
            building.monthly_fee.fee_per_sqm_histogram.sample_size,
          )} sales with a reported fee. Below: median price by fee band.`}
        >
          <HistogramBarChart
            hist={building.monthly_fee.fee_per_sqm_histogram}
            xFormat={(v) => formatNumber(v)}
            countLabel="sales"
            reference={{
              value: building.monthly_fee.fee_per_sqm_histogram.p50,
              label: "median",
            }}
            height={180}
          />
          <div className="mt-4 border-t border-ledger-border pt-4">
            <p className="eyebrow mb-2 text-ledger-dimmed">Median price by fee band (kr/month)</p>
            <SimpleBarChart
              data={feeBucketBars}
              valueFormat={formatShortSek}
              valueLabel="Median price"
              height={170}
            />
          </div>
        </FigureFrame>
      </div>
    </section>
  );
}
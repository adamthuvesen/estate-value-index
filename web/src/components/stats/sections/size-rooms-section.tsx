"use client";

import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { SimpleBarChart, type SimpleBar } from "@/components/stats/charts/simple-bar-chart";
import { TrendLineChart, type TrendPoint } from "@/components/stats/charts/trend-line-chart";
import type { OverallSizeRooms } from "@/lib/overall-statistics-types";
import {
  formatNumber,
  formatShortSek,
  formatShortThousands,
} from "@/lib/format";

const ROOM_ORDER = ["1", "2", "3", "4+"];
const LOW_N = 30;

export function SizeRoomsSection({
  sizeRooms,
  updatedMeta,
}: {
  sizeRooms: OverallSizeRooms;
  updatedMeta: string;
}) {
  const byRooms: SimpleBar[] = ROOM_ORDER.filter(
    (key) => sizeRooms.price_per_sqm_by_rooms[key],
  ).map((key) => {
    const row = sizeRooms.price_per_sqm_by_rooms[key];
    return {
      label: key === "4+" ? "4+ rm" : `${key} rm`,
      value: row.median,
      muted: row.count < LOW_N,
      note: `n=${formatNumber(row.count)}`,
    };
  });

  const bySize: SimpleBar[] = sizeRooms.price_by_size.map((row) => ({
    label: row.bucket,
    value: row.median_price,
    muted: row.count < LOW_N,
    note: `n=${formatNumber(row.count)}`,
  }));

  const curve: TrendPoint[] = sizeRooms.ppsqm_vs_size_curve.map((point) => ({
    label: point.size_bucket,
    value: point.median_price_per_sqm,
  }));

  const dist: SimpleBar[] = Object.entries(sizeRooms.size_distribution.room_distribution)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([room, count]) => ({
      label: room === "4+" ? "4+ rm" : `${room} rm`,
      value: count,
    }));

  const living = sizeRooms.size_distribution.living_area;
  const curveFirst = sizeRooms.ppsqm_vs_size_curve[0];
  const curveLast = sizeRooms.ppsqm_vs_size_curve[sizeRooms.ppsqm_vs_size_curve.length - 1];
  const smallPremium =
    curveFirst && curveLast
      ? (
          (curveFirst.median_price_per_sqm / curveLast.median_price_per_sqm - 1) *
          100
        ).toFixed(0)
      : null;

  return (
    <section id="size-rooms" className="scroll-mt-24">
      <SectionIntro
        chapter="05"
        title="Size & rooms"
        lead={
          <>
            The median home is {formatNumber(living.median)} m².{" "}
            {smallPremium !== null && (
              <>
                Small flats carry a per-metre premium: the smallest band sells for about{" "}
                {smallPremium}% more per m² than the largest.
              </>
            )}
          </>
        }
      />

      <div className="mt-8 grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FigureFrame
          kind="figure"
          index={11}
          title="Price per m², by room count"
          meta={updatedMeta}
          footnote="Median kr/m² within each room-count band. Thin bands are muted."
        >
          <SimpleBarChart
            data={byRooms}
            layout="vertical"
            categoryWidth={56}
            valueFormat={(v) => formatNumber(v)}
            valueLabel="Median / m²"
            height={200}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={12}
          title="Median price, by size band"
          meta={updatedMeta}
          footnote="Median sold price across living-area bands (m²). Thin bands are muted."
        >
          <SimpleBarChart
            data={bySize}
            valueFormat={formatShortSek}
            valueLabel="Median price"
            height={220}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={13}
          title="The small-flat premium"
          meta={updatedMeta}
          footnote="Median kr/m² against living area. Buckets with fewer than 30 sales are dropped upstream."
        >
          <TrendLineChart
            data={curve}
            valueFormat={(v) => `${formatNumber(v)} kr/m²`}
            axisFormat={formatShortThousands}
            valueLabel="Median / m²"
            height={220}
          />
        </FigureFrame>

        <FigureFrame
          kind="figure"
          index={14}
          title="How the stock breaks down by rooms"
          meta={updatedMeta}
          footnote={`Count of sales by room count. Living area spans ${formatNumber(
            living.min,
          )}–${formatNumber(living.max)} m² (median ${formatNumber(living.median)}).`}
        >
          <SimpleBarChart
            data={dist}
            layout="vertical"
            categoryWidth={56}
            valueFormat={formatNumber}
            valueLabel="sales"
            height={200}
          />
        </FigureFrame>
      </div>
    </section>
  );
}
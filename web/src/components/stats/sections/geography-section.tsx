"use client";

import { useState } from "react";
import Link from "next/link";
import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import { Segmented } from "@/components/area/charts/segmented";
import type { GeographyArea, OverallGeography } from "@/lib/overall-statistics-types";
import { formatNumber, formatSek, formatSharePct } from "@/lib/format";

const LOW_N = 30;
const RANK_SLICE = 20;

function RankRows({
  areas,
  max,
  rankOffset,
}: {
  areas: GeographyArea[];
  max: number;
  rankOffset: number;
}) {
  return (
    <>
      {areas.map((area, i) => {
        const width = (area.median_price_per_sqm / max) * 100;
        const low = area.sales_count < LOW_N;
        return (
          <li key={area.area_name} className="group grid grid-cols-[1.5rem_9rem_1fr_auto] items-center gap-3">
            <span className="num text-right text-caption text-ledger-dimmed">{rankOffset + i + 1}</span>
            <Link
              href={`/area/${area.area_name}`}
              className="focus-ring truncate text-body-sm font-medium text-ledger-text transition-colors hover:text-ledger-accent"
            >
              {area.display_name}
              {low && (
                <span className="num text-val-over" aria-label="Limited sample">
                  {" "}
                  †
                </span>
              )}
            </Link>
            <span className="relative h-3.5 rounded-pill bg-ledger-elevated">
              <span
                className="absolute inset-y-0 left-0 rounded-pill bg-ledger-accent"
                style={{ width: `${width}%`, opacity: low ? 0.4 : 1 }}
                aria-hidden
              />
            </span>
            <span className="flex items-baseline gap-3">
              <span className="num w-16 text-right text-body-sm font-semibold text-ledger-text">
                {formatNumber(area.median_price_per_sqm)}
              </span>
              <span className="num hidden w-24 text-right text-caption text-ledger-dimmed sm:inline">
                {area.undervalued_share !== null
                  ? `${formatSharePct(area.undervalued_share)} undervalued`
                  : "—"}
              </span>
            </span>
          </li>
        );
      })}
    </>
  );
}

function RankChart({ areas }: { areas: GeographyArea[] }) {
  const max = Math.max(...areas.map((a) => a.median_price_per_sqm));
  if (areas.length <= RANK_SLICE * 2) {
    return (
      <ol className="space-y-1.5">
        <RankRows areas={areas} max={max} rankOffset={0} />
      </ol>
    );
  }
  const top = areas.slice(0, RANK_SLICE);
  const bottom = areas.slice(-RANK_SLICE);
  const hidden = areas.length - RANK_SLICE * 2;
  return (
    <ol className="space-y-1.5">
      <RankRows areas={top} max={max} rankOffset={0} />
      <li
        className="num my-3 border-y border-dashed border-ledger-border py-2 text-center text-caption text-ledger-dimmed"
        aria-label={`${hidden} areas omitted from the chart`}
      >
        ··· {hidden} areas between — see the table view ···
      </li>
      <RankRows areas={bottom} max={max} rankOffset={areas.length - RANK_SLICE} />
    </ol>
  );
}

function RankTable({ areas }: { areas: GeographyArea[] }) {
  return (
    <div className="-mx-4 overflow-x-auto sm:-mx-5">
      <table className="w-full min-w-[34rem] border-collapse">
        <thead>
          <tr className="border-b border-ledger-border-emphasis">
            <th className="px-3 py-2 text-right eyebrow text-ledger-dimmed">#</th>
            <th className="px-3 py-2 text-left eyebrow text-ledger-dimmed">Area</th>
            <th className="px-3 py-2 text-right eyebrow text-ledger-dimmed">kr/m²</th>
            <th className="hidden px-3 py-2 text-right eyebrow text-ledger-dimmed sm:table-cell">
              Median price
            </th>
            <th className="px-3 py-2 text-right eyebrow text-ledger-dimmed">Sales</th>
            <th className="px-3 py-2 text-right eyebrow text-ledger-dimmed">Undervalued</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ledger-border">
          {areas.map((area, i) => (
            <tr key={area.area_name} className="group transition-colors hover:bg-ledger-elevated/60">
              <td className="num px-3 py-2 text-right text-body-sm text-ledger-dimmed">{i + 1}</td>
              <td className="px-3 py-2">
                <Link
                  href={`/area/${area.area_name}`}
                  className="focus-ring text-body-sm font-medium text-ledger-text transition-colors group-hover:text-ledger-accent"
                >
                  {area.display_name}
                  {area.sales_count < LOW_N && (
                    <span className="num text-val-over" aria-label="Limited sample">
                      {" "}
                      †
                    </span>
                  )}
                </Link>
              </td>
              <td className="num px-3 py-2 text-right text-body-sm font-semibold text-ledger-text">
                {formatNumber(area.median_price_per_sqm)}
              </td>
              <td className="num hidden px-3 py-2 text-right text-body-sm text-ledger-muted sm:table-cell">
                {formatSek(area.median_sold_price)}
              </td>
              <td className="num px-3 py-2 text-right text-body-sm text-ledger-muted">
                {formatNumber(area.sales_count)}
              </td>
              <td className="num px-3 py-2 text-right text-body-sm text-ledger-muted">
                {area.undervalued_share !== null ? formatSharePct(area.undervalued_share) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GeographySection({
  geography,
  updatedMeta,
}: {
  geography: OverallGeography;
  updatedMeta: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const areas = geography.areas;
  // The chart ranks only areas with a trustworthy median; the table keeps everything.
  const ranked = areas.filter((a) => a.sales_count >= LOW_N);
  const chartAreas = ranked.length > 0 ? ranked : areas;
  const top = chartAreas[0];
  const bottom = chartAreas[chartAreas.length - 1];
  const ratio = bottom ? (top.median_price_per_sqm / bottom.median_price_per_sqm).toFixed(1) : "—";
  const hasLow = areas.some((a) => a.sales_count < LOW_N);

  return (
    <section id="geography" className="scroll-mt-24">
      <SectionIntro
        chapter="04"
        title="Geography"
        lead={
          <>
            The register covers {areas.length} areas; {chartAreas.length} have at least {LOW_N}{" "}
            recorded sales and make the ranking. {top.display_name} tops it at{" "}
            {formatNumber(top.median_price_per_sqm)} kr/m² — roughly {ratio}× the median of{" "}
            {bottom.display_name}, the cheapest. The muted figure on the right is the model’s
            undervalued share.
          </>
        }
      />

      <div className="mt-8">
        <FigureFrame
          kind="figure"
          index={10}
          title="The register, ranked by price per m²"
          meta={updatedMeta}
          actions={
            <Segmented
              ariaLabel="View mode"
              value={view}
              onChange={setView}
              options={[
                { value: "chart", label: "Chart" },
                { value: "table", label: "Table" },
              ]}
            />
          }
          footnote={
            hasLow
              ? "Chart ranks areas with at least 30 recorded sales; the table lists every area. † Fewer than 30 sales — read with care. Undervalued share is the model’s estimate, null where unavailable."
              : "Undervalued share is the model’s estimate, null where unavailable."
          }
        >
          {view === "chart" ? <RankChart areas={chartAreas} /> : <RankTable areas={areas} />}
        </FigureFrame>
      </div>
    </section>
  );
}

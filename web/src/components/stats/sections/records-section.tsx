"use client";

import Link from "next/link";
import { FigureFrame } from "@/components/ui/figure-frame";
import { SectionIntro } from "@/components/stats/section-intro";
import type { OverallRecords, RecordSale } from "@/lib/overall-statistics-types";
import {
  formatDateSv,
  formatNumber,
  formatSek,
  formatSignedPct,
} from "@/lib/format";

interface CardConfig {
  label: string;
  record: RecordSale;
  headline: string;
  caption: string;
  footnote?: string;
}

function RecordCard({ label, record, headline, caption, footnote }: CardConfig) {
  return (
    <div className="ledger-card flex flex-col p-5">
      <p className="eyebrow text-ledger-accent">{label}</p>
      <p className="num mt-3 font-display text-headline font-semibold tracking-tight text-ledger-text">
        {headline}
      </p>
      <p className="mt-1 text-body-sm text-ledger-muted">{caption}</p>

      <div className="mt-4 border-t border-ledger-border pt-3 text-body-sm">
        {record.url ? (
          <a
            href={record.url}
            target="_blank"
            rel="noopener noreferrer"
            className="focus-ring inline-flex items-baseline gap-1 font-medium text-ledger-text transition-colors hover:text-ledger-accent"
          >
            <span className="truncate">{record.address}</span>
            <span aria-hidden className="text-ledger-dimmed">
              ↗
            </span>
          </a>
        ) : (
          <span className="font-medium text-ledger-text">{record.address}</span>
        )}
        <p className="mt-1 text-caption text-ledger-muted">
          <Link
            href={`/area/${record.area_name}`}
            className="focus-ring transition-colors hover:text-ledger-accent"
          >
            {record.display_name}
          </Link>
          {" · "}
          <span className="num">{formatDateSv(record.sold_date)}</span>
          {record.living_area ? (
            <span className="num"> · {formatNumber(record.living_area)} m²</span>
          ) : null}
        </p>
      </div>

      {footnote && <p className="mt-3 text-caption text-ledger-dimmed">{footnote}</p>}
    </div>
  );
}

export function RecordsSection({
  records,
  updatedMeta,
}: {
  records: OverallRecords;
  updatedMeta: string;
}) {
  const cards: CardConfig[] = [
    {
      label: "Most expensive",
      record: records.most_expensive,
      headline: formatSek(records.most_expensive.sold_price),
      caption: `${formatNumber(records.most_expensive.rooms)} rooms`,
    },
    {
      label: "Cheapest",
      record: records.cheapest,
      headline: formatSek(records.cheapest.sold_price),
      caption: `${formatNumber(records.cheapest.rooms)} rooms`,
    },
    {
      label: "Highest kr/m²",
      record: records.highest_price_per_sqm,
      headline: `${formatNumber(records.highest_price_per_sqm.price_per_sqm)} kr/m²`,
      caption: `Sold for ${formatSek(records.highest_price_per_sqm.sold_price)}`,
    },
    {
      label: "Fastest sale",
      record: records.fastest_sale,
      headline: `${formatNumber(records.fastest_sale.days_on_market)} ${
        records.fastest_sale.days_on_market === 1 ? "day" : "days"
      }`,
      caption: `On the market, then gone`,
    },
    {
      label: "Biggest bid-up",
      record: records.biggest_bid_up,
      headline: formatSignedPct(records.biggest_bid_up.premium_pct),
      caption: `${formatSek(records.biggest_bid_up.listing_price)} asking → ${formatSek(
        records.biggest_bid_up.sold_price,
      )}`,
    },
  ];

  if (records.best_value) {
    cards.push({
      label: "Best value",
      record: records.best_value,
      headline: formatSignedPct(records.best_value.prediction_delta_percentage),
      caption: `Model value score ${formatNumber(records.best_value.value_score)}`,
    });
  }

  return (
    <section id="records" className="scroll-mt-24">
      <SectionIntro
        chapter="07"
        title="The record book"
        lead={
          <>
            The extremes of the register — the priciest sale, the fastest turnaround, the wildest
            bidding war — and the streets that traded hands most often.
          </>
        }
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <RecordCard key={card.label} {...card} />
        ))}
      </div>

      <div className="mt-10">
        <FigureFrame
          kind="table"
          index={1}
          title="Busiest streets"
          meta={updatedMeta}
          footnote="Top 10 streets by number of recorded sales. A street is the address with its house number removed."
        >
          <div className="-mx-4 overflow-x-auto sm:-mx-5">
            <table className="w-full min-w-[24rem] border-collapse">
              <thead>
                <tr className="border-b border-ledger-border-emphasis">
                  <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">#</th>
                  <th className="px-4 py-2 text-left eyebrow text-ledger-dimmed">Street</th>
                  <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">Sales</th>
                  <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">Median price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ledger-border">
                {records.top_streets.map((street, i) => (
                  <tr key={street.street} className="transition-colors hover:bg-ledger-elevated/50">
                    <td className="num px-4 py-2.5 text-right text-body-sm text-ledger-dimmed">
                      {i + 1}
                    </td>
                    <td className="px-4 py-2.5 text-body-sm font-medium text-ledger-text">
                      {street.street}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-body-sm text-ledger-muted">
                      {formatNumber(street.sales_count)}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-body-sm text-ledger-text">
                      {formatSek(street.median_sold_price)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </FigureFrame>
      </div>
    </section>
  );
}
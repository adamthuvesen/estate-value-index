"use client";

import type { RecentProperty } from "@/lib/area-types";
import { formatDateSv, formatNumber, formatSek } from "@/lib/format";
import { FigureFrame } from "@/components/ui/figure-frame";
import { ButtonLink } from "@/components/ui/button";
import { useRoomFilter } from "@/components/area/room-filter-provider";
import { figureMeta, roomScopeNote } from "@/lib/area-report";

interface RecentSalesTableProps {
  recentProperties: RecentProperty[];
  areaName: string;
  updatedAt: string;
  stale: boolean;
}

function AddressCell({ property }: { property: RecentProperty }) {
  if (property.url) {
    return (
      <a
        href={property.url}
        target="_blank"
        rel="noreferrer"
        className="focus-ring inline-flex items-baseline gap-1 font-medium text-ledger-text transition-colors hover:text-ledger-accent"
      >
        <span className="truncate">{property.address}</span>
        <span aria-hidden className="text-ledger-dimmed">
          ↗
        </span>
      </a>
    );
  }
  return <span className="font-medium text-ledger-text">{property.address}</span>;
}

export function RecentSalesTable({
  recentProperties,
  areaName,
  updatedAt,
  stale,
}: RecentSalesTableProps) {
  const { filter, stats } = useRoomFilter();
  const properties = stats?.recent_properties ?? recentProperties;
  const note = roomScopeNote(filter, stats?.property_count);

  return (
    <FigureFrame
      kind="table"
      index={1}
      id="recent"
      title="Recent sales"
      meta={figureMeta(updatedAt, note)}
      stale={stale}
      actions={
        <ButtonLink href={`/value-finder?area=${areaName}`} variant="secondary" size="sm">
          View all in Value Finder
        </ButtonLink>
      }
    >
      {properties.length === 0 ? (
        <p className="py-6 text-center text-body-sm text-ledger-muted">
          No recorded sales for this selection.
        </p>
      ) : (
        <div className="-mx-4 overflow-x-auto sm:-mx-5">
          <table className="w-full min-w-[30rem] border-collapse">
            <thead>
              <tr className="border-b border-ledger-border-emphasis">
                <th className="px-4 py-2 text-left eyebrow text-ledger-dimmed">Address</th>
                <th className="px-4 py-2 text-left eyebrow text-ledger-dimmed">Sold</th>
                <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">m²</th>
                <th className="hidden px-4 py-2 text-right eyebrow text-ledger-dimmed sm:table-cell">
                  Rooms
                </th>
                <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">Price</th>
                <th className="hidden px-4 py-2 text-right eyebrow text-ledger-dimmed sm:table-cell">
                  kr/m²
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ledger-border">
              {properties.map((property) => (
                <tr
                  key={property.listing_id}
                  className="align-top transition-colors hover:bg-ledger-elevated/50"
                >
                  <td className="max-w-[14rem] px-4 py-2.5 text-body-sm">
                    <AddressCell property={property} />
                    <p className="num mt-0.5 text-caption text-ledger-muted sm:hidden">
                      {formatNumber(property.rooms)} rooms
                      {property.price_per_sqm
                        ? ` · ${formatNumber(property.price_per_sqm)} kr/m²`
                        : ""}
                    </p>
                  </td>
                  <td className="num whitespace-nowrap px-4 py-2.5 text-left text-body-sm text-ledger-muted">
                    {formatDateSv(property.sold_date)}
                  </td>
                  <td className="num px-4 py-2.5 text-right text-body-sm text-ledger-text">
                    {formatNumber(property.living_area)}
                  </td>
                  <td className="num hidden px-4 py-2.5 text-right text-body-sm text-ledger-muted sm:table-cell">
                    {formatNumber(property.rooms)}
                  </td>
                  <td className="num whitespace-nowrap px-4 py-2.5 text-right text-body-sm font-semibold text-ledger-text">
                    {formatSek(property.sold_price)}
                  </td>
                  <td className="num hidden whitespace-nowrap px-4 py-2.5 text-right text-body-sm text-ledger-muted sm:table-cell">
                    {property.price_per_sqm ? formatNumber(property.price_per_sqm) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </FigureFrame>
  );
}

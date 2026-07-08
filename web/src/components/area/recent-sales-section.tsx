"use client";

import Link from "next/link";
import type { RecentProperty } from "@/lib/area-types";
import { formatNumber, formatSek } from "@/lib/format";
import { useRoomFilter } from "@/components/area/room-filter-provider";

interface RecentSalesSectionProps {
  recentProperties: RecentProperty[];
  areaName: string;
}

export function RecentSalesSection({ recentProperties, areaName }: RecentSalesSectionProps) {
  const { stats } = useRoomFilter();
  const properties = stats?.recent_properties ?? recentProperties;

  return (
    <div id="recent" className="ledger-card mb-6 p-5 sm:p-6">
      <div className="mb-6 flex items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold tracking-tight text-ledger-text">Recent sales</h2>
        <Link href={`/value-finder?area=${areaName}`} className="ledger-btn focus-ring text-[13px]">
          View all
        </Link>
      </div>
      <div className="divide-y divide-ledger-border overflow-hidden rounded-xl border border-ledger-border">
        {properties.map((property) => (
          <div
            key={property.listing_id}
            className="flex items-center justify-between gap-3 px-3 py-2 transition-colors hover:bg-ledger-elevated/50"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-ledger-text">
                {property.address}
              </p>
              <p className="truncate text-[11px] text-ledger-muted">
                <span className="num">{formatNumber(property.living_area)}</span> m² ·{" "}
                <span className="num">{property.rooms}</span> rooms · sold {property.sold_date}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="num text-[13px] font-semibold text-ledger-text">
                {formatSek(property.sold_price)}
              </p>
              <p className="num text-[11px] text-ledger-muted">
                {formatSek(property.price_per_sqm)}/m²
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

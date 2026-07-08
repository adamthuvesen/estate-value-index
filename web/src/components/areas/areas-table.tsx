"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";
import { TierChip } from "@/components/ui/badge";
import type { AreaOverview } from "@/lib/area-types";
import {
  formatNumber,
  formatNumberOrDash,
  formatSek,
} from "@/lib/format";

type SortField = keyof AreaOverview;
type SortOrder = "asc" | "desc";

/** Low price/m² = good value (green); high = expensive (clay red). */
function gradientClass(normalized: number): string {
  if (normalized >= 0.8) return "text-val-high font-semibold";
  if (normalized >= 0.6) return "text-val-over";
  if (normalized >= 0.4) return "text-ledger-muted";
  if (normalized >= 0.2) return "text-val-great";
  return "text-val-exc font-semibold";
}

function priceChangeClass(value: number): string {
  if (value > 0) return "text-val-exc";
  if (value < 0) return "text-val-high";
  return "text-ledger-muted";
}

function SortArrow({ active, order }: { active: boolean; order: SortOrder }) {
  if (!active) return <span className="text-ledger-border-emphasis">↕</span>;
  return <span className="text-ledger-accent">{order === "asc" ? "↑" : "↓"}</span>;
}

function SortHeader({
  field,
  label,
  align = "left",
  className,
  sortField,
  sortOrder,
  onSort,
}: {
  field: SortField;
  label: string;
  align?: "left" | "right";
  className?: string;
  sortField: SortField;
  sortOrder: SortOrder;
  onSort: (field: SortField) => void;
}) {
  return (
    <th className={cn("px-3 py-2.5", align === "right" ? "text-right" : "text-left", className)}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn(
          "focus-ring inline-flex items-center gap-1 eyebrow text-ledger-dimmed transition-colors hover:text-ledger-text",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        <span className="text-[10px] leading-none">
          <SortArrow active={sortField === field} order={sortOrder} />
        </span>
      </button>
    </th>
  );
}

export function AreasTable({ areas }: { areas: AreaOverview[] }) {
  const [sortField, setSortField] = useState<SortField>("listing_count");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder((order) => (order === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  // Precompute the per-m² gradient bounds once, not per cell.
  const perSqmBounds = useMemo(() => {
    const values = areas
      .map((a) => a.avg_price_per_sqm)
      .filter((p): p is number => p !== null);
    if (values.length === 0) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { min, range: max - min };
  }, [areas]);

  const perSqmClass = (value: number | null): string => {
    if (value === null) return "text-ledger-dimmed";
    if (!perSqmBounds) return "text-ledger-dimmed";
    if (perSqmBounds.range === 0) return "text-ledger-muted";
    return gradientClass((value - perSqmBounds.min) / perSqmBounds.range);
  };

  const sortedAreas = useMemo(() => {
    const sorted = [...areas];
    sorted.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return 1;
      if (bVal === null) return -1;
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortOrder === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortOrder === "asc" ? aVal - bVal : bVal - aVal;
      }
      return 0;
    });
    return sorted;
  }, [areas, sortField, sortOrder]);

  const header = (field: SortField, label: string, align: "left" | "right" = "left", className?: string) => (
    <SortHeader
      field={field}
      label={label}
      align={align}
      className={className}
      sortField={sortField}
      sortOrder={sortOrder}
      onSort={handleSort}
    />
  );

  return (
    <div className="-mx-4 overflow-x-auto sm:-mx-5">
      <table className="w-full min-w-[46rem] border-collapse">
        <thead>
          <tr className="border-b border-ledger-border-emphasis">
            <th className="px-3 py-2.5 text-right">
              <span className="eyebrow text-ledger-dimmed">#</span>
            </th>
            {header("display_name", "Area")}
            {header("price_tier", "Tier")}
            {header("avg_sold_price", "Avg price", "right")}
            {header("avg_price_per_sqm", "Per m²", "right")}
            {header("listing_count", "Homes", "right")}
            {header("price_change_mean", "Δ price", "right", "hidden md:table-cell")}
            {header("undervalued_pct", "Undervalued", "right")}
            {header("days_on_market_median", "Days", "right", "hidden md:table-cell")}
          </tr>
        </thead>
        <tbody className="divide-y divide-ledger-border">
          {sortedAreas.map((area, index) => (
            <tr key={area.area_name} className="group transition-colors hover:bg-ledger-elevated/60">
              <td className="num px-3 py-2.5 text-right text-body-sm text-ledger-dimmed">
                {index + 1}
              </td>
              <td className="px-3 py-2.5">
                <Link
                  href={`/area/${area.area_name}`}
                  className="focus-ring inline-flex items-baseline gap-1 text-body-sm font-medium text-ledger-text transition-colors group-hover:text-ledger-accent"
                >
                  {area.display_name}
                  {area.has_limited_data && (
                    <span className="num text-val-over" aria-label="Limited sample">
                      †
                    </span>
                  )}
                </Link>
              </td>
              <td className="px-3 py-2.5">
                <TierChip tier={area.price_tier} />
              </td>
              <td className="num whitespace-nowrap px-3 py-2.5 text-right text-body-sm text-ledger-text">
                {formatSek(area.avg_sold_price)}
              </td>
              <td
                className={cn(
                  "num whitespace-nowrap px-3 py-2.5 text-right text-body-sm",
                  perSqmClass(area.avg_price_per_sqm),
                )}
              >
                {area.avg_price_per_sqm !== null ? formatNumber(area.avg_price_per_sqm) : "—"}
              </td>
              <td className="num whitespace-nowrap px-3 py-2.5 text-right text-body-sm text-ledger-muted">
                {formatNumber(area.listing_count)}
              </td>
              <td
                className={cn(
                  "num hidden whitespace-nowrap px-3 py-2.5 text-right text-body-sm md:table-cell",
                  priceChangeClass(area.price_change_mean),
                )}
              >
                {area.price_change_mean > 0 ? "+" : ""}
                {formatSek(area.price_change_mean)}
              </td>
              <td className="num whitespace-nowrap px-3 py-2.5 text-right text-body-sm text-ledger-muted">
                {formatNumberOrDash(area.undervalued_pct, 1)}%
              </td>
              <td className="num hidden whitespace-nowrap px-3 py-2.5 text-right text-body-sm text-ledger-muted md:table-cell">
                {formatNumber(area.days_on_market_median)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

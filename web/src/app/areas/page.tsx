"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { AreaListResponse, AreaOverview } from "@/lib/area-types";
import {
  formatDateSv,
  formatNumber,
  formatNumberOrDash,
  formatSek,
  getStaleInfo,
} from "@/lib/format";

type ApiErrorResponse = {
  error_code?: string;
  error_message?: string;
  remediation?: string;
};

const buildAreasErrorMessage = (payload: ApiErrorResponse | null, status: number) => {
  if (payload?.error_code === "AREA_DATA_MISSING") {
    return "Area statistics are not available yet. Run the enrichment pipeline or enable GCS downloads.";
  }
  if (payload?.error_code === "AREA_DATA_ERROR") {
    return "Area statistics could not be loaded. Check the data pipeline and server logs.";
  }
  if (status === 404) {
    return "Area statistics are not available yet.";
  }
  return "Failed to load area data. Please try again later.";
};

export default function AreasPage() {
  const [data, setData] = useState<AreaListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<keyof AreaOverview>("listing_count");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const response = await fetch("/api/area");
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as ApiErrorResponse | null;
          throw new Error(buildAreasErrorMessage(payload, response.status));
        }
        const json = await response.json();
        setData(json);
      } catch (err) {
        console.error("Error fetching areas:", err);
        const fallbackMessage = "Failed to load area data. Please try again later.";
        if (err instanceof Error && err.message) {
          const safeMessage =
            err.message.includes("Area") || err.message.includes("Failed")
              ? err.message
              : fallbackMessage;
          setError(safeMessage);
        } else {
          setError(fallbackMessage);
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchAreas();
  }, []);

  const handleSort = (field: keyof AreaOverview) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const getSortedAreas = (): AreaOverview[] => {
    if (!data?.areas) return [];

    const sorted = [...data.areas];
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
  };

  const getPriceTierBadgeClass = (tier: string) => {
    switch (tier) {
      case "premium":
        return "bg-emerald-950/40 text-emerald-300 border-emerald-500/40";
      case "upper":
        return "bg-emerald-900/30 text-emerald-400 border-emerald-500/30";
      case "medium":
        return "bg-emerald-800/20 text-emerald-500 border-emerald-500/25";
      case "budget":
        return "bg-emerald-700/15 text-emerald-600 border-emerald-500/20";
      default:
        return "bg-tactical-elevated text-tactical-muted border-tactical-border";
    }
  };

  // Color gradient: low = green, middle = gray, high = red
  const gradientClass = (normalized: number): string => {
    if (normalized >= 0.8) return "text-red-600 font-bold";
    if (normalized >= 0.6) return "text-red-400 font-semibold";
    if (normalized >= 0.4) return "text-gray-400";
    if (normalized >= 0.2) return "text-emerald-400 font-semibold";
    return "text-emerald-600 font-bold";
  };

  const getPricePerSqmColor = (value: number | null, allAreas: AreaOverview[]) => {
    if (value === null) return "text-tactical-muted";

    const validPrices = allAreas
      .map(a => a.avg_price_per_sqm)
      .filter((p): p is number => p !== null);

    if (validPrices.length === 0) return "text-tactical-muted";

    const min = Math.min(...validPrices);
    const max = Math.max(...validPrices);
    const range = max - min;

    if (range === 0) return "text-tactical-muted";

    return gradientClass((value - min) / range);
  };

  const getPriceChangeColor = (value: number, allAreas: AreaOverview[]) => {
    const allChanges = allAreas.map(a => a.price_change_mean);
    const min = Math.min(...allChanges);
    const max = Math.max(...allChanges);
    const range = max - min;

    if (range === 0) return "text-tactical-muted";

    return gradientClass((value - min) / range);
  };

  const SortButton = ({ field, label }: { field: keyof AreaOverview; label: string }) => (
    <button
      onClick={() => handleSort(field)}
      className="flex items-center gap-1 text-left tactical-label hover:text-tactical-text transition-colors duration-tactical"
    >
      {label}
      {sortField === field && (
        <span className="text-tactical-accent text-xs">{sortOrder === "asc" ? "↑" : "↓"}</span>
      )}
    </button>
  );

  if (isLoading) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners">
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="mb-4 inline-block h-12 w-12 animate-spin rounded-full border-4 border-tactical-border border-t-tactical-accent"></div>
                <p className="text-tactical-muted font-mono text-xs tracking-tactical uppercase">Loading areas...</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners">
            <div className="rounded-tactical border border-tactical-accent/30 bg-tactical-accent/10 p-8 text-center">
              <p className="text-lg font-mono font-medium text-tactical-accent">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const staleInfo = getStaleInfo(data?.metadata.generated_at);

  const areas = getSortedAreas();

  return (
    <div className="min-h-screen bg-tactical-bg">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners relative">
          <div className="mb-12 text-center">
            <p className="tactical-label">CLASSIFIED // ESTATE VALUE INDEX</p>
            <h1 className="tactical-header-xl mt-3">
              STOCKHOLM AREAS
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-tactical-muted font-mono tracking-tactical">
              Explore comprehensive market insights and statistics for {data?.metadata.total_areas} neighborhoods across Stockholm
            </p>
          </div>

          {staleInfo?.isStale && (
            <div className="mb-8 rounded-tactical border border-tactical-accent/30 bg-tactical-accent/10 p-4 text-center">
              <p className="text-xs font-mono text-tactical-accent">
                Data is {Math.floor(staleInfo.ageDays)} days old. Last updated{" "}
                {formatDateSv(staleInfo.generatedAt)}.
              </p>
            </div>
          )}

          <div className="mx-auto mb-10 max-w-3xl">
            <div className="grid grid-cols-1 gap-px overflow-hidden rounded-tactical bg-tactical-border sm:grid-cols-3">
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Total Areas</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {data?.metadata.total_areas}
                </dd>
              </div>
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Total Properties</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {formatNumber(data?.metadata.total_properties || 0)}
                </dd>
              </div>
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Last Updated</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {data?.metadata.generated_at ? new Date(data.metadata.generated_at).toLocaleDateString("sv-SE") : "N/A"}
                </dd>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-tactical bg-tactical-elevated border border-tactical-border">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-tactical-surface border-b border-tactical-border-emphasis">
              <tr>
                <th className="px-4 py-2.5 text-left">
                  <SortButton field="display_name" label="AREA" />
                </th>
                <th className="px-4 py-2.5 text-left">
                  <SortButton field="price_tier" label="TIER" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="avg_sold_price" label="AVG PRICE" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="avg_price_per_sqm" label="AVG PRICE / M²" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="listing_count" label="PROPERTIES" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="price_change_mean" label="PRICE CHANGE" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="undervalued_pct" label="UNDERVALUED %" />
                </th>
                <th className="px-4 py-2.5 text-right whitespace-nowrap">
                  <SortButton field="days_on_market_median" label="DAYS ON MARKET" />
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-tactical-border">
              {areas.map((area) => (
                <tr
                  key={area.area_name}
                  className="transition-colors duration-tactical hover:bg-tactical-surface"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/area/${area.area_name}`}
                      className="tactical-focus-ring font-medium text-tactical-text transition-colors duration-tactical hover:text-tactical-accent font-mono text-xs"
                    >
                      {area.display_name}
                      {area.has_limited_data && (
                        <span className="ml-2 text-xs text-tactical-accent-hover">⚠️ LIMITED DATA</span>
                      )}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-tactical border px-2.5 py-0.5 text-xs font-mono font-semibold uppercase ${getPriceTierBadgeClass(
                        area.price_tier
                      )}`}
                    >
                      {area.price_tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-tactical-text font-mono text-xs whitespace-nowrap">
                    {formatSek(area.avg_sold_price)}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-mono text-xs whitespace-nowrap ${getPricePerSqmColor(area.avg_price_per_sqm, areas)}`}>
                    {area.avg_price_per_sqm ? `${formatNumber(area.avg_price_per_sqm)} KR/M²` : "N/A"}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-tactical-muted font-mono text-xs whitespace-nowrap">
                    {formatNumber(area.listing_count)}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-mono text-xs whitespace-nowrap ${getPriceChangeColor(area.price_change_mean, areas)}`}>
                    {area.price_change_mean > 0 ? "+" : ""}
                    {formatSek(area.price_change_mean)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-tactical-muted font-mono text-xs whitespace-nowrap">
                    {formatNumberOrDash(area.undervalued_pct, 1)}%
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-tactical-muted font-mono text-xs whitespace-nowrap">
                    {formatNumber(area.days_on_market_median)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

          <div className="mt-8 text-center text-xs font-mono text-tactical-muted tracking-tactical uppercase">
            <p>Click on any area to view detailed analytics and insights</p>
          </div>
        </div>
      </div>
    </div>
  );
}

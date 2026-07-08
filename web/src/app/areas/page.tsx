"use client";

/* eslint-disable react-hooks/static-components -- SortButton closes over sort state; Phase 2 hoists it into areas-table.tsx */

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
    return "Area statistics aren’t available yet. Run the enrichment pipeline or enable GCS downloads.";
  }
  if (payload?.error_code === "AREA_DATA_ERROR") {
    return "Area statistics couldn’t be loaded. Check the data pipeline and server logs.";
  }
  if (status === 404) {
    return "Area statistics aren’t available yet.";
  }
  return "Couldn’t load area data. Please try again later.";
};

const TIER_LABEL: Record<string, string> = {
  premium: "Premium",
  upper: "Upper",
  medium: "Medium",
  budget: "Budget",
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
        const fallbackMessage = "Couldn’t load area data. Please try again later.";
        if (err instanceof Error && err.message) {
          const safeMessage =
            err.message.includes("Area") || err.message.includes("load")
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

  // Diverging color: low = green (good value), high = clay red (expensive)
  const gradientClass = (normalized: number): string => {
    if (normalized >= 0.8) return "text-val-high font-semibold";
    if (normalized >= 0.6) return "text-val-over";
    if (normalized >= 0.4) return "text-ledger-muted";
    if (normalized >= 0.2) return "text-val-great";
    return "text-val-exc font-semibold";
  };

  const getPricePerSqmColor = (value: number | null, allAreas: AreaOverview[]) => {
    if (value === null) return "text-ledger-dimmed";
    const validPrices = allAreas.map((a) => a.avg_price_per_sqm).filter((p): p is number => p !== null);
    if (validPrices.length === 0) return "text-ledger-dimmed";
    const min = Math.min(...validPrices);
    const max = Math.max(...validPrices);
    const range = max - min;
    if (range === 0) return "text-ledger-muted";
    return gradientClass((value - min) / range);
  };

  const getPriceChangeColor = (value: number) => (value > 0 ? "text-val-exc" : value < 0 ? "text-val-high" : "text-ledger-muted");

  const SortButton = ({ field, label, align = "left" }: { field: keyof AreaOverview; label: string; align?: "left" | "right" }) => (
    <button
      onClick={() => handleSort(field)}
      className={`flex w-full items-center gap-1 text-[11px] font-semibold uppercase tracking-eyebrow text-ledger-dimmed transition-colors hover:text-ledger-text ${
        align === "right" ? "justify-end" : "justify-start"
      }`}
    >
      {label}
      <span className={`text-[10px] ${sortField === field ? "text-ledger-accent" : "text-transparent"}`}>
        {sortField === field ? (sortOrder === "asc" ? "↑" : "↓") : "↕"}
      </span>
    </button>
  );

  if (isLoading) {
    return (
      <PageShell>
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-ledger-border border-t-ledger-text" />
            <p className="text-[13px] text-ledger-muted">Loading areas…</p>
          </div>
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell>
        <div className="mx-auto mt-4 max-w-xl rounded-2xl border border-ledger-border bg-ledger-surface px-6 py-12 text-center shadow-elev-1">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-val-over-tint">
            <svg className="h-5 w-5 text-val-over" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
            </svg>
          </div>
          <p className="mt-4 text-[14px] text-ledger-muted">{error}</p>
        </div>
      </PageShell>
    );
  }

  const staleInfo = getStaleInfo(data?.metadata.generated_at);
  const areas = getSortedAreas();

  return (
    <PageShell totalAreas={data?.metadata.total_areas}>
      {staleInfo?.isStale && (
        <div className="mx-auto mt-6 max-w-2xl rounded-xl border border-val-over-line bg-val-over-tint px-4 py-3 text-center">
          <p className="text-[13px] text-val-over">
            Data is {Math.floor(staleInfo.ageDays)} days old — last updated {formatDateSv(staleInfo.generatedAt)}.
          </p>
        </div>
      )}

      <dl className="mx-auto mt-8 flex max-w-md items-stretch justify-center divide-x divide-ledger-border rounded-2xl border border-ledger-border bg-ledger-surface shadow-elev-1">
        <Stat value={String(data?.metadata.total_areas ?? "—")} label="Areas" />
        <Stat value={formatNumber(data?.metadata.total_properties || 0)} label="Properties" />
        <Stat
          value={data?.metadata.generated_at ? new Date(data.metadata.generated_at).toLocaleDateString("sv-SE") : "—"}
          label="Updated"
          small
        />
      </dl>

      <div className="mt-10 overflow-hidden rounded-2xl border border-ledger-border bg-ledger-surface shadow-elev-1">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-ledger-border">
                <th className="px-4 py-3 text-left"><SortButton field="display_name" label="Area" /></th>
                <th className="px-4 py-3 text-left"><SortButton field="price_tier" label="Tier" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="avg_sold_price" label="Avg price" align="right" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="avg_price_per_sqm" label="Per m²" align="right" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="listing_count" label="Homes" align="right" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="price_change_mean" label="Δ price" align="right" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="undervalued_pct" label="Undervalued" align="right" /></th>
                <th className="px-4 py-3 text-right"><SortButton field="days_on_market_median" label="Days" align="right" /></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ledger-border">
              {areas.map((area) => (
                <tr key={area.area_name} className="group transition-colors hover:bg-ledger-elevated/50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/area/${area.area_name}`}
                      className="focus-ring inline-flex items-center gap-2 text-[13px] font-medium text-ledger-text transition-colors group-hover:text-ledger-accent"
                    >
                      {area.display_name}
                      {area.has_limited_data && (
                        <span className="rounded-pill bg-val-over-tint px-1.5 py-0.5 text-[10px] font-medium text-val-over">
                          limited
                        </span>
                      )}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex rounded-pill border border-ledger-border bg-ledger-elevated px-2.5 py-0.5 text-[12px] font-medium text-ledger-muted">
                      {TIER_LABEL[area.price_tier] ?? area.price_tier}
                    </span>
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-right text-[13px] text-ledger-text">
                    {formatSek(area.avg_sold_price)}
                  </td>
                  <td className={`num whitespace-nowrap px-4 py-3 text-right text-[13px] ${getPricePerSqmColor(area.avg_price_per_sqm, areas)}`}>
                    {area.avg_price_per_sqm ? `${formatNumber(area.avg_price_per_sqm)}` : "—"}
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-right text-[13px] text-ledger-muted">
                    {formatNumber(area.listing_count)}
                  </td>
                  <td className={`num whitespace-nowrap px-4 py-3 text-right text-[13px] ${getPriceChangeColor(area.price_change_mean)}`}>
                    {area.price_change_mean > 0 ? "+" : ""}
                    {formatSek(area.price_change_mean)}
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-right text-[13px] text-ledger-muted">
                    {formatNumberOrDash(area.undervalued_pct, 1)}%
                  </td>
                  <td className="num whitespace-nowrap px-4 py-3 text-right text-[13px] text-ledger-muted">
                    {formatNumber(area.days_on_market_median)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="mt-5 text-center text-[13px] text-ledger-dimmed">
        Select any area for detailed analytics.
      </p>
    </PageShell>
  );
}

function PageShell({ children, totalAreas }: { children: React.ReactNode; totalAreas?: number }) {
  return (
    <div className="min-h-screen bg-ledger-bg">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        <header className="mx-auto max-w-2xl text-center animate-fade-in-up">
          <p className="font-mono text-[12px] font-semibold uppercase tracking-eyebrow text-ledger-accent">
            Areas
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-[1.06] tracking-tight text-ledger-text sm:text-[46px]">
            Stockholm neighbourhoods
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-ledger-muted">
            Market statistics{typeof totalAreas === "number" ? ` across ${totalAreas} areas` : ""} — prices, momentum,
            and where the model finds the most undervalued homes.
          </p>
        </header>
        {children}
      </div>
    </div>
  );
}

function Stat({ value, label, small = false }: { value: string; label: string; small?: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center px-4 py-4">
      <dd
        className={`num whitespace-nowrap font-semibold text-ledger-text ${
          small ? "text-base" : "text-2xl"
        }`}
      >
        {value}
      </dd>
      <dt className="mt-1 text-[12px] text-ledger-muted">{label}</dt>
    </div>
  );
}

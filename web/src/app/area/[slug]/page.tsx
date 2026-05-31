"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import type { AreaDetails, RoomFilter } from "@/lib/area-types";
import {
  formatDateSv,
  formatNumber,
  formatNumberOrDash,
  formatPercent,
  formatSek,
  getStaleInfo,
} from "@/lib/format";
import { PriceTrendChart } from "@/components/area/price-trend-chart";
import { ValueDistributionChart } from "@/components/area/value-distribution-chart";
import { RoomComparisonChart } from "@/components/area/room-comparison-chart";
import { ConstructionEraChart } from "@/components/area/construction-era-chart";
import { SimilarAreas } from "@/components/area/similar-areas";
import { SectionNavigation } from "@/components/area/section-navigation";
import { RoomFilterComponent } from "@/components/area/room-filter";
import type { AreaOverview } from "@/lib/area-types";

type ApiErrorResponse = {
  error_code?: string;
  error_message?: string;
  remediation?: string;
};

const buildAreaDetailErrorMessage = (payload: ApiErrorResponse | null, status: number) => {
  if (payload?.error_code === "AREA_NOT_FOUND") {
    return "Area not found. Please choose a different area.";
  }
  if (payload?.error_code === "AREA_DATA_MISSING") {
    return "Area statistics are not available yet. Run the enrichment pipeline or enable GCS downloads.";
  }
  if (payload?.error_code === "AREA_DATA_ERROR") {
    return "Area statistics could not be loaded. Check the data pipeline and server logs.";
  }
  if (status === 404) {
    return "Area not found. Please choose a different area.";
  }
  return "Failed to load area data. Please try again later.";
};

export default function AreaDetailPage() {
  const params = useParams();
  const areaSlug = params.slug as string;

  const [data, setData] = useState<AreaDetails | null>(null);
  const [allAreas, setAllAreas] = useState<AreaOverview[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRoomFilter, setSelectedRoomFilter] = useState<RoomFilter>("all");

  useEffect(() => {
    const controller = new AbortController();

    const fetchData = async () => {
      try {
        const [areaResponse, allAreasResponse] = await Promise.all([
          fetch(`/api/area/${areaSlug}`, { signal: controller.signal }),
          fetch("/api/area", { signal: controller.signal }),
        ]);

        if (!areaResponse.ok) {
          const payload = (await areaResponse.json().catch(() => null)) as ApiErrorResponse | null;
          throw new Error(buildAreaDetailErrorMessage(payload, areaResponse.status));
        }

        const areaData = await areaResponse.json();
        setData(areaData);

        if (allAreasResponse.ok) {
          const allAreasData = await allAreasResponse.json();
          setAllAreas(allAreasData.areas || []);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        console.error("Error fetching area data:", err);
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
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      controller.abort();
    };
  }, [areaSlug]);

  const getPriceTierBadgeClass = (tier: string) => {
    switch (tier) {
      case "premium":
        return "bg-tactical-accent/10 text-tactical-accent border-tactical-accent/30";
      case "upper":
        return "bg-tactical-accent-hover/10 text-tactical-accent-hover border-tactical-accent-hover/30";
      case "medium":
        return "bg-tactical-success/10 text-tactical-success border-tactical-success/30";
      case "budget":
        return "bg-tactical-elevated text-tactical-muted border-tactical-border";
      default:
        return "bg-tactical-elevated text-tactical-muted border-tactical-border";
    }
  };


  if (isLoading) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners">
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="mb-4 inline-block h-12 w-12 animate-spin rounded-full border-4 border-tactical-border border-t-tactical-accent"></div>
                <p className="text-tactical-muted font-mono text-xs tracking-tactical uppercase">Loading area data...</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners">
            <div className="rounded-tactical border border-tactical-accent/30 bg-tactical-accent/10 p-8 text-center">
              <p className="text-lg font-mono font-medium text-tactical-accent">{error || "Area not found"}</p>
              <Link
                href="/areas"
                className="tactical-btn-primary tactical-focus-ring mt-4 inline-block px-4 py-2 text-xs uppercase"
              >
                ← BACK TO ALL AREAS
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const filteredData = data.by_room_count?.[selectedRoomFilter] ?? null;
  const staleInfo = getStaleInfo(data.metadata.generated_at);

  return (
    <div className="min-h-screen bg-tactical-bg">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners relative">
          <nav className="mb-8 text-xs font-mono text-tactical-muted tracking-tactical">
            <Link href="/" className="tactical-focus-ring transition-colors duration-tactical hover:text-tactical-text uppercase">
              Home
            </Link>
            {" / "}
            <Link href="/areas" className="tactical-focus-ring transition-colors duration-tactical hover:text-tactical-text uppercase">
              Areas
            </Link>
            {" / "}
            <span className="font-medium text-tactical-text uppercase">{data.display_name}</span>
          </nav>

          <div className="mb-12 text-center">
            <p className="tactical-label">CLASSIFIED // ESTATE VALUE INDEX</p>
            <div className="mt-3 mb-4 flex items-center justify-center gap-3">
              <h1 className="tactical-header-xl">
                {data.display_name}
              </h1>
              <span
                className={`inline-flex rounded-tactical border px-4 py-1.5 text-xs font-mono font-semibold uppercase ${getPriceTierBadgeClass(
                  data.price_tier
                )}`}
              >
                {data.price_tier}
              </span>
            </div>
            {data.has_limited_data && (
              <p className="text-xs font-mono text-tactical-accent-hover">
                ⚠️ LIMITED DATA AVAILABLE ({data.sample_size} PROPERTIES) - ESTIMATES MAY VARY
              </p>
            )}
          </div>

          {staleInfo?.isStale && (
            <div className="mb-8 rounded-tactical border border-tactical-accent/30 bg-tactical-accent/10 p-4 text-center">
              <p className="text-xs font-mono text-tactical-accent">
                Data is {Math.floor(staleInfo.ageDays)} days old. Last updated{" "}
                {formatDateSv(staleInfo.generatedAt)}.
              </p>
            </div>
          )}

          <SectionNavigation areaName={data.display_name} />

          <RoomFilterComponent
            selectedFilter={selectedRoomFilter}
            onFilterChange={setSelectedRoomFilter}
            roomData={data.by_room_count}
          />

          <div id="overview" className="mx-auto mb-10 max-w-3xl">
            <div className="grid grid-cols-1 gap-px overflow-hidden rounded-tactical bg-tactical-border sm:grid-cols-3">
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Average Price Per M²</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {(filteredData?.overview.avg_price_per_sqm ?? data.overview.avg_price_per_sqm)
                    ? formatNumber(filteredData?.overview.avg_price_per_sqm ?? data.overview.avg_price_per_sqm)
                    : "N/A"}
                </dd>
                <p className="mt-1 text-xs text-tactical-muted font-mono">
                  SOLD: {formatSek(filteredData?.overview.avg_sold_price ?? data.overview.avg_sold_price)}
                </p>
              </div>
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Market Activity</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {formatNumber(filteredData?.overview.listing_count ?? data.overview.listing_count)}
                </dd>
                <p className="mt-1 text-xs text-tactical-muted font-mono">TOTAL PROPERTIES</p>
              </div>
              <div className="bg-tactical-elevated px-4 py-5 sm:p-6 border border-tactical-border">
                <dt className="tactical-label">Days on Market</dt>
                <dd className="mt-1 text-3xl font-semibold tracking-tactical text-tactical-text font-mono">
                  {formatNumber(filteredData?.market_dynamics.days_on_market_median ?? data.market_dynamics.days_on_market_median)}
                </dd>
                <p className="mt-1 text-xs text-tactical-muted font-mono">MEDIAN LISTING DURATION</p>
              </div>
            </div>
          </div>

          <div className="tactical-section-separator"></div>
          <div id="market" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 tactical-header-lg">Market Dynamics</h2>

        <div className="mb-8">
          <PriceTrendChart
            median_price_3m={data.overview.median_price_3m}
            median_price_6m={data.overview.median_price_6m}
            median_price_12m={data.overview.median_price_12m}
            monthly_prices={data.overview.monthly_prices}
            avgLivingArea={data.size_analysis.size_distribution.living_area.mean}
          />
        </div>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="tactical-label">Price Change (Mean)</p>
            <p
              className={`mt-2 text-2xl font-bold font-mono ${
                (filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean) > 0
                  ? "text-tactical-success"
                  : "text-tactical-accent"
              }`}
            >
              {(filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean) > 0 ? "+" : ""}
              {formatSek(filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean)}
            </p>
          </div>
          <div>
            <p className="tactical-label">Volatility</p>
            <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">
              {formatSek(filteredData?.market_dynamics.volatility ?? data.market_dynamics.volatility)}
            </p>
          </div>
          <div>
            <p className="tactical-label">Sales Volume (3M)</p>
            <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">
              {formatNumber(data.market_dynamics.sales_volume_3m)}
            </p>
            <p className="mt-1 text-xs text-tactical-muted font-mono">
              6M: {formatNumber(data.market_dynamics.sales_volume_6m)} | 12M:{" "}
              {formatNumber(data.market_dynamics.sales_volume_12m)}
            </p>
          </div>
          <div>
            <p className="tactical-label">Liquidity Score</p>
            <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">
              {formatNumberOrDash(filteredData?.market_dynamics.liquidity ?? data.market_dynamics.liquidity, 2)}
            </p>
          </div>
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div id="value" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 tactical-header-lg">Value Insights</h2>
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-tactical bg-tactical-success/10 border border-tactical-success/30 p-4">
            <p className="tactical-label text-tactical-success">Undervalued Properties</p>
            <p className="mt-2 text-3xl font-bold text-tactical-success font-mono">
              {formatPercent(filteredData?.value_insights.undervalued_pct ?? data.value_insights.undervalued_pct)}
            </p>
            <p className="mt-1 text-xs text-tactical-success font-mono">
              {formatNumber(filteredData?.value_insights.undervalued_count ?? data.value_insights.undervalued_count)} PROPERTIES
            </p>
          </div>
          <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
            <p className="tactical-label">Avg Value Score</p>
            <p className="mt-2 text-3xl font-bold text-tactical-text font-mono">
              {formatNumberOrDash(filteredData?.value_insights.avg_value_score ?? data.value_insights.avg_value_score, 1)}
            </p>
            <p className="mt-1 text-xs text-tactical-muted font-mono">
              MEDIAN: {formatNumberOrDash(filteredData?.value_insights.median_value_score ?? data.value_insights.median_value_score, 1)}
            </p>
          </div>
          <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
            <p className="tactical-label">Avg Prediction Delta</p>
            <p
              className={`mt-2 text-2xl font-bold font-mono ${
                (filteredData?.value_insights.avg_prediction_delta ?? data.value_insights.avg_prediction_delta) > 0
                  ? "text-tactical-success"
                  : "text-tactical-accent"
              }`}
            >
              {(filteredData?.value_insights.avg_prediction_delta ?? data.value_insights.avg_prediction_delta) > 0 ? "+" : ""}
              {formatSek(filteredData?.value_insights.avg_prediction_delta ?? data.value_insights.avg_prediction_delta)}
            </p>
          </div>
        </div>

        <div>
          <ValueDistributionChart
            value_tier_distribution={filteredData?.value_insights.value_tier_distribution ?? data.value_insights.value_tier_distribution}
          />
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div id="size" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 tactical-header-lg">Size Analysis</h2>

        <div className="mb-8">
          <RoomComparisonChart price_per_sqm_by_rooms={data.size_analysis.price_per_sqm_by_rooms} />
        </div>

        <div>
          <h3 className="mb-4 text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Property Size Distribution</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
              <p className="tactical-label">Living Area (M²)</p>
              <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">
                {formatNumber(data.size_analysis.size_distribution.living_area.median)} M²
              </p>
              <div className="mt-2 space-y-1 text-xs text-tactical-muted font-mono">
                <p>MEAN: {formatNumber(data.size_analysis.size_distribution.living_area.mean)} M²</p>
                <p>
                  RANGE: {formatNumber(data.size_analysis.size_distribution.living_area.min)} -{" "}
                  {formatNumber(data.size_analysis.size_distribution.living_area.max)} M²
                </p>
              </div>
            </div>
            <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
              <p className="mb-3 tactical-label">Room Distribution</p>
              <div className="space-y-2">
                {Object.entries(data.size_analysis.size_distribution.room_distribution)
                  .sort(([a], [b]) => {
                    if (a === "4+") return 1;
                    if (b === "4+") return -1;
                    return parseInt(a) - parseInt(b);
                  })
                  .map(([rooms, count]) => (
                    <div key={rooms} className="flex items-center justify-between text-xs font-mono">
                      <span className="text-tactical-muted">{rooms} ROOM{rooms !== "1" ? "S" : ""}</span>
                      <span className="font-bold text-tactical-text">{formatNumber(count)}</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div id="characteristics" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 tactical-header-lg">Property Characteristics</h2>

        <div className="mb-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-6">
            <div className="flex items-center justify-between">
              <p className="tactical-label">Elevator</p>
              <span className="text-3xl font-bold text-tactical-text font-mono">
                {formatPercent(
                  filteredData?.property_characteristics.elevator_pct ?? data.property_characteristics.elevator_pct
                )}
              </span>
            </div>
            <p className="mt-2 text-xs text-tactical-muted font-mono">OF PROPERTIES HAVE ELEVATOR ACCESS</p>
          </div>
          <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-6">
            <div className="flex items-center justify-between">
              <p className="tactical-label">Balcony</p>
              <span className="text-3xl font-bold text-tactical-text font-mono">
                {formatPercent(
                  filteredData?.property_characteristics.balcony_pct ?? data.property_characteristics.balcony_pct
                )}
              </span>
            </div>
            <p className="mt-2 text-xs text-tactical-muted font-mono">OF PROPERTIES HAVE A BALCONY</p>
          </div>
        </div>

        <div>
          <ConstructionEraChart
            construction_era={filteredData?.construction_era ?? data.construction_era}
          />
        </div>
      </div>

          {allAreas.length > 0 && (
            <>
              <div className="tactical-section-separator"></div>
              <div id="similar" className="mb-8 tactical-card p-6 sm:p-8">
                <SimilarAreas
                  currentArea={data.area_name}
                  currentPriceTier={data.price_tier}
                  avgSoldPrice={data.overview.avg_sold_price}
                  allAreas={allAreas}
                />
              </div>
            </>
          )}

          <div className="tactical-section-separator"></div>
          <div id="recent" className="mb-8 tactical-card p-6 sm:p-8">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="tactical-header-lg">Recent Sales</h2>
          <Link
            href={`/value-finder?area=${data.area_name}`}
            className="tactical-btn-primary tactical-focus-ring px-4 py-2 text-xs uppercase"
          >
            View all →
          </Link>
        </div>
        <div className="space-y-4">
          {(filteredData?.recent_properties ?? data.recent_properties).map((property) => (
            <div
              key={property.listing_id}
              className="tactical-card-hover flex items-center justify-between rounded-tactical border border-tactical-border bg-tactical-elevated p-4 transition-colors duration-tactical hover:border-tactical-border-emphasis"
            >
              <div className="flex-1">
                <p className="font-medium text-tactical-text font-mono text-sm">{property.address}</p>
                <p className="mt-1 text-xs text-tactical-muted font-mono">
                  {formatNumber(property.living_area)} M² · {property.rooms} ROOMS · SOLD {property.sold_date}
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-tactical-text font-mono">{formatSek(property.sold_price)}</p>
                <p className="text-xs text-tactical-muted font-mono">{formatSek(property.price_per_sqm)}/M²</p>
              </div>
            </div>
          ))}
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div className="tactical-card p-8 text-center border-tactical-accent/30 bg-tactical-accent/5">
        <h3 className="tactical-header-md">Find Properties in {data.display_name}</h3>
        <p className="mt-3 text-xs text-tactical-muted font-mono tracking-tactical">
          BROWSE ALL {formatNumber(data.overview.listing_count)} PROPERTIES AND DISCOVER UNDERVALUED OPPORTUNITIES
        </p>
        <Link
          href={`/value-finder?area=${data.area_name}`}
          className="tactical-btn-primary tactical-focus-ring mt-6 inline-block px-8 py-3 text-xs font-semibold uppercase"
        >
          Explore {data.display_name} Properties
        </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

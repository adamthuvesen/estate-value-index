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

  const TIER_LABEL: Record<string, string> = {
    premium: "Premium",
    upper: "Upper",
    medium: "Medium",
    budget: "Budget",
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
          <div className="flex items-center justify-center py-24">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-tactical-border border-t-tactical-text" />
              <p className="text-[13px] text-tactical-muted">Loading area…</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-tactical-bg">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
          <div className="mx-auto mt-4 max-w-xl rounded-2xl border border-tactical-border bg-tactical-surface px-6 py-12 text-center shadow-elev-1">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-val-over-tint">
              <svg className="h-5 w-5 text-val-over" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
              </svg>
            </div>
            <p className="mt-4 text-[14px] text-tactical-muted">{error || "Area not found."}</p>
            <Link
              href="/areas"
              className="tactical-btn tactical-focus-ring mt-6 inline-flex text-[13px]"
            >
              Back to all areas
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const filteredData = data.by_room_count?.[selectedRoomFilter] ?? null;
  const staleInfo = getStaleInfo(data.metadata.generated_at);

  return (
    <div className="min-h-screen bg-tactical-bg">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        <div className="relative">
          <nav className="mb-8 text-[13px] text-tactical-muted">
            <Link href="/" className="tactical-focus-ring transition-colors hover:text-tactical-text">
              Home
            </Link>
            {" / "}
            <Link href="/areas" className="tactical-focus-ring transition-colors hover:text-tactical-text">
              Areas
            </Link>
            {" / "}
            <span className="font-medium text-tactical-text">{data.display_name}</span>
          </nav>

          <div className="mb-12 text-center animate-fade-in-up">
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-accent">
              Area report
            </p>
            <div className="mt-3 mb-4 flex flex-wrap items-center justify-center gap-3">
              <h1 className="text-4xl font-semibold leading-[1.06] tracking-tight text-tactical-text sm:text-[46px]">
                {data.display_name}
              </h1>
              <span className="inline-flex rounded-pill border border-tactical-border bg-tactical-elevated px-3 py-1 text-[13px] font-medium text-tactical-muted">
                {TIER_LABEL[data.price_tier] ?? data.price_tier}
              </span>
            </div>
            {data.has_limited_data && (
              <p className="text-[13px] text-val-over">
                Limited data available ({data.sample_size} properties) — estimates may vary.
              </p>
            )}
          </div>

          {staleInfo?.isStale && (
            <div className="mx-auto mb-8 max-w-2xl rounded-xl border border-val-over-line bg-val-over-tint px-4 py-3 text-center">
              <p className="text-[13px] text-val-over">
                Data is {Math.floor(staleInfo.ageDays)} days old — last updated {formatDateSv(staleInfo.generatedAt)}.
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
            <dl className="grid grid-cols-1 divide-y divide-tactical-border overflow-hidden rounded-2xl border border-tactical-border bg-tactical-surface shadow-elev-1 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              <div className="px-5 py-6">
                <dt className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Average price per m²</dt>
                <dd className="num mt-1.5 text-3xl font-semibold text-tactical-text">
                  {(filteredData?.overview.avg_price_per_sqm ?? data.overview.avg_price_per_sqm)
                    ? formatNumber(filteredData?.overview.avg_price_per_sqm ?? data.overview.avg_price_per_sqm)
                    : "—"}
                </dd>
                <p className="mt-1 text-[12px] text-tactical-muted">
                  Sold: <span className="num">{formatSek(filteredData?.overview.avg_sold_price ?? data.overview.avg_sold_price)}</span>
                </p>
              </div>
              <div className="px-5 py-6">
                <dt className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Market activity</dt>
                <dd className="num mt-1.5 text-3xl font-semibold text-tactical-text">
                  {formatNumber(filteredData?.overview.listing_count ?? data.overview.listing_count)}
                </dd>
                <p className="mt-1 text-[12px] text-tactical-muted">Total properties</p>
              </div>
              <div className="px-5 py-6">
                <dt className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Days on market</dt>
                <dd className="num mt-1.5 text-3xl font-semibold text-tactical-text">
                  {formatNumber(filteredData?.market_dynamics.days_on_market_median ?? data.market_dynamics.days_on_market_median)}
                </dd>
                <p className="mt-1 text-[12px] text-tactical-muted">Median listing duration</p>
              </div>
            </dl>
          </div>

          <div className="tactical-section-separator"></div>
          <div id="market" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 text-2xl font-semibold tracking-tight text-tactical-text">Market dynamics</h2>

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
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Price change (mean)</p>
            <p
              className={`num mt-2 text-2xl font-semibold ${
                (filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean) > 0
                  ? "text-val-exc"
                  : "text-val-high"
              }`}
            >
              {(filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean) > 0 ? "+" : ""}
              {formatSek(filteredData?.market_dynamics.price_change_mean ?? data.market_dynamics.price_change_mean)}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Volatility</p>
            <p className="num mt-2 text-2xl font-semibold text-tactical-text">
              {formatSek(filteredData?.market_dynamics.volatility ?? data.market_dynamics.volatility)}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Sales volume (3M)</p>
            <p className="num mt-2 text-2xl font-semibold text-tactical-text">
              {formatNumber(data.market_dynamics.sales_volume_3m)}
            </p>
            <p className="num mt-1 text-[12px] text-tactical-muted">
              6M: {formatNumber(data.market_dynamics.sales_volume_6m)} · 12M:{" "}
              {formatNumber(data.market_dynamics.sales_volume_12m)}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Liquidity score</p>
            <p className="num mt-2 text-2xl font-semibold text-tactical-text">
              {formatNumberOrDash(filteredData?.market_dynamics.liquidity ?? data.market_dynamics.liquidity, 2)}
            </p>
          </div>
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div id="value" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 text-2xl font-semibold tracking-tight text-tactical-text">Value insights</h2>
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-val-exc-line bg-val-exc-tint p-4">
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-val-exc">Undervalued properties</p>
            <p className="num mt-2 text-3xl font-semibold text-val-exc">
              {formatPercent(filteredData?.value_insights.undervalued_pct ?? data.value_insights.undervalued_pct)}
            </p>
            <p className="mt-1 text-[12px] text-val-exc">
              <span className="num">{formatNumber(filteredData?.value_insights.undervalued_count ?? data.value_insights.undervalued_count)}</span> properties
            </p>
          </div>
          <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Avg value score</p>
            <p className="num mt-2 text-3xl font-semibold text-tactical-text">
              {formatNumberOrDash(filteredData?.value_insights.avg_value_score ?? data.value_insights.avg_value_score, 1)}
            </p>
            <p className="mt-1 text-[12px] text-tactical-muted">
              Median: <span className="num">{formatNumberOrDash(filteredData?.value_insights.median_value_score ?? data.value_insights.median_value_score, 1)}</span>
            </p>
          </div>
          <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-4">
            <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Avg prediction delta</p>
            <p
              className={`num mt-2 text-2xl font-semibold ${
                (filteredData?.value_insights.avg_prediction_delta ?? data.value_insights.avg_prediction_delta) > 0
                  ? "text-val-exc"
                  : "text-val-high"
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
        <h2 className="mb-6 text-2xl font-semibold tracking-tight text-tactical-text">Size analysis</h2>

        <div className="mb-8">
          <RoomComparisonChart price_per_sqm_by_rooms={data.size_analysis.price_per_sqm_by_rooms} />
        </div>

        <div>
          <h3 className="mb-4 text-[17px] font-semibold tracking-tight text-tactical-text">Property size distribution</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-4">
              <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Living area (m²)</p>
              <p className="num mt-2 text-2xl font-semibold text-tactical-text">
                {formatNumber(data.size_analysis.size_distribution.living_area.median)} m²
              </p>
              <div className="mt-2 space-y-1 text-[12px] text-tactical-muted">
                <p>Mean: <span className="num">{formatNumber(data.size_analysis.size_distribution.living_area.mean)}</span> m²</p>
                <p>
                  Range: <span className="num">{formatNumber(data.size_analysis.size_distribution.living_area.min)}</span> –{" "}
                  <span className="num">{formatNumber(data.size_analysis.size_distribution.living_area.max)}</span> m²
                </p>
              </div>
            </div>
            <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-4">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Room distribution</p>
              <div className="space-y-2">
                {Object.entries(data.size_analysis.size_distribution.room_distribution)
                  .sort(([a], [b]) => {
                    if (a === "4+") return 1;
                    if (b === "4+") return -1;
                    return parseInt(a) - parseInt(b);
                  })
                  .map(([rooms, count]) => (
                    <div key={rooms} className="flex items-center justify-between text-[13px]">
                      <span className="text-tactical-muted">{rooms} room{rooms !== "1" ? "s" : ""}</span>
                      <span className="num font-medium text-tactical-text">{formatNumber(count)}</span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div id="characteristics" className="mb-8 tactical-card p-6 sm:p-8">
        <h2 className="mb-6 text-2xl font-semibold tracking-tight text-tactical-text">Property characteristics</h2>

        <div className="mb-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-6">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Elevator</p>
              <span className="num text-3xl font-semibold text-tactical-text">
                {formatPercent(
                  filteredData?.property_characteristics.elevator_pct ?? data.property_characteristics.elevator_pct
                )}
              </span>
            </div>
            <p className="mt-2 text-[12px] text-tactical-muted">of properties have elevator access</p>
          </div>
          <div className="rounded-xl border border-tactical-border bg-tactical-elevated p-6">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Balcony</p>
              <span className="num text-3xl font-semibold text-tactical-text">
                {formatPercent(
                  filteredData?.property_characteristics.balcony_pct ?? data.property_characteristics.balcony_pct
                )}
              </span>
            </div>
            <p className="mt-2 text-[12px] text-tactical-muted">of properties have a balcony</p>
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
        <div className="mb-6 flex items-center justify-between gap-3">
          <h2 className="text-2xl font-semibold tracking-tight text-tactical-text">Recent sales</h2>
          <Link
            href={`/value-finder?area=${data.area_name}`}
            className="tactical-btn tactical-focus-ring text-[13px]"
          >
            View all
          </Link>
        </div>
        <div className="space-y-3">
          {(filteredData?.recent_properties ?? data.recent_properties).map((property) => (
            <div
              key={property.listing_id}
              className="flex items-center justify-between gap-4 rounded-xl border border-tactical-border bg-tactical-elevated p-4 transition-colors hover:border-tactical-border-emphasis"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium text-tactical-text">{property.address}</p>
                <p className="mt-1 text-[12px] text-tactical-muted">
                  <span className="num">{formatNumber(property.living_area)}</span> m² · <span className="num">{property.rooms}</span> rooms · sold {property.sold_date}
                </p>
              </div>
              <div className="text-right">
                <p className="num text-[15px] font-semibold text-tactical-text">{formatSek(property.sold_price)}</p>
                <p className="num text-[12px] text-tactical-muted">{formatSek(property.price_per_sqm)}/m²</p>
              </div>
            </div>
          ))}
        </div>
      </div>

          <div className="tactical-section-separator"></div>
          <div className="tactical-card p-8 text-center">
        <h3 className="text-xl font-semibold tracking-tight text-tactical-text">Find properties in {data.display_name}</h3>
        <p className="mt-3 text-[14px] text-tactical-muted">
          Browse all <span className="num">{formatNumber(data.overview.listing_count)}</span> properties and discover undervalued opportunities.
        </p>
        <Link
          href={`/value-finder?area=${data.area_name}`}
          className="tactical-btn-primary tactical-focus-ring mt-6 inline-flex text-[13px]"
        >
          Explore {data.display_name} properties
        </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

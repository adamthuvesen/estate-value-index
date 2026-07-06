"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PropertyCard } from "@/components/value-finder/property-card";
import { FiltersPanel } from "@/components/value-finder/filters-panel";
import { SortControls } from "@/components/value-finder/sort-controls";
import { Pagination } from "@/components/value-finder/pagination";
import type {
  ValueFinderFilters,
  ValueFinderResponse,
  ValueFinderFacetsResponse,
  SortField,
  SortOrder,
  ValueTier,
} from "@/lib/value-finder-types";

function ValueFinderContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [properties, setProperties] = useState<ValueFinderResponse | null>(null);
  const [metadata, setMetadata] = useState<ValueFinderFacetsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getFiltersFromUrl = useCallback((): ValueFinderFilters => {
    return {
      sort: (searchParams.get("sort") as SortField) || "value_score",
      order: (searchParams.get("order") as SortOrder) || "desc",
      limit: Number(searchParams.get("limit")) || 50,
      offset: Number(searchParams.get("offset")) || 0,
      area: searchParams.get("area")?.split(",").filter(Boolean),
      min_living_area: searchParams.get("min_living_area") ? Number(searchParams.get("min_living_area")) : undefined,
      max_living_area: searchParams.get("max_living_area") ? Number(searchParams.get("max_living_area")) : undefined,
      min_rooms: searchParams.get("min_rooms") ? Number(searchParams.get("min_rooms")) : undefined,
      max_rooms: searchParams.get("max_rooms") ? Number(searchParams.get("max_rooms")) : undefined,
      min_price: searchParams.get("min_price") ? Number(searchParams.get("min_price")) : undefined,
      max_price: searchParams.get("max_price") ? Number(searchParams.get("max_price")) : undefined,
      property_type: searchParams.get("property_type")?.split(",").filter(Boolean),
      has_elevator: searchParams.get("has_elevator") === "true" ? true : undefined,
      has_balcony: searchParams.get("has_balcony") === "true" ? true : undefined,
      min_value_score: searchParams.get("min_value_score") ? Number(searchParams.get("min_value_score")) : undefined,
      max_value_score: searchParams.get("max_value_score") ? Number(searchParams.get("max_value_score")) : undefined,
      value_tier: searchParams.get("value_tier")?.split(",").filter(Boolean) as ValueTier[],
      search: searchParams.get("search") || undefined,
    };
  }, [searchParams]);

  const updateUrl = useCallback(
    (newFilters: Partial<ValueFinderFilters>) => {
      const current = getFiltersFromUrl();
      const updated = { ...current, ...newFilters };

      const params = new URLSearchParams();
      Object.entries(updated).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          if (Array.isArray(value)) {
            if (value.length > 0) {
              params.set(key, value.join(","));
            }
          } else {
            params.set(key, String(value));
          }
        }
      });

      router.push(`/value-finder?${params.toString()}`, { scroll: false });
    },
    [router, getFiltersFromUrl]
  );

  useEffect(() => {
    const fetchMetadata = async () => {
      try {
        const response = await fetch("/api/value-finder/metadata");
        if (!response.ok) {
          throw new Error("Failed to fetch metadata");
        }
        const data = await response.json();
        setMetadata(data);
      } catch (err) {
        console.error("Error fetching metadata:", err);
        setError("Failed to load filter options. Please try again later.");
      }
    };

    fetchMetadata();
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    const fetchProperties = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams(searchParams.toString());
        const response = await fetch(`/api/value-finder?${params.toString()}`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error("Failed to fetch properties");
        }

        const data = await response.json();
        setProperties(data);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        console.error("Error fetching properties:", err);
        setError("Failed to load properties. Please try again later.");
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    if (metadata) {
      fetchProperties();
    }

    return () => {
      controller.abort();
    };
  }, [searchParams, metadata]);

  const handleFiltersChange = (newFilters: Partial<ValueFinderFilters>) => {
    // Reset to first page when filters change
    updateUrl({ ...newFilters, offset: 0 });
  };

  const handleClearFilters = () => {
    router.push("/value-finder");
  };

  const handleSortChange = (field: SortField, order: SortOrder) => {
    updateUrl({ sort: field, order, offset: 0 });
  };

  const handlePageSizeChange = (size: number) => {
    updateUrl({ limit: size, offset: 0 });
  };

  const handlePageChange = (page: number) => {
    const filters = getFiltersFromUrl();
    const newOffset = (page - 1) * (filters.limit || 50);
    updateUrl({ offset: newOffset });
  };

  const currentFilters = getFiltersFromUrl();

  return (
    <div className="min-h-screen bg-tactical-bg">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
        {/* Hero */}
        <header className="mx-auto max-w-2xl text-center animate-fade-in-up">
          <p className="font-mono text-[12px] font-semibold uppercase tracking-tactical-wide text-tactical-accent">
            Value Finder
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-[1.06] tracking-tight text-tactical-text sm:text-[46px]">
            Find undervalued
            <br className="hidden sm:block" /> Stockholm homes
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-tactical-muted">
            Every recent sale, scored against the model&rsquo;s estimate. Filter by value tier to surface
            the widest gaps between price paid and predicted worth.
          </p>

          {metadata && (
            <dl className="mx-auto mt-8 flex max-w-md items-stretch justify-center divide-x divide-tactical-border rounded-2xl border border-tactical-border bg-tactical-surface shadow-elev-1">
              <Stat
                value={metadata.statistics.total_properties.toLocaleString("en-US")}
                label="Properties"
              />
              <Stat value={metadata.statistics.value_score.mean.toFixed(1)} label="Avg score" />
              <Stat
                value={String(metadata.statistics.area_statistics.total_areas)}
                label="Areas"
              />
            </dl>
          )}
        </header>

        {error && (
          <div className="mx-auto mt-8 max-w-2xl rounded-xl border border-val-high-line bg-val-high-tint p-4">
            <p className="text-[13px] font-medium text-val-high">{error}</p>
          </div>
        )}

        <div className="mt-10 flex flex-col gap-6 lg:mt-12 lg:flex-row lg:gap-8">
          <aside className="lg:w-[300px] lg:shrink-0">
            {metadata && (
              <div>
                <FiltersPanel
                  filters={currentFilters}
                  availableAreas={metadata.available_areas}
                  propertyTypes={metadata.property_types}
                  priceRange={metadata.price_range}
                  livingAreaRange={metadata.living_area_range}
                  roomsRange={metadata.rooms_range}
                  valueScoreRange={metadata.value_score_range}
                  onFiltersChange={handleFiltersChange}
                  onClearFilters={handleClearFilters}
                  isLoading={isLoading}
                />
              </div>
            )}
          </aside>

          <main className="min-w-0 flex-1">
            {properties && (
              <SortControls
                sortField={currentFilters.sort || "value_score"}
                sortOrder={currentFilters.order || "desc"}
                totalResults={properties.total}
                pageSize={currentFilters.limit || 50}
                onSortChange={handleSortChange}
                onPageSizeChange={handlePageSizeChange}
                isLoading={isLoading}
              />
            )}

            {isLoading && (
              <div className="flex items-center justify-center py-24">
                <div className="flex flex-col items-center gap-3">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-tactical-border border-t-tactical-text" />
                  <p className="text-[13px] text-tactical-muted">Loading properties…</p>
                </div>
              </div>
            )}

            {!isLoading && properties && properties.properties.length > 0 && (
              <>
                <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
                  {properties.properties.map((property) => (
                    <PropertyCard key={property.listing_id} property={property} />
                  ))}
                </div>

                <Pagination
                  currentPage={properties.page}
                  totalPages={properties.total_pages}
                  totalResults={properties.total}
                  pageSize={properties.page_size}
                  onPageChange={handlePageChange}
                  isLoading={isLoading}
                />
              </>
            )}

            {!isLoading && properties && properties.properties.length === 0 && (
              <div className="mt-6 rounded-2xl border border-tactical-border bg-tactical-surface px-6 py-16 text-center shadow-elev-1">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-tactical-elevated">
                  <svg className="h-6 w-6 text-tactical-dimmed" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <h3 className="mt-4 text-lg font-semibold text-tactical-text">No matches</h3>
                <p className="mx-auto mt-1.5 max-w-sm text-[14px] text-tactical-muted">
                  Nothing fits these filters. Try widening the range or clearing a tier.
                </p>
                <button onClick={handleClearFilters} className="tactical-btn-primary mx-auto mt-5">
                  Clear all filters
                </button>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-1 flex-col items-center px-5 py-4">
      <dd className="num text-2xl font-semibold text-tactical-text">{value}</dd>
      <dt className="mt-1 text-[12px] text-tactical-muted">{label}</dt>
    </div>
  );
}

export default function ValueFinderPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-tactical-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-tactical-border border-t-tactical-text" />
          <p className="text-[13px] text-tactical-muted">Loading…</p>
        </div>
      </div>
    }>
      <ValueFinderContent />
    </Suspense>
  );
}


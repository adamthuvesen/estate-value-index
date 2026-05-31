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
  ValueFinderMetadataResponse,
  SortField,
  SortOrder,
  ValueTier,
} from "@/lib/value-finder-types";

function ValueFinderContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [properties, setProperties] = useState<ValueFinderResponse | null>(null);
  const [metadata, setMetadata] = useState<ValueFinderMetadataResponse | null>(null);
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
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="tactical-card p-6 sm:p-8 lg:p-10 tactical-corners relative">
          <div className="mb-8">
            <div className="text-center space-y-3">
              <p className="tactical-label">CLASSIFIED // ESTATE VALUE INDEX</p>
              <h1 className="text-4xl font-bold tracking-tactical text-tactical-text sm:text-5xl font-mono">
                PROPERTY VALUE FINDER
              </h1>
              <p className="mx-auto mt-4 max-w-2xl text-sm text-tactical-muted font-mono leading-relaxed">
                DISCOVER PROPERTIES IN STOCKHOLM BASED ON AI MODEL PREDICTIONS //
                FILTER BY VALUE TIER TO IDENTIFY OPTIMAL ACQUISITION TARGETS
              </p>
            </div>

            {metadata && (
              <div className="mx-auto mt-10 max-w-3xl">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="tactical-card p-5 border-tactical-border-emphasis">
                    <dt className="tactical-label mb-2">PROPERTIES ANALYZED</dt>
                    <dd className="text-3xl font-bold tracking-tactical text-tactical-text font-mono">
                      {metadata.statistics.total_properties.toLocaleString("en-US")}
                    </dd>
                  </div>
                  <div className="tactical-card p-5 border-tactical-border-emphasis">
                    <dt className="tactical-label mb-2">AVG VALUE SCORE</dt>
                    <dd className="text-3xl font-bold tracking-tactical text-tactical-text font-mono">
                      {metadata.statistics.value_score.mean.toFixed(1)}
                    </dd>
                  </div>
                  <div className="tactical-card p-5 border-tactical-border-emphasis">
                    <dt className="tactical-label mb-2">AREAS COVERED</dt>
                    <dd className="text-3xl font-bold tracking-tactical text-tactical-text font-mono">
                      {metadata.statistics.area_statistics.total_areas}
                    </dd>
                  </div>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="mb-6 tactical-card p-4 border-tactical-accent">
              <p className="tactical-label text-tactical-accent mb-2">ERROR</p>
              <p className="text-xs font-mono text-tactical-accent tracking-tactical">{error.toUpperCase()}</p>
            </div>
          )}

          <div className="flex flex-col gap-6 lg:flex-row">
          <aside className="lg:w-80">
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

          <main className="flex-1">
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
               <div className="mt-6 flex items-center justify-center py-12">
                 <div className="text-center">
                   <div className="mb-4 inline-block h-12 w-12 animate-spin rounded-tactical border-4 border-tactical-border border-t-tactical-accent"></div>
                   <p className="tactical-label text-tactical-muted">LOADING PROPERTIES...</p>
                 </div>
               </div>
             )}

            {!isLoading && properties && properties.properties.length > 0 && (
              <>
                <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
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
              <div className="mt-12 text-center">
                <svg
                  className="mx-auto h-24 w-24 text-tactical-border"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
                <h3 className="mt-4 text-lg font-bold text-tactical-text font-mono tracking-tactical">NO RESULTS FOUND</h3>
                <p className="mt-2 text-xs text-tactical-muted font-mono">
                  ADJUST FILTER PARAMETERS TO EXPAND SEARCH RESULTS
                </p>
                 <button
                   onClick={handleClearFilters}
                   className="mt-4 tactical-btn-primary"
                 >
                   CLEAR ALL FILTERS
                 </button>
              </div>
            )}
          </main>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ValueFinderPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-tactical-bg flex items-center justify-center">
        <div className="text-center">
          <div className="mb-4 inline-block h-12 w-12 animate-spin rounded-tactical border-4 border-tactical-border border-t-tactical-accent"></div>
          <p className="tactical-label text-tactical-muted">LOADING...</p>
        </div>
      </div>
    }>
      <ValueFinderContent />
    </Suspense>
  );
}


"use client";

import { useState } from "react";
import { formatCurrency } from "@/lib/format";
import {
  VALUE_TIERS,
  type ValueFinderFilters,
  type ValueTier,
} from "@/lib/value-finder-types";

interface FiltersPanelProps {
  filters: ValueFinderFilters;
  availableAreas: string[];
  propertyTypes: string[];
  priceRange: { min: number; max: number };
  livingAreaRange: { min: number; max: number };
  roomsRange: { min: number; max: number };
  valueScoreRange: { min: number; max: number };
  onFiltersChange: (filters: Partial<ValueFinderFilters>) => void;
  onClearFilters: () => void;
  isLoading?: boolean;
}

const VALUE_TIER_TEXT_COLORS: Record<ValueTier, string> = {
  "Excellent Value": "text-tactical-success",
  "Great Value": "text-tactical-success",
  "Good Value": "text-tactical-text",
  "Fair Value": "text-tactical-muted",
  Overvalued: "text-tactical-accent-hover",
  "Highly Overvalued": "text-tactical-accent",
};

export function FiltersPanel({
  filters,
  availableAreas,
  propertyTypes,
  priceRange,
  livingAreaRange,
  roomsRange,
  valueScoreRange,
  onFiltersChange,
  onClearFilters,
  isLoading = false,
}: FiltersPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [areaSearch, setAreaSearch] = useState("");

  const activeFilterCount = Object.entries(filters).filter(([key, value]) => {
    if (key === "sort" || key === "order" || key === "limit" || key === "offset") return false;
    if (value === undefined || value === null) return false;
    if (Array.isArray(value) && value.length === 0) return false;
    return true;
  }).length;

  const handleAreaToggle = (area: string) => {
    const currentAreas = Array.isArray(filters.area) ? filters.area : filters.area ? [filters.area] : [];
    const newAreas = currentAreas.includes(area)
      ? currentAreas.filter((a) => a !== area)
      : [...currentAreas, area];
    onFiltersChange({ area: newAreas.length > 0 ? newAreas : undefined });
  };

  const filteredAreas = availableAreas.filter((area) =>
    area.toLowerCase().includes(areaSearch.toLowerCase())
  );

  const selectedAreas = Array.isArray(filters.area) ? filters.area : filters.area ? [filters.area] : [];

  return (
    <div className="tactical-card">
      <div className="flex items-center justify-between border-b border-tactical-border p-4">
        <div className="flex items-center gap-3">
          <h2 className="tactical-label">FILTER PARAMETERS</h2>
          {activeFilterCount > 0 && (
            <span className="tactical-badge-active">
              {activeFilterCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {activeFilterCount > 0 && (
            <button
              onClick={onClearFilters}
              disabled={isLoading}
              className="tactical-focus-ring text-xs font-mono text-tactical-accent hover:text-tactical-accent-hover disabled:opacity-30 tracking-tactical"
            >
              CLEAR ALL
            </button>
          )}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="tactical-focus-ring rounded-tactical p-1 hover:bg-tactical-elevated"
            aria-label={isExpanded ? "Hide filters" : "Show filters"}
          >
            <svg
              className={`h-5 w-5 text-tactical-muted transition-transform ${isExpanded ? "rotate-180" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="divide-y divide-tactical-border">
          <div className="p-4">
            <label className="mb-3 block tactical-label">
              VALUE TIER {filters.value_tier && Array.isArray(filters.value_tier) && filters.value_tier.length > 0 && `(${filters.value_tier.length})`}
            </label>
            <div className="space-y-2">
              {VALUE_TIERS.map((tier) => {
                const selectedTiers = Array.isArray(filters.value_tier) ? filters.value_tier : filters.value_tier ? [filters.value_tier] : [];
                const isSelected = selectedTiers.includes(tier);

                return (
                  <label key={tier} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={isSelected}
                  onChange={() => {
                    const newTiers = isSelected
                      ? selectedTiers.filter((t) => t !== tier)
                      : [...selectedTiers, tier];
                    onFiltersChange({ value_tier: newTiers.length > 0 ? newTiers : undefined });
                  }}
                  disabled={isLoading}
                  className="disabled:cursor-not-allowed disabled:opacity-30"
                    />
                    <span className={`text-xs font-mono font-semibold ${VALUE_TIER_TEXT_COLORS[tier]}`}>{tier.toUpperCase()}</span>
                  </label>
                );
              })}
            </div>
            <div className="mt-2 text-[10px] text-tactical-dimmed font-mono tracking-tactical">
              PROPERTIES MUST BE 5% OR 200K SEK BELOW PREDICTED PRICE
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">
              VALUE SCORE: {filters.min_value_score ?? valueScoreRange.min} - {filters.max_value_score ?? valueScoreRange.max}
            </label>
            <div className="space-y-3">
              <div>
                <label htmlFor="min-value-score" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MIN
                </label>
                <input
                  id="min-value-score"
                  type="range"
                  min={valueScoreRange.min}
                  max={valueScoreRange.max}
                  value={filters.min_value_score ?? valueScoreRange.min}
                  onChange={(e) => onFiltersChange({ min_value_score: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
              <div>
                <label htmlFor="max-value-score" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MAX
                </label>
                <input
                  id="max-value-score"
                  type="range"
                  min={valueScoreRange.min}
                  max={valueScoreRange.max}
                  value={filters.max_value_score ?? valueScoreRange.max}
                  onChange={(e) => onFiltersChange({ max_value_score: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">
              PRICE: {formatCurrency(filters.min_price ?? priceRange.min)} - {formatCurrency(filters.max_price ?? priceRange.max)}
            </label>
            <div className="space-y-3">
              <div>
                <label htmlFor="min-price" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MIN
                </label>
                <input
                  id="min-price"
                  type="range"
                  min={priceRange.min}
                  max={priceRange.max}
                  step={100000}
                  value={filters.min_price ?? priceRange.min}
                  onChange={(e) => onFiltersChange({ min_price: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
              <div>
                <label htmlFor="max-price" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MAX
                </label>
                <input
                  id="max-price"
                  type="range"
                  min={priceRange.min}
                  max={priceRange.max}
                  step={100000}
                  value={filters.max_price ?? priceRange.max}
                  onChange={(e) => onFiltersChange({ max_price: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">
              LIVING AREA: {filters.min_living_area ?? livingAreaRange.min} - {filters.max_living_area ?? livingAreaRange.max} M²
            </label>
            <div className="space-y-3">
              <div>
                <label htmlFor="min-living-area" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MIN
                </label>
                <input
                  id="min-living-area"
                  type="range"
                  min={livingAreaRange.min}
                  max={livingAreaRange.max}
                  value={filters.min_living_area ?? livingAreaRange.min}
                  onChange={(e) => onFiltersChange({ min_living_area: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
              <div>
                <label htmlFor="max-living-area" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MAX
                </label>
                <input
                  id="max-living-area"
                  type="range"
                  min={livingAreaRange.min}
                  max={livingAreaRange.max}
                  value={filters.max_living_area ?? livingAreaRange.max}
                  onChange={(e) => onFiltersChange({ max_living_area: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">
              NUMBER OF ROOMS: {filters.min_rooms ?? roomsRange.min} - {filters.max_rooms ?? roomsRange.max}
            </label>
            <div className="space-y-3">
              <div>
                <label htmlFor="min-rooms" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MIN
                </label>
                <input
                  id="min-rooms"
                  type="range"
                  min={roomsRange.min}
                  max={roomsRange.max}
                  value={filters.min_rooms ?? roomsRange.min}
                  onChange={(e) => onFiltersChange({ min_rooms: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
              <div>
                <label htmlFor="max-rooms" className="mb-1 block text-[10px] text-tactical-muted font-mono tracking-tactical">
                  MAX
                </label>
                <input
                  id="max-rooms"
                  type="range"
                  min={roomsRange.min}
                  max={roomsRange.max}
                  value={filters.max_rooms ?? roomsRange.max}
                  onChange={(e) => onFiltersChange({ max_rooms: Number(e.target.value) })}
                  disabled={isLoading}
                  className="w-full disabled:cursor-not-allowed disabled:opacity-30"
                />
              </div>
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">
              AREAS {selectedAreas.length > 0 && `(${selectedAreas.length})`}
            </label>
            <input
              type="text"
              placeholder="SEARCH AREA..."
              value={areaSearch}
              onChange={(e) => setAreaSearch(e.target.value)}
              className="tactical-input mb-3 w-full"
            />
            <div className="max-h-60 space-y-2 overflow-y-auto">
              {filteredAreas.map((area) => (
                <label key={area} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedAreas.includes(area)}
                    onChange={() => handleAreaToggle(area)}
                    disabled={isLoading}
                    className="disabled:cursor-not-allowed disabled:opacity-30"
                  />
                  <span className="text-xs text-tactical-text font-mono">{area}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">PROPERTY TYPE</label>
            <div className="space-y-2">
              {propertyTypes.map((type) => {
                const selectedTypes = Array.isArray(filters.property_type) ? filters.property_type : filters.property_type ? [filters.property_type] : [];
                const isSelected = selectedTypes.includes(type);
                return (
                  <label key={type} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => {
                        const newTypes = isSelected
                          ? selectedTypes.filter((t) => t !== type)
                          : [...selectedTypes, type];
                        onFiltersChange({ property_type: newTypes.length > 0 ? newTypes : undefined });
                      }}
                      disabled={isLoading}
                      className="disabled:cursor-not-allowed disabled:opacity-30"
                    />
                    <span className="text-xs text-tactical-text font-mono">{type}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="p-4">
            <label className="mb-3 block tactical-label">AMENITIES</label>
            <div className="space-y-2">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.has_elevator === true}
                  onChange={(e) => onFiltersChange({ has_elevator: e.target.checked ? true : undefined })}
                  disabled={isLoading}
                  className="disabled:cursor-not-allowed disabled:opacity-30"
                />
                <span className="text-xs text-tactical-text font-mono">ELEVATOR</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.has_balcony === true}
                  onChange={(e) => onFiltersChange({ has_balcony: e.target.checked ? true : undefined })}
                  disabled={isLoading}
                  className="disabled:cursor-not-allowed disabled:opacity-30"
                />
                <span className="text-xs text-tactical-text font-mono">BALCONY</span>
              </label>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

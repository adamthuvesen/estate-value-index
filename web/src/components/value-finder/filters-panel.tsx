"use client";

import { useState } from "react";
import { formatSek } from "@/lib/format";
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

const VALUE_TIER_DOT: Record<ValueTier, string> = {
  "Excellent Value": "bg-val-exc",
  "Great Value": "bg-val-great",
  "Good Value": "bg-val-good",
  "Fair Value": "bg-val-fair",
  Overvalued: "bg-val-over",
  "Highly Overvalued": "bg-val-high",
};

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">
      {children}
    </div>
  );
}

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
  const [areaSearch, setAreaSearch] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

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
  const selectedTiers = Array.isArray(filters.value_tier)
    ? filters.value_tier
    : filters.value_tier
      ? [filters.value_tier]
      : [];

  return (
    <div className="tactical-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-tactical-border px-5 py-4">
        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          className="tactical-focus-ring flex items-center gap-2 lg:pointer-events-none"
          aria-expanded={mobileOpen}
        >
          <h2 className="text-[15px] font-semibold text-tactical-text">Filters</h2>
          {activeFilterCount > 0 && (
            <span className="tactical-badge-active num">{activeFilterCount}</span>
          )}
          <svg
            className={`h-4 w-4 text-tactical-dimmed transition-transform lg:hidden ${mobileOpen ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 9l6 6 6-6" />
          </svg>
        </button>
        {activeFilterCount > 0 && (
          <button
            onClick={onClearFilters}
            disabled={isLoading}
            className="tactical-focus-ring text-[13px] font-medium text-tactical-accent transition-colors hover:text-tactical-accent-hover disabled:opacity-40"
          >
            Clear all
          </button>
        )}
      </div>

      <div className={`${mobileOpen ? "block" : "hidden"} divide-y divide-tactical-border lg:block`}>
        {/* Value tier */}
        <div className="px-5 py-5">
          <FieldLabel>Value tier</FieldLabel>
          <div className="space-y-1">
            {VALUE_TIERS.map((tier) => {
              const isSelected = selectedTiers.includes(tier);
              return (
                <label
                  key={tier}
                  className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-tactical-elevated/60"
                >
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
                    className="disabled:cursor-not-allowed disabled:opacity-40"
                  />
                  <span className={`h-2 w-2 shrink-0 rounded-full ${VALUE_TIER_DOT[tier]}`} aria-hidden />
                  <span className="text-[13px] font-medium text-tactical-text">{tier}</span>
                </label>
              );
            })}
          </div>
          <p className="mt-3 text-[12px] leading-relaxed text-tactical-dimmed">
            A property counts as good value when it sold at least 5% or 200k kr below the model estimate.
          </p>
        </div>

        <RangeField
          label="Value score"
          value={`${filters.min_value_score ?? valueScoreRange.min}–${filters.max_value_score ?? valueScoreRange.max}`}
          min={valueScoreRange.min}
          max={valueScoreRange.max}
          minValue={filters.min_value_score ?? valueScoreRange.min}
          maxValue={filters.max_value_score ?? valueScoreRange.max}
          onMin={(v) => onFiltersChange({ min_value_score: v })}
          onMax={(v) => onFiltersChange({ max_value_score: v })}
          disabled={isLoading}
        />

        <RangeField
          label="Price"
          value={`${formatSek(filters.min_price ?? priceRange.min)} – ${formatSek(filters.max_price ?? priceRange.max)}`}
          min={priceRange.min}
          max={priceRange.max}
          step={100000}
          minValue={filters.min_price ?? priceRange.min}
          maxValue={filters.max_price ?? priceRange.max}
          onMin={(v) => onFiltersChange({ min_price: v })}
          onMax={(v) => onFiltersChange({ max_price: v })}
          disabled={isLoading}
        />

        <RangeField
          label="Living area"
          value={`${filters.min_living_area ?? livingAreaRange.min}–${filters.max_living_area ?? livingAreaRange.max} m²`}
          min={livingAreaRange.min}
          max={livingAreaRange.max}
          minValue={filters.min_living_area ?? livingAreaRange.min}
          maxValue={filters.max_living_area ?? livingAreaRange.max}
          onMin={(v) => onFiltersChange({ min_living_area: v })}
          onMax={(v) => onFiltersChange({ max_living_area: v })}
          disabled={isLoading}
        />

        <RangeField
          label="Rooms"
          value={`${filters.min_rooms ?? roomsRange.min}–${filters.max_rooms ?? roomsRange.max}`}
          min={roomsRange.min}
          max={roomsRange.max}
          minValue={filters.min_rooms ?? roomsRange.min}
          maxValue={filters.max_rooms ?? roomsRange.max}
          onMin={(v) => onFiltersChange({ min_rooms: v })}
          onMax={(v) => onFiltersChange({ max_rooms: v })}
          disabled={isLoading}
        />

        {/* Areas */}
        <div className="px-5 py-5">
          <FieldLabel>
            Areas {selectedAreas.length > 0 && <span className="text-tactical-accent">({selectedAreas.length})</span>}
          </FieldLabel>
          <input
            type="text"
            placeholder="Search areas…"
            value={areaSearch}
            onChange={(e) => setAreaSearch(e.target.value)}
            className="tactical-input mb-3 w-full"
          />
          <div className="space-y-1">
            {filteredAreas.map((area) => (
              <label
                key={area}
                className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-tactical-elevated/60"
              >
                <input
                  type="checkbox"
                  checked={selectedAreas.includes(area)}
                  onChange={() => handleAreaToggle(area)}
                  disabled={isLoading}
                  className="disabled:cursor-not-allowed disabled:opacity-40"
                />
                <span className="text-[13px] text-tactical-text">{area}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Property type */}
        {propertyTypes.length > 0 && (
          <div className="px-5 py-5">
            <FieldLabel>Property type</FieldLabel>
            <div className="space-y-1">
              {propertyTypes.map((type) => {
                const selectedTypes = Array.isArray(filters.property_type)
                  ? filters.property_type
                  : filters.property_type
                    ? [filters.property_type]
                    : [];
                const isSelected = selectedTypes.includes(type);
                return (
                  <label
                    key={type}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-tactical-elevated/60"
                  >
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
                      className="disabled:cursor-not-allowed disabled:opacity-40"
                    />
                    <span className="text-[13px] text-tactical-text">{type}</span>
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* Amenities */}
        <div className="px-5 py-5">
          <FieldLabel>Amenities</FieldLabel>
          <div className="space-y-1">
            <label className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-tactical-elevated/60">
              <input
                type="checkbox"
                checked={filters.has_elevator === true}
                onChange={(e) => onFiltersChange({ has_elevator: e.target.checked ? true : undefined })}
                disabled={isLoading}
                className="disabled:cursor-not-allowed disabled:opacity-40"
              />
              <span className="text-[13px] text-tactical-text">Elevator</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-tactical-elevated/60">
              <input
                type="checkbox"
                checked={filters.has_balcony === true}
                onChange={(e) => onFiltersChange({ has_balcony: e.target.checked ? true : undefined })}
                disabled={isLoading}
                className="disabled:cursor-not-allowed disabled:opacity-40"
              />
              <span className="text-[13px] text-tactical-text">Balcony</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

function RangeField({
  label,
  value,
  min,
  max,
  step,
  minValue,
  maxValue,
  onMin,
  onMax,
  disabled,
}: {
  label: string;
  value: string;
  min: number;
  max: number;
  step?: number;
  minValue: number;
  maxValue: number;
  onMin: (v: number) => void;
  onMax: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="px-5 py-5">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">
          {label}
        </span>
        <span className="num text-[12px] font-medium text-tactical-muted">{value}</span>
      </div>
      <div className="space-y-3">
        <div className="flex items-center gap-2.5">
          <span className="w-8 shrink-0 text-[11px] text-tactical-dimmed">Min</span>
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={minValue}
            onChange={(e) => onMin(Number(e.target.value))}
            disabled={disabled}
            className="w-full disabled:cursor-not-allowed disabled:opacity-40"
          />
        </div>
        <div className="flex items-center gap-2.5">
          <span className="w-8 shrink-0 text-[11px] text-tactical-dimmed">Max</span>
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={maxValue}
            onChange={(e) => onMax(Number(e.target.value))}
            disabled={disabled}
            className="w-full disabled:cursor-not-allowed disabled:opacity-40"
          />
        </div>
      </div>
    </div>
  );
}

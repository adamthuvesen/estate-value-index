"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DualRangeSlider } from "@/components/ui/dual-range-slider";
import { formatSek } from "@/lib/format";
import { VALUE_TIER_STYLES } from "@/lib/tiers";
import {
  VALUE_TIERS,
  type ValueFinderFilters,
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

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <div className="eyebrow mb-3">{children}</div>;
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
    <div className="ledger-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-ledger-border px-5 py-4">
        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          className="focus-ring flex items-center gap-2 lg:pointer-events-none"
          aria-expanded={mobileOpen}
        >
          <h2 className="eyebrow text-ledger-text">Filters</h2>
          {activeFilterCount > 0 && (
            <Badge variant="accent" className="num">{activeFilterCount}</Badge>
          )}
          <svg
            className={`h-4 w-4 text-ledger-dimmed transition-transform lg:hidden ${mobileOpen ? "rotate-180" : ""}`}
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
            className="focus-ring text-[13px] font-medium text-ledger-accent transition-colors hover:text-ledger-accent-hover disabled:opacity-40"
          >
            Clear all
          </button>
        )}
      </div>

      <div className={`${mobileOpen ? "block" : "hidden"} divide-y divide-ledger-border lg:block`}>
        {/* Value tier */}
        <div className="px-5 py-5">
          <FieldLabel>Value tier</FieldLabel>
          <div className="space-y-1">
            {VALUE_TIERS.map((tier) => {
              const isSelected = selectedTiers.includes(tier);
              return (
                <label
                  key={tier}
                  className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-ledger-elevated/60"
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
                  <span className={`h-2 w-2 shrink-0 rounded-full ${VALUE_TIER_STYLES[tier].dot}`} aria-hidden />
                  <span className="text-[13px] font-medium text-ledger-text">{VALUE_TIER_STYLES[tier].label}</span>
                </label>
              );
            })}
          </div>
          <p className="mt-3 text-[12px] leading-relaxed text-ledger-dimmed">
            A property counts as good value when it sold at least 5% or 200k kr below the model estimate.
          </p>
        </div>

        <RangeField
          label="Value score"
          min={valueScoreRange.min}
          max={valueScoreRange.max}
          minValue={filters.min_value_score ?? valueScoreRange.min}
          maxValue={filters.max_value_score ?? valueScoreRange.max}
          format={(lo, hi) => `${lo}–${hi}`}
          onCommit={(lo, hi) =>
            onFiltersChange({ min_value_score: lo, max_value_score: hi })
          }
        />

        <RangeField
          label="Price"
          min={priceRange.min}
          max={priceRange.max}
          step={100000}
          minValue={filters.min_price ?? priceRange.min}
          maxValue={filters.max_price ?? priceRange.max}
          format={(lo, hi) => `${formatSek(lo)} – ${formatSek(hi)}`}
          onCommit={(lo, hi) => onFiltersChange({ min_price: lo, max_price: hi })}
        />

        <RangeField
          label="Living area"
          min={livingAreaRange.min}
          max={livingAreaRange.max}
          minValue={filters.min_living_area ?? livingAreaRange.min}
          maxValue={filters.max_living_area ?? livingAreaRange.max}
          format={(lo, hi) => `${lo}–${hi} m²`}
          onCommit={(lo, hi) =>
            onFiltersChange({ min_living_area: lo, max_living_area: hi })
          }
        />

        <RangeField
          label="Rooms"
          min={roomsRange.min}
          max={roomsRange.max}
          minValue={filters.min_rooms ?? roomsRange.min}
          maxValue={filters.max_rooms ?? roomsRange.max}
          format={(lo, hi) => `${lo}–${hi}`}
          onCommit={(lo, hi) => onFiltersChange({ min_rooms: lo, max_rooms: hi })}
        />

        {/* Areas */}
        <div className="px-5 py-5">
          <FieldLabel>
            Areas {selectedAreas.length > 0 && <span className="text-ledger-accent">({selectedAreas.length})</span>}
          </FieldLabel>
          <input
            type="text"
            placeholder="Search areas…"
            value={areaSearch}
            onChange={(e) => setAreaSearch(e.target.value)}
            className="ledger-input mb-3 w-full"
          />
          <div className="space-y-1">
            {filteredAreas.map((area) => (
              <label
                key={area}
                className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-ledger-elevated/60"
              >
                <input
                  type="checkbox"
                  checked={selectedAreas.includes(area)}
                  onChange={() => handleAreaToggle(area)}
                  disabled={isLoading}
                  className="disabled:cursor-not-allowed disabled:opacity-40"
                />
                <span className="text-[13px] text-ledger-text">{area}</span>
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
                    className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-ledger-elevated/60"
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
                    <span className="text-[13px] text-ledger-text">{type}</span>
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
            <label className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-ledger-elevated/60">
              <input
                type="checkbox"
                checked={filters.has_elevator === true}
                onChange={(e) => onFiltersChange({ has_elevator: e.target.checked ? true : undefined })}
                disabled={isLoading}
                className="disabled:cursor-not-allowed disabled:opacity-40"
              />
              <span className="text-[13px] text-ledger-text">Elevator</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2.5 rounded-md py-1 transition-colors hover:bg-ledger-elevated/60">
              <input
                type="checkbox"
                checked={filters.has_balcony === true}
                onChange={(e) => onFiltersChange({ has_balcony: e.target.checked ? true : undefined })}
                disabled={isLoading}
                className="disabled:cursor-not-allowed disabled:opacity-40"
              />
              <span className="text-[13px] text-ledger-text">Balcony</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

function RangeField({
  label,
  min,
  max,
  step,
  minValue,
  maxValue,
  format,
  onCommit,
}: {
  label: string;
  min: number;
  max: number;
  step?: number;
  minValue: number;
  maxValue: number;
  format: (low: number, high: number) => string;
  onCommit: (low: number, high: number) => void;
}) {
  // Live readout follows the drag; the URL update fires only on release.
  const [display, setDisplay] = useState<[number, number]>([minValue, maxValue]);

  // Re-sync the readout when the committed pair changes (URL nav / clear all).
  const signature = `${minValue}:${maxValue}`;
  const [prevSignature, setPrevSignature] = useState(signature);
  if (signature !== prevSignature) {
    setPrevSignature(signature);
    setDisplay([minValue, maxValue]);
  }

  return (
    <div className="px-5 py-5">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <span className="eyebrow">{label}</span>
        <span className="num text-[12px] font-medium text-ledger-muted">
          {format(display[0], display[1])}
        </span>
      </div>
      <DualRangeSlider
        min={min}
        max={max}
        step={step}
        value={[minValue, maxValue]}
        onChange={setDisplay}
        onCommit={([low, high]) => onCommit(low, high)}
        ariaLabel={[`Minimum ${label.toLowerCase()}`, `Maximum ${label.toLowerCase()}`]}
      />
    </div>
  );
}

"use client";

import type { FormEvent } from "react";

import type { PredictionInput, SampleListing } from "@/lib/prediction-types";

type PredictionFormProps = {
  formData: PredictionInput;
  areaOptions: string[];
  sampleListings: SampleListing[];
  selectedSampleIndex: number;
  modelLabel: string;
  modelLabels: Record<string, string>;
  isLoading: boolean;
  isApiReady: boolean;
  onFieldChange: (field: keyof PredictionInput, value: string) => void;
  onSampleLoad: (index: number) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

const fieldLabel = "text-[12px] font-medium text-ledger-muted";
const fieldControl =
  "rounded-sm border border-ledger-border bg-ledger-surface px-3 py-2 text-[14px] text-ledger-text transition-colors placeholder:text-ledger-dimmed hover:border-ledger-border-emphasis focus:border-ledger-accent focus:shadow-focus focus:outline-hidden";

export function PredictionForm({
  formData,
  areaOptions,
  sampleListings,
  selectedSampleIndex,
  modelLabel,
  modelLabels,
  isLoading,
  isApiReady,
  onFieldChange,
  onSampleLoad,
  onSubmit,
}: PredictionFormProps) {
  return (
    <form onSubmit={onSubmit} className="ledger-card space-y-6 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-ledger-text">Property details</h3>
        <span className="ledger-badge-inactive">{modelLabel}</span>
      </div>

      {/* Sample presets */}
      <div>
        <span className={`${fieldLabel} mb-2 block`}>Try a sample</span>
        <div className="flex flex-wrap gap-2">
          {sampleListings.map((listing, index) => {
            const selected = selectedSampleIndex === index;
            return (
              <button
                key={listing.name}
                type="button"
                onClick={() => onSampleLoad(index)}
                className={`rounded-pill border px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  selected
                    ? "border-ledger-text bg-ledger-text text-white"
                    : "border-ledger-border bg-ledger-surface text-ledger-muted hover:border-ledger-border-emphasis hover:text-ledger-text"
                }`}
              >
                {listing.name}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Listing price (kr)</span>
          <input type="number" value={formData.listing_price} onChange={(e) => onFieldChange("listing_price", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Living area (m²) *</span>
          <input required type="number" value={formData.living_area} onChange={(e) => onFieldChange("living_area", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Rooms</span>
          <select value={formData.rooms} onChange={(e) => onFieldChange("rooms", e.target.value)} className={fieldControl}>
            <option value="1">1 room</option>
            <option value="2">2 rooms</option>
            <option value="3">3 rooms</option>
            <option value="4">4 rooms</option>
            <option value="5">5+ rooms</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Monthly fee (kr)</span>
          <input type="number" value={formData.monthly_fee} onChange={(e) => onFieldChange("monthly_fee", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Days on market</span>
          <input type="number" value={formData.days_on_market} onChange={(e) => onFieldChange("days_on_market", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Construction year</span>
          <input type="number" value={formData.construction_year} onChange={(e) => onFieldChange("construction_year", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Property type</span>
          <select value={formData.property_type} onChange={(e) => onFieldChange("property_type", e.target.value)} className={fieldControl}>
            <option value="Lägenhet">Lägenhet</option>
            <option value="Villa">Villa</option>
            <option value="Radhus">Radhus</option>
            <option value="Kedjehus">Kedjehus</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Area</span>
          <select value={formData.area} onChange={(e) => onFieldChange("area", e.target.value)} className={fieldControl}>
            {areaOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Listing ID (optional)</span>
          <input value={formData.listing_id} onChange={(e) => onFieldChange("listing_id", e.target.value)} className={fieldControl} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Floor</span>
          <input type="number" value={formData.floor} onChange={(e) => onFieldChange("floor", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Elevator</span>
          <select value={formData.elevator} onChange={(e) => onFieldChange("elevator", e.target.value)} className={fieldControl}>
            <option value="">Unknown</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Balcony</span>
          <select value={formData.balcony} onChange={(e) => onFieldChange("balcony", e.target.value)} className={fieldControl}>
            <option value="">Unknown</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Latitude</span>
          <input type="number" value={formData.latitude} onChange={(e) => onFieldChange("latitude", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Longitude</span>
          <input type="number" value={formData.longitude} onChange={(e) => onFieldChange("longitude", e.target.value)} className={`num ${fieldControl}`} />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={fieldLabel}>Model</span>
          <select value={formData.model} onChange={(e) => onFieldChange("model", e.target.value)} className={fieldControl}>
            {Object.entries(modelLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-col gap-3 border-t border-ledger-border pt-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[13px] text-ledger-muted">
          Estimating with <span className="font-medium text-ledger-text">{modelLabel}</span>
        </p>
        <button type="submit" disabled={isLoading || !isApiReady} className="ledger-btn-primary">
          {!isApiReady ? "Starting model…" : isLoading ? "Estimating…" : "Estimate value"}
        </button>
      </div>
    </form>
  );
}

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
    <form onSubmit={onSubmit} className="tactical-card p-6 tactical-corners space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
        <div className="space-y-1">
          <p className="tactical-label">SCENARIO PRESETS</p>
          <h3 className="text-xl font-bold text-tactical-text tracking-tactical">SAMPLE LISTINGS</h3>
        </div>
        <span className="tactical-badge border-tactical-border-emphasis text-tactical-muted">
          {modelLabel}
        </span>
      </header>

      <div className="flex flex-wrap gap-2">
        {sampleListings.map((listing, index) => (
          <button
            key={listing.name}
            type="button"
            onClick={() => onSampleLoad(index)}
            className={`tactical-btn text-[10px] ${
              selectedSampleIndex === index
                ? "border-tactical-success text-tactical-success tactical-glow-success"
                : ""
            }`}
          >
            {listing.name}
          </button>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">LISTING PRICE (SEK) *</span>
          <input
            required
            type="number"
            value={formData.listing_price}
            onChange={(event) => onFieldChange("listing_price", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">LIVING AREA (M²) *</span>
          <input
            required
            type="number"
            value={formData.living_area}
            onChange={(event) => onFieldChange("living_area", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">ROOMS</span>
          <select
            value={formData.rooms}
            onChange={(event) => onFieldChange("rooms", event.target.value)}
            className="tactical-input"
          >
            <option value="1">1 ROOM</option>
            <option value="2">2 ROOMS</option>
            <option value="3">3 ROOMS</option>
            <option value="4">4 ROOMS</option>
            <option value="5">5+ ROOMS</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">MONTHLY FEE (SEK)</span>
          <input
            type="number"
            value={formData.monthly_fee}
            onChange={(event) => onFieldChange("monthly_fee", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">DAYS ON MARKET</span>
          <input
            type="number"
            value={formData.days_on_market}
            onChange={(event) => onFieldChange("days_on_market", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">CONSTRUCTION YEAR</span>
          <input
            type="number"
            value={formData.construction_year}
            onChange={(event) => onFieldChange("construction_year", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">PROPERTY TYPE</span>
          <select
            value={formData.property_type}
            onChange={(event) => onFieldChange("property_type", event.target.value)}
            className="tactical-input"
          >
            <option value="Lägenhet">LÄGENHET</option>
            <option value="Villa">VILLA</option>
            <option value="Radhus">RADHUS</option>
            <option value="Kedjehus">KEDJEHUS</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">AREA</span>
          <select
            value={formData.area}
            onChange={(event) => onFieldChange("area", event.target.value)}
            className="tactical-input"
          >
            {areaOptions.map((option) => (
              <option key={option} value={option}>
                {option.toUpperCase()}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">LISTING ID (OPTIONAL)</span>
          <input
            value={formData.listing_id}
            onChange={(event) => onFieldChange("listing_id", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">FLOOR</span>
          <input
            type="number"
            value={formData.floor}
            onChange={(event) => onFieldChange("floor", event.target.value)}
            className="tactical-input"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">ELEVATOR</span>
          <select
            value={formData.elevator}
            onChange={(event) => onFieldChange("elevator", event.target.value)}
            className="tactical-input"
          >
            <option value="">UNKNOWN</option>
            <option value="true">YES</option>
            <option value="false">NO</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">BALCONY</span>
          <select
            value={formData.balcony}
            onChange={(event) => onFieldChange("balcony", event.target.value)}
            className="tactical-input"
          >
            <option value="">UNKNOWN</option>
            <option value="true">YES</option>
            <option value="false">NO</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="tactical-label">MODEL</span>
          <select
            value={formData.model}
            onChange={(event) => onFieldChange("model", event.target.value)}
            className="tactical-input"
          >
            {Object.entries(modelLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-col gap-3 border border-tactical-border bg-tactical-elevated p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-mono text-tactical-muted tracking-tactical">
          SELECTED MODEL:
          <span className="ml-2 tactical-badge border-tactical-accent text-tactical-accent">
            {modelLabel.toUpperCase()}
          </span>
        </p>
        <button type="submit" disabled={isLoading || !isApiReady} className="tactical-btn-primary">
          {!isApiReady ? "STARTING API..." : isLoading ? "EXECUTING..." : "EXECUTE PREDICTION"}
        </button>
      </div>
    </form>
  );
}

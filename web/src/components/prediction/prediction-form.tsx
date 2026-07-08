"use client";

import type { FormEvent, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FigureFrame } from "@/components/ui/figure-frame";
import { cn } from "@/lib/cn";
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
  listingUrl: string;
  isPrefilling: boolean;
  onListingUrlChange: (value: string) => void;
  onPrefill: () => void;
  onFieldChange: (field: keyof PredictionInput, value: string) => void;
  onSampleLoad: (index: number) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

const AMENITY_OPTIONS = [
  { value: "", label: "Unknown" },
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
] as const;

export function PredictionForm({
  formData,
  areaOptions,
  sampleListings,
  selectedSampleIndex,
  modelLabel,
  modelLabels,
  isLoading,
  isApiReady,
  listingUrl,
  isPrefilling,
  onListingUrlChange,
  onPrefill,
  onFieldChange,
  onSampleLoad,
  onSubmit,
}: PredictionFormProps) {
  return (
    <FigureFrame
      kind="panel"
      index={1}
      title="Property details"
      meta={`Estimating with ${modelLabel}`}
    >
      <form onSubmit={onSubmit} className="space-y-7">
        {/* Start from a listing — merged prefill strip */}
        <div>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <span className="eyebrow text-ledger-muted">Start from a listing</span>
            <span className="text-caption text-ledger-dimmed">Optional</span>
          </div>
          <div className="flex flex-col gap-2.5 sm:flex-row">
            <input
              type="url"
              value={listingUrl}
              onChange={(event) => onListingUrlChange(event.target.value)}
              placeholder="https://www.booli.se/annons/123"
              className="ledger-input w-full flex-1"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={onPrefill}
              disabled={isPrefilling || isLoading}
              className="shrink-0"
            >
              {isPrefilling ? "Importing…" : "Import"}
            </Button>
          </div>
          <p className="mt-2 text-body-sm text-ledger-muted">
            Paste a Booli URL to auto-fill the form, or start from a sample below.
          </p>
        </div>

        {/* Sample presets */}
        <div>
          <span className="eyebrow mb-2 block text-ledger-muted">Try a sample</span>
          <div className="flex flex-wrap gap-2">
            {sampleListings.map((listing, index) => {
              const selected = selectedSampleIndex === index;
              return (
                <button
                  key={listing.name}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSampleLoad(index)}
                  className={cn(
                    "focus-ring rounded-pill border px-3 py-1.5 text-body-sm font-medium transition-colors",
                    selected
                      ? "border-ledger-text bg-ledger-text text-white"
                      : "border-ledger-border bg-ledger-surface text-ledger-muted hover:border-ledger-border-emphasis hover:text-ledger-text",
                  )}
                >
                  {listing.name}
                </button>
              );
            })}
          </div>
        </div>

        <FieldGroup legend="Listing">
          <Field label="Listing price (kr)">
            <input
              type="number"
              value={formData.listing_price}
              onChange={(e) => onFieldChange("listing_price", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
          <Field label="Listing ID (optional)">
            <input
              value={formData.listing_id}
              onChange={(e) => onFieldChange("listing_id", e.target.value)}
              className="ledger-input w-full"
            />
          </Field>
          <Field label="Days on market">
            <input
              type="number"
              value={formData.days_on_market}
              onChange={(e) => onFieldChange("days_on_market", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
        </FieldGroup>

        <FieldGroup legend="Home">
          <Field label="Living area (m²)" required>
            <input
              required
              type="number"
              value={formData.living_area}
              onChange={(e) => onFieldChange("living_area", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
          <Field label="Rooms">
            <select
              value={formData.rooms}
              onChange={(e) => onFieldChange("rooms", e.target.value)}
              className="ledger-input w-full"
            >
              <option value="1">1 room</option>
              <option value="2">2 rooms</option>
              <option value="3">3 rooms</option>
              <option value="4">4 rooms</option>
              <option value="5">5+ rooms</option>
            </select>
          </Field>
          <Field label="Property type">
            <select
              value={formData.property_type}
              onChange={(e) => onFieldChange("property_type", e.target.value)}
              className="ledger-input w-full"
            >
              <option value="Lägenhet">Lägenhet</option>
              <option value="Villa">Villa</option>
              <option value="Radhus">Radhus</option>
              <option value="Kedjehus">Kedjehus</option>
            </select>
          </Field>
          <Field label="Construction year">
            <input
              type="number"
              value={formData.construction_year}
              onChange={(e) => onFieldChange("construction_year", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
          <Field label="Floor">
            <input
              type="number"
              value={formData.floor}
              onChange={(e) => onFieldChange("floor", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
          <Field label="Monthly fee (kr)">
            <input
              type="number"
              value={formData.monthly_fee}
              onChange={(e) => onFieldChange("monthly_fee", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
        </FieldGroup>

        <FieldGroup legend="Location">
          <Field label="Area">
            <select
              value={formData.area}
              onChange={(e) => onFieldChange("area", e.target.value)}
              className="ledger-input w-full"
            >
              {areaOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Latitude">
            <input
              type="number"
              value={formData.latitude}
              onChange={(e) => onFieldChange("latitude", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
          <Field label="Longitude">
            <input
              type="number"
              value={formData.longitude}
              onChange={(e) => onFieldChange("longitude", e.target.value)}
              className="ledger-input num w-full"
            />
          </Field>
        </FieldGroup>

        <FieldGroup legend="Amenities">
          <AmenityToggle
            label="Elevator"
            value={formData.elevator}
            onChange={(value) => onFieldChange("elevator", value)}
          />
          <AmenityToggle
            label="Balcony"
            value={formData.balcony}
            onChange={(value) => onFieldChange("balcony", value)}
          />
        </FieldGroup>

        <div className="flex flex-col gap-4 border-t border-ledger-border pt-5 sm:flex-row sm:items-end sm:justify-between">
          <Field label="Model" className="w-full sm:max-w-[220px]">
            <select
              value={formData.model}
              onChange={(e) => onFieldChange("model", e.target.value)}
              className="ledger-input w-full"
            >
              {Object.entries(modelLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <div className="flex items-center gap-3">
            <p className="hidden text-caption text-ledger-dimmed sm:block">
              Result appears as Figure&nbsp;2
            </p>
            <Button type="submit" variant="primary" disabled={isLoading || !isApiReady}>
              {!isApiReady ? "Starting model…" : isLoading ? "Estimating…" : "Estimate value"}
            </Button>
          </div>
        </div>
      </form>
    </FigureFrame>
  );
}

function FieldGroup({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="border-t border-ledger-border pt-5">
      <legend className="eyebrow mb-3 text-ledger-accent">{legend}</legend>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </fieldset>
  );
}

function AmenityToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-caption font-medium text-ledger-muted">{label}</span>
      <div
        role="group"
        aria-label={label}
        className="inline-flex w-fit rounded-pill border border-ledger-border bg-ledger-surface p-0.5"
      >
        {AMENITY_OPTIONS.map((option) => {
          const selected = value === option.value;
          return (
            <button
              key={option.value || "unknown"}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
              className={cn(
                "focus-ring rounded-pill px-3.5 py-1 text-body-sm font-medium transition-colors",
                selected
                  ? "bg-ledger-text text-white"
                  : "text-ledger-muted hover:text-ledger-text",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

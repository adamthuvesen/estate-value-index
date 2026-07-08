"use client";

import { PredictionForm } from "@/components/prediction/prediction-form";
import { PredictionResults } from "@/components/prediction/prediction-results";
import { usePredictionForm } from "@/hooks/use-prediction-form";
import type { SampleListing } from "@/lib/prediction-types";

interface PredictionAppProps {
  sampleListings: SampleListing[];
  defaultAreas: string[];
  modelLabels: Record<string, string>;
}

export function PredictionApp({ sampleListings, defaultAreas, modelLabels }: PredictionAppProps) {
  const {
    formData,
    listingUrl,
    setListingUrl,
    areaOptions,
    prediction,
    error,
    selectedSampleIndex,
    isPrefilling,
    isLoading,
    isApiReady,
    currencyFormatter,
    handleFieldChange,
    handleSampleLoad,
    handlePrefillFromUrl,
    handleSubmit,
    modelLabel,
    priceDifference,
    differencePercent,
    isAboveAsking,
  } = usePredictionForm({ sampleListings, defaultAreas, modelLabels });

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <section className="space-y-4 lg:col-span-2">
        <PredictionForm
          formData={formData}
          areaOptions={areaOptions}
          sampleListings={sampleListings}
          selectedSampleIndex={selectedSampleIndex}
          modelLabel={modelLabel}
          modelLabels={modelLabels}
          isLoading={isLoading}
          isApiReady={isApiReady}
          listingUrl={listingUrl}
          isPrefilling={isPrefilling}
          onListingUrlChange={setListingUrl}
          onPrefill={handlePrefillFromUrl}
          onFieldChange={handleFieldChange}
          onSampleLoad={handleSampleLoad}
          onSubmit={handleSubmit}
        />

        {error && (
          <div className="rounded-ledger border border-val-high-line bg-val-high-tint p-4">
            <p className="text-body-sm font-medium text-val-high">{error}</p>
          </div>
        )}
      </section>

      <PredictionResults
        prediction={prediction}
        modelLabel={modelLabel}
        currencyFormatter={currencyFormatter}
        priceDifference={priceDifference}
        differencePercent={differencePercent}
        isAboveAsking={isAboveAsking}
      />
    </div>
  );
}

export default PredictionApp;

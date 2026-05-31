"use client";

type ListingPrefillProps = {
  listingUrl: string;
  onListingUrlChange: (value: string) => void;
  onPrefill: () => void;
  isPrefilling: boolean;
  isLoading: boolean;
};

export function ListingPrefill({
  listingUrl,
  onListingUrlChange,
  onPrefill,
  isPrefilling,
  isLoading,
}: ListingPrefillProps) {
  return (
    <div className="tactical-card p-6 tactical-corners">
      <header className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
        <div className="space-y-1">
          <p className="tactical-label">DATA IMPORT</p>
          <h3 className="text-xl font-bold text-tactical-text tracking-tactical">BOOLI URL</h3>
        </div>
        <button
          type="button"
          onClick={onPrefill}
          disabled={isPrefilling || isLoading}
          className="tactical-btn-primary"
        >
          {isPrefilling ? "IMPORTING..." : "IMPORT PROPERTY"}
        </button>
      </header>
      <input
        type="url"
        value={listingUrl}
        onChange={(event) => onListingUrlChange(event.target.value)}
        placeholder="https://www.booli.se/annons/123"
        className="tactical-input w-full"
      />
      <p className="mt-2 text-[10px] text-tactical-muted font-mono tracking-tactical">
        AUTO-FILL FIELDS // MANUAL OVERRIDE AVAILABLE BEFORE PREDICTION EXECUTION
      </p>
    </div>
  );
}

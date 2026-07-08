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
    <div className="ledger-card p-6">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-ledger-text">Start from a listing</h3>
        <span className="text-[12px] text-ledger-dimmed">Optional</span>
      </div>
      <div className="flex flex-col gap-2.5 sm:flex-row">
        <input
          type="url"
          value={listingUrl}
          onChange={(event) => onListingUrlChange(event.target.value)}
          placeholder="https://www.booli.se/annons/123"
          className="ledger-input w-full flex-1"
        />
        <button
          type="button"
          onClick={onPrefill}
          disabled={isPrefilling || isLoading}
          className="ledger-btn-primary shrink-0"
        >
          {isPrefilling ? "Importing…" : "Import"}
        </button>
      </div>
      <p className="mt-2.5 text-[13px] text-ledger-muted">
        Paste a Booli URL to auto-fill the form. You can edit anything before estimating.
      </p>
    </div>
  );
}

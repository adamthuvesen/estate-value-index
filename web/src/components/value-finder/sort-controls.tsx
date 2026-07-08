import type { SortField, SortOrder } from "@/lib/value-finder-types";

interface SortControlsProps {
  sortField: SortField;
  sortOrder: SortOrder;
  pageSize: number;
  onSortChange: (field: SortField, order: SortOrder) => void;
  onPageSizeChange: (size: number) => void;
  isLoading?: boolean;
}

const sortOptions: { value: SortField; label: string }[] = [
  { value: "value_score", label: "Value score" },
  { value: "prediction_delta_percentage", label: "Discount (%)" },
  { value: "prediction_delta_absolute", label: "Discount (kr)" },
  { value: "sold_date", label: "Sold date" },
  { value: "sold_price", label: "Price" },
  { value: "living_area", label: "Living area" },
];

/** Human label for a sort field — shared with the figure caption meta. */
export function sortFieldLabel(field: SortField): string {
  return sortOptions.find((o) => o.value === field)?.label ?? field;
}

const pageSizeOptions = [20, 50, 100];

const selectClass =
  "focus-ring appearance-none rounded-sm border border-ledger-border bg-ledger-surface bg-size-[16px] bg-position-[right_0.6rem_center] bg-no-repeat py-1.5 pl-3 pr-8 text-[13px] font-medium text-ledger-text transition-colors hover:border-ledger-border-emphasis focus:border-ledger-accent focus:outline-hidden disabled:opacity-40";

// inline chevron so selects match the light system without a global appearance reset
const chevron =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%2363666E' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' viewBox='0 0 24 24'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")";

export function SortControls({
  sortField,
  sortOrder,
  pageSize,
  onSortChange,
  onPageSizeChange,
  isLoading = false,
}: SortControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5">
          <label htmlFor="sort-field" className="text-[13px] text-ledger-muted">
            Sort
          </label>
          <select
            id="sort-field"
            value={sortField}
            onChange={(e) => onSortChange(e.target.value as SortField, sortOrder)}
            disabled={isLoading}
            className={selectClass}
            style={{ backgroundImage: chevron }}
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => onSortChange(sortField, sortOrder === "asc" ? "desc" : "asc")}
          disabled={isLoading}
          className="ledger-btn focus-ring px-2.5 py-1.5"
          title={sortOrder === "asc" ? "Ascending" : "Descending"}
          aria-label={`Sort ${sortOrder === "asc" ? "ascending" : "descending"}`}
        >
          <svg
            className={`h-4 w-4 text-ledger-muted transition-transform duration-ledger ${sortOrder === "asc" ? "rotate-180" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14m0 0l6-6m-6 6l-6-6" />
          </svg>
        </button>

        <span className="mx-1 hidden h-5 w-px bg-ledger-border sm:block" aria-hidden />

        <div className="flex items-center gap-1.5">
          <label htmlFor="page-size" className="text-[13px] text-ledger-muted">
            Show
          </label>
          <select
            id="page-size"
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            disabled={isLoading}
            className={selectClass}
            style={{ backgroundImage: chevron }}
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
    </div>
  );
}

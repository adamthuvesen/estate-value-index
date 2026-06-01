import type { SortField, SortOrder } from "@/lib/value-finder-types";

interface SortControlsProps {
  sortField: SortField;
  sortOrder: SortOrder;
  totalResults: number;
  pageSize: number;
  onSortChange: (field: SortField, order: SortOrder) => void;
  onPageSizeChange: (size: number) => void;
  isLoading?: boolean;
}

const sortOptions: { value: SortField; label: string }[] = [
  { value: "value_score", label: "Value Score" },
  { value: "prediction_delta_percentage", label: "Discount (%)" },
  { value: "prediction_delta_absolute", label: "Discount (SEK)" },
  { value: "sold_date", label: "Sold Date" },
  { value: "sold_price", label: "Price" },
  { value: "living_area", label: "Living Area" },
];

const pageSizeOptions = [20, 50, 100];

export function SortControls({
  sortField,
  sortOrder,
  totalResults,
  pageSize,
  onSortChange,
  onPageSizeChange,
  isLoading = false,
}: SortControlsProps) {
  const handleSortFieldChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onSortChange(e.target.value as SortField, sortOrder);
  };

  const handleSortOrderToggle = () => {
    onSortChange(sortField, sortOrder === "asc" ? "desc" : "asc");
  };

  const handlePageSizeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onPageSizeChange(Number(e.target.value));
  };

  return (
      <div className="tactical-card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <label htmlFor="sort-field" className="tactical-label whitespace-nowrap">
            SORT BY:
          </label>
          <select
            id="sort-field"
            value={sortField}
            onChange={handleSortFieldChange}
            disabled={isLoading}
            className="tactical-input tactical-focus-ring py-1.5 pl-3 pr-10 text-xs"
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={handleSortOrderToggle}
          disabled={isLoading}
          className="tactical-btn-primary tactical-focus-ring inline-flex items-center gap-2 px-3 py-1.5 text-xs uppercase"
          title={sortOrder === "asc" ? "Ascending order" : "Descending order"}
        >
          {sortOrder === "asc" ? (
            <>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12"
                />
              </svg>
              <span className="hidden sm:inline">Ascending</span>
            </>
          ) : (
            <>
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4"
                />
              </svg>
              <span className="hidden sm:inline">Descending</span>
            </>
          )}
        </button>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-xs font-mono text-tactical-muted">
          <span className="font-semibold text-tactical-text">{totalResults}</span> {totalResults === 1 ? 'RESULT' : 'RESULTS'}
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor="page-size" className="tactical-label whitespace-nowrap">
            PER PAGE:
          </label>
          <select
            id="page-size"
            value={pageSize}
            onChange={handlePageSizeChange}
            disabled={isLoading}
            className="tactical-input tactical-focus-ring py-1.5 pl-3 pr-10 text-xs"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}


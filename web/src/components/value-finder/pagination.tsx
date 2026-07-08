interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalResults: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  isLoading?: boolean;
}

export function Pagination({
  currentPage,
  totalPages,
  totalResults,
  pageSize,
  onPageChange,
  isLoading = false,
}: PaginationProps) {
  const startResult = (currentPage - 1) * pageSize + 1;
  const endResult = Math.min(currentPage * pageSize, totalResults);

  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    const maxVisible = 7;

    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
      return pages;
    }

    pages.push(1);
    if (currentPage > 3) pages.push("...");
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) pages.push(i);
    if (currentPage < totalPages - 2) pages.push("...");
    pages.push(totalPages);

    return pages;
  };

  const handlePrevious = () => {
    if (currentPage > 1 && !isLoading) onPageChange(currentPage - 1);
  };
  const handleNext = () => {
    if (currentPage < totalPages && !isLoading) onPageChange(currentPage + 1);
  };
  const handlePageClick = (page: number | string) => {
    if (typeof page === "number" && page !== currentPage && !isLoading) onPageChange(page);
  };

  if (totalPages <= 1) {
    return (
      <div className="flex items-center justify-center py-6 text-[13px] text-ledger-muted">
        Showing all {totalResults.toLocaleString("en-US")} {totalResults === 1 ? "home" : "homes"}
      </div>
    );
  }

  const arrowBtn =
    "ledger-btn focus-ring h-9 px-3 text-[13px] disabled:opacity-40";

  return (
    <div className="flex flex-col items-center gap-4 py-8">
      <p className="num text-[13px] text-ledger-muted">
        <span className="font-semibold text-ledger-text">{startResult.toLocaleString("en-US")}</span>–
        <span className="font-semibold text-ledger-text">{endResult.toLocaleString("en-US")}</span>{" "}
        <span className="font-sans">of</span>{" "}
        <span className="font-semibold text-ledger-text">{totalResults.toLocaleString("en-US")}</span>
      </p>

      <nav className="flex items-center gap-1.5" aria-label="Pagination">
        <button onClick={handlePrevious} disabled={currentPage === 1 || isLoading} className={arrowBtn} aria-label="Previous page">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div className="flex items-center gap-1">
          {getPageNumbers().map((page, index) => {
            if (page === "...") {
              return (
                <span key={`ellipsis-${index}`} className="px-1.5 text-ledger-dimmed">
                  …
                </span>
              );
            }
            const pageNum = page as number;
            const isCurrent = pageNum === currentPage;
            return (
              <button
                key={pageNum}
                onClick={() => handlePageClick(pageNum)}
                disabled={isLoading}
                className={`focus-ring num h-9 min-w-9 rounded-sm px-2.5 text-[13px] font-medium transition-colors duration-ledger ${
                  isCurrent
                    ? "bg-ledger-text text-white"
                    : "border border-ledger-border bg-ledger-surface text-ledger-text hover:bg-ledger-elevated disabled:opacity-40"
                }`}
                aria-label={`Go to page ${pageNum}`}
                aria-current={isCurrent ? "page" : undefined}
              >
                {pageNum}
              </button>
            );
          })}
        </div>

        <button onClick={handleNext} disabled={currentPage === totalPages || isLoading} className={arrowBtn} aria-label="Next page">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </nav>
    </div>
  );
}

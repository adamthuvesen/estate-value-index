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
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
      return pages;
    }

    pages.push(1);
    if (currentPage > 3) {
      pages.push("...");
    }

    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }

    if (currentPage < totalPages - 2) {
      pages.push("...");
    }
    pages.push(totalPages);

    return pages;
  };

  const handlePrevious = () => {
    if (currentPage > 1 && !isLoading) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages && !isLoading) {
      onPageChange(currentPage + 1);
    }
  };

  const handlePageClick = (page: number | string) => {
    if (typeof page === "number" && page !== currentPage && !isLoading) {
      onPageChange(page);
    }
  };

  if (totalPages <= 1) {
    return (
      <div className="flex items-center justify-center py-4 text-xs font-mono text-tactical-muted">
        SHOWING {totalResults} {totalResults === 1 ? "RESULT" : "RESULTS"}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 py-6">
      <div className="text-xs font-mono text-tactical-muted">
        SHOWING <span className="font-semibold text-tactical-text">{startResult}</span> TO{" "}
        <span className="font-semibold text-tactical-text">{endResult}</span> OF{" "}
        <span className="font-semibold text-tactical-text">{totalResults}</span> {totalResults === 1 ? 'RESULT' : 'RESULTS'}
      </div>

      <nav className="flex items-center gap-2" aria-label="Pagination">
        <button
          onClick={handlePrevious}
          disabled={currentPage === 1 || isLoading}
          className="tactical-btn-primary tactical-focus-ring inline-flex items-center px-3 py-2 text-xs uppercase disabled:opacity-30"
          aria-label="Previous page"
        >
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          <span className="ml-1 hidden sm:inline">Previous</span>
        </button>

        <div className="flex items-center gap-1">
          {getPageNumbers().map((page, index) => {
            if (page === "...") {
              return (
                <span
                  key={`ellipsis-${index}`}
                  className="px-3 py-2 text-tactical-muted font-mono"
                >
                  ...
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
                className={`tactical-focus-ring min-w-[2.5rem] rounded-tactical px-3 py-2 text-xs font-mono font-semibold transition-all duration-tactical ease-tactical ${
                  isCurrent
                    ? "bg-tactical-accent border border-tactical-accent text-tactical-bg"
                    : "border border-tactical-border bg-tactical-elevated text-tactical-text hover:border-tactical-border-emphasis disabled:cursor-not-allowed disabled:opacity-30"
                }`}
                aria-label={`Go to page ${pageNum}`}
                aria-current={isCurrent ? "page" : undefined}
              >
                {pageNum}
              </button>
            );
          })}
        </div>

        <button
          onClick={handleNext}
          disabled={currentPage === totalPages || isLoading}
          className="tactical-btn-primary tactical-focus-ring inline-flex items-center px-3 py-2 text-xs uppercase disabled:opacity-30"
          aria-label="Next page"
        >
          <span className="mr-1 hidden sm:inline">Next</span>
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
      </nav>

      {isLoading && (
        <div className="text-xs font-mono text-tactical-muted">
          LOADING...
        </div>
      )}
    </div>
  );
}


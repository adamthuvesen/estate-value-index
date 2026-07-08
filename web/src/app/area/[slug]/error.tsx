"use client";

import Link from "next/link";

/** Unexpected-error boundary for the area report. Known states (missing data,
 *  unknown slug) are handled in the page itself; this is the genuine-crash path. */
export default function AreaError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
      <div className="mx-auto mt-4 max-w-xl rounded-2xl border border-ledger-border bg-ledger-surface px-6 py-12 text-center shadow-elev-1">
        <p className="eyebrow text-val-high">Something went wrong</p>
        <h1 className="mt-3 font-display text-title text-ledger-text">
          The area report could not be loaded
        </h1>
        <p className="mt-3 text-[14px] text-ledger-muted">
          An unexpected error occurred while preparing the statistics.
          {error.digest && <span className="num"> (ref {error.digest})</span>}
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <button onClick={reset} className="ledger-btn-primary focus-ring text-[13px]">
            Try again
          </button>
          <Link href="/areas" className="ledger-btn focus-ring text-[13px]">
            Back to all areas
          </Link>
        </div>
      </div>
    </div>
  );
}

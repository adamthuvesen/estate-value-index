import { Skeleton } from "@/components/ui/skeleton";

/** Editorial skeleton — replaces the old full-page spinner. The single data
 *  source resolves atomically, so one route-level skeleton beats per-section
 *  Suspense theater. */
export default function AreaLoading() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14" aria-busy>
      {/* Breadcrumb */}
      <Skeleton className="mb-8 h-4 w-48" />

      {/* Hero */}
      <div className="mb-8 flex flex-col items-center gap-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-10 w-72 max-w-full" />
        <Skeleton className="h-3 w-40" />
      </div>

      {/* Room filter strip */}
      <div className="mx-auto mb-6 max-w-3xl">
        <Skeleton className="h-14 w-full rounded-xl" />
      </div>

      {/* KPI row */}
      <div className="mx-auto mb-6 max-w-3xl">
        <Skeleton className="h-28 w-full rounded-2xl" />
      </div>

      {/* Figure-frame stubs */}
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="mb-6 border-t-2 border-ledger-border pt-4">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="mt-2 h-6 w-52" />
          <Skeleton className="mt-4 h-56 w-full rounded-xl" />
        </div>
      ))}
    </div>
  );
}

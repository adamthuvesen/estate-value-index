import { cn } from "@/lib/cn";

/** A single shimmering placeholder block. `animate-pulse` is stilled by the
 *  global reduced-motion rule. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-sm bg-ledger-elevated", className)}
      aria-hidden
    />
  );
}

/** Placeholder for a property/area card while data loads. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("ledger-card flex flex-col gap-3 p-4", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
        <Skeleton className="h-9 w-9 rounded-lg" />
      </div>
      <Skeleton className="h-16 w-full rounded-lg" />
      <div className="grid grid-cols-4 gap-3">
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
      </div>
    </div>
  );
}

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface StatBarProps {
  children: ReactNode;
  className?: string;
}

/** Row of hairline-divided figures — the shared page/area hero stat strip. */
export function StatBar({ children, className }: StatBarProps) {
  return (
    <dl className={cn("flex flex-wrap gap-x-8 gap-y-5", className)}>{children}</dl>
  );
}

interface StatProps {
  value: ReactNode;
  label: ReactNode;
  small?: boolean;
  className?: string;
}

export function Stat({ value, label, small = false, className }: StatProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 border-l border-ledger-border pl-4 first:border-l-0 first:pl-0",
        className,
      )}
    >
      <dt className="eyebrow text-ledger-dimmed">{label}</dt>
      <dd
        className={cn(
          "num font-display font-semibold tracking-tight text-ledger-text",
          small ? "text-title" : "text-headline",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

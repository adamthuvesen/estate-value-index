"use client";

import { cn } from "@/lib/cn";

interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/** Compact segmented toggle for a FigureFrame's actions slot. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="inline-flex items-center rounded-pill border border-ledger-border bg-ledger-elevated p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "focus-ring rounded-pill px-2.5 py-1 text-[12px] font-medium transition-colors",
              active
                ? "bg-ledger-text text-white"
                : "text-ledger-muted hover:text-ledger-text",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

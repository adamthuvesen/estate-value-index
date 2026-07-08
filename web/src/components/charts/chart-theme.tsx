"use client";

import { useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import type { ValueTier } from "@/lib/value-finder-types";

/* ------------------------------------------------------------------ *
 * Tokens → chart. Every color references a CSS variable so charts
 * track the ledger palette instead of carrying hardcoded hexes.
 * ------------------------------------------------------------------ */

export const chartColors = {
  ink: "var(--color-ledger-text)",
  accent: "var(--color-ledger-accent)",
  grid: "var(--color-ledger-border)",
  axisLine: "var(--color-ledger-border-emphasis)",
  tick: "var(--color-ledger-muted)",
  surface: "var(--color-ledger-surface)",
} as const;

/** Spread into any Recharts `<XAxis/>` / `<YAxis/>` — muted ticks, no rules. */
export const axisDefaults = {
  stroke: chartColors.axisLine,
  tick: { fill: chartColors.tick, fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

/** Spread into `<CartesianGrid/>` — faint horizontal hairlines only. */
export const gridDefaults = {
  stroke: chartColors.grid,
  strokeDasharray: "3 3",
  vertical: false,
} as const;

export const chartPalette = {
  ink: chartColors.ink,
  accent: chartColors.accent,
  valTiers: {
    "Excellent Value": "var(--color-val-exc)",
    "Great Value": "var(--color-val-great)",
    "Good Value": "var(--color-val-good)",
    "Fair Value": "var(--color-val-fair)",
    Overvalued: "var(--color-val-over)",
    "Highly Overvalued": "var(--color-val-high)",
  } satisfies Record<ValueTier, string>,
} as const;

/* ------------------------------------------------------------------ *
 * Reduced-motion hook → feed to Recharts `isAnimationActive`.
 * ------------------------------------------------------------------ */

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false,
  );
}

/* ------------------------------------------------------------------ *
 * Shared tooltip. Pass as `<Tooltip content={<ChartTooltip .../>} />`;
 * Recharts injects `active` / `payload` / `label` at render.
 * ------------------------------------------------------------------ */

interface TooltipEntry {
  name?: string | number;
  value?: string | number;
  color?: string;
  dataKey?: string | number;
  payload?: Record<string, unknown>;
}

interface ChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: TooltipEntry[];
  /** Format a value cell. Returns `[value]` or `[value, name]`. */
  formatter?: (
    value: string | number,
    name: string | number | undefined,
    entry: TooltipEntry,
  ) => ReactNode | [ReactNode, ReactNode];
  labelFormatter?: (label: string | number | undefined) => ReactNode;
  /** Draw the series color swatch beside each row (default true). */
  indicator?: boolean;
}

export function ChartTooltip({
  active,
  label,
  payload,
  formatter,
  labelFormatter,
  indicator = true,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-md border border-ledger-border bg-ledger-surface px-3 py-2 shadow-elev-2">
      {label !== undefined && (
        <p className="mb-1 text-[12px] font-semibold text-ledger-muted">
          {labelFormatter ? labelFormatter(label) : label}
        </p>
      )}
      <ul className="space-y-0.5">
        {payload.map((entry, i) => {
          const rawValue = entry.value ?? "";
          const formatted = formatter
            ? formatter(rawValue, entry.name, entry)
            : rawValue;
          const [valueNode, nameNode] = Array.isArray(formatted)
            ? formatted
            : [formatted, entry.name];
          return (
            <li key={i} className="flex items-center gap-2 text-[13px]">
              {indicator && (
                <span
                  className="h-2 w-2 shrink-0 rounded-[2px]"
                  style={{ backgroundColor: entry.color ?? chartColors.ink }}
                  aria-hidden
                />
              )}
              {nameNode !== undefined && nameNode !== "" && (
                <span className="text-ledger-muted">{nameNode}</span>
              )}
              <span className="num ml-auto font-medium text-ledger-text">
                {valueNode}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Shared empty-state for a chart slot.
 * ------------------------------------------------------------------ */

export function ChartEmpty({
  message = "Not enough data to plot.",
  height = 210,
}: {
  message?: string;
  height?: number;
}) {
  return (
    <div
      className="flex items-center justify-center rounded-md border border-dashed border-ledger-border bg-ledger-elevated px-6 text-center"
      style={{ height }}
    >
      <p className="text-[13px] text-ledger-muted">{message}</p>
    </div>
  );
}

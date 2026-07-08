import type { ValueTier } from "@/lib/value-finder-types";

/**
 * Display labels for an area's `price_tier`. Single source consumed by the
 * areas register, the area detail page, and the similar-areas cards so a tier
 * rename can't drift between pages.
 */
export const PRICE_TIER_LABEL: Record<string, string> = {
  premium: "Premium",
  upper: "Upper",
  medium: "Medium",
  budget: "Budget",
};

/**
 * Tailwind class bundles for a property's value tier. Each field names the
 * intent — `dot`/`text` for inline labels, `chip` for the score badge,
 * `gauge` for the fair-value bar fill.
 */
export type TierStyle = {
  label: string;
  dot: string;
  text: string;
  chip: string;
  gauge: string;
};

export const VALUE_TIER_STYLES: Record<ValueTier, TierStyle> = {
  "Excellent Value": {
    label: "Excellent value",
    dot: "bg-val-exc",
    text: "text-val-exc",
    chip: "bg-val-exc-tint text-val-exc border-val-exc-line",
    gauge: "bg-val-exc",
  },
  "Great Value": {
    label: "Great value",
    dot: "bg-val-great",
    text: "text-val-great",
    chip: "bg-val-exc-tint text-val-great border-val-exc-line",
    gauge: "bg-val-great",
  },
  "Good Value": {
    label: "Good value",
    dot: "bg-val-good",
    text: "text-val-good",
    chip: "bg-val-fair-tint text-val-good border-ledger-border",
    gauge: "bg-val-good",
  },
  "Fair Value": {
    label: "Fair value",
    dot: "bg-val-fair",
    text: "text-val-fair",
    chip: "bg-val-fair-tint text-val-fair border-ledger-border",
    gauge: "bg-val-fair",
  },
  Overvalued: {
    label: "Overvalued",
    dot: "bg-val-over",
    text: "text-val-over",
    chip: "bg-val-over-tint text-val-over border-val-over-line",
    gauge: "bg-val-over",
  },
  "Highly Overvalued": {
    label: "Highly overvalued",
    dot: "bg-val-high",
    text: "text-val-high",
    chip: "bg-val-high-tint text-val-high border-val-high-line",
    gauge: "bg-val-high",
  },
};

export const FALLBACK_TIER: TierStyle = VALUE_TIER_STYLES["Fair Value"];

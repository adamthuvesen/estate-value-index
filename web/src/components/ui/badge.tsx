import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { PRICE_TIER_LABEL } from "@/lib/tiers";

export type BadgeVariant = "neutral" | "accent" | "tint";

const BASE =
  "inline-flex items-center justify-center gap-1 rounded-pill border " +
  "px-2.5 py-0.5 text-[11px] font-semibold tracking-eyebrow";

const VARIANTS: Record<BadgeVariant, string> = {
  neutral: "border-ledger-border bg-ledger-surface text-ledger-muted",
  accent: "border-transparent bg-ledger-accent text-white",
  tint: "border-ledger-accent/20 bg-ledger-accent-tint text-ledger-accent",
};

interface BadgeProps {
  variant?: BadgeVariant;
  className?: string;
  children: ReactNode;
}

export function Badge({ variant = "neutral", className, children }: BadgeProps) {
  return <span className={cn(BASE, VARIANTS[variant], className)}>{children}</span>;
}

/** Area price-tier chip (premium · upper · medium · budget). */
export function TierChip({ tier, className }: { tier: string; className?: string }) {
  return (
    <Badge variant="neutral" className={cn("uppercase", className)}>
      {PRICE_TIER_LABEL[tier] ?? tier}
    </Badge>
  );
}

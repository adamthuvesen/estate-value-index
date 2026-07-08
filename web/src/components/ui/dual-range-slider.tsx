"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";

interface DualRangeSliderProps {
  min: number;
  max: number;
  step?: number;
  /** Controlled [low, high] pair. */
  value: [number, number];
  /** Fires on every drag frame with the live pair (local state). */
  onChange?: (value: [number, number]) => void;
  /** Fires once on release — the moment to push URL / expensive state. */
  onCommit?: (value: [number, number]) => void;
  ariaLabel?: [string, string];
  className?: string;
}

function pct(value: number, min: number, max: number): number {
  if (max <= min) return 0;
  return ((value - min) / (max - min)) * 100;
}

export function DualRangeSlider({
  min,
  max,
  step = 1,
  value,
  onChange,
  onCommit,
  ariaLabel = ["Minimum", "Maximum"],
  className,
}: DualRangeSliderProps) {
  const [low, setLow] = useState(value[0]);
  const [high, setHigh] = useState(value[1]);

  // Re-sync when the parent-controlled pair changes (e.g. URL navigation).
  // Adjusting state during render off a tracked signature is React's
  // recommended alternative to a setState-in-effect resync.
  const signature = `${value[0]}:${value[1]}`;
  const [prevSignature, setPrevSignature] = useState(signature);
  if (signature !== prevSignature) {
    setPrevSignature(signature);
    setLow(value[0]);
    setHigh(value[1]);
  }

  const commit = (next: [number, number]) => onCommit?.(next);

  const handleLow = (raw: number) => {
    const next = Math.min(raw, high);
    setLow(next);
    onChange?.([next, high]);
  };

  const handleHigh = (raw: number) => {
    const next = Math.max(raw, low);
    setHigh(next);
    onChange?.([low, next]);
  };

  const leftPct = pct(low, min, max);
  const rightPct = 100 - pct(high, min, max);

  // Keep the lower thumb grabbable once both thumbs sit in the top half.
  const lowOnTop = low > max - (max - min) / 2;

  return (
    <div className={cn("range-dual", className)}>
      <span className="range-dual__track" aria-hidden />
      <span
        className="range-dual__fill"
        style={{ left: `${leftPct}%`, right: `${rightPct}%` }}
        aria-hidden
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={low}
        aria-label={ariaLabel[0]}
        style={{ zIndex: lowOnTop ? 4 : 3 }}
        onChange={(e) => handleLow(Number(e.target.value))}
        onMouseUp={() => commit([low, high])}
        onTouchEnd={() => commit([low, high])}
        onKeyUp={() => commit([low, high])}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={high}
        aria-label={ariaLabel[1]}
        style={{ zIndex: 3 }}
        onChange={(e) => handleHigh(Number(e.target.value))}
        onMouseUp={() => commit([low, high])}
        onTouchEnd={() => commit([low, high])}
        onKeyUp={() => commit([low, high])}
      />
    </div>
  );
}

"use client";

import { useRef, useState } from "react";
import type { Histogram } from "@/lib/overall-statistics-types";
import { binIndexForValue, histogramBars, maxCount } from "@/lib/histogram";
import { usePrefersReducedMotion } from "@/components/charts/chart-theme";
import { formatNumber } from "@/lib/format";

interface BarcodeStripProps {
  strip: Histogram;
  /** City-wide median kr/m² — annotated on the strip. */
  medianPerSqm: number;
}

const VIEW_H = 100;
const BASE_TICK = 7;
const GROW = 86;

/**
 * The page's signature: the 200-bin kr/m² distribution drawn as a single dense
 * line of hairline ticks whose height and opacity encode each bin's count.
 * Hovering reads out the kr/m² band and sale count under the cursor.
 */
export function BarcodeStrip({ strip, medianPerSqm }: BarcodeStripProps) {
  const reduce = usePrefersReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const bars = histogramBars(strip);
  const nbins = bars.length;
  const peak = maxCount(strip) || 1;
  const medianBin = binIndexForValue(strip, medianPerSqm);

  const handleMove = (clientX: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const fraction = (clientX - rect.left) / rect.width;
    const idx = Math.max(0, Math.min(nbins - 1, Math.floor(fraction * nbins)));
    setHover(idx);
  };

  const active = hover !== null ? bars[hover] : null;
  const hoverLeftPct = active ? ((active.index + 0.5) / nbins) * 100 : 0;

  return (
    <figure className="mt-10">
      <figcaption className="mb-3 flex items-baseline justify-between gap-4">
        <p className="eyebrow text-ledger-accent">The market on one line</p>
        <p className="text-caption text-ledger-dimmed">
          Every price per m², {formatNumber(strip.sample_size)} sales
        </p>
      </figcaption>

      <div
        ref={containerRef}
        className="relative w-full cursor-crosshair select-none"
        onMouseMove={(e) => handleMove(e.clientX)}
        onMouseLeave={() => setHover(null)}
        onTouchStart={(e) => handleMove(e.touches[0].clientX)}
        onTouchMove={(e) => handleMove(e.touches[0].clientX)}
        onTouchEnd={() => setHover(null)}
        role="img"
        aria-label={`Distribution of price per m² across ${formatNumber(
          strip.sample_size,
        )} sales, from ${formatNumber(strip.min)} to ${formatNumber(
          strip.max,
        )} kr per m². Median ${formatNumber(medianPerSqm)} kr per m².`}
      >
        <svg
          viewBox={`0 0 ${nbins} ${VIEW_H}`}
          preserveAspectRatio="none"
          className="block h-[132px] w-full"
        >
          {/* Median guide */}
          <line
            x1={medianBin + 0.5}
            x2={medianBin + 0.5}
            y1={0}
            y2={VIEW_H}
            stroke="var(--color-ledger-accent)"
            strokeWidth={0.35}
            strokeDasharray="2 2"
            opacity={0.55}
            vectorEffect="non-scaling-stroke"
          />
          {bars.map((bar) => {
            const ratio = bar.count / peak;
            const h = BASE_TICK + ratio * GROW;
            const isHover = hover === bar.index;
            const baseOpacity = 0.22 + ratio * 0.7;
            return (
              <rect
                key={bar.index}
                x={bar.index + 0.2}
                width={0.6}
                y={VIEW_H - h}
                height={h}
                fill={isHover ? "var(--color-ledger-accent)" : "var(--color-ledger-text)"}
                opacity={isHover ? 1 : baseOpacity}
                style={
                  reduce
                    ? undefined
                    : {
                        transformBox: "fill-box",
                        transformOrigin: "bottom",
                        animation: `barcode-grow 620ms cubic-bezier(0.22,0.61,0.36,1) ${
                          (bar.index / nbins) * 260
                        }ms both`,
                      }
                }
              />
            );
          })}
        </svg>

        {/* Hover guide + readout */}
        {active && (
          <div
            className="pointer-events-none absolute top-0 z-10 -translate-x-1/2"
            style={{ left: `${hoverLeftPct}%` }}
          >
            <div className="whitespace-nowrap rounded-md border border-ledger-border bg-ledger-surface px-2.5 py-1.5 text-center shadow-elev-2">
              <span className="num block text-body-sm font-semibold text-ledger-text">
                {formatNumber(active.center)} kr/m²
              </span>
              <span className="num block text-caption text-ledger-muted">
                {formatNumber(active.count)} {active.count === 1 ? "sale" : "sales"}
              </span>
            </div>
          </div>
        )}

        {/* Baseline */}
        <div className="h-px w-full bg-ledger-border-emphasis" aria-hidden />
      </div>

      {/* Min / median / max labels */}
      <div className="relative mt-2 h-8 text-caption">
        <StripLabel align="left" caption="min" value={strip.min} />
        <StripLabel
          leftPct={((medianBin + 0.5) / nbins) * 100}
          caption="median"
          value={medianPerSqm}
          accent
        />
        <StripLabel align="right" caption="max" value={strip.max} />
      </div>
    </figure>
  );
}

function StripLabel({
  align,
  leftPct,
  caption,
  value,
  accent = false,
}: {
  align?: "left" | "right";
  leftPct?: number;
  caption: string;
  value: number;
  accent?: boolean;
}) {
  const positional =
    align === "left"
      ? { left: 0 }
      : align === "right"
        ? { right: 0 }
        : { left: `${leftPct}%`, transform: "translateX(-50%)" };

  return (
    <div className="absolute top-0 flex flex-col leading-tight" style={positional}>
      <span
        className={`num text-[13px] font-semibold ${
          accent ? "text-ledger-accent" : "text-ledger-text"
        }`}
      >
        {formatNumber(value)}
      </span>
      <span className="eyebrow text-ledger-dimmed">{caption}</span>
    </div>
  );
}

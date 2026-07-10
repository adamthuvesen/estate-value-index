import type { Histogram } from "@/lib/overall-statistics-types";

export interface HistogramBar {
  /** Bin index. */
  index: number;
  /** Left edge of the bin. */
  start: number;
  /** Right edge of the bin. */
  end: number;
  /** Bin midpoint — the x value used to place reference lines. */
  center: number;
  count: number;
}

/**
 * Expand a pre-binned histogram into one row per bin with resolved edges.
 * Pure and side-effect free so chart components stay declarative.
 */
export function histogramBars(hist: Histogram): HistogramBar[] {
  return hist.counts.map((count, index) => {
    const start = hist.min + index * hist.bin_width;
    return {
      index,
      start,
      end: start + hist.bin_width,
      center: start + hist.bin_width / 2,
      count,
    };
  });
}

/** Bin index that a value falls into, clamped to the histogram's range. */
export function binIndexForValue(hist: Histogram, value: number): number {
  if (hist.bin_width <= 0) return 0;
  const raw = Math.floor((value - hist.min) / hist.bin_width);
  return Math.max(0, Math.min(hist.counts.length - 1, raw));
}

/** Largest bin count — for opacity/height scaling of the barcode strip. */
export function maxCount(hist: Histogram): number {
  return hist.counts.reduce((m, c) => (c > m ? c : m), 0);
}

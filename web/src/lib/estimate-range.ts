import { formatNumber } from "./format";

export interface EstimateRange {
  /** Model estimate rounded to the nearest 100k — never shown directly in the UI. */
  center: number;
  min: number;
  max: number;
  /** Half-width of the window (±). */
  halfWidth: number;
}

const STEP = 100_000;

/**
 * The UI shows a value window, not the raw model output — a point estimate
 * like 11 981 389 kr overstates the model's precision. Round the estimate to
 * the nearest 100k and use a simple absolute window: ±100k below 6M, ±200k
 * from 6M through 12M, and ±300k above 12M.
 */
export function estimateRange(predicted: number): EstimateRange {
  const center = Math.round(predicted / STEP) * STEP;
  const halfWidth = center > 12_000_000
    ? 3 * STEP
    : center >= 6_000_000
      ? 2 * STEP
      : STEP;
  return { center, min: center - halfWidth, max: center + halfWidth, halfWidth };
}

export function formatEstimateRange(range: EstimateRange): string {
  return `${formatNumber(range.min)} – ${formatNumber(range.max)} kr`;
}

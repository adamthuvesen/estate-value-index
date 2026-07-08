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
 * the nearest 100k and open a ±100k window (±200k from 6M kr, where absolute
 * spreads are larger).
 */
export function estimateRange(predicted: number): EstimateRange {
  const center = Math.round(predicted / STEP) * STEP;
  const halfWidth = center >= 6_000_000 ? 2 * STEP : STEP;
  return { center, min: center - halfWidth, max: center + halfWidth, halfWidth };
}

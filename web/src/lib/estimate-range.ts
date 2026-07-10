import { formatNumber } from "./format";

export interface EstimateRange {
  /** Model estimate rounded to the nearest 100k — never shown directly in the UI. */
  center: number;
  min: number;
  max: number;
}

export interface BucketFactor {
  /** q35 of actual/predicted for the bucket — the low edge multiplier. */
  lower: number;
  /** q65 of actual/predicted for the bucket — the high edge multiplier. */
  upper: number;
}

export interface EstimateRangeFactors {
  /** Lower price edge of each bucket, ascending; buckets[i] covers [edges[i], edges[i+1]). */
  edges: number[];
  /** One factor pair per bucket; the final bucket is open-ended above. */
  buckets: BucketFactor[];
}

const STEP = 100_000;

/**
 * Empirical q35/q65 factors of actual/predicted per predicted-price bucket,
 * measured on the most recent 3 months of the temporal holdout (eval date
 * 2026-07-09, no_list_price model). This 30% interval is deliberately tight and
 * the bands it yields are asymmetric by design. Used as the fallback until a
 * fresh training run carries `estimate_range_factors` in the model metrics
 * artifact — production models predate that block.
 * Source: scratchpad/estimate_range_eval.json (ratios_by_bucket q35/q65).
 */
export const DEFAULT_ESTIMATE_RANGE_FACTORS: EstimateRangeFactors = {
  edges: [3_000_000, 4_000_000, 5_000_000, 6_000_000, 8_000_000, 10_000_000, 13_000_000],
  buckets: [
    { lower: 0.9403, upper: 0.9974 },
    { lower: 0.9671, upper: 1.0352 },
    { lower: 0.9629, upper: 1.0433 },
    { lower: 0.9938, upper: 1.0792 },
    { lower: 0.9956, upper: 1.0791 },
    { lower: 0.9948, upper: 1.0771 },
    { lower: 0.9672, upper: 1.0583 },
  ],
};

function lookupBucket(predicted: number, factors: EstimateRangeFactors): BucketFactor {
  const { edges, buckets } = factors;
  // Clamp below the first edge to the first bucket, at/above the last to the last.
  if (predicted >= edges[edges.length - 1]) {
    return buckets[buckets.length - 1];
  }
  for (let i = 0; i < edges.length - 1; i += 1) {
    if (predicted < edges[i + 1]) {
      return buckets[i];
    }
  }
  return buckets[0];
}

/**
 * The UI shows a value window, not the raw model output — a point estimate like
 * 11 981 389 kr overstates the model's precision. The window is a per-bucket
 * empirical interval: low = floor(predicted·q35), high = ceil(predicted·q65),
 * each rounded outward to whole 100k. `center` (nearest 100k) drives value
 * comparisons but is never displayed on its own.
 */
export function estimateRange(
  predicted: number,
  factors: EstimateRangeFactors = DEFAULT_ESTIMATE_RANGE_FACTORS,
): EstimateRange {
  const center = Math.round(predicted / STEP) * STEP;
  const { lower, upper } = lookupBucket(predicted, factors);
  const min = Math.floor((predicted * lower) / STEP) * STEP;
  const max = Math.ceil((predicted * upper) / STEP) * STEP;
  return { center, min, max };
}

export function formatEstimateRange(range: EstimateRange): string {
  return `${formatNumber(range.min)} – ${formatNumber(range.max)} kr`;
}

interface ArtifactBucket {
  lower_edge: number | null;
  upper_edge: number | null;
  lower: number;
  upper: number;
}

/**
 * Convert the `estimate_range_factors` block from a model metrics artifact into
 * the shape `estimateRange` consumes. Returns null on any malformed input so
 * callers fall back to {@link DEFAULT_ESTIMATE_RANGE_FACTORS}.
 */
export function estimateRangeFactorsFromArtifact(raw: unknown): EstimateRangeFactors | null {
  if (typeof raw !== "object" || raw === null) return null;
  const rawBuckets = (raw as { buckets?: unknown }).buckets;
  if (!Array.isArray(rawBuckets) || rawBuckets.length === 0) return null;

  const edges: number[] = [];
  const buckets: BucketFactor[] = [];
  for (const entry of rawBuckets as ArtifactBucket[]) {
    if (
      typeof entry?.lower_edge !== "number" ||
      typeof entry?.lower !== "number" ||
      typeof entry?.upper !== "number" ||
      !Number.isFinite(entry.lower) ||
      !Number.isFinite(entry.upper)
    ) {
      return null;
    }
    // Edges must be strictly ascending for the bucket lookup to be well-defined.
    if (edges.length > 0 && entry.lower_edge <= edges[edges.length - 1]) return null;
    edges.push(entry.lower_edge);
    buckets.push({ lower: entry.lower, upper: entry.upper });
  }

  return { edges, buckets };
}

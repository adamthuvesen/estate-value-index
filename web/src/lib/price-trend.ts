import type { AreaOverviewStats } from "@/lib/area-types";

export type PriceUnit = "per_sqm" | "total";

type MonthlyPrices = NonNullable<AreaOverviewStats["monthly_prices"]>;

/** The overview fields the monthly series is built from. */
export interface MonthlySeriesSource {
  monthly_prices?: MonthlyPrices;
  median_price_3m: number | null;
  median_price_6m: number | null;
  median_price_12m: number | null;
}

export interface MonthlyPoint {
  /** Short month name, e.g. "Jan". */
  month: string;
  /** 12 (oldest) … 1 (last month). */
  monthsAgo: number;
  /** Human label, e.g. "12mo ago" / "Last month". */
  label: string;
  /** Value in the resolved unit, or null when there is no real datapoint (gaps preserved). */
  value: number | null;
  /** True only for a real monthly datapoint — never a fill or a median. */
  isReal: boolean;
}

export interface MedianPoint {
  key: "3m" | "6m" | "12m";
  monthsAgo: number;
  label: string;
  value: number | null;
}

export type PriceTrendMode = "line" | "medians" | "empty";

export interface MonthlySeries {
  points: MonthlyPoint[];
  medians: MedianPoint[];
  realCount: number;
  mode: PriceTrendMode;
  /** Resolved unit — falls back to "total" when per-m² is requested without a valid living area. */
  unit: PriceUnit;
}

export interface BuildMonthlySeriesOptions {
  /** Requested unit; defaults to "total". */
  unit?: PriceUnit;
  /** Average living area (m²), required to render per-m². */
  avgLivingArea?: number | null;
  /** Reference "now" for month labels; defaults to the current date. */
  now?: Date;
}

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function isReal(raw: number | null | undefined): raw is number {
  return typeof raw === "number" && raw > 0;
}

/**
 * Build a 12-month price series with gaps preserved — no forward/back fill.
 *
 * The old chart fabricated a continuous line by filling missing months; this
 * keeps nulls so the chart can honestly break the line. `mode` tells the
 * consumer what to render:
 * - "line"    — ≥3 real monthly points
 * - "medians" — <3 real points but 3/6/12-month medians exist (dumbbell fallback)
 * - "empty"   — no real points and no medians
 */
export function buildMonthlySeries(
  source: MonthlySeriesSource,
  options: BuildMonthlySeriesOptions = {},
): MonthlySeries {
  const { unit = "total", avgLivingArea = null, now = new Date() } = options;

  const perSqm = unit === "per_sqm" && typeof avgLivingArea === "number" && avgLivingArea > 0;
  const resolvedUnit: PriceUnit = perSqm ? "per_sqm" : "total";

  const convert = (raw: number): number =>
    perSqm ? Math.round(raw / (avgLivingArea as number)) : raw;

  const currentMonth = now.getMonth();
  const monthly = source.monthly_prices;

  const points: MonthlyPoint[] = [];
  for (let i = 12; i >= 1; i--) {
    const raw = monthly?.[`month_${i}` as keyof MonthlyPrices] ?? null;
    const real = isReal(raw);
    points.push({
      month: MONTH_NAMES[(currentMonth - i + 12) % 12],
      monthsAgo: i,
      label: i === 1 ? "Last month" : `${i}mo ago`,
      value: real ? convert(raw) : null,
      isReal: real,
    });
  }

  const medianSources: Array<Omit<MedianPoint, "value"> & { raw: number | null }> = [
    { key: "3m", monthsAgo: 3, label: "3-mo median", raw: source.median_price_3m },
    { key: "6m", monthsAgo: 6, label: "6-mo median", raw: source.median_price_6m },
    { key: "12m", monthsAgo: 12, label: "12-mo median", raw: source.median_price_12m },
  ];
  const medians: MedianPoint[] = medianSources.map(({ raw, ...rest }) => ({
    ...rest,
    value: raw !== null ? convert(raw) : null,
  }));

  const realCount = points.filter((p) => p.isReal).length;
  const hasMedians = medians.some((m) => m.value !== null);

  const mode: PriceTrendMode = realCount >= 3 ? "line" : hasMedians ? "medians" : "empty";

  return { points, medians, realCount, mode, unit: resolvedUnit };
}

/**
 * Trailing % change from the first to the last REAL point (fills ignored).
 * Returns null when fewer than 2 real points exist.
 */
export function computeTrailingChange(points: MonthlyPoint[]): number | null {
  const real = points.filter((p): p is MonthlyPoint & { value: number } => p.isReal && p.value !== null);
  if (real.length < 2) {
    return null;
  }
  const first = real[0].value;
  const last = real[real.length - 1].value;
  return ((last - first) / first) * 100;
}

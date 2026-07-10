/**
 * Shared display formatters for the web app.
 */

/**
 * Format a possibly-null number with fixed decimals, returning an em-dash for
 * nullish input. Use this for any API field that can be `null` (sparse areas
 * with low listing counts often return null for liquidity, value scores, etc.)
 * before passing through `.toFixed()`.
 */
export function formatNumberOrDash(
  value: number | null | undefined,
  decimals: number,
): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(decimals);
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return new Intl.NumberFormat("sv-SE").format(Math.round(value));
}

export function formatRawNumber(value: number): string {
  return new Intl.NumberFormat("sv-SE").format(value);
}

export function formatSek(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency: "SEK",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatSekPerSqm(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `${formatNumber(value)} kr/m²`;
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  return `${formatNumberOrDash(value, decimals)}%`;
}

/** Format a 0..1 fraction as a percentage string (multiplies by 100 first). */
export function formatSharePct(
  fraction: number | null | undefined,
  decimals = 0,
): string {
  if (fraction === null || fraction === undefined) return "—";
  return `${(fraction * 100).toFixed(decimals)}%`;
}

/** Signed percent with an explicit leading `+`/`−`, e.g. `+4.4%`. */
export function formatSignedPct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(decimals)}%`;
}

export function formatShortThousands(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

export function formatShortSek(value: number | null | undefined): string {
  if (value === null || value === undefined) return "N/A";
  return `${formatShortThousands(value)} kr`;
}

/**
 * Turn a lowercase area/municipality slug (e.g. `"bromma_alsten"`, sourced
 * from the dataset's ASCII-normalized area key) into a presentable label
 * (`"Bromma Alsten"`). Slugs never carry diacritics, so this can't recover
 * exact Swedish spelling — it's a display approximation, not a name lookup.
 */
export function titleCaseArea(value: string): string {
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

const MONTH_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "2024-03" → "Mar ’24". Falls back to the input if it isn't `YYYY-MM`. */
export function formatMonthShort(yearMonth: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(yearMonth);
  if (!match) return yearMonth;
  const month = MONTH_ABBR[Number(match[2]) - 1] ?? match[2];
  return `${month} ’${match[1].slice(2)}`;
}

/** Calendar-month index 1..12 → "Jan". */
export function formatMonthOfYear(month: number): string {
  return MONTH_ABBR[month - 1] ?? String(month);
}

export function formatDateSv(date: Date | string): string {
  const parsedDate = typeof date === "string" ? new Date(date) : date;
  return parsedDate.toLocaleDateString("sv-SE");
}

export const AREA_DATA_STALE_DAYS = 8;

export function getStaleInfo(
  generatedAtValue: string | null | undefined,
  thresholdDays = AREA_DATA_STALE_DAYS,
): { generatedAt: Date; ageDays: number; isStale: boolean } | null {
  if (!generatedAtValue) return null;

  const generatedAt = new Date(generatedAtValue);
  if (Number.isNaN(generatedAt.getTime())) return null;

  const ageDays = (Date.now() - generatedAt.getTime()) / (1000 * 60 * 60 * 24);
  return {
    generatedAt,
    ageDays,
    isStale: ageDays > thresholdDays,
  };
}

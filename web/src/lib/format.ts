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

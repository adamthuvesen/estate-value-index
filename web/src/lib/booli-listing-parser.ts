/**
 * Booli listing URL parsing and boolean coercion shared by the predictor's
 * fetch-listing and predict routes.
 * Boolean coercion matches `estate_value_index.ingestion.booli.normalization.to_bool`.
 */

export const LISTING_ID_PATTERNS = [/^\/(?:annons|bostad)\/(?:[^/]+\/)*?(\d+)\/?$/i];
export const LISTING_ID_QUERY_KEYS = ['booliid', 'listingid', 'objectid', 'id'];

const TRUTHY = new Set(['true', 't', 'yes', 'y', '1', 'ja']);
const FALSY = new Set(['false', 'f', 'no', 'n', '0', 'nej']);

/** Align with Python `to_bool` / `_coerce_nullable_bool` truth table. */
export function coerceBool(value: unknown): boolean | null {
  if (value == null) {
    return null;
  }
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
    return null;
  }
  if (typeof value === 'string') {
    const token = value.trim().toLowerCase();
    if (TRUTHY.has(token)) return true;
    if (FALSY.has(token)) return false;
    return null;
  }
  return null;
}

export function extractListingId(parsed: URL): string | null {
  for (const pattern of LISTING_ID_PATTERNS) {
    const match = parsed.pathname.match(pattern);
    if (match) {
      return match[1];
    }
  }
  for (const key of LISTING_ID_QUERY_KEYS) {
    const value = parsed.searchParams.get(key);
    if (value && /^\d+$/.test(value)) {
      return value;
    }
  }
  return null;
}

export type ParsedBooliListing = {
  listing_id: string;
  listing_price: number | null;
  living_area: number | null;
  rooms: number | null;
  monthly_fee: number | null;
  construction_year: number | null;
  days_on_market: number | null;
  property_type: string;
  municipality: string;
  area: string | null;
  floor: number | null;
  elevator: boolean | null;
  balcony: boolean | null;
  latitude?: number | null;
  longitude?: number | null;
  source_url: string;
};

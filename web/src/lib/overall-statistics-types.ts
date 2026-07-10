/**
 * Types for `data/derived/overall_statistics.json` — the city-wide statistical
 * report behind the `/stats` page. Mirrors the frozen data contract exactly
 * (snake_case, shares as 0..1 fractions, pre-binned histograms). Keep in sync
 * with the Python generator; do not add or drop keys without flagging it.
 */

/**
 * Pre-binned histogram. `counts[i]` covers `[min + i·bin_width, min + (i+1)·bin_width)`.
 * Percentiles are computed on the unclipped values; counts are binned over the
 * clipped `[min, max]` range. `sample_size` is the null-filtered, pre-clip count.
 */
export interface Histogram {
  min: number;
  max: number;
  bin_width: number;
  counts: number[];
  p1: number;
  p25: number;
  p50: number;
  p75: number;
  p99: number;
  sample_size: number;
}

export interface RecordSale {
  address: string;
  /** Normalized area key — same normalization as `area_statistics.json`. */
  area_name: string;
  display_name: string;
  /** "YYYY-MM-DD". */
  sold_date: string;
  /** Booli listing URL, or null. */
  url: string | null;
  living_area: number | null;
  rooms: number | null;
  sold_price: number;
}

export interface OverallStatisticsMetadata {
  /** "YYYY-MM-DD", latest sold_date. */
  generated_at: string;
  total_properties: number;
  /** Areas published in area_statistics.json (51), same filter logic. */
  total_areas: number;
  date_range: { start: string; end: string };
  data_sources: { raw_listings: string; value_analysis: string };
}

export interface OverallHero {
  total_sales: number;
  total_areas: number;
  median_sold_price: number;
  median_price_per_sqm: number;
  /** 200 bins over p0.5–p99.5 of price_per_sqm. */
  price_per_sqm_strip: Histogram;
}

export interface ListingVsSold {
  /** Rows with a listing_price (non-null, > 0). */
  sample_size: number;
  median_listing_price: number;
  median_sold_price: number;
  /** Median of (sold − list) / list × 100. */
  median_premium_pct: number;
  /** 0..1, sold > list. */
  share_over_ask: number;
  share_under_ask: number;
  share_at_ask: number;
}

export interface OverallPrices {
  sold_price_histogram: Histogram;
  price_per_sqm_histogram: Histogram;
  listing_vs_sold: ListingVsSold;
}

export interface MonthlyPricePoint {
  /** "YYYY-MM". */
  month: string;
  median_price_per_sqm: number;
  median_sold_price: number;
  sales_count: number;
  /** True only for the current (incomplete) month. */
  is_partial: boolean;
}

export interface SeasonalityPoint {
  /** 1..12. */
  month_of_year: number;
  median_price_per_sqm: number;
  /** Mean sales per occurrence of that calendar month. */
  avg_sales_count: number;
}

export interface OverallOverTime {
  monthly: MonthlyPricePoint[];
  seasonality: SeasonalityPoint[];
}

export interface AreaPremium {
  area_name: string;
  display_name: string;
  avg_premium_pct: number;
  median_premium_pct: number;
  sample_size: number;
}

export interface MonthlyOverUnder {
  month: string;
  share_over_ask: number;
  share_under_ask: number;
  share_at_ask: number;
  sample_size: number;
  is_partial: boolean;
}

export interface OverallBidding {
  sample_size: number;
  /** Values = (sold − list) / list × 100, clipped p1–p99. */
  premium_pct_histogram: Histogram;
  monthly_over_under: MonthlyOverUnder[];
  top_premium_areas: AreaPremium[];
  bottom_premium_areas: AreaPremium[];
}

export interface GeographyArea {
  area_name: string;
  display_name: string;
  median_price_per_sqm: number;
  median_sold_price: number;
  sales_count: number;
  /** 0..1, joined from value_analysis; null if unavailable. */
  undervalued_share: number | null;
}

export interface OverallGeography {
  areas: GeographyArea[];
}

/** Reused from area_statistics: keyed by room bucket ("1", "2", "3", "4+"). */
export interface PpsqmByRooms {
  [roomKey: string]: {
    median: number;
    mean: number;
    min: number;
    max: number;
    count: number;
  };
}

export interface PriceBySizeBucket {
  bucket: string;
  median_price: number;
  count: number;
}

export interface SizeDistribution {
  living_area: {
    median: number | null;
    mean: number | null;
    min: number | null;
    max: number | null;
  };
  room_distribution: Record<string, number>;
}

export interface PpsqmVsSizePoint {
  size_bucket: string;
  bucket_min: number;
  /** null for the open-ended top bucket. */
  bucket_max: number | null;
  median_price_per_sqm: number;
  sample_size: number;
}

export interface OverallSizeRooms {
  price_per_sqm_by_rooms: PpsqmByRooms;
  price_by_size: PriceBySizeBucket[];
  size_distribution: SizeDistribution;
  ppsqm_vs_size_curve: PpsqmVsSizePoint[];
}

export interface ConstructionEraPoint {
  era: string;
  count: number;
  /** 0..1. */
  share: number;
  median_price_per_sqm: number;
}

export interface AmenityEffect {
  /** Rows where the flag is confirmed (null/unknown excluded). */
  known_count: number;
  /**
   * 0..1 among known rows. In the production dataset the source only reports
   * the flag when the amenity is present, so this is 1.0 and the "without" arm
   * below is null — a price comparison isn't possible.
   */
  share_with: number;
  median_ppsqm_with: number;
  /** Null when the source never reports the amenity as absent. */
  median_ppsqm_without: number | null;
  /** (with − without) / without × 100. Null without a "without" arm. */
  naive_diff_pct: number | null;
  /** Median of per-area diffs; areas need ≥20 rows per arm. Null if none qualify. */
  within_area_diff_pct: number | null;
  within_area_sample_areas: number;
}

export interface FloorPoint {
  floor_bucket: string;
  median_price_per_sqm: number;
  sample_size: number;
}

export interface FeeBucketPoint {
  fee_bucket: string;
  median_sold_price: number;
  median_price_per_sqm: number;
  sample_size: number;
}

export interface OverallBuilding {
  construction_era: ConstructionEraPoint[];
  amenities: {
    balcony: AmenityEffect;
    elevator: AmenityEffect;
  };
  by_floor: FloorPoint[];
  monthly_fee: {
    /** monthly_fee / living_area, clipped p1–p99. */
    fee_per_sqm_histogram: Histogram;
    median_price_by_fee_bucket: FeeBucketPoint[];
  };
}

export interface TopStreet {
  street: string;
  sales_count: number;
  median_sold_price: number;
}

export interface OverallRecords {
  most_expensive: RecordSale;
  cheapest: RecordSale;
  highest_price_per_sqm: RecordSale & { price_per_sqm: number };
  fastest_sale: RecordSale & { days_on_market: number };
  biggest_bid_up: RecordSale & { premium_pct: number; listing_price: number };
  best_value:
    | (RecordSale & { prediction_delta_percentage: number; value_score: number })
    | null;
  top_streets: TopStreet[];
}

export interface OverallStatisticsData {
  metadata: OverallStatisticsMetadata;
  hero: OverallHero;
  prices: OverallPrices;
  over_time: OverallOverTime;
  bidding: OverallBidding;
  geography: OverallGeography;
  size_rooms: OverallSizeRooms;
  building: OverallBuilding;
  records: OverallRecords;
}

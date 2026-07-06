export interface ValueProperty {
  listing_id: string;
  url: string | null;
  address: string;
  area: string;
  municipality: string;
  living_area: number;
  rooms: number;
  property_type: string;
  construction_year: number | null;
  monthly_fee: number;
  floor: number | null;
  elevator: boolean | null;
  balcony: boolean | null;
  sold_price: number;
  predicted_price: number;
  prediction_delta_absolute: number;
  prediction_delta_percentage: number;
  is_undervalued: boolean;
  value_score: number;
  value_tier: ValueTier;
  sold_date: string;
  days_on_market: number | null;
  listing_price: number | null;
  price_per_sqm: number | null;
  latitude?: number | null;
  longitude?: number | null;
}

export type ValueTier =
  | "Excellent Value"
  | "Great Value"
  | "Good Value"
  | "Fair Value"
  | "Overvalued"
  | "Highly Overvalued";

/**
 * Canonical ordering for `ValueTier` (best to worst). Single source of truth
 * for the metadata route, the filters panel, and the distribution chart so a
 * tier rename can't drift between display and data.
 */
export const VALUE_TIERS: readonly ValueTier[] = [
  "Excellent Value",
  "Great Value",
  "Good Value",
  "Fair Value",
  "Overvalued",
  "Highly Overvalued",
] as const;

export interface ValueAnalysisMetadata {
  generated_at: string;
  model_type: string;
  model_path: string;
  data_source: string;
  filters: {
    only_undervalued: boolean;
    min_value_score: number | null;
  };
  thresholds?: {
    undervalue_threshold_pct: number;
    undervalue_threshold_abs: number;
  };
}

export interface ValueStatistics {
  total_properties: number;
  undervalued_count: number;
  overvalued_count: number;
  undervalued_percentage: number;
  value_score: {
    mean: number;
    median: number;
    min: number;
    max: number;
    std: number;
  };
  prediction_delta_absolute: {
    mean: number;
    median: number;
    min: number;
    max: number;
  };
  prediction_delta_percentage: {
    mean: number;
    median: number;
    min: number;
    max: number;
  };
  value_tier_distribution: Record<ValueTier, number>;
  area_statistics: {
    total_areas: number;
    top_undervalued_areas: Record<string, number>;
  };
  model_performance: {
    mae: number | null;
    rmse: number | null;
    mape: number | null;
    n_train: number | null;
    n_test: number | null;
  };
}

export interface ValueAnalysisData {
  metadata: ValueAnalysisMetadata;
  statistics: ValueStatistics;
  properties: ValueProperty[];
}

export type SortField =
  | "value_score"
  | "prediction_delta_percentage"
  | "prediction_delta_absolute"
  | "sold_date"
  | "sold_price"
  | "living_area";

export type SortOrder = "asc" | "desc";

export interface ValueFinderFilters {
  sort?: SortField;
  order?: SortOrder;
  limit?: number;
  offset?: number;

  // Property filters
  area?: string | string[];
  min_living_area?: number;
  max_living_area?: number;
  min_rooms?: number;
  max_rooms?: number;
  min_price?: number;
  max_price?: number;
  property_type?: string | string[];
  has_elevator?: boolean;
  has_balcony?: boolean;

  // Value filters
  min_value_score?: number;
  max_value_score?: number;
  value_tier?: ValueTier | ValueTier[];

  // Search
  search?: string;
}

export interface ValueFinderResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  filters_applied: Partial<ValueFinderFilters>;
  metadata: ValueAnalysisMetadata;
  properties: ValueProperty[];
}

export interface ValueFinderMetadataResponse {
  available_areas: string[];
  available_municipalities: string[];
  property_types: string[];
  value_tiers: ValueTier[];
  price_range: { min: number; max: number };
  living_area_range: { min: number; max: number };
  rooms_range: { min: number; max: number };
  value_score_range: { min: number; max: number };
  statistics: ValueStatistics;
  last_updated: string;
}

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface RangeFilter {
  min: number;
  max: number;
  step?: number;
}

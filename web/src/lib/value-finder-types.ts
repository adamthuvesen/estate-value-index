import type { ValueTier } from "./generated/api-types";

export type {
  ValueAnalysisData,
  ValueAnalysisMetadata,
  ValueProperty,
  ValueStatistics,
  ValueTier,
} from "./generated/api-types";
import type { ValueAnalysisMetadata, ValueProperty, ValueStatistics } from "./generated/api-types";

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

export interface ValueFinderFacetsResponse {
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

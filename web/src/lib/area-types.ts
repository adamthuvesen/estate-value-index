import type { AreaSizeAnalysis, PriceTier } from "./generated/api-types";

export type {
  AreaMarketDynamics,
  AreaOverviewStats,
  AreaPropertyCharacteristics,
  AreaSizeAnalysis,
  AreaStatistics,
  AreaStatisticsData,
  AreaStatisticsMetadata,
  AreaValueInsights,
  ConstructionEraDistribution,
  PriceBySizeBucket,
  PriceTier,
  RecentProperty,
  RoomFilteredStatistics,
  SizeDistribution,
} from "./generated/api-types";

export type PricePerSqmByRooms = AreaSizeAnalysis["price_per_sqm_by_rooms"];

/** Keys of `AreaStatistics.by_room_count`. */
export type RoomFilter = "all" | "1" | "2" | "3" | "4+";

/** Lightweight per-area summary used in the comparison table */
export interface AreaOverview {
  area_name: string;
  display_name: string;
  price_tier: PriceTier;
  avg_sold_price: number;
  avg_price_per_sqm: number | null;
  listing_count: number;
  inventory: number;
  median_price_3m: number | null;
  days_on_market_median: number;
  price_change_mean: number;
  volatility: number;
  undervalued_pct: number | null;
  has_limited_data: boolean;
  sample_size: number;
}

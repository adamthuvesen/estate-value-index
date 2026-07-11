export type PriceTier = "budget" | "medium" | "upper" | "premium";

export type RoomFilter = "all" | "1" | "2" | "3" | "4+";

export interface AreaStatisticsMetadata {
  generated_at: string;
  total_areas: number;
  total_properties: number;
  data_sources: {
    feature_context: string;
    value_analysis: string;
    raw_listings: string;
  };
}

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

export interface AreaOverviewStats {
  avg_listing_price: number;
  avg_sold_price: number;
  avg_price_per_sqm: number | null;
  listing_count: number;
  inventory: number;
  median_price_3m: number | null;
  median_price_6m: number | null;
  median_price_12m: number | null;
  monthly_prices?: {
    month_1?: number | null;
    month_2?: number | null;
    month_3?: number | null;
    month_4?: number | null;
    month_5?: number | null;
    month_6?: number | null;
    month_7?: number | null;
    month_8?: number | null;
    month_9?: number | null;
    month_10?: number | null;
    month_11?: number | null;
    month_12?: number | null;
  };
}

export interface AreaMarketDynamics {
  volatility: number;
  days_on_market_median: number;
  price_change_mean: number;
  sales_volume_3m: number;
  sales_volume_6m: number;
  sales_volume_12m: number;
  liquidity: number | null;
}

export interface AreaValueInsights {
  undervalued_count: number;
  undervalued_pct: number | null;
  avg_value_score: number | null;
  median_value_score: number | null;
  avg_prediction_delta: number;
  value_tier_distribution: Record<string, number>;
}

export interface PricePerSqmByRooms {
  [roomKey: string]: {
    median: number;
    mean: number;
    min: number;
    max: number;
    count: number;
  };
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

export interface PriceBySizeBucket {
  bucket: string;
  median_price: number;
  count: number;
}

export interface AreaSizeAnalysis {
  price_per_sqm_by_rooms: PricePerSqmByRooms;
  price_by_size: PriceBySizeBucket[];
  size_distribution: SizeDistribution;
}

export interface AreaPropertyCharacteristics {
  elevator_pct: number;
  balcony_pct: number;
}

export interface ConstructionEraDistribution {
  median_year: number | null;
  oldest: number | null;
  newest: number | null;
  era_distribution: Record<string, number>;
  avg_age: number | null;
}

export interface RecentProperty {
  listing_id: string;
  url: string | null;
  address: string;
  sold_price: number;
  sold_date: string;
  living_area: number;
  rooms: number;
  price_per_sqm: number | null;
}

export interface RoomFilteredStatistics {
  overview: Omit<AreaOverviewStats, 'monthly_prices'>;
  market_dynamics: AreaMarketDynamics;
  value_insights: AreaValueInsights;
  property_characteristics: AreaPropertyCharacteristics;
  construction_era: ConstructionEraDistribution;
  recent_properties: RecentProperty[];
  property_count: number;
}

/** Full per-area statistics, used by the area detail page */
export interface AreaStatistics {
  area_name: string;
  display_name: string;
  price_tier: PriceTier;
  overview: AreaOverviewStats;
  market_dynamics: AreaMarketDynamics;
  value_insights: AreaValueInsights;
  size_analysis: AreaSizeAnalysis;
  property_characteristics: AreaPropertyCharacteristics;
  construction_era: ConstructionEraDistribution;
  recent_properties: RecentProperty[];
  by_room_count?: Record<RoomFilter, RoomFilteredStatistics>;
  has_limited_data: boolean;
  sample_size: number;
}

export interface AreaStatisticsData {
  metadata: AreaStatisticsMetadata;
  areas: Record<string, AreaStatistics>;
}

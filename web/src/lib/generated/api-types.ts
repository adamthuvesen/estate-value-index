/* Generated from the Pydantic models by `just types` (scripts/export_web_schema.py). Do not edit. */

/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PriceTier".
 */
export type PriceTier = "budget" | "medium" | "upper" | "premium";
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueTier".
 */
export type ValueTier =
  "Excellent Value" | "Great Value" | "Good Value" | "Fair Value" | "Overvalued" | "Highly Overvalued";

export interface WebTypes {}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "Amenities".
 */
export interface Amenities {
  balcony: AmenityEffect;
  elevator: AmenityEffect;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AmenityEffect".
 */
export interface AmenityEffect {
  known_count: number;
  median_ppsqm_with: number;
  median_ppsqm_without: number | null;
  naive_diff_pct: number | null;
  share_with: number;
  within_area_diff_pct: number | null;
  within_area_sample_areas: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaMarketDynamics".
 */
export interface AreaMarketDynamics {
  days_on_market_median: number;
  liquidity: number | null;
  price_change_mean: number;
  sales_volume_12m: number;
  sales_volume_3m: number;
  sales_volume_6m: number;
  volatility: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaOverviewBase".
 */
export interface AreaOverviewBase {
  avg_listing_price: number;
  avg_price_per_sqm: number | null;
  avg_sold_price: number;
  inventory: number;
  listing_count: number;
  median_price_12m: number | null;
  median_price_3m: number | null;
  median_price_6m: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaOverviewStats".
 */
export interface AreaOverviewStats {
  avg_listing_price: number;
  avg_price_per_sqm: number | null;
  avg_sold_price: number;
  inventory: number;
  listing_count: number;
  median_price_12m: number | null;
  median_price_3m: number | null;
  median_price_6m: number | null;
  monthly_prices: MonthlyPrices;
}
/**
 * Median sold price per month; ``month_1`` is the most recent month.
 *
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "MonthlyPrices".
 */
export interface MonthlyPrices {
  month_1: number | null;
  month_10: number | null;
  month_11: number | null;
  month_12: number | null;
  month_2: number | null;
  month_3: number | null;
  month_4: number | null;
  month_5: number | null;
  month_6: number | null;
  month_7: number | null;
  month_8: number | null;
  month_9: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaPremium".
 */
export interface AreaPremium {
  area_name: string;
  avg_premium_pct: number;
  display_name: string;
  median_premium_pct: number;
  sample_size: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaPropertyCharacteristics".
 */
export interface AreaPropertyCharacteristics {
  balcony_pct: number;
  elevator_pct: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaSizeAnalysis".
 */
export interface AreaSizeAnalysis {
  price_by_size: PriceBySizeBucket[];
  price_per_sqm_by_rooms: {
    [k: string]: RoomPriceStats;
  };
  size_distribution: SizeDistribution;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PriceBySizeBucket".
 */
export interface PriceBySizeBucket {
  bucket: string;
  count: number;
  median_price: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "RoomPriceStats".
 */
export interface RoomPriceStats {
  count: number;
  max: number;
  mean: number;
  median: number;
  min: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "SizeDistribution".
 */
export interface SizeDistribution {
  living_area: LivingAreaSummary;
  room_distribution: {
    [k: string]: number;
  };
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "LivingAreaSummary".
 */
export interface LivingAreaSummary {
  max: number | null;
  mean: number | null;
  median: number | null;
  min: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaStatistics".
 */
export interface AreaStatistics {
  area_name: string;
  by_room_count: {
    [k: string]: RoomFilteredStatistics;
  };
  construction_era: ConstructionEraDistribution;
  display_name: string;
  has_limited_data: boolean;
  market_dynamics: AreaMarketDynamics;
  overview: AreaOverviewStats;
  price_tier: PriceTier;
  property_characteristics: AreaPropertyCharacteristics;
  recent_properties: RecentProperty[];
  sample_size: number;
  size_analysis: AreaSizeAnalysis;
  value_insights: AreaValueInsights;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "RoomFilteredStatistics".
 */
export interface RoomFilteredStatistics {
  construction_era: ConstructionEraDistribution;
  market_dynamics: AreaMarketDynamics;
  overview: AreaOverviewBase;
  property_characteristics: AreaPropertyCharacteristics;
  property_count: number;
  recent_properties: RecentProperty[];
  value_insights: AreaValueInsights;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ConstructionEraDistribution".
 */
export interface ConstructionEraDistribution {
  avg_age: number | null;
  era_distribution: {
    [k: string]: number;
  };
  median_year: number | null;
  newest: number | null;
  oldest: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "RecentProperty".
 */
export interface RecentProperty {
  address: string | null;
  listing_id: string;
  living_area: number;
  price_per_sqm: number | null;
  rooms: number;
  sold_date: string;
  sold_price: number;
  url: string | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaValueInsights".
 */
export interface AreaValueInsights {
  avg_prediction_delta: number;
  avg_value_score: number | null;
  median_value_score: number | null;
  undervalued_count: number;
  undervalued_pct: number | null;
  value_tier_distribution: {
    [k: string]: number;
  };
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaStatisticsData".
 */
export interface AreaStatisticsData {
  areas: {
    [k: string]: AreaStatistics;
  };
  metadata: AreaStatisticsMetadata;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaStatisticsMetadata".
 */
export interface AreaStatisticsMetadata {
  data_sources: AreaStatisticsDataSources;
  generated_at: string;
  total_areas: number;
  total_properties: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "AreaStatisticsDataSources".
 */
export interface AreaStatisticsDataSources {
  feature_context: string;
  raw_listings: string;
  value_analysis: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "BestValueSale".
 */
export interface BestValueSale {
  address: string;
  area_name: string;
  display_name: string;
  living_area: number | null;
  prediction_delta_percentage: number;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
  value_score: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "BiggestBidUpSale".
 */
export interface BiggestBidUpSale {
  address: string;
  area_name: string;
  display_name: string;
  listing_price: number;
  living_area: number | null;
  premium_pct: number;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ConstructionEraPoint".
 */
export interface ConstructionEraPoint {
  count: number;
  era: string;
  median_price_per_sqm: number;
  share: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "DateRange".
 */
export interface DateRange {
  end: string;
  start: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "DeltaSummary".
 */
export interface DeltaSummary {
  max: number;
  mean: number;
  median: number;
  min: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "EstimateRangeBucket".
 */
export interface EstimateRangeBucket {
  fallback: boolean;
  lower: number;
  lower_edge: number | null;
  sample_size: number;
  upper: number;
  upper_edge: number | null;
}
/**
 * The ``estimate_range_factors`` block in the metrics artifact and the predict response.
 *
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "EstimateRangeFactors".
 */
export interface EstimateRangeFactors {
  buckets: EstimateRangeBucket[];
  interval_pct: number;
  lower_percentile: number;
  min_bucket_samples: number;
  pooled: PooledEstimateRange;
  recent_slice_months: number;
  sample_size: number;
  slice_end: string;
  slice_start: string;
  upper_percentile: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PooledEstimateRange".
 */
export interface PooledEstimateRange {
  lower: number;
  upper: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "FastestSale".
 */
export interface FastestSale {
  address: string;
  area_name: string;
  days_on_market: number;
  display_name: string;
  living_area: number | null;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "FeeBucketPoint".
 */
export interface FeeBucketPoint {
  fee_bucket: string;
  median_price_per_sqm: number;
  median_sold_price: number;
  sample_size: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "FloorPoint".
 */
export interface FloorPoint {
  floor_bucket: string;
  median_price_per_sqm: number;
  sample_size: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "GeographyArea".
 */
export interface GeographyArea {
  area_name: string;
  display_name: string;
  median_price_per_sqm: number;
  median_sold_price: number;
  sales_count: number;
  undervalued_share: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "HighestPricePerSqmSale".
 */
export interface HighestPricePerSqmSale {
  address: string;
  area_name: string;
  display_name: string;
  living_area: number | null;
  price_per_sqm: number;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
}
/**
 * ``counts[i]`` covers ``[min + i*bin_width, min + (i+1)*bin_width)``.
 *
 * Percentiles use the unclipped values; ``sample_size`` is the pre-clip count.
 *
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "Histogram".
 */
export interface Histogram {
  bin_width: number;
  counts: number[];
  max: number;
  min: number;
  p1: number;
  p25: number;
  p50: number;
  p75: number;
  p99: number;
  sample_size: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ListingVsSold".
 */
export interface ListingVsSold {
  median_listing_price: number;
  median_premium_pct: number;
  median_sold_price: number;
  sample_size: number;
  share_at_ask: number;
  share_over_ask: number;
  share_under_ask: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ModelPerformance".
 */
export interface ModelPerformance {
  mae: number | null;
  mape: number | null;
  n_test: number | null;
  n_train: number | null;
  rmse: number | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "MonthlyFeeAnalysis".
 */
export interface MonthlyFeeAnalysis {
  fee_per_sqm_histogram: Histogram;
  median_price_by_fee_bucket: FeeBucketPoint[];
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "MonthlyOverUnder".
 */
export interface MonthlyOverUnder {
  is_partial: boolean;
  month: string;
  sample_size: number;
  share_at_ask: number;
  share_over_ask: number;
  share_under_ask: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "MonthlyPricePoint".
 */
export interface MonthlyPricePoint {
  is_partial: boolean;
  median_price_per_sqm: number;
  median_sold_price: number;
  month: string;
  sales_count: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallBidding".
 */
export interface OverallBidding {
  bottom_premium_areas: AreaPremium[];
  monthly_over_under: MonthlyOverUnder[];
  premium_pct_histogram: Histogram;
  sample_size: number;
  top_premium_areas: AreaPremium[];
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallBuilding".
 */
export interface OverallBuilding {
  amenities: Amenities;
  by_floor: FloorPoint[];
  construction_era: ConstructionEraPoint[];
  monthly_fee: MonthlyFeeAnalysis;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallDataSources".
 */
export interface OverallDataSources {
  raw_listings: string;
  value_analysis: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallGeography".
 */
export interface OverallGeography {
  areas: GeographyArea[];
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallHero".
 */
export interface OverallHero {
  median_price_per_sqm: number;
  median_sold_price: number;
  price_per_sqm_strip: Histogram;
  total_areas: number;
  total_sales: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallOverTime".
 */
export interface OverallOverTime {
  monthly: MonthlyPricePoint[];
  seasonality: SeasonalityPoint[];
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "SeasonalityPoint".
 */
export interface SeasonalityPoint {
  avg_sales_count: number;
  median_price_per_sqm: number;
  month_of_year: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallPrices".
 */
export interface OverallPrices {
  listing_vs_sold: ListingVsSold;
  price_per_sqm_histogram: Histogram;
  sold_price_histogram: Histogram;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallRecords".
 */
export interface OverallRecords {
  best_value: BestValueSale | null;
  biggest_bid_up: BiggestBidUpSale;
  cheapest: RecordSale;
  fastest_sale: FastestSale;
  highest_price_per_sqm: HighestPricePerSqmSale;
  most_expensive: RecordSale;
  top_streets: TopStreet[];
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "RecordSale".
 */
export interface RecordSale {
  address: string;
  area_name: string;
  display_name: string;
  living_area: number | null;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "TopStreet".
 */
export interface TopStreet {
  median_sold_price: number;
  sales_count: number;
  street: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallSizeRooms".
 */
export interface OverallSizeRooms {
  ppsqm_vs_size_curve: PpsqmVsSizePoint[];
  price_by_size: PriceBySizeBucket[];
  price_per_sqm_by_rooms: {
    [k: string]: RoomPriceStats;
  };
  size_distribution: SizeDistribution;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PpsqmVsSizePoint".
 */
export interface PpsqmVsSizePoint {
  bucket_max: number | null;
  bucket_min: number;
  median_price_per_sqm: number;
  sample_size: number;
  size_bucket: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallStatisticsData".
 */
export interface OverallStatisticsData {
  bidding: OverallBidding;
  building: OverallBuilding;
  geography: OverallGeography;
  hero: OverallHero;
  metadata: OverallStatisticsMetadata;
  over_time: OverallOverTime;
  prices: OverallPrices;
  records: OverallRecords;
  size_rooms: OverallSizeRooms;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "OverallStatisticsMetadata".
 */
export interface OverallStatisticsMetadata {
  data_sources: OverallDataSources;
  date_range: DateRange;
  generated_at: string;
  total_areas: number;
  total_properties: number;
}
/**
 * Prediction request payload.
 *
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PredictionRequest".
 */
export interface PredictionRequest {
  /**
   * Area/neighborhood name
   */
  area?: string;
  /**
   * Has balcony
   */
  balcony?: boolean | null;
  /**
   * Year property was constructed
   */
  construction_year?: number;
  /**
   * Days property has been on market
   */
  days_on_market?: number;
  /**
   * Has elevator
   */
  elevator?: boolean | null;
  /**
   * Floor number
   */
  floor?: number | null;
  /**
   * Property latitude
   */
  latitude?: number | null;
  /**
   * Property listing price in SEK
   */
  listing_price?: number | null;
  /**
   * Living area in square meters
   */
  living_area: number;
  /**
   * Property longitude
   */
  longitude?: number | null;
  /**
   * Model id to use
   */
  model?: "auto" | "no_list_price" | "with_list_price";
  /**
   * Monthly fee in SEK
   */
  monthly_fee?: number;
  /**
   * Municipality name
   */
  municipality?: string;
  /**
   * Property type
   */
  property_type?: string;
  /**
   * Number of rooms
   */
  rooms?: number;
}
/**
 * Prediction response payload.
 *
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "PredictionResponse".
 */
export interface PredictionResponse {
  estimate_range_factors?: EstimateRangeFactors | null;
  input: PredictionRequest;
  model_id: string;
  model_type: string;
  model_used: string;
  predicted_price: number;
  requires_listing_price: boolean;
  status?: string;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ScoreSummary".
 */
export interface ScoreSummary {
  max: number;
  mean: number;
  median: number;
  min: number;
  std: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueAnalysisData".
 */
export interface ValueAnalysisData {
  metadata: ValueAnalysisMetadata;
  properties: ValueProperty[];
  statistics: ValueStatistics;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueAnalysisMetadata".
 */
export interface ValueAnalysisMetadata {
  data_source: string;
  filters: ValueAnalysisFilters;
  generated_at: string;
  model_path: string;
  model_type: string;
  thresholds: ValueAnalysisThresholds;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueAnalysisFilters".
 */
export interface ValueAnalysisFilters {
  min_value_score: number | null;
  only_undervalued: boolean;
  training_filters_applied: boolean;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueAnalysisThresholds".
 */
export interface ValueAnalysisThresholds {
  undervalue_threshold_abs: number;
  undervalue_threshold_pct: number;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueProperty".
 */
export interface ValueProperty {
  address: string;
  area: string;
  balcony: boolean | null;
  construction_year: number | null;
  days_on_market: number | null;
  elevator: boolean | null;
  floor: number | null;
  is_rankable: boolean;
  is_undervalued: boolean;
  latitude?: number | null;
  listing_id: string;
  listing_price: number | null;
  living_area: number | null;
  longitude?: number | null;
  missing_core_fields: string[];
  monthly_fee: number | null;
  municipality: string;
  predicted_price: number;
  prediction_delta_absolute: number;
  prediction_delta_percentage: number;
  price_per_sqm: number | null;
  property_type: string;
  rank_suppressed_reason: string | null;
  rooms: number | null;
  sold_date: string;
  sold_price: number;
  url: string | null;
  value_score: number | null;
  value_tier: ValueTier | null;
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueStatistics".
 */
export interface ValueStatistics {
  area_statistics: ValueAreaStatistics;
  model_performance: ModelPerformance;
  overvalued_count: number;
  prediction_delta_absolute: DeltaSummary;
  prediction_delta_percentage: DeltaSummary;
  rankable_count: number;
  total_properties: number;
  undervalued_count: number;
  undervalued_percentage: number;
  unrankable_count: number;
  value_score: ScoreSummary;
  value_tier_distribution: {
    [k: string]: number;
  };
}
/**
 * This interface was referenced by `WebTypes`'s JSON-Schema
 * via the `definition` "ValueAreaStatistics".
 */
export interface ValueAreaStatistics {
  top_undervalued_areas: {
    [k: string]: number;
  };
  total_areas: number;
}

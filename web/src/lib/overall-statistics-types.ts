/**
 * Types for `data/derived/overall_statistics.json`, the city-wide report behind
 * the `/stats` page. Generated from `analytics/web_json.py`; shares are 0..1 fractions.
 */
import type { OverallSizeRooms } from "./generated/api-types";

export type {
  AmenityEffect,
  AreaPremium,
  ConstructionEraPoint,
  FeeBucketPoint,
  FloorPoint,
  GeographyArea,
  Histogram,
  ListingVsSold,
  MonthlyOverUnder,
  MonthlyPricePoint,
  OverallBidding,
  OverallBuilding,
  OverallGeography,
  OverallHero,
  OverallOverTime,
  OverallPrices,
  OverallRecords,
  OverallSizeRooms,
  OverallStatisticsData,
  OverallStatisticsMetadata,
  PpsqmVsSizePoint,
  PriceBySizeBucket,
  RecordSale,
  SeasonalityPoint,
  SizeDistribution,
  TopStreet,
} from "./generated/api-types";

export type PpsqmByRooms = OverallSizeRooms["price_per_sqm_by_rooms"];

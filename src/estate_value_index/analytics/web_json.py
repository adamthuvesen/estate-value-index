"""The contract of the three derived JSON files the web app reads.

Each generator validates its output against these models before it writes the
file. ``scripts/export_web_schema.py`` turns them into the JSON Schema that
``web/src/lib/generated/api-types.ts`` is generated from (``just fix``), so the
Python output and the TypeScript types cannot drift apart. Class names are the
TypeScript type names.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- value_analysis.json ---

type ValueTier = Literal[
    "Excellent Value",
    "Great Value",
    "Good Value",
    "Fair Value",
    "Overvalued",
    "Highly Overvalued",
]


class ValueProperty(_Strict):
    listing_id: str
    url: str | None
    address: str | None
    area: str
    municipality: str | None
    # Null on suppressed rows (rank_suppressed_reason "missing_living_area").
    living_area: float | None
    # Nullable in the listing row; the export keeps listings without them.
    rooms: float | None
    property_type: str | None
    construction_year: float | None
    monthly_fee: float | None
    floor: float | None
    elevator: bool | None
    balcony: bool | None
    sold_price: float
    predicted_price: float
    prediction_delta_absolute: float
    prediction_delta_percentage: float
    is_undervalued: bool
    # Suppressed rows (is_rankable false) carry a null score and tier: they stay
    # searchable but are held out of the ranking.
    value_score: float | None
    value_tier: ValueTier | None
    is_rankable: bool
    rank_suppressed_reason: str | None
    missing_core_fields: list[str]
    # Ingest can sell a listing with no recorded date; the export keeps it.
    sold_date: str | None
    days_on_market: float | None
    listing_price: float | None
    price_per_sqm: float | None
    latitude: float | None = None
    longitude: float | None = None


class ValueAnalysisFilters(_Strict):
    only_undervalued: bool
    min_value_score: float | None
    training_filters_applied: bool


class ValueAnalysisThresholds(_Strict):
    undervalue_threshold_pct: float
    undervalue_threshold_abs: float


class ValueAnalysisMetadata(_Strict):
    generated_at: str
    model_type: str
    model_path: str
    data_source: str
    filters: ValueAnalysisFilters
    thresholds: ValueAnalysisThresholds


class ScoreSummary(_Strict):
    mean: float
    median: float
    min: float
    max: float
    std: float


class DeltaSummary(_Strict):
    mean: float
    median: float
    min: float
    max: float


class ValueAreaStatistics(_Strict):
    total_areas: int
    top_undervalued_areas: dict[str, int]


class ModelPerformance(_Strict):
    mae: float | None
    rmse: float | None
    mape: float | None
    n_train: int | None
    n_test: int | None


class ValueStatistics(_Strict):
    total_properties: int
    rankable_count: int
    unrankable_count: int
    undervalued_count: int
    overvalued_count: int
    undervalued_percentage: float
    value_score: ScoreSummary
    prediction_delta_absolute: DeltaSummary
    prediction_delta_percentage: DeltaSummary
    value_tier_distribution: dict[ValueTier, int]
    area_statistics: ValueAreaStatistics
    model_performance: ModelPerformance


class ValueAnalysisData(_Strict):
    metadata: ValueAnalysisMetadata
    statistics: ValueStatistics
    properties: list[ValueProperty]


# --- area_statistics.json ---

type PriceTier = Literal["budget", "medium", "upper", "premium"]


class AreaStatisticsDataSources(_Strict):
    feature_context: str
    value_analysis: str
    raw_listings: str


class AreaStatisticsMetadata(_Strict):
    generated_at: str
    total_areas: int
    total_properties: int
    data_sources: AreaStatisticsDataSources


class MonthlyPrices(_Strict):
    """Median sold price per month; ``month_1`` is the most recent month."""

    month_1: float | None
    month_2: float | None
    month_3: float | None
    month_4: float | None
    month_5: float | None
    month_6: float | None
    month_7: float | None
    month_8: float | None
    month_9: float | None
    month_10: float | None
    month_11: float | None
    month_12: float | None


class AreaOverviewBase(_Strict):
    avg_listing_price: float
    avg_sold_price: float
    avg_price_per_sqm: float | None
    listing_count: int
    inventory: float
    median_price_3m: float | None
    median_price_6m: float | None
    median_price_12m: float | None


class AreaOverviewStats(AreaOverviewBase):
    monthly_prices: MonthlyPrices


class AreaMarketDynamics(_Strict):
    volatility: float
    days_on_market_median: float
    price_change_mean: float
    sales_volume_3m: float
    sales_volume_6m: float
    sales_volume_12m: float
    liquidity: float | None


class AreaValueInsights(_Strict):
    undervalued_count: int
    undervalued_pct: float | None
    avg_value_score: float | None
    median_value_score: float | None
    avg_prediction_delta: float
    value_tier_distribution: dict[str, int]


class RoomPriceStats(_Strict):
    median: float
    mean: float
    min: float
    max: float
    count: int


class LivingAreaSummary(_Strict):
    median: float | None
    mean: float | None
    min: float | None
    max: float | None


class SizeDistribution(_Strict):
    living_area: LivingAreaSummary
    room_distribution: dict[str, int]


class PriceBySizeBucket(_Strict):
    bucket: str
    median_price: float
    count: int


class AreaSizeAnalysis(_Strict):
    price_per_sqm_by_rooms: dict[str, RoomPriceStats]
    price_by_size: list[PriceBySizeBucket]
    size_distribution: SizeDistribution


class AreaPropertyCharacteristics(_Strict):
    elevator_pct: float
    balcony_pct: float


class ConstructionEraDistribution(_Strict):
    median_year: float | None
    oldest: float | None
    newest: float | None
    era_distribution: dict[str, int]
    avg_age: float | None


class RecentProperty(_Strict):
    listing_id: str
    url: str | None
    address: str | None
    sold_price: float
    sold_date: str
    living_area: float | None
    rooms: float | None
    price_per_sqm: float | None


class RoomFilteredStatistics(_Strict):
    overview: AreaOverviewBase
    market_dynamics: AreaMarketDynamics
    value_insights: AreaValueInsights
    property_characteristics: AreaPropertyCharacteristics
    construction_era: ConstructionEraDistribution
    recent_properties: list[RecentProperty]
    property_count: int


class AreaStatistics(_Strict):
    area_name: str
    display_name: str
    price_tier: PriceTier
    overview: AreaOverviewStats
    market_dynamics: AreaMarketDynamics
    value_insights: AreaValueInsights
    size_analysis: AreaSizeAnalysis
    property_characteristics: AreaPropertyCharacteristics
    construction_era: ConstructionEraDistribution
    recent_properties: list[RecentProperty]
    # Keyed by room filter: "all", "1", "2", "3", "4+".
    by_room_count: dict[str, RoomFilteredStatistics]
    has_limited_data: bool
    sample_size: int


class AreaStatisticsData(_Strict):
    metadata: AreaStatisticsMetadata
    areas: dict[str, AreaStatistics]


# --- overall_statistics.json (shares are 0..1 fractions) ---


class Histogram(_Strict):
    """``counts[i]`` covers ``[min + i*bin_width, min + (i+1)*bin_width)``.

    Percentiles use the unclipped values; ``sample_size`` is the pre-clip count.
    """

    min: float
    max: float
    bin_width: float
    counts: list[int]
    p1: float
    p25: float
    p50: float
    p75: float
    p99: float
    sample_size: int


class RecordSale(_Strict):
    address: str | None
    area_name: str
    display_name: str
    # A record can be an undated sale; `_record_base` passes the missing date on.
    sold_date: str | None
    url: str | None
    living_area: float | None
    rooms: float | None
    sold_price: float


class HighestPricePerSqmSale(RecordSale):
    price_per_sqm: float


class FastestSale(RecordSale):
    days_on_market: float


class BiggestBidUpSale(RecordSale):
    premium_pct: float
    listing_price: float


class BestValueSale(RecordSale):
    prediction_delta_percentage: float
    value_score: float


class DateRange(_Strict):
    start: str
    end: str


class OverallDataSources(_Strict):
    raw_listings: str
    value_analysis: str


class OverallStatisticsMetadata(_Strict):
    generated_at: str
    total_properties: int
    total_areas: int
    date_range: DateRange
    data_sources: OverallDataSources


class OverallHero(_Strict):
    total_sales: int
    total_areas: int
    median_sold_price: float
    median_price_per_sqm: float
    price_per_sqm_strip: Histogram


class ListingVsSold(_Strict):
    sample_size: int
    median_listing_price: float
    median_sold_price: float
    median_premium_pct: float
    share_over_ask: float
    share_under_ask: float
    share_at_ask: float


class OverallPrices(_Strict):
    sold_price_histogram: Histogram
    price_per_sqm_histogram: Histogram
    listing_vs_sold: ListingVsSold


class MonthlyPricePoint(_Strict):
    month: str
    median_price_per_sqm: float
    median_sold_price: float
    sales_count: int
    is_partial: bool


class SeasonalityPoint(_Strict):
    month_of_year: int
    median_price_per_sqm: float
    avg_sales_count: float


class OverallOverTime(_Strict):
    monthly: list[MonthlyPricePoint]
    seasonality: list[SeasonalityPoint]


class AreaPremium(_Strict):
    area_name: str
    display_name: str
    avg_premium_pct: float
    median_premium_pct: float
    sample_size: int


class MonthlyOverUnder(_Strict):
    month: str
    share_over_ask: float
    share_under_ask: float
    share_at_ask: float
    sample_size: int
    is_partial: bool


class OverallBidding(_Strict):
    sample_size: int
    premium_pct_histogram: Histogram
    monthly_over_under: list[MonthlyOverUnder]
    top_premium_areas: list[AreaPremium]
    bottom_premium_areas: list[AreaPremium]


class GeographyArea(_Strict):
    area_name: str
    display_name: str
    median_price_per_sqm: float
    median_sold_price: float
    sales_count: int
    undervalued_share: float | None


class OverallGeography(_Strict):
    areas: list[GeographyArea]


class PpsqmVsSizePoint(_Strict):
    size_bucket: str
    bucket_min: float
    bucket_max: float | None
    median_price_per_sqm: float
    sample_size: int


class OverallSizeRooms(_Strict):
    price_per_sqm_by_rooms: dict[str, RoomPriceStats]
    price_by_size: list[PriceBySizeBucket]
    size_distribution: SizeDistribution
    ppsqm_vs_size_curve: list[PpsqmVsSizePoint]


class ConstructionEraPoint(_Strict):
    era: str
    count: int
    share: float
    median_price_per_sqm: float


class AmenityEffect(_Strict):
    known_count: int
    share_with: float
    median_ppsqm_with: float | None
    median_ppsqm_without: float | None
    naive_diff_pct: float | None
    within_area_diff_pct: float | None
    within_area_sample_areas: int


class Amenities(_Strict):
    balcony: AmenityEffect
    elevator: AmenityEffect


class FloorPoint(_Strict):
    floor_bucket: str
    median_price_per_sqm: float
    sample_size: int


class FeeBucketPoint(_Strict):
    fee_bucket: str
    median_sold_price: float
    median_price_per_sqm: float
    sample_size: int


class MonthlyFeeAnalysis(_Strict):
    fee_per_sqm_histogram: Histogram
    median_price_by_fee_bucket: list[FeeBucketPoint]


class OverallBuilding(_Strict):
    construction_era: list[ConstructionEraPoint]
    amenities: Amenities
    by_floor: list[FloorPoint]
    monthly_fee: MonthlyFeeAnalysis


class TopStreet(_Strict):
    street: str
    sales_count: int
    median_sold_price: float


class OverallRecords(_Strict):
    most_expensive: RecordSale
    cheapest: RecordSale
    highest_price_per_sqm: HighestPricePerSqmSale
    fastest_sale: FastestSale
    biggest_bid_up: BiggestBidUpSale
    best_value: BestValueSale | None
    top_streets: list[TopStreet]


class OverallStatisticsData(_Strict):
    metadata: OverallStatisticsMetadata
    hero: OverallHero
    prices: OverallPrices
    over_time: OverallOverTime
    bidding: OverallBidding
    geography: OverallGeography
    size_rooms: OverallSizeRooms
    building: OverallBuilding
    records: OverallRecords

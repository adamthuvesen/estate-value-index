import { toAreaOverview, getAreaOverviewList } from "../area-overview";
import { getAreaStatisticsData } from "../area-statistics-cache";
import type { AreaStatistics, AreaStatisticsData, PricePerSqmByRooms } from "../area-types";

jest.mock("../area-statistics-cache", () => ({
  getAreaStatisticsData: jest.fn(),
}));

const mockedGetAreaStatisticsData =
  getAreaStatisticsData as jest.MockedFunction<typeof getAreaStatisticsData>;

function areaStatistics(
  partial: Partial<AreaStatistics> & Pick<AreaStatistics, "area_name">,
): AreaStatistics {
  return {
    display_name: partial.area_name,
    price_tier: "medium",
    overview: {
      avg_listing_price: 5_000_000,
      avg_sold_price: 4_800_000,
      avg_price_per_sqm: null,
      listing_count: 10,
      inventory: 4,
      median_price_3m: 4_700_000,
      median_price_6m: 4_650_000,
      median_price_12m: 4_600_000,
    },
    market_dynamics: {
      volatility: 0.12,
      days_on_market_median: 21,
      price_change_mean: 1.5,
      sales_volume_3m: 3,
      sales_volume_6m: 6,
      sales_volume_12m: 12,
      liquidity: null,
    },
    value_insights: {
      undervalued_count: 2,
      undervalued_pct: 20,
      avg_value_score: null,
      median_value_score: null,
      avg_prediction_delta: 0,
      value_tier_distribution: {},
    },
    size_analysis: {
      price_per_sqm_by_rooms: {},
      price_by_size: [],
      size_distribution: {
        living_area: { median: 60, mean: 60, min: 30, max: 100 },
        room_distribution: {},
      },
    },
    property_characteristics: { elevator_pct: 50, balcony_pct: 60 },
    construction_era: {
      median_year: 1960,
      oldest: 1900,
      newest: 2020,
      era_distribution: {},
      avg_age: 60,
    },
    recent_properties: [],
    has_limited_data: false,
    sample_size: 30,
    ...partial,
  };
}

function statisticsData(areas: AreaStatistics[]): AreaStatisticsData {
  return {
    metadata: {
      generated_at: "2026-06-01T00:00:00Z",
      total_areas: areas.length,
      total_properties: 0,
      data_sources: { feature_context: "fixture", value_analysis: "fixture", raw_listings: "fixture" },
    },
    areas: Object.fromEntries(areas.map((a) => [a.area_name, a])),
  };
}

const rooms: PricePerSqmByRooms = {
  "1": { median: 100_000, mean: 100_000, min: 90_000, max: 110_000, count: 2 },
  "2": { median: 80_000, mean: 80_000, min: 70_000, max: 90_000, count: 8 },
};

describe("toAreaOverview", () => {
  it("computes the count-weighted average price/m² across room buckets", () => {
    const area = areaStatistics({ area_name: "a" });
    area.size_analysis.price_per_sqm_by_rooms = rooms;
    // (100000*2 + 80000*8) / 10 = 84000
    expect(toAreaOverview(area).avg_price_per_sqm).toBe(84_000);
  });

  it("rounds the weighted average", () => {
    const area = areaStatistics({ area_name: "a" });
    area.size_analysis.price_per_sqm_by_rooms = {
      "1": { median: 0, mean: 100_001, min: 0, max: 0, count: 1 },
      "2": { median: 0, mean: 100_002, min: 0, max: 0, count: 2 },
    };
    // (100001 + 200004) / 3 = 100001.67 → 100002
    expect(toAreaOverview(area).avg_price_per_sqm).toBe(100_002);
  });

  it("returns null price/m² when there are no room buckets", () => {
    const area = areaStatistics({ area_name: "a" });
    expect(toAreaOverview(area).avg_price_per_sqm).toBeNull();
  });

  it("returns null price/m² when total count is zero", () => {
    const area = areaStatistics({ area_name: "a" });
    area.size_analysis.price_per_sqm_by_rooms = {
      "1": { median: 0, mean: 100_000, min: 0, max: 0, count: 0 },
    };
    expect(toAreaOverview(area).avg_price_per_sqm).toBeNull();
  });

  it("maps every overview field from the source record", () => {
    const area = areaStatistics({
      area_name: "sodermalm",
      display_name: "Södermalm",
      price_tier: "premium",
      has_limited_data: true,
      sample_size: 7,
    });
    const row = toAreaOverview(area);
    expect(row).toMatchObject({
      area_name: "sodermalm",
      display_name: "Södermalm",
      price_tier: "premium",
      avg_sold_price: 4_800_000,
      listing_count: 10,
      inventory: 4,
      median_price_3m: 4_700_000,
      days_on_market_median: 21,
      price_change_mean: 1.5,
      volatility: 0.12,
      undervalued_pct: 20,
      has_limited_data: true,
      sample_size: 7,
    });
  });
});

describe("getAreaOverviewList", () => {
  afterEach(() => mockedGetAreaStatisticsData.mockReset());

  it("returns all areas sorted by listing count descending", async () => {
    mockedGetAreaStatisticsData.mockResolvedValue(
      statisticsData([
        areaStatistics({ area_name: "small", overview: { ...areaStatistics({ area_name: "small" }).overview, listing_count: 5 } }),
        areaStatistics({ area_name: "big", overview: { ...areaStatistics({ area_name: "big" }).overview, listing_count: 50 } }),
        areaStatistics({ area_name: "mid", overview: { ...areaStatistics({ area_name: "mid" }).overview, listing_count: 20 } }),
      ]),
    );

    const list = await getAreaOverviewList();
    expect(list.map((a) => a.area_name)).toEqual(["big", "mid", "small"]);
    expect(list.map((a) => a.listing_count)).toEqual([50, 20, 5]);
  });
});

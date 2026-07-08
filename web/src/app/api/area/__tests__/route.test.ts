import { GET } from "../route";
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";
import { DataFileMissingError } from "@/lib/data-file-errors";
import type { AreaStatistics, AreaStatisticsData } from "@/lib/area-types";

jest.mock("@/lib/area-statistics-cache", () => ({
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
      price_per_sqm_by_rooms: {
        "2": { median: 80_000, mean: 80_000, min: 70_000, max: 90_000, count: 4 },
      },
      price_by_size: [],
      size_distribution: {
        living_area: { median: 60, mean: 60, min: 30, max: 100 },
        room_distribution: {},
      },
    },
    property_characteristics: { elevator_pct: 50, balcony_pct: 60 },
    construction_era: { median_year: 1960, oldest: 1900, newest: 2020, era_distribution: {}, avg_age: 60 },
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

beforeEach(() => {
  mockedGetAreaStatisticsData.mockReset();
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => jest.restoreAllMocks());

describe("GET /api/area", () => {
  it("returns metadata plus areas sorted by listing count, with the weighted price/m²", async () => {
    const small = areaStatistics({ area_name: "small" });
    small.overview.listing_count = 5;
    const big = areaStatistics({ area_name: "big" });
    big.overview.listing_count = 50;
    mockedGetAreaStatisticsData.mockResolvedValue(statisticsData([small, big]));

    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe(
      "public, s-maxage=300, stale-while-revalidate=600",
    );
    expect(body.metadata.total_areas).toBe(2);
    expect(body.areas.map((a: { area_name: string }) => a.area_name)).toEqual(["big", "small"]);
    // Single "2"-room bucket, mean 80000 → weighted avg 80000
    expect(body.areas[0].avg_price_per_sqm).toBe(80_000);
  });

  it("returns a 404 when the underlying data file is missing", async () => {
    mockedGetAreaStatisticsData.mockRejectedValue(
      new DataFileMissingError(
        "File not found: derived/area_statistics.json. GCS fallback is disabled.",
        "derived/area_statistics.json",
        "gs://bucket/derived/area_statistics.json",
      ),
    );

    const response = await GET();
    expect(response.status).toBe(404);
  });

  it("returns a 500 on unexpected errors", async () => {
    mockedGetAreaStatisticsData.mockRejectedValue(new Error("boom"));

    const response = await GET();
    expect(response.status).toBe(500);
  });
});

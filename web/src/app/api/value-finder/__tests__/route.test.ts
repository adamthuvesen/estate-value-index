import { NextRequest } from "next/server";
import { GET as getValueFinder } from "../route";
import { GET as getMetadata } from "../metadata/route";
import { DataFileMissingError } from "@/lib/data-file-errors";
import { getValueAnalysisData } from "@/lib/value-analysis-cache";

jest.mock("@/lib/value-analysis-cache", () => ({
  getValueAnalysisData: jest.fn(),
}));

const mockedGetValueAnalysisData =
  getValueAnalysisData as jest.MockedFunction<typeof getValueAnalysisData>;

function makeRequest(query = ""): NextRequest {
  return new NextRequest(`http://localhost/api/value-finder${query}`);
}

function valueAnalysisData() {
  return {
    metadata: {
      generated_at: "2026-01-01T00:00:00Z",
      model_type: "price_tiered_ensemble",
      model_path: "models/price_prediction_model_no_list_price.joblib",
      data_source: "fixture",
      filters: {
        only_undervalued: false,
        min_value_score: null,
      },
    },
    statistics: {
      total_properties: 1,
      undervalued_count: 1,
      overvalued_count: 0,
      undervalued_percentage: 100,
      value_score: { mean: 80, median: 80, min: 80, max: 80, std: 0 },
      prediction_delta_absolute: { mean: -100000, median: -100000, min: -100000, max: -100000 },
      prediction_delta_percentage: { mean: -5, median: -5, min: -5, max: -5 },
      value_tier_distribution: {
        "Excellent Value": 1,
        "Great Value": 0,
        "Good Value": 0,
        "Fair Value": 0,
        Overvalued: 0,
        "Highly Overvalued": 0,
      },
      area_statistics: {
        total_areas: 1,
        top_undervalued_areas: { sodermalm: 1 },
      },
      model_performance: {
        mae: 250000,
        rmse: 300000,
        mape: 4,
        n_train: 10,
        n_test: 2,
      },
    },
    properties: [
      {
        listing_id: "1",
        url: null,
        address: "Testgatan 1",
        area: "sodermalm",
        municipality: "stockholm",
        living_area: 55,
        rooms: 2,
        property_type: "Lägenhet",
        construction_year: 1970,
        monthly_fee: 3000,
        floor: 2,
        elevator: true,
        balcony: false,
        sold_price: 4_000_000,
        predicted_price: 4_100_000,
        prediction_delta_absolute: -100_000,
        prediction_delta_percentage: -2.5,
        is_undervalued: true,
        value_score: 80,
        value_tier: "Excellent Value",
        is_rankable: true,
        rank_suppressed_reason: null,
        missing_core_fields: [],
        sold_date: "2025-01-01",
        days_on_market: 12,
        listing_price: 3_900_000,
        price_per_sqm: 72_727,
      },
    ],
  } as any;
}

beforeEach(() => {
  mockedGetValueAnalysisData.mockReset();
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("value-finder API errors", () => {
  it("rejects negative pagination before loading data", async () => {
    const response = await getValueFinder(makeRequest("?offset=-1"));
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("offset");
    expect(mockedGetValueAnalysisData).not.toHaveBeenCalled();
  });

  it("rejects malformed numeric filters before loading data", async () => {
    const response = await getValueFinder(makeRequest("?limit=abc"));
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("limit");
    expect(mockedGetValueAnalysisData).not.toHaveBeenCalled();
  });

  it("rejects unknown sort fields before loading data", async () => {
    const response = await getValueFinder(makeRequest("?sort=legacy_score"));
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("sort");
    expect(mockedGetValueAnalysisData).not.toHaveBeenCalled();
  });

  it("returns filtered data for valid queries", async () => {
    mockedGetValueAnalysisData.mockResolvedValue(valueAnalysisData());

    const response = await getValueFinder(makeRequest("?limit=1&offset=0&value_tier=Excellent%20Value"));
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.total).toBe(1);
    expect(body.properties).toHaveLength(1);
  });

  it("does not expose internal loader details from the listing route on 500", async () => {
    const internalMessage =
      "Failed to load data from /app/data/derived/value_analysis.json or GCS (secret-bucket/value_analysis.json): credentials missing";
    mockedGetValueAnalysisData.mockRejectedValue(new Error(internalMessage));

    const response = await getValueFinder(makeRequest());
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body).toMatchObject({
      error_code: "VALUE_ANALYSIS_DATA_ERROR",
      error_message: "Failed to load value analysis data.",
    });
    expect(JSON.stringify(body)).not.toContain("/app/data");
    expect(JSON.stringify(body)).not.toContain("secret-bucket");
    expect(JSON.stringify(body)).not.toContain("credentials missing");
  });

  it("does not expose internal loader details from the metadata route on 500", async () => {
    const internalMessage =
      "Failed to parse /Users/adam/dev/data/derived/value_analysis.json from private-bucket";
    mockedGetValueAnalysisData.mockRejectedValue(new Error(internalMessage));

    const response = await getMetadata();
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body).toMatchObject({
      error_code: "VALUE_ANALYSIS_DATA_ERROR",
      error_message: "Failed to load value analysis data.",
    });
    expect(JSON.stringify(body)).not.toContain("/Users/adam");
    expect(JSON.stringify(body)).not.toContain("private-bucket");
  });

  it("returns a safe missing-data response without local paths", async () => {
    mockedGetValueAnalysisData.mockRejectedValue(
      new DataFileMissingError(
        "Data file is not available and GCS fallback is disabled.",
        "/app/data/derived/value_analysis.json",
        "derived/value_analysis.json",
      )
    );

    const response = await getValueFinder(makeRequest());
    const body = await response.json();

    expect(response.status).toBe(404);
    expect(body).toMatchObject({
      error_code: "VALUE_ANALYSIS_DATA_MISSING",
      error_message: "Value analysis data is not available yet.",
    });
    expect(JSON.stringify(body)).not.toContain("/app/data");
  });
});

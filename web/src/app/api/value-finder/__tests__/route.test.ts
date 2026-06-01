import { NextRequest } from "next/server";
import { GET as getValueFinder } from "../route";
import { GET as getMetadata } from "../metadata/route";
import { getValueAnalysisData } from "@/lib/value-analysis-cache";

jest.mock("@/lib/value-analysis-cache", () => ({
  getValueAnalysisData: jest.fn(),
}));

const mockedGetValueAnalysisData =
  getValueAnalysisData as jest.MockedFunction<typeof getValueAnalysisData>;

function makeRequest(): NextRequest {
  return new NextRequest("http://localhost/api/value-finder");
}

beforeEach(() => {
  mockedGetValueAnalysisData.mockReset();
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("value-finder API errors", () => {
  it("does not expose internal loader details from the listing route on 500", async () => {
    const internalMessage =
      "Failed to load data from /app/data/enrichment/value_analysis.json or GCS (secret-bucket/value_analysis.json): credentials missing";
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
      "Failed to parse /Users/adam/dev/data/enrichment/value_analysis.json from private-bucket";
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
    const internalMessage =
      "File not found: /app/data/enrichment/value_analysis.json. GCS fallback is disabled.";
    mockedGetValueAnalysisData.mockRejectedValue(new Error(internalMessage));

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
